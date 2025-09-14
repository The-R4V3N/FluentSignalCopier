// src/components/ChannelPerformance.tsx

// Licensed under the Fluent Signal Copier Limited Use License v1.0
// See LICENSE.txt for terms. No warranty; use at your own risk.
// Copyright (c) 2025 R4V3N. All rights reserved.

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { api } from "../lib/api";

export type ChanRow = {
    channel: string;
    signal_score: number | null;   // averaged per channel
    win_rate: number | null;
    opens: number;
    closes: number;
    avg_confidence: number | null;
    last_signal: string | null;
};

type RawRec = {
    action?: string;               // "OPEN" | "CLOSE" | ...
    source?: string;               // channel name (may be internal/blank for CLOSE)
    symbol?: string;
    gid?: string | number;
    oid?: string | number;
    id?: string | number;          // sometimes OPENs use id only
    ticket?: string | number;      // present on CLOSE
    profit?: number | string;
    p?: number | string;
    pnl?: number | string;
    profit_usd?: number | string;
    net_profit?: number | string;
    confidence?: number;           // optional per-OPEN confidence (0..100)
    score?: number;                // optional per-OPEN score
    signal_score?: number;         // optional alt name
    t?: number | string;           // unix seconds
    ts?: number | string;          // alt time
    time?: number | string;        // alt time
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
        const s = x.replace(/[^\d,.\-]/g, "").replace(/(\d),(?=\d{3}\b)/g, "$1");
        const t = s.includes(",") && !s.includes(".") ? s.replace(",", ".") : s.replace(/,/g, "");
        const n = Number(t);
        return Number.isFinite(n) ? n : null;
    }
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
}

function pickProfit(rec: RawRec): number | null {
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
    try { return new Date(t * 1000).toLocaleString(); } catch { return null; }
}

/** Decide the canonical channel for a row.
 * 1) Prefer OPEN.source from gid/oid/id join
 * 2) Else for CLOSE with blank key/source, use heuristic:
 *    choose the channel whose most recent OPEN in the same symbol
 *    occurred <= the CLOSE time.
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

    // Heuristic only for CLOSE rows
    if ((row.action ?? "").toUpperCase() !== "CLOSE") return "";

    const sym = (row.symbol || "").trim().toUpperCase();
    if (!sym) return "";

    const tClose = coalesceTime(row);
    const perChan = latestOpenBySymbolAndChannel.get(sym);
    if (!perChan) return "";

    let best = ""; let bestTs = -1;
    for (const [chan, ts] of perChan) {
        if (INTERNAL_SOURCES.has(chan)) continue;
        if (typeof ts !== "number") continue;
        if (tClose !== null && ts > tClose) continue; // OPEN after CLOSE → ignore
        if (ts > bestTs) { bestTs = ts; best = chan; }
    }
    return best; // may be ""
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

/* ---------- theme helpers ---------- */
function tintStyle(colorVar: string, pct = 12): React.CSSProperties {
    return { background: `color-mix(in srgb, ${colorVar} ${pct}%, transparent)` };
}
const BUY_VAR = "var(--signal-buy, #22c55e)";
const SCORE_VAR = "var(--signal-modify, #3b82f6)";

