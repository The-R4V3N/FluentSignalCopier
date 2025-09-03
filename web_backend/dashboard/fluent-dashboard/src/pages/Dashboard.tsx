import { useEffect, useState } from "react";
import { api, type Metrics } from "../api";
import ChannelPerformance from "../components/ChannelPerformance";
import StatCard from "../components/StatCard";
import ControlsBar from "../components/ControlsBar";
import RecentSignalsTable from "../components/RecentSignalsTable";

function formatPnl(n: number | null | undefined) {
    if (typeof n !== "number" || !isFinite(n)) return "—";
    const sign = n >= 0 ? "+" : "−";
    const abs = Math.abs(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
    return `${sign}$${abs}`;
}

export default function Dashboard() {
    const [paused, setPaused] = useState(false);
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [positions, setPositions] = useState<any[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [chanSummary, setChanSummary] = useState<{
        totals: { opens: number; closes: number; channels: number };
        overallWinRate: number | null;
        bestByWin?: any;
        bestByScore?: any;
    } | null>(null);

    // poll metrics + positions
    useEffect(() => {
        let alive = true;

        const load = async () => {
            try {
                const [m, p] = await Promise.all([
                    api.getMetrics(),
                    api.getPositions().catch(() => []),
                ]);
                if (!alive) return;
                setMetrics(m);
                setPositions(Array.isArray(p) ? p : []);
                setPaused(Boolean(m?.state?.paused));
                setError(null);
            } catch (e: any) {
                if (!alive) return;
                setError(e?.message || "Failed to load data");
            }
        };

        load();
        const id = setInterval(load, 2000);
        return () => {
            alive = false;
            clearInterval(id);
        };
    }, []);

    const openPositions = positions.length;          // authoritative count from /api/positions
    const pnl30 = metrics?.pnl_30d ?? null;          // 30d PnL from /api/metrics
    const quality = metrics?.state?.quality ?? 60;

    return (
        <>
            {/* KPI cards */}
            <section className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                    title="Active Channels"
                    value={
                        chanSummary?.totals?.channels != null
                            ? String(chanSummary.totals.channels)
                            : "—"
                    }
                />
                <StatCard
                    title="Win Rate (overall)"
                    value={
                        chanSummary?.overallWinRate != null
                            ? `${chanSummary.overallWinRate.toFixed(1)}%`
                            : "—"
                    }
                />
                <StatCard title="PnL (30d)" value={formatPnl(pnl30)} />
                <StatCard title="Open Positions" value={openPositions} />
            </section>

            {/* Optional error banner */}
            {error && (
                <div className="mt-3 text-sm text-rose-400">
                    {error}
                </div>
            )}

            {/* Controls */}
            <div className="md:mt-4 h-16" aria-hidden />{/* spacer for potential sticky bar */}
            <ControlsBar
                paused={paused}
                onStart={async () => {
                    try { await api.start(); setPaused(false); } catch (_) { }
                }}
                onStop={async () => {
                    try { await api.stop(); setPaused(true); } catch (_) { }
                }}
                onTogglePause={async () => {
                    const next = !paused;
                    try { await api.pause(next); setPaused(next); } catch (_) { }
                }}
                qualityDefault={quality}
                onQualityChange={async (val: number) => {
                    try { await api.setQuality(val); } catch (_) { }
                }}
            />

            {/* Data sections */}
            <section className="mt-6 grid grid-cols-1 xl:grid-cols-5 gap-4">
                <div className="xl:col-span-3">
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 sm:p-4">
                        <div className="mb-2 sm:mb-3 font-medium">Recent Signals</div>
                        {/* Wire real rows later; empty array now satisfies the prop */}
                        <RecentSignalsTable rows={[]} />
                    </div>
                </div>
                <div className="xl:col-span-2">
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 sm:p-4">
                        <div className="mb-2 sm:mb-3 font-medium">Channel Performance</div>
                        {/* History page renders the interactive table; here you can add a compact widget or leave blank */}
                        <div className="text-sm text-white/60">Open History to explore channel stats.</div>
                    </div>
                </div>
            </section>
            <ChannelPerformance
                onSummary={(s) => setChanSummary(s)}
            // pass selected/onSelect if you already use them
            />
        </>
    );
}
