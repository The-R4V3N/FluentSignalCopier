import { useEffect, useMemo, useRef, useState } from "react";

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

const INTERNAL_SOURCES = new Set(["", "EA", "GUI", "WEB"]);

// join key: prefer gid, then oid, then id (OPENs sometimes only have id)
const keyFor = (r: RawRec) => String(r.gid ?? r.oid ?? r.id ?? "").trim();

function num(x: any): number | null {
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
}

// Accept multiple possible profit field names
function pickProfit(rec: RawRec): number | null {
    return (
        num(rec.profit) ??
        num(rec.p) ??
        num(rec.pnl) ??
        num(rec.profit_usd) ??
        num(rec.net_profit) ??
        null
    );
}

function coalesceTime(rec: RawRec): number | null {
    return num(rec.t ?? rec.ts ?? rec.time);
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

export default function ChannelPerformance({
    selected,
    onSelect,
    onSummary,
}: {
    selected?: string | null;
    onSelect?: (channel: string | null) => void;
    onSummary?: (s: {
        bestByWin?: ChanRow | null;
        bestByScore?: ChanRow | null;
        totals: { opens: number; closes: number; channels: number };
    }) => void;
}) {
    const [rows, setRows] = useState<ChanRow[]>([]);
    const polling = useRef<number | null>(null);

    // Poll raw signals and compute channel stats on the client
    useEffect(() => {
        const fetchAndBuild = async () => {
            let data: RawRec[] = [];
            try {
                const r = await fetch("http://127.0.0.1:8000/api/signals?limit=500");
                const json = await r.json();
                data = Array.isArray(json) ? (json as RawRec[]) : [];
            } catch {
                data = [];
            }

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

                    // Always count a close in the denominator (prevents staying at "—")
                    acc.totalClosed += 1;

                    const p = pickProfit(rec);
                    if (p !== null && p > 0) acc.wins += 1;
                }

                const tVal = coalesceTime(rec);
                if (tVal !== null) acc.lastT = Math.max(acc.lastT ?? 0, tVal);
            }

            // 3) Convert to ChanRow[]
            const out: ChanRow[] = [];
            for (const [channel, a] of byChan) {
                const win_rate =
                    a.totalClosed > 0 ? (a.wins / a.totalClosed) * 100 : null;

                const avg_confidence = a.confN > 0 ? a.confSum / a.confN : null;

                // Fallback: if no explicit score fields, use avg confidence as "signal score"
                const explicitScore = a.scoreN > 0 ? a.scoreSum / a.scoreN : null;
                const signal_score =
                    explicitScore !== null ? explicitScore : avg_confidence;

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

            // 4) Sort: by win %, then by closes desc
            out.sort((a, b) => {
                const aw = a.win_rate ?? -1, bw = b.win_rate ?? -1;
                if (bw !== aw) return bw - aw;
                return b.closes - a.closes;
            });

            setRows(out);
        };

        // initial load + lightweight polling (every 5s)
        fetchAndBuild();
        polling.current = window.setInterval(fetchAndBuild, 5000);
        return () => {
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
        return { bestByWin, bestByScore, totals };
    }, [rows]);

    useEffect(() => {
        onSummary?.(summary);
    }, [summary]); // eslint-disable-line

    const isBestWin = (r: ChanRow) => summary.bestByWin && r.channel === summary.bestByWin.channel;
    const isBestScore = (r: ChanRow) => summary.bestByScore && r.channel === summary.bestByScore.channel;

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
            <div className="overflow-hidden rounded-2xl border border-white/10">
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
                                        <span>{r.channel}</span>
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
