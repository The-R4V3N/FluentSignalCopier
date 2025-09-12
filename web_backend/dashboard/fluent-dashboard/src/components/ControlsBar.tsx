import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";

export default function ControlsBar() {
    const [running, setRunning] = useState(false);
    const [paused, setPaused] = useState(false);
    const [q, setQ] = useState(60);
    const [busy, setBusy] = useState<string | null>(null);
    const [err, setErr] = useState<string | null>(null);

    // hydrate from backend state
    useEffect(() => {
        let alive = true;
        (async () => {
            try {
                const s = await api.getState();
                if (!alive) return;
                setRunning(!!s.running);
                setPaused(!!s.paused);
                setQ(Number.isFinite(s.quality) ? s.quality : 60);
            } catch (e: any) {
                setErr(e?.message || "Failed to load control state");
            }
        })();
        return () => { alive = false; };
    }, []);

    async function call(name: string, fn: () => Promise<any>) {
        setBusy(name);
        setErr(null);
        try {
            const res = await fn();
            const runningNext = !!(res.running ?? res.state?.running ?? running);
            const pausedNext = !!(res.paused ?? res.state?.paused ?? paused);
            const qNextRaw = (res.quality ?? res.state?.quality);
            const qNext = Number.isFinite(qNextRaw) ? Number(qNextRaw) : q;

            setRunning(runningNext);
            setPaused(pausedNext);
            setQ(qNext);
        } catch (e: any) {
            setErr(e?.message || "Request failed");
        } finally {
            setBusy(null);
        }
    }

    const onStart = () => call("start", () => api.start());
    const onStop = () => call("stop", () => api.stop());
    const onTogglePause = () => call("pause", () => api.pause(!paused));
    const onEmergency = () => call("emergency", () => api.emergencyCloseAll() as any);

    // send slider only when released
    const lastSentRef = useRef<number>(q);
    const sendQuality = () =>
        call("set-quality", () => api.setQuality(Math.round(q))).then(() => {
            lastSentRef.current = q;
        });

    const qLabel = useMemo(() => `Signal quality`, []);
    const qValueLabel = useMemo(() => String(Math.round(q)), [q]);

    return (
        <>
            {/* Sticky action bar on small screens */}
            <div
                className="
          md:hidden fixed bottom-0 inset-x-0 z-30
          border-t token-border
          px-3 py-2
          [padding-bottom:calc(env(safe-area-inset-bottom,0px)+0.5rem)]
          backdrop-blur
        "
                style={{ background: "color-mix(in srgb, var(--surface) 92%, transparent)" }}
            >
                <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={onStart}
                            disabled={busy !== null || running}
                            aria-busy={busy === "start"}
                            className="flex-1 rounded-xl h-11 bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60"
                        >
                            Start
                        </button>
                        <button
                            onClick={onTogglePause}
                            disabled={busy !== null || !running}
                            aria-busy={busy === "pause"}
                            className="flex-1 rounded-xl h-11 bg-amber-600 hover:bg-amber-700 text-white font-medium disabled:opacity-60"
                        >
                            {paused ? "Resume" : "Pause"}
                        </button>
                        <button
                            onClick={onStop}
                            disabled={busy !== null || !running}
                            aria-busy={busy === "stop"}
                            className="flex-1 rounded-xl h-11 bg-rose-600 hover:bg-rose-700 text-white font-medium disabled:opacity-60"
                        >
                            Stop
                        </button>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            onClick={onEmergency}
                            disabled={busy !== null}
                            aria-busy={busy === "emergency"}
                            className="rounded-xl px-3 h-10 bg-[var(--signal-emergency,#dc267f)] hover:opacity-90 text-white font-medium disabled:opacity-60"
                            title="Disable and close all positions immediately"
                        >
                            Stop + Close All
                        </button>

                        <div className="flex items-center gap-3 flex-1">
                            <span className="text-sm muted shrink-0">{qLabel}</span>
                            <input
                                aria-label="Signal quality"
                                type="range"
                                min={0}
                                max={100}
                                value={q}
                                onChange={(e) => setQ(Number(e.target.value))}
                                onMouseUp={() => { if (lastSentRef.current !== q) sendQuality(); }}
                                onTouchEnd={() => { if (lastSentRef.current !== q) sendQuality(); }}
                                className="w-full accent-emerald-500 h-2 rounded-lg"
                            />
                            <span className="w-10 text-right text-sm muted">{qValueLabel}</span>
                        </div>
                    </div>

                    {err && <div className="text-xs" style={{ color: "var(--signal-sell)" }}>{err}</div>}
                </div>
            </div>

            {/* Desktop card */}
            <div className="hidden md:block mt-4">
                <div className="card p-4 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={onStart}
                            disabled={busy !== null || running}
                            aria-busy={busy === "start"}
                            className="rounded-lg px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60"
                        >
                            START
                        </button>
                        <button
                            onClick={onTogglePause}
                            disabled={busy !== null || !running}
                            aria-busy={busy === "pause"}
                            className="rounded-lg px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white font-medium disabled:opacity-60"
                        >
                            {paused ? "RESUME" : "PAUSE"}
                        </button>
                        <button
                            onClick={onStop}
                            disabled={busy !== null || !running}
                            aria-busy={busy === "stop"}
                            className="rounded-lg px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-medium disabled:opacity-60"
                        >
                            STOP
                        </button>
                        <button
                            onClick={onEmergency}
                            disabled={busy !== null}
                            aria-busy={busy === "emergency"}
                            className="rounded-lg px-4 py-2 bg-[var(--signal-emergency,#dc267f)] hover:opacity-90 text-white font-medium disabled:opacity-60"
                            title="Write EMERGENCY_CLOSE_ALL to signals log"
                        >
                            STOP + CLOSE ALL
                        </button>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="text-sm muted">Signal quality</span>
                        <input
                            aria-label="Signal quality"
                            type="range"
                            min={0}
                            max={100}
                            value={q}
                            onChange={(e) => setQ(Number(e.target.value))}
                            onMouseUp={() => { if (lastSentRef.current !== q) sendQuality(); }}
                            onTouchEnd={() => { if (lastSentRef.current !== q) sendQuality(); }}
                            className="w-56 accent-emerald-500"
                        />
                        <span className="w-10 text-right">{qValueLabel}</span>
                    </div>
                </div>

                {err && <div className="mt-2 text-xs" style={{ color: "var(--signal-sell)" }}>{err}</div>}
            </div>
        </>
    );
}
