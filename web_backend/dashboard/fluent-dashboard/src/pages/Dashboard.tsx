import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import StatCard from "../components/StatCard";
import type { Rec } from "../components/RecentSignalsTable";
import ControlsBar from "../components/ControlsBar";
import { useWebSocketFeed } from "../hooks/useWebSocketFeed";
import { API_BASE } from "../config"; // 👈 dynamic API base

type Metrics = { heartbeat: "ok" | "stale" | "dead" | string; counts: Record<string, number> };

export default function Dashboard() {
    const [metrics, setMetrics] = useState<Metrics>({ heartbeat: "dead", counts: {} as any });
    const [rows, setRows] = useState<Rec[]>([]);
    const [paused, setPaused] = useState(false);
    const qualityRef = useRef<number>(60); // UI-only threshold like the desktop slider

    // initial load
    useEffect(() => {
        (async () => {
            const [m, s, st] = await Promise.all([
                fetch(`${API_BASE}/api/metrics`).then(r => r.json()),
                fetch(`${API_BASE}/api/signals?limit=200`).then(r => r.json()),
                fetch(`${API_BASE}/api/state`).then(r => r.json()).catch(() => null),
            ]);
            document.title = "Fluent Signal Copier — Dashboard";
            setMetrics(m);
            setRows(Array.isArray(s) ? s : []);
            if (st) {
                setPaused(!!st.paused);
                qualityRef.current = st.quality ?? 60;
            }
        })();
    }, []);

    // live feed
    const onMsg = useCallback((rec: Rec) => {
        if (paused) return;                    // UI pause
        // apply a simple “quality” gate if backend doesn't filter
        const conf = typeof rec.confidence === "number" ? rec.confidence : 100;
        if (rec.action === "OPEN" && conf < (qualityRef.current ?? 0)) return;

        setRows(prev => [...prev.slice(-199), rec]); // keep 200
        // update counters quickly
        setMetrics(m => {
            const c = { ...(m.counts || {}) };
            const k = (rec.action || "MISC").toLowerCase();
            c[k] = (c[k] || 0) + 1;
            return { ...m, counts: c };
        });
    }, [paused]);

    useWebSocketFeed(onMsg);

    // derived session stats
    const { channels, opens, closes, totalSignals } = useMemo(() => {
        const ch = new Set<string>();
        let o = 0, c = 0, t = 0;
        for (const r of rows) {
            if (r?.source) ch.add(String(r.source));
            const a = (r?.action || "").toUpperCase();
            if (a === "OPEN") o++;
            if (a === "CLOSE") c++;
            if (a) t++;
        }
        return { channels: ch.size, opens: o, closes: c, totalSignals: t };
    }, [rows]);

    // heartbeat dot color
    const hbDot = metrics.heartbeat === "ok" ? "green" : metrics.heartbeat === "stale" ? "yellow" : "red";
    const sigDot = metrics.counts.open > 0 ? "green" : "red";
    const opnDot = metrics.counts.open > 0 ? "green" : "red";
    const clsDot = metrics.counts.close > 0 ? "green" : "red";
    const chnDot = channels > 0 ? "green" : "red";
    const modDot = metrics.counts.modify > 0 ? "green" : "red";
    const modTpDot = metrics.counts.modify_tp > 0 ? "green" : "red";
    const qltDot = qualityRef.current >= 60 ? "green" : qualityRef.current >= 30 ? "yellow" : "red";

    // actions → hit endpoints
    const api = {
        start: () => fetch(`${API_BASE}/api/start`, { method: "POST" }).then(() => { }),
        stop: () => fetch(`${API_BASE}/api/stop`, { method: "POST" }).then(() => { }),
        pauseIntake: (p: boolean) =>
            fetch(`${API_BASE}/api/pause`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ paused: p }),
            }).then(() => setPaused(p)),
        emergency: () =>
            fetch(`${API_BASE}/api/emergency-close-all`, { method: "POST" }),
        setQuality: (q: number) => {
            qualityRef.current = q;
            fetch(`${API_BASE}/api/set-quality`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ threshold: q }),
            }).catch(() => { });
        },
    };

    return (
        <div className="mx-auto max-w-[1200px] px-6 py-6 space-y-6">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-semibold">Fluent Signal Copier — Web Dashboard</h1>
                <button
                    onClick={api.emergency}
                    className="rounded-lg px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white font-medium"
                >
                    EMERGENCY CLOSE ALL
                </button>
            </div>

            {/* Controls row (Start/Stop/Pause + Signal Quality slider) */}
            <ControlsBar
                paused={paused}
                onStart={api.start}
                onStop={api.stop}
                onTogglePause={() => api.pauseIntake(!paused)}
                qualityDefault={60}
                onQualityChange={api.setQuality}
            />

            {/* KPI cards */}
            <div className="grid gap-4 md:grid-cols-4">
                <StatCard title="EA Heartbeat" value={String(metrics.heartbeat).toUpperCase()} dot={hbDot as any} />
                <StatCard title="Signals " value={totalSignals} dot={sigDot as any} />
                <StatCard title="Opens" value={opens} dot={opnDot as any} />
                <StatCard title="Closes" value={closes} dot={clsDot as any} />
            </div>

            {/* extra card to match desktop */}
            <div className="grid gap-4 md:grid-cols-4">
                <StatCard title="Channels" value={channels} dot={chnDot as any} />
                <StatCard title="Modify" value={metrics.counts.modify || 0} dot={modDot as any} />
                <StatCard title="Modify TP" value={metrics.counts.modify_tp || 0} dot={modTpDot as any} />
                <StatCard title="Quality ≥" value={qualityRef.current} dot={qltDot as any} />
            </div>

        </div>
    );
}
