// src/pages/History.tsx

// Licensed under the Fluent Signal Copier Limited Use License v1.0
// See LICENSE.txt for terms. No warranty; use at your own risk.
// Copyright (c) 2025 R4V3N. All rights reserved.

import { useCallback, useEffect, useMemo, useState } from "react";
import RecentSignalsTable, { type Rec } from "../components/RecentSignalsTable";
import ChannelPerformance from "../components/ChannelPerformance";
import StatCard from "../components/StatCard";
import { useWebSocketFeed } from "../hooks/useWebSocketFeed";

/* ---------- Types & helpers ---------- */

type Row = Rec & {
    action?: string;
    gid?: string | number;
    oid?: string | number;
    id?: string | number;
    source?: string;
    result?: "WIN" | "LOSS" | "BREAKEVEN";
    pnl?: number;              // realized PnL in account currency
    symbol?: string;
    t?: number | string;
    ts?: number | string;
    time?: number | string;
    risk_percent?: number;
};

const INTERNAL_SOURCES = new Set([
    "",
    "EA",
    "GUI",
    "WEB",
    "SYSTEM",
    "BACKEND",
    "INTERNAL",
]);

// join key: prefer gid, then oid, then id
const keyFor = (r: Row) => String(r.gid ?? r.oid ?? r.id ?? "").trim();

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

function coalesceTime(rec: Row): number | null {
    const n = parseNumeric(rec.t ?? rec.ts ?? rec.time);
    return n != null ? Math.trunc(n) : null; // expect unix seconds
}

/** Prefer OPEN.source via gid/oid/id join; else (for CLOSE), choose the channel
 *  whose most recent OPEN in the same symbol occurred <= the CLOSE time. */
function canonicalSource(
    row: Row,
    opensByKey: Map<string, Row>,
    latestOpenBySymbolAndChannel: Map<string, Map<string, number>>
): string {
    // 1) Exact join
    const k = keyFor(row);
    const open = k ? opensByKey.get(k) : undefined;
    const fromJoin = String(open?.source ?? row.source ?? "").trim();
    if (fromJoin && !INTERNAL_SOURCES.has(fromJoin)) return fromJoin;

    // 2) Heuristic only for CLOSE
    if ((row.action ?? "").toUpperCase() !== "CLOSE") return "";
    const sym = (row.symbol || "").trim().toUpperCase();
    if (!sym) return "";

    const tClose = coalesceTime(row);
    const perChan = latestOpenBySymbolAndChannel.get(sym);
    if (!perChan) return "";

    let best = "";
    let bestTs = -1;
    for (const [chan, ts] of perChan) {
        if (INTERNAL_SOURCES.has(chan)) continue;
        if (typeof ts !== "number") continue;
        if (tClose !== null && ts > tClose) continue; // OPEN after CLOSE → ignore
        if (ts > bestTs) {
            bestTs = ts;
            best = chan;
        }
    }
    return best; // may be ""
}

/* ---------- Page ---------- */

