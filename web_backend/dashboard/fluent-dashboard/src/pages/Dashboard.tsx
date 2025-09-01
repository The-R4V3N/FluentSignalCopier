import { useState } from "react";
import StatCard from "../components/StatCard";
import ControlsBar from "../components/ControlsBar";
import RecentSignalsTable from "../components/RecentSignalsTable";

export default function Dashboard() {
    const [paused, setPaused] = useState(false);

    return (
        <>
            {/* KPI cards */}
            <section className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard title="Active Channels" value="12" />
                <StatCard title="Win Rate (30d)" value="74%" />
                <StatCard title="PnL (30d)" value="+$1,920" />
                <StatCard title="Open Positions" value="3" />
            </section>

            {/* Controls */}
            <div className="md:mt-4 h-16" aria-hidden />{/* spacer for potential sticky bar */}
            <ControlsBar
                paused={paused}
                onStart={() => setPaused(false)}
                onStop={() => setPaused(true)}
                onTogglePause={() => setPaused(p => !p)}
                qualityDefault={60}
                onQualityChange={() => { }}
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
                        {/* History page renders the interactive table; here you can
               add a compact widget or leave blank */}
                        <div className="text-sm text-white/60">Open History to explore channel stats.</div>
                    </div>
                </div>
            </section>
        </>
    );
}
