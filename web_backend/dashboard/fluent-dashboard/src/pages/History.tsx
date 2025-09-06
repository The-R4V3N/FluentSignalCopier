// src/pages/History.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import RecentSignalsTable, { type Rec } from "../components/RecentSignalsTable";
import ChannelPerformance from "../components/ChannelPerformance";
import StatCard from "../components/StatCard";
import { useWebSocketFeed } from "../hooks/useWebSocketFeed";

/* === Canonical source attribution (OPEN is truth) === */
type Row = Rec & { action?: string; gid?: string; oid?: string; source?: string };
const INTERNAL_SOURCES = new Set(["", "EA", "GUI", "WEB"]);
const keyFor = (r: Row) => (r.gid || r.oid || "").trim();
function canonicalSource(row: Row, opensByKey: Map<string, Row>): string {
    const k = keyFor(row);
    const open = k ? opensByKey.get(k) : undefined;
    const src = (open?.source || row.source || "").trim();
    return INTERNAL_SOURCES.has(src) ? "" : src;
}

export default function HistoryPage() {
    const [rows, setRows] = useState<Rec[]>([]);
    const [paused, setPaused] = useState(false);
    const [selectedChannel, setSelectedChannel] = useState<string | null>(null);

    // summary from ChannelPerformance
    const [bestWinName, setBestWinName] = useState<string>("—");
    const [bestScoreName, setBestScoreName] = useState<string>("—");
    const [totals, setTotals] = useState({ opens: 0, closes: 0, channels: 0 });

    // lightweight toast
    const [toast, setToast] = useState<string | null>(null);

    // clearing state for the button UX
    const [clearing, setClearing] = useState(false);

    useEffect(() => {
        document.title = "Fluent Signal Copier — History";
    }, []);

    useEffect(() => {
        (async () => {
            const data = await fetch("/api/signals?limit=200").then(r => r.json());
            setRows(Array.isArray(data) ? data : []);
        })();
    }, []);

    async function onClearHistory() {
        if (clearing) return;
        setClearing(true);
        try {
            // use the consolidated endpoint and always save a backup
            const r = await fetch("/api/signals/clear?backup=true", { method: "POST" });
            const j = await r.json();
            if (!r.ok || !j.ok) throw new Error(j?.error || "Failed to clear history");
            setRows([]);
            setToast("History cleared (backup saved).");
        } catch (e: any) {
            setToast(e?.message || "Failed to clear history");
        } finally {
            setClearing(false);
            setTimeout(() => setToast(null), 3000);
        }
    }

    const onMsg = useCallback((rec: Rec) => {
        if (paused) return;
        setRows(prev => [...prev.slice(-199), rec]);
    }, [paused]);

    useWebSocketFeed(onMsg);

    // Build opens index
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

    // Canonicalize sources for display
    const rowsCanon: Row[] = useMemo(() => {
        return (rows as Row[])
            .map(r => ({ ...r, source: canonicalSource(r, opensByKey) }))
            .filter(r => !!r.source);
    }, [rows, opensByKey]);

    const filteredRows = useMemo(() => {
        if (!selectedChannel) return rowsCanon;
        return rowsCanon.filter(r => (r.source || "") === selectedChannel);
    }, [rowsCanon, selectedChannel]);

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
                            Clear filter: <span className="ml-1 font-semibold">{selectedChannel}</span>
                        </button>
                    )}

                    {/* Clear history */}
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

                {/* Pause / Resume */}
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
                    {selectedChannel && (
                        <span className="muted text-sm">
                            Filtering by <span className="font-semibold text-[var(--text)]">{selectedChannel}</span>
                        </span>
                    )}
                </div>
                <div className="card overflow-hidden">
                    <RecentSignalsTable rows={filteredRows as Rec[]} />
                </div>
            </div>
        </div>
    );
}
