// src/components/ControlsBar.tsx
import { useEffect, useState } from "react";

type Props = {
    paused: boolean;
    onStart: () => void;
    onStop: () => void;
    onTogglePause: () => void;
    qualityDefault?: number;
    onQualityChange?: (q: number) => void;
};

export default function ControlsBar({
    paused,
    onStart,
    onStop,
    onTogglePause,
    qualityDefault = 60,
    onQualityChange,
}: Props) {
    const [q, setQ] = useState(qualityDefault);
    useEffect(() => {
        onQualityChange?.(q);
    }, [q, onQualityChange]);

    return (
        <div className="card elevate p-4 w-full">
            {/* single flexible row; wraps on small screens */}
            <div className="flex flex-wrap items-center gap-3">
                {/* Left: action buttons */}
                <div className="flex items-center gap-2">
                    <button
                        onClick={onStart}
                        className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                    >
                        START
                    </button>
                    <button
                        onClick={onStop}
                        className="px-4 py-2 rounded-lg bg-slate-600 hover:bg-slate-700 text-white font-medium"
                    >
                        STOP
                    </button>
                    <button
                        onClick={onTogglePause}
                        className={`px-4 py-2 rounded-lg text-white font-medium ${paused ? "bg-amber-600 hover:bg-amber-700" : "bg-sky-600 hover:bg-sky-700"
                            }`}
                    >
                        {paused ? "Resume intake" : "Pause intake"}
                    </button>
                </div>

                {/* Right: slider grows to fill remaining width */}
                <div className="flex items-center gap-3 ml-auto w-full sm:w-auto sm:flex-1">
                    <span className="text-sm muted whitespace-nowrap">Signal Quality ≥</span>
                    <input
                        type="range"
                        min={0}
                        max={100}
                        value={q}
                        onChange={(e) => setQ(parseInt(e.target.value, 10))}
                        className="flex-1 min-w-[220px] accent-fuchsia-500"
                    />
                    <span className="w-10 text-right font-semibold text-[var(--text)]">{q}</span>
                </div>
            </div>
        </div>
    );
}
