import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Metrics } from "../api";
import ChannelPerformance from "../components/ChannelPerformance";
import StatCard from "../components/StatCard";
import ControlsBar from "../components/ControlsBar";
import RecentSignalsTable, { type Rec as SignalRec } from "../components/RecentSignalsTable";
import {useWebSocketFeed} from "../hooks/useWebSocketFeed";

function formatPnl(n: number | null | undefined) {
    if (typeof n !== "number" || !isFinite(n)) return "—";
    const sign = n >= 0 ? "+" : "−";
    const abs = Math.abs(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
    return `${sign}$${abs}`;
}

// Normalize any backend/WS record into the table's SignalRec shape
function normalizeRec(r: any): SignalRec | null {
    if (!r) return null;

    // If WS callback ever forwards a string, try to parse it
    if (typeof r === "string") {
        try { r = JSON.parse(r); } catch { return null; }
    }

    const rec: SignalRec = {
        t: r.t ?? r.time ?? r.timestamp ?? null,
        action: r.action,
        symbol: r.symbol,
        side: r.side,
        order_type: r.order_type ?? r.type,
        entry: r.entry ?? r.price ?? r.entry_price,
        entry_ref: r.entry_ref,
        sl: r.sl ?? r.stop_loss ?? r.stoploss,
        tps: r.tps ?? r.tp_list ?? (typeof r.tp === "number" ? [r.tp] : r.tp),
        source: r.source ?? r.channel,
        confidence: r.confidence,
        new_sl: r.new_sl,
        new_tps_csv: r.new_tps_csv,
        tp_slot: r.tp_slot,
        tp_to: r.tp_to,
    };
    return rec;
}

export default function Dashboard() {
    const [paused, setPaused] = useState(false);
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [positions, setPositions] = useState<any[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [recentSignals, setRecentSignals] = useState<SignalRec[]>([]);
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
        return () => { alive = false; clearInterval(id); };
    }, []);

    // Initial hydration for Recent Signals (so it's not empty until the first WS event)
    useEffect(() => {
        let alive = true;
        (async () => {
            try {
                const res = await fetch("/api/history?limit=50");
                if (res.ok) {
                    const data = await res.json();
                    const raw: any[] = Array.isArray(data)
                        ? data
                        : (data?.items ?? data?.rows ?? data?.data ?? []);
                    const mapped = raw.map(normalizeRec).filter(Boolean) as SignalRec[];

                    const ALLOW = new Set(["OPEN", "MODIFY", "MODIFY_TP", "EMERGENCY_CLOSE_ALL"]);
                    const filtered = mapped.filter(r => ALLOW.has((r.action || "").toUpperCase()));

                    const deduped = (() => {
                        const seen = new Set<string>();
                        const out: SignalRec[] = [];
                        for (const r of filtered) {
                            const k = `${r.action}|${r.symbol}|${r.t}|${r.entry_ref ?? ""}`;
                            if (seen.has(k)) continue;
                            seen.add(k);
                            out.push(r);
                        }
                        return out;
                    })();

                    const top3 = deduped
                        .sort((a, b) => (b?.t ?? 0) - (a?.t ?? 0))
                        .slice(0, 3);

                    if (!alive) return;
                    setRecentSignals(top3);
                }
            } catch {
                // ignore – WS will populate
            }
        })();
        return () => { alive = false; };
    }, []);

    // Live updates via WebSocket feed
    useWebSocketFeed((incoming: any) => {
        const rec = normalizeRec(incoming);
        if (!rec) return;

        const ALLOW = new Set(["OPEN", "MODIFY", "MODIFY_TP", "EMERGENCY_CLOSE_ALL"]);
        if (!ALLOW.has((rec.action || "").toUpperCase())) return;

        const keyNew = `${rec.action}|${rec.symbol}|${rec.t}|${rec.entry_ref ?? ""}`;
        setRecentSignals(prev => {
            // Remove any existing duplicate
            const filtered = prev.filter(r =>
                `${r.action}|${r.symbol}|${r.t}|${r.entry_ref ?? ""}` !== keyNew
            );
            // Insert newest and keep only 3
            const next = [rec, ...filtered]
                .sort((a, b) => (b?.t ?? 0) - (a?.t ?? 0))
                .slice(0, 3);
            return next;
        });
    });

    const openPositions = positions.length;
    const pnl30 = metrics?.pnl_30d ?? null;
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
            {error && <div className="mt-3 text-sm text-rose-400">{error}</div>}

            {/* Controls */}
            <div className="md:mt-4 h-16" aria-hidden />
            <ControlsBar
                paused={paused}
                onStart={async () => { try { await api.start(); setPaused(false); } catch { } }}
                onStop={async () => { try { await api.stop(); setPaused(true); } catch { } }}
                onTogglePause={async () => {
                    const next = !paused;
                    try { await api.pause(next); setPaused(next); } catch { }
                }}
                qualityDefault={quality}
                onQualityChange={async (val: number) => { try { await api.setQuality(val); } catch { } }}
            />

            {/* Recent Signals – last 3 + link to full history */}
            <section className="mt-6 w-full max-w-5xl mx-auto">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3 sm:p-4">
                    <div className="mb-2 sm:mb-3 flex items-center justify-between">
                        <div className="font-medium">
                            Recent Signals <span className="opacity-70">(last 3)</span>
                        </div>
                        <Link
                            to="/history"
                            className="text-sm font-medium underline underline-offset-4 hover:opacity-80"
                        >
                            View full history
                        </Link>
                    </div>
                    <RecentSignalsTable rows={recentSignals} />
                </div>
            </section>

            <ChannelPerformance onSummary={(s) => setChanSummary(s)} />
        </>
    );
}