/** ChannelPerformance */
export default function ChannelPerformance({ selected = null, onSelect, onSummary }: Props) {
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
                totalClosed: number; // denominator for win%
                confSum: number;
                confN: number;
                scoreSum: number;
                scoreN: number;
                lastT?: number;
            };

            const byChan = new Map<string, Acc>();
            const BUCKET_UNKNOWN = "—";

            for (const rec of data) {
                let canon = canonicalSource(rec, opensByKey, latestOpenBySymbolAndChannel);

                // Drop explicit internal sources; but KEEP unknowns in a "—" bucket
                if (canon && INTERNAL_SOURCES.has(canon)) canon = "";

                const channelKey = canon || BUCKET_UNKNOWN;

                let acc = byChan.get(channelKey);
                if (!acc) {
                    acc = {
                        opens: 0, closes: 0, wins: 0, totalClosed: 0,
                        confSum: 0, confN: 0, scoreSum: 0, scoreN: 0, lastT: undefined,
                    };
                    byChan.set(channelKey, acc);
                }

                const act = (rec.action ?? "").toUpperCase();
                if (act === "OPEN") {
                    acc.opens += 1;

                    if (typeof rec.confidence === "number") {
                        acc.confSum += rec.confidence; acc.confN += 1;
                    }
                    const scoreVal =
                        (typeof rec.signal_score === "number" ? rec.signal_score : null) ??
                        (typeof rec.score === "number" ? rec.score : null);
                    if (scoreVal !== null) { acc.scoreSum += scoreVal!; acc.scoreN += 1; }
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

                const explicitScore = a.scoreN > 0 ? a.scoreSum / a.scoreN : null;
                const signal_score = explicitScore !== null ? explicitScore : avg_confidence;

                out.push({
                    channel,
                    signal_score: signal_score == null ? null : Number(signal_score.toFixed(1)),
                    win_rate: win_rate == null ? null : Number(win_rate.toFixed(1)),
                    opens: a.opens,
                    closes: a.closes,
                    avg_confidence: avg_confidence == null ? null : Number(avg_confidence.toFixed(1)),
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
        const validWin = rows.filter((r) => typeof r.win_rate === "number");
        const validScore = rows.filter((r) => typeof r.signal_score === "number");

        const bestByWin = validWin.length
            ? [...validWin].sort((a, b) => b.win_rate! - a.win_rate!)[0]
            : null;
        const bestByScore = validScore.length
            ? [...validScore].sort((a, b) => b.signal_score! - a.signal_score!)[0]
            : null;

        const totals = {
            opens: rows.reduce((s, r) => s + (r.opens || 0), 0),
            closes: rows.reduce((s, r) => s + (r.closes || 0), 0),
            channels: rows.length,
        };

        // Weighted overall win-rate across channels by number of closes
        let weightedWins = 0, totalCloses = 0;
        rows.forEach((r) => {
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

    const rowTintStyle = (r: ChanRow): React.CSSProperties | undefined => {
        if (selected === r.channel) return { background: "var(--surface-2)" };
        if (isBestWin(r)) return tintStyle(BUY_VAR, 14);
        if (isBestScore(r)) return tintStyle(SCORE_VAR, 14);
        return undefined;
    };

    const fmtPct = (v: number | null | undefined) =>
        typeof v === "number" ? `${v.toFixed(1)}%` : "—";

    const onRowClick = (r: ChanRow) => {
        onSelect?.(selected === r.channel ? null : r.channel);
    };

    return (
        <div className="space-y-2">
            <h2 className="font-semibold">Channel Performance</h2>

            {/* Mobile: Card list */}
            <ul className="md:hidden space-y-3">
                {rows.map((r, i) => (
                    <li
                        key={i}
                        className="card p-3 cursor-pointer"
                        style={rowTintStyle(r)}
                        onClick={() => onRowClick(r)}
                    >
                        <div className="font-medium flex items-center gap-2">
                            <span className="truncate">{r.channel}</span>
                            {isBestWin(r) && (
                                <span
                                    className="rounded px-1.5 py-0.5 text-[11px]"
                                    style={{ ...tintStyle(BUY_VAR, 22), color: BUY_VAR }}
                                >
                                    Top Win%
                                </span>
                            )}
                            {isBestScore(r) && (
                                <span
                                    className="rounded px-1.5 py-0.5 text-[11px]"
                                    style={{ ...tintStyle(SCORE_VAR, 22), color: SCORE_VAR }}
                                >
                                    Top Score
                                </span>
                            )}
                            {selected === r.channel && (
                                <span className="rounded px-1.5 py-0.5 text-[11px]" style={{ background: "var(--surface-2)" }}>
                                    Selected
                                </span>
                            )}
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-1 text-sm muted">
                            <div><span>Score:</span> {typeof r.signal_score === "number" ? `${r.signal_score.toFixed(1)}%` : "—"}</div>
                            <div><span>Win rate:</span> {fmtPct(r.win_rate)}</div>
                            <div><span>Opens/Closes:</span> {r.opens}/{r.closes}</div>
                            <div><span>Avg conf:</span> {typeof r.avg_confidence === "number" ? r.avg_confidence.toFixed(1) : "—"}</div>
                            <div className="col-span-2"><span>Last:</span> {r.last_signal ?? "—"}</div>
                        </div>
                    </li>
                ))}
                {!rows.length && <li className="card p-3 muted">No data yet.</li>}
            </ul>

            {/* Desktop: Table */}
            <div className="hidden md:block overflow-hidden rounded-2xl">
                <table className="w-full text-sm leading-6 card">
                    <thead className="sticky top-0 table-header">
                        <tr className="text-left muted">
                            {["Channel", "Signal Score", "Win %", "Opens", "Closes", "Avg Conf", "Last Signal"].map((h) => (
                                <th key={h} className="px-3 py-2 whitespace-nowrap">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="[&>tr:nth-child(odd)]:[background:var(--surface-2)]">
                        {rows.map((r, i) => (
                            <tr key={i} className="border-t token-border hover:[background:var(--surface-2)] cursor-pointer" onClick={() => onRowClick(r)}>
                                <td className="px-3 py-2">{r.channel}</td>
                                <td className="px-3 py-2">{typeof r.signal_score === "number" ? `${r.signal_score.toFixed(1)}%` : "—"}</td>
                                <td className="px-3 py-2">{fmtPct(r.win_rate)}</td>
                                <td className="px-3 py-2">{r.opens}</td>
                                <td className="px-3 py-2">{r.closes}</td>
                                <td className="px-3 py-2">{typeof r.avg_confidence === "number" ? r.avg_confidence.toFixed(1) : "—"}</td>
                                <td className="px-3 py-2">{r.last_signal ?? "—"}</td>
                            </tr>
                        ))}
                        {!rows.length && (
                            <tr><td className="px-3 py-3 muted" colSpan={7}>No data yet.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
