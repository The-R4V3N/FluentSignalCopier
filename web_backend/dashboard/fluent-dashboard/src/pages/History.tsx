import { useCallback, useEffect, useMemo, useState } from "react";
import RecentSignalsTable from "../components/RecentSignalsTable";
import type { Rec } from "../components/RecentSignalsTable";
import ChannelPerformance from "../components/ChannelPerformance";
import StatCard from "../components/StatCard";
import { useWebSocketFeed } from "../hooks/useWebSocketFeed";

/* === NEW: helpers for canonical source attribution === */
type Row = Rec & { action?: string; gid?: string; oid?: string; source?: string };

const INTERNAL_SOURCES = new Set(["", "EA", "GUI", "WEB"]);
const keyFor = (r: Row) => (r.gid || r.oid || "").trim();

function canonicalSource(row: Row, opensByKey: Map<string, Row>): string {
    const k = keyFor(row);
    const open = k ? opensByKey.get(k) : undefined;
    // Prefer OPEN.source (truth), then row.source; strip internals
    const src = (open?.source || row.source || "").trim();
    return INTERNAL_SOURCES.has(src) ? "" : src;
}
/* ===================================================== */

export default function HistoryPage() {
    const [rows, setRows] = useState<Rec[]>([]);
    const [paused, setPaused] = useState(false);
    const [selectedChannel, setSelectedChannel] = useState<string | null>(null);

    // summary from ChannelPerformance
    const [bestWinName, setBestWinName] = useState<string>("—");
    const [bestScoreName, setBestScoreName] = useState<string>("—");
    const [totals, setTotals] = useState({ opens: 0, closes: 0, channels: 0 });

    useEffect(() => {
        (async () => {
            const data = await fetch("http://127.0.0.1:8000/api/signals?limit=200").then(r => r.json());
            setRows(Array.isArray(data) ? data : []);
        })();
    }, []);

    document.title = "Fluent Signal Copier — History";

    const onMsg = useCallback((rec: Rec) => {
        if (paused) return;
        setRows(prev => [...prev.slice(-199), rec]);
    }, [paused]);

    useWebSocketFeed(onMsg);

    /* === NEW: Build opens index from current rows === */
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

    /* === NEW: Canonicalize sources for all rows (display layer only) === */
    const rowsCanon: Row[] = useMemo(() => {
        return (rows as Row[])
            .map(r => {
                const src = canonicalSource(r, opensByKey);
                // Rewrite source for UI, drop internal/blank sources
                return { ...r, source: src };
            })
            .filter(r => !!r.source); // hide internal (EA/GUI/WEB) and blanks
    }, [rows, opensByKey]);

    /* === CHANGED: filter using canonicalized source === */
    const filteredRows = useMemo(() => {
        if (!selectedChannel) return rowsCanon;
        return rowsCanon.filter(r => (r.source || "") === selectedChannel);
    }, [rowsCanon, selectedChannel]);

    return (
        <div className="p-6 space-y-6">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-semibold">History</h1>
                <div className="flex items-center gap-2">
                    {selectedChannel && (
                        <button
                            className="rounded-lg px-3 py-1.5 bg-white/10 hover:bg-white/15 text-white/90"
                            onClick={() => setSelectedChannel(null)}
                            title="Clear channel filter"
                        >
                            Clear filter: <span className="ml-1 font-semibold">{selectedChannel}</span>
                        </button>
                    )}
                    <button
                        className={`rounded-lg px-3 py-2 ${paused ? "bg-amber-600" : "bg-sky-600"} hover:opacity-90 text-white`}
                        onClick={() => setPaused(p => !p)}
                    >
                        {paused ? "Resume feed" : "Pause feed"}
                    </button>
                </div>
            </div>

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

            {/* Recent signals (filtered) */}
            <div>
                <div className="mb-2 flex items-center justify-between">
                    <h2 className="text-white/80">Recent Signals</h2>
                    {selectedChannel && (
                        <span className="text-sm text-white/60">
                            Filtering by <span className="font-semibold text-white/80">{selectedChannel}</span>
                        </span>
                    )}
                </div>
                {/* NOTE: RecentSignalsTable will now receive rows where source is canonicalized */}
                <RecentSignalsTable rows={filteredRows as Rec[]} />
            </div>
        </div>
    );
}
