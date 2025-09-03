import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { api } from "../lib/api";

export type ChanRow = {
    channel: string;
    signal_score: number | null;  // averaged per channel
    win_rate: number | null;
    opens: number;
    closes: number;
    avg_confidence: number | null;
    last_signal: string | null;
};

type RawRec = {
    action?: string;              // "OPEN" | "CLOSE" | ...
    source?: string;              // channel name (may be internal/blank for CLOSE)
    symbol?: string;
    gid?: string | number;
    oid?: string | number;
    id?: string | number;         // sometimes OPENs use id only
    ticket?: string | number;     // present on CLOSE
    profit?: number | string;
    p?: number | string;
    pnl?: number | string;
    profit_usd?: number | string;
    net_profit?: number | string;
    confidence?: number;          // optional per-OPEN confidence (0..100)
    score?: number;               // optional per-OPEN score
    signal_score?: number;        // optional alt name
    t?: number | string;          // unix seconds
    ts?: number | string;         // alt time
    time?: number | string;       // alt time
};

const INTERNAL_SOURCES = new Set([
    "", "EA", "GUI", "WEB", "SYSTEM", "BACKEND", "INTERNAL"
]);

// join key: prefer gid, then oid, then id (OPENs sometimes only have id)
const keyFor = (r: RawRec) => String(r.gid ?? r.oid ?? r.id ?? "").trim();

function parseNumeric(x: any): number | null {
    if (x == null) return null;
    if (typeof x === "number" && Number.isFinite(x)) return x;
    if (typeof x === "string") {
        // remove spaces and currency symbols, normalize comma decimals
        const s = x.replace(/[^\d,.\-]/g, "").replace(/(\d),(?=\d{3}\b)/g, "$1"); // keep thousands, handle EU style
        const t = s.includes(",") && !s.includes(".") ? s.replace(",", ".") : s.replace(/,/g, "");
        const n = Number(t);
        return Number.isFinite(n) ? n : null;
    }
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
}

function pickProfit(rec: RawRec): number | null {
    // Try the likely fields in order
    return (
        parseNumeric(rec.profit_usd) ??
        parseNumeric(rec.profit) ??
        parseNumeric(rec.pnl) ??
        parseNumeric(rec.p) ??
        parseNumeric(rec.net_profit) ??
        null
    );
}

function coalesceTime(rec: RawRec): number | null {
    const n = parseNumeric(rec.t ?? rec.ts ?? rec.time);
    return n != null ? Math.trunc(n) : null; // expect unix seconds
}

function fmtWhen(t?: number | null): string | null {
    if (!t || !Number.isFinite(t)) return null;
    try {
        return new Date(t * 1000).toLocaleString();
    } catch {
        return null;
    }
}

/** Decide the canonical channel for a row.
 * 1) Prefer OPEN.source from gid/oid/id join
 * 2) Else for CLOSE with blank key/source, use heuristic:
 *    take the channel whose most recent OPEN in the *same symbol*
 *    occurred before the CLOSE time.
 */
function canonicalSource(
    row: RawRec,
    opensByKey: Map<string, RawRec>,
    latestOpenBySymbolAndChannel: Map<string, Map<string, number>>
): string {
    // Primary: exact join via gid/oid/id
    const k = keyFor(row);
    const open = k ? opensByKey.get(k) : undefined;
    const fromJoin = String(open?.source ?? row.source ?? "").trim();
    if (fromJoin && !INTERNAL_SOURCES.has(fromJoin)) return fromJoin;

    // Heuristic: only for CLOSE rows with blank/unknown source
    if ((row.action ?? "").toUpperCase() !== "CLOSE") return "";

    const sym = (row.symbol || "").trim().toUpperCase();
    if (!sym) return "";

    const closerTs = coalesceTime(row);
    const perChan = latestOpenBySymbolAndChannel.get(sym);
    if (!perChan) return "";

    // Find channel with the closest OPEN <= close time
    let bestChan = "";
    let bestTs = -1;
    for (const [chan, ts] of perChan) {
        if (INTERNAL_SOURCES.has(chan)) continue;
        if (typeof ts !== "number") continue;
        if (closerTs !== null && ts > closerTs) continue; // OPEN after CLOSE -> ignore
        if (ts > bestTs) {
            bestTs = ts;
            bestChan = chan;
        }
    }
    return bestChan; // may be "" if none found
}

