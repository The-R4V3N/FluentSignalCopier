import { useEffect, useState } from "react";

export default function ControlsBar(props: {
    paused: boolean;
    onStart: () => void;
    onStop: () => void;
    onTogglePause: () => void;
    qualityDefault?: number;
    onQualityChange?: (q: number) => void;
}) {
    const [q, setQ] = useState(props.qualityDefault ?? 60);
    useEffect(() => {
        props.onQualityChange?.(q);
    }, [q]);

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
                style={{
                    // translucent surface using theme tokens
                    background: "color-mix(in srgb, var(--surface) 92%, transparent)",
                }}
            >
                <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={props.onStart}
                            className="flex-1 rounded-xl h-11 bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                        >
                            Start
                        </button>
                        <button
                            onClick={props.onTogglePause}
                            className="flex-1 rounded-xl h-11 bg-amber-600 hover:bg-amber-700 text-white font-medium"
                        >
                            {props.paused ? "Resume" : "Pause"}
                        </button>
                        <button
                            onClick={props.onStop}
                            className="flex-1 rounded-xl h-11 bg-rose-600 hover:bg-rose-700 text-white font-medium"
                        >
                            Stop
                        </button>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-sm muted shrink-0">Signal quality</span>
                        <input
                            aria-label="Signal quality"
                            type="range"
                            min={0}
                            max={100}
                            value={q}
                            onChange={(e) => setQ(Number(e.target.value))}
                            className="w-full accent-emerald-500 h-2 rounded-lg"
                        />
                        <span className="w-10 text-right text-sm muted">{q}</span>
                    </div>
                </div>
            </div>

            {/* Desktop card */}
            <div className="hidden md:block mt-4">
                <div className="card p-4 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={props.onStart}
                            className="rounded-lg px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                        >
                            START
                        </button>
                        <button
                            onClick={props.onTogglePause}
                            className="rounded-lg px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white font-medium"
                        >
                            {props.paused ? "RESUME" : "PAUSE"}
                        </button>
                        <button
                            onClick={props.onStop}
                            className="rounded-lg px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-medium"
                        >
                            STOP
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
                            className="w-56 accent-emerald-500"
                        />
                        <span className="w-10 text-right">{q}</span>
                    </div>
                </div>
            </div>
        </>
    );
}