export default function HistoryPage() {
    const [rows, setRows] = useState<Rec[]>([]);
    const [paused, setPaused] = useState(false);
    const [selectedChannel, setSelectedChannel] = useState<string | null>(null);

    // Summary (filled by ChannelPerformance)
    const [bestWinName, setBestWinName] = useState<string>("—");
    const [bestScoreName, setBestScoreName] = useState<string>("—");
    const [totals, setTotals] = useState({ opens: 0, closes: 0, channels: 0 });

    // Toast + clear state
    const [toast, setToast] = useState<string | null>(null);
    const [clearing, setClearing] = useState(false);

    useEffect(() => {
        document.title = "Fluent Signal Copier — History";
    }, []);

    // Initial load
    useEffect(() => {
        (async () => {
            try {
                const data = await fetch("/api/history?limit=200").then(r => r.json());
                setRows(Array.isArray(data?.items) ? (data.items as Rec[]) : []);
            } catch {
                setRows([]);
            }
        })();
    }, []);

    async function onClearHistory() {
        if (clearing) return;
        setClearing(true);
        try {
            const r = await fetch("/api/signals/clear?backup=true", { method: "POST" });
            const j = await r.json();
            if (!r.ok || !j.ok) throw new Error(j?.error || "Failed to clear history");
            setRows([]);
            // Reset KPI cards immediately
            setTotals({ opens: 0, closes: 0, channels: 0 });
            setBestWinName("—");
            setBestScoreName("—");
            setToast("History cleared (backup saved).");
        } catch (e: any) {
            setToast(e?.message || "Failed to clear history");
        } finally {
            setClearing(false);
            setTimeout(() => setToast(null), 3000);
        }
    }

    // Live updates (append)
    const onMsg = useCallback((rec: Rec) => {
        if (paused) return;
        setRows(prev => [...prev.slice(-499), rec]); // keep last ~500 in memory
    }, [paused]);
    useWebSocketFeed(onMsg);

    // Build OPEN index by gid/oid/id
    const opensByKey = useMemo(() => {
        const m = new Map<string, Row>();
        for (const r of rows as Row[]) {
            if ((r.action || "").toUpperCase() === "OPEN") {
                const k = keyFor(r);
                if (k) m.set(k, r);
            }
        }
        return m;
    }, [rows]);

    // Latest OPEN time by (symbol, channel) for heuristic
    const latestOpenBySymbolAndChannel = useMemo(() => {
        const m = new Map<string, Map<string, number>>();
        for (const r of rows as Row[]) {
            if ((r.action || "").toUpperCase() !== "OPEN") continue;
            const src = (r.source || "").trim();
            if (INTERNAL_SOURCES.has(src)) continue;
            const sym = (r.symbol || "").trim().toUpperCase();
            const tVal = coalesceTime(r);
            if (!sym || tVal == null) continue;

            let perChan = m.get(sym);
            if (!perChan) {
                perChan = new Map<string, number>();
                m.set(sym, perChan);
            }
            const prev = perChan.get(src) ?? -1;
            if (tVal > prev) perChan.set(src, tVal);
        }
        return m;
    }, [rows]);

    // Canonicalize sources for display — DO NOT DROP unknowns; render as "—"
    const rowsCanon: Row[] = useMemo(() => {
        return (rows as Row[]).map(r => {
            const src = canonicalSource(r, opensByKey, latestOpenBySymbolAndChannel);
            return { ...r, source: src || "—" };
        });
    }, [rows, opensByKey, latestOpenBySymbolAndChannel]);

    // Optional channel filter
    const filteredRows = useMemo(() => {
        if (!selectedChannel) return rowsCanon;
        return rowsCanon.filter(r => (r.source || "") === selectedChannel);
    }, [rowsCanon, selectedChannel]);

    // Sort newest first for the table
    const tableRows: Rec[] = useMemo(() => {
        const getT = (x: any) => parseNumeric((x as any).t ?? (x as any).ts ?? (x as any).time) ?? 0;
        return [...filteredRows].sort((a, b) => getT(b) - getT(a)).slice(0, 300);
    }, [filteredRows]);

    return (
        <div className="p-6 space-y-6">
            <h1 className="text-xl font-semibold">History</h1>

            {/* Controls bar */}
            <div className="card p-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    {selectedChannel && (
                        <button
                            className="px-3 py-1.5 rounded-lg border token-border bg-[var(--surface-2)]"
                            onClick={() => setSelectedChannel(null)}
                            title="Clear channel filter"
                        >
                            Clear filter:
                            <span className="ml-1 font-semibold">{selectedChannel}</span>
                        </button>
                    )}
                    <button
                        className="px-3 py-1.5 rounded-lg border token-border bg-[var(--surface-2)] disabled:opacity-60"
                        onClick={onClearHistory}
                        title="Clear the stored signals history"
                        disabled={clearing}
                        aria-busy={clearing}
                    >
                        {clearing ? "Clearing…" : "Clear history"}
                    </button>
                </div>

                <button
                    className="px-3 py-1.5 rounded-lg border token-border"
                    onClick={() => setPaused(p => !p)}
                >
                    {paused ? "Resume feed" : "Pause feed"}
                </button>
            </div>

            {/* Toast */}
            {toast && (
                <div
                    className="fixed bottom-4 right-4 rounded-lg border token-border px-4 py-2 shadow-lg"
                    style={{ background: "var(--surface)", color: "var(--text)" }}
                    role="status"
                    aria-live="polite"
                >
                    {toast}
                </div>
            )}

            {/* KPI cards */}
            <div className="grid gap-4 md:grid-cols-4">
                <StatCard title="Channels" value={totals.channels} />
                <StatCard title="Total Opens" value={totals.opens} />
                <StatCard title="Total Closes" value={totals.closes} />
                <StatCard title="Selected" value={selectedChannel ?? "—"} />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
                <StatCard title="Best by Win %" value={bestWinName} />
                <StatCard title="Best by Signal Score" value={bestScoreName} />
            </div>

            {/* Channel Performance (click to filter) */}
            <ChannelPerformance
                selected={selectedChannel}
                onSelect={setSelectedChannel}
                onSummary={(s) => {
                    setTotals(s.totals);
                    setBestWinName(s.bestByWin?.channel ?? "—");
                    setBestScoreName(s.bestByScore?.channel ?? "—");
                }}
            />

            {/* Recent signals */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold">Recent Signals</h2>
                    <div className="text-sm muted">
                        Showing {tableRows.length} row{tableRows.length === 1 ? "" : "s"}
                        {selectedChannel ? ` • Filter: ${selectedChannel}` : ""}
                    </div>
                </div>
                <RecentSignalsTable rows={tableRows} />
            </div>
        </div>
    );
}
