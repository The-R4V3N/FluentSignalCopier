import { useCallback, useEffect, useMemo, useState } from "react";
import RecentSignalsTable from "../components/RecentSignalsTable";
import type { Rec } from "../components/RecentSignalsTable";
import ChannelPerformance from "../components/ChannelPerformance";
import StatCard from "../components/StatCard";
import { useWebSocketFeed } from "../hooks/useWebSocketFeed";

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

    // filtered view for Recent Signals
    const filteredRows = useMemo(() => {
        if (!selectedChannel) return rows;
        return rows.filter(r => (r.source || "") === selectedChannel);
    }, [rows, selectedChannel]);

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
                <RecentSignalsTable rows={filteredRows} />
            </div>
        </div>
    );
}