type Props = {
    selected?: string | null;
    onSelect?: (channel: string | null) => void;
    onSummary?: (s: {
        bestByWin?: ChanRow | null;
        bestByScore?: ChanRow | null;
        totals: { opens: number; closes: number; channels: number };
        overallWinRate: number | null;
    }) => void;
};

/** ChannelPerformance
 * - Props are optional for backward-compat (`Dashboard` can render without handlers).
 * - Renders mobile cards on small screens, table on md+.
 */
export default function ChannelPerformance({
    selected = null,
    onSelect,
    onSummary,
}: Props) {
    const [rows, setRows] = useState<ChanRow[]>([]);
    const polling = useRef<number | null>(null);

    // Poll raw signals and compute channel stats on the client
    useEffect(() => {
        let cancelled = false;

        const fetchAndBuild = async () => {
            let data: RawRec[] = [];
            try {
                const r = await fetch(api("/api/signals?limit=500"));
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const json = await r.json();
                data = Array.isArray(json) ? (json as RawRec[]) : [];
            } catch {
                data = [];
            }
            if (cancelled) return;

            // 1) Build OPEN index and "latest open by symbol & channel"
            const opensByKey = new Map<string, RawRec>();
            const latestOpenBySymbolAndChannel = new Map<string, Map<string, number>>();

            for (const rec of data) {
                if ((rec.action ?? "").toUpperCase() !== "OPEN") continue;

                const k = keyFor(rec);
                if (k) opensByKey.set(k, rec);

                const src = String(rec.source ?? "").trim();
                if (INTERNAL_SOURCES.has(src)) continue;

                const sym = (rec.symbol || "").trim().toUpperCase();
                const tVal = coalesceTime(rec);
                if (!sym || tVal === null) continue;

                let perChan = latestOpenBySymbolAndChannel.get(sym);
                if (!perChan) {
                    perChan = new Map<string, number>();
                    latestOpenBySymbolAndChannel.set(sym, perChan);
                }
                const prev = perChan.get(src) ?? -1;
                if (tVal > prev) perChan.set(src, tVal);
            }

            // 2) Aggregate by canonical source
            type Acc = {
                opens: number;
                closes: number;
                wins: number;
                totalClosed: number;   // denominator for win%
                confSum: number;
                confN: number;
                scoreSum: number;
                scoreN: number;
                lastT?: number;
            };

            const byChan = new Map<string, Acc>();

            for (const rec of data) {
                const canon = canonicalSource(rec, opensByKey, latestOpenBySymbolAndChannel);
                if (!canon) continue; // drop EA/GUI/WEB/blank/unknown

                let acc = byChan.get(canon);
                if (!acc) {
                    acc = {
                        opens: 0, closes: 0, wins: 0, totalClosed: 0,
                        confSum: 0, confN: 0, scoreSum: 0, scoreN: 0,
                        lastT: undefined,
                    };
                    byChan.set(canon, acc);
                }

                const act = (rec.action ?? "").toUpperCase();
                if (act === "OPEN") {
                    acc.opens += 1;

                    if (typeof rec.confidence === "number") {
                        acc.confSum += rec.confidence;
                        acc.confN += 1;
                    }

                    const scoreVal =
                        (typeof rec.signal_score === "number" ? rec.signal_score : null) ??
                        (typeof rec.score === "number" ? rec.score : null);

                    if (scoreVal !== null) {
                        acc.scoreSum += scoreVal!;
                        acc.scoreN += 1;
                    }
                } else if (act === "CLOSE") {
                    acc.closes += 1;
                    acc.totalClosed += 1; // always count CLOSE in denominator
                    const p = pickProfit(rec);
                    if (p !== null && p > 0) acc.wins += 1;
                }

                const tVal = coalesceTime(rec);
                if (tVal !== null) acc.lastT = Math.max(acc.lastT ?? 0, tVal);
            }

            // 3) Convert to ChanRow[]
            const out: ChanRow[] = [];
            for (const [channel, a] of byChan) {
                const win_rate = a.totalClosed > 0 ? (a.wins / a.totalClosed) * 100 : null;
                const avg_confidence = a.confN > 0 ? a.confSum / a.confN : null;

                // Fallback: if no explicit score fields, use avg confidence as "signal score"
                const explicitScore = a.scoreN > 0 ? a.scoreSum / a.scoreN : null;
                const signal_score = explicitScore !== null ? explicitScore : avg_confidence;

                out.push({
                    channel,
                    signal_score,
                    win_rate,
                    opens: a.opens,
                    closes: a.closes,
                    avg_confidence,
                    last_signal: fmtWhen(a.lastT ?? null),
                });
            }

            // 4) Sort: by win %, then by closes desc, then by name
            out.sort((a, b) => {
                const aw = a.win_rate ?? -1, bw = b.win_rate ?? -1;
                if (bw !== aw) return bw - aw;
                if (b.closes !== a.closes) return b.closes - a.closes;
                return a.channel.localeCompare(b.channel);
            });

            setRows(out);
        };

        // initial load + lightweight polling (every 5s)
        fetchAndBuild();
        polling.current = window.setInterval(fetchAndBuild, 5000);
        return () => {
            cancelled = true;
            if (polling.current) window.clearInterval(polling.current);
        };
    }, []);

    // Summary for KPI cards above
    const summary = useMemo(() => {
        const validWin = rows.filter(r => typeof r.win_rate === "number");
        const validScore = rows.filter(r => typeof r.signal_score === "number");

        const bestByWin = validWin.length
            ? [...validWin].sort((a, b) => (b.win_rate! - a.win_rate!))[0]
            : null;
        const bestByScore = validScore.length
            ? [...validScore].sort((a, b) => (b.signal_score! - a.signal_score!))[0]
            : null;

        const totals = {
            opens: rows.reduce((s, r) => s + (r.opens || 0), 0),
            closes: rows.reduce((s, r) => s + (r.closes || 0), 0),
            channels: rows.length,
        };

        // Weighted overall win-rate across channels by number of closes
        let weightedWins = 0, totalCloses = 0;
        rows.forEach(r => {
            if (typeof r.win_rate === "number" && r.closes > 0) {
                weightedWins += (r.win_rate / 100) * r.closes;
                totalCloses += r.closes;
            }
        });
        const overallWinRate = totalCloses > 0 ? (weightedWins / totalCloses) * 100 : null;

        return { bestByWin, bestByScore, totals, overallWinRate };
    }, [rows]);

    useEffect(() => {
        onSummary?.(summary);
    }, [summary, onSummary]);

    const isBestWin = useCallback(
        (r: ChanRow) => summary.bestByWin && r.channel === summary.bestByWin.channel,
        [summary.bestByWin]
    );
    const isBestScore = useCallback(
        (r: ChanRow) => summary.bestByScore && r.channel === summary.bestByScore.channel,
        [summary.bestByScore]
    );

    const rowTint = (r: ChanRow) =>
        selected === r.channel
            ? "bg-white/15"
            : isBestWin(r) || isBestScore(r)
                ? "bg-emerald-500/10"
                : "";

    const fmtPct = (v: number | null | undefined) =>
        typeof v === "number" ? `${v.toFixed(1)}%` : "—";

    const onRowClick = (r: ChanRow) => {
        onSelect?.(selected === r.channel ? null : r.channel);
    };

    return (
        <div className="space-y-2">
            <h2 className="text-white/80">Channel Performance</h2>

            {/* Mobile: Card list */}
            <ul className="md:hidden space-y-3">
                {rows.map((r, i) => (
                    <li
                        key={i}
                        className={`rounded-2xl border border-white/10 bg-black/20 p-3 ${rowTint(r)}`}
                        onClick={() => onRowClick(r)}
                    >
                        <div className="font-medium flex items-center gap-2">
                            <span className="truncate">{r.channel}</span>
                            {isBestWin(r) && (
                                <span className="rounded px-1.5 py-0.5 text-[11px] bg-emerald-600/20 text-emerald-300">
                                    Top Win%
                                </span>
                            )}
                            {isBestScore(r) && (
                                <span className="rounded px-1.5 py-0.5 text-[11px] bg-sky-600/20 text-sky-300">
                                    Top Score
                                </span>
                            )}
                            {selected === r.channel && (
                                <span className="rounded px-1.5 py-0.5 text-[11px] bg-white/20 text-white/90">
                                    Selected
                                </span>
                            )}
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-1 text-sm text-zinc-300">
                            <div><span className="text-zinc-400">Score:</span> {typeof r.signal_score === "number" ? `${r.signal_score.toFixed(1)}%` : "—"}</div>
                            <div><span className="text-zinc-400">Win rate:</span> {fmtPct(r.win_rate)}</div>
                            <div><span className="text-zinc-400">Opens/Closes:</span> {r.opens}/{r.closes}</div>
                            <div><span className="text-zinc-400">Avg conf:</span> {typeof r.avg_confidence === "number" ? r.avg_confidence.toFixed(1) : "—"}</div>
                            <div className="col-span-2"><span className="text-zinc-400">Last:</span> {r.last_signal ?? "—"}</div>
                        </div>
                    </li>
                ))}
                {!rows.length && (
                    <li className="rounded-2xl border border-white/10 bg-black/20 p-3 text-white/60">
                        No data yet.
                    </li>
                )}
            </ul>

            {/* Desktop: Table */}
            <div className="hidden md:block overflow-hidden rounded-2xl border border-white/10">
                <table className="w-full text-sm leading-6">
                    <thead className="sticky top-0 bg-black/40 backdrop-blur supports-[backdrop-filter]:bg-black/30">
                        <tr className="text-left text-white/70">
                            {["Channel", "Signal Score", "Win %", "Opens", "Closes", "Avg Conf", "Last Signal"].map(h => (
                                <th key={h} className="px-3 py-2">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="[&>tr:nth-child(odd)]:bg-white/[0.02]">
                        {rows.map((r, i) => (
                            <tr
                                key={i}
                                onClick={() => onRowClick(r)}
                                className={`border-t border-white/10 hover:bg-white/10 transition-colors cursor-pointer ${rowTint(r)}`}
                                title="Click to filter Recent Signals by this channel"
                            >
                                <td className="px-3 py-2">
                                    <div className="flex items-center gap-2">
                                        <span className="truncate">{r.channel}</span>
                                        {isBestWin(r) && (
                                            <span className="rounded px-1.5 py-0.5 text-[11px] bg-emerald-600/20 text-emerald-300">
                                                Top Win%
                                            </span>
                                        )}
                                        {isBestScore(r) && (
                                            <span className="rounded px-1.5 py-0.5 text-[11px] bg-sky-600/20 text-sky-300">
                                                Top Score
                                            </span>
                                        )}
                                        {selected === r.channel && (
                                            <span className="rounded px-1.5 py-0.5 text-[11px] bg-white/20 text-white/90">
                                                Selected
                                            </span>
                                        )}
                                    </div>
                                </td>
                                <td className="px-3 py-2 tabular-nums">
                                    {typeof r.signal_score === "number" ? r.signal_score.toFixed(1) + "%" : "—"}
                                </td>
                                <td className="px-3 py-2 tabular-nums">{fmtPct(r.win_rate)}</td>
                                <td className="px-3 py-2 tabular-nums">{r.opens}</td>
                                <td className="px-3 py-2 tabular-nums">{r.closes}</td>
                                <td className="px-3 py-2 tabular-nums">
                                    {typeof r.avg_confidence === "number" ? r.avg_confidence.toFixed(1) : "—"}
                                </td>
                                <td className="px-3 py-2">{r.last_signal ?? "—"}</td>
                            </tr>
                        ))}
                        {!rows.length && (
                            <tr className="border-t border-white/10">
                                <td className="px-3 py-6 text-white/60" colSpan={7}>No data yet.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
