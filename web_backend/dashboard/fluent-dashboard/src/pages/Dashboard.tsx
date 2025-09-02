import { useEffect, useState } from "react";
import { api, type Metrics } from "../api";
import StatCard from "../components/StatCard";

function formatPnl(n: number | null | undefined) {
    if (typeof n !== "number" || !isFinite(n)) return "—";
    const sign = n >= 0 ? "+" : "−";
    const abs = Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `${sign}$${abs}`;
}

export default function Dashboard() {
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let alive = true;

        const load = async () => {
            try {
                const m = await api.getMetrics();
                if (!alive) return;
                setMetrics(m);
                setError(null);
            } catch (e: any) {
                if (!alive) return;
                setError(e?.message || "Failed to load metrics");
            }
        };

        load();
        const id = setInterval(load, 2000);
        return () => {
            alive = false;
            clearInterval(id);
        };
    }, []);

    const openPositions = metrics?.open_positions ?? 0;
    const pnl30 = metrics?.pnl_30d ?? null;

    return (
        <div className="px-6 py-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <StatCard title="Active Channels" value={12} /> {/* keep as-is if you calculate elsewhere */}
                <StatCard title="Win Rate (30d)" value="74%" /> {/* replace with your real computation when ready */}
                <StatCard title="PnL (30d)" value={formatPnl(pnl30)} />
                <StatCard title="Open Positions" value={openPositions} />
            </div>

            {/* ...rest of your dashboard (controls, recent signals, etc.) */}
            {error && (
                <div className="mt-4 text-sm text-red-400">
                    {error}
                </div>
            )}
        </div>
    );
}