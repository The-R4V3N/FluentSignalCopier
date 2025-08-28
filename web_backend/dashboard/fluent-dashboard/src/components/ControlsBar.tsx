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
    useEffect(() => { props.onQualityChange?.(q); }, [q]);
    return (
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="flex gap-3">
                <button onClick={props.onStart} className="rounded-lg px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium">START</button>
                <button onClick={props.onStop} className="rounded-lg px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white font-medium">STOP</button>
                <button onClick={props.onTogglePause} className={`rounded-lg px-4 py-2 ${props.paused ? "bg-amber-600 hover:bg-amber-700" : "bg-sky-600 hover:bg-sky-700"} text-white font-medium`}>
                    {props.paused ? "Resume intake" : "Pause intake"}
                </button>
            </div>
            <div className="flex items-center gap-3">
                <span className="text-sm text-white/70">Signal Quality ≥</span>
                <input type="range" min={0} max={100} value={q} onChange={(e) => setQ(parseInt(e.target.value, 10))} className="w-56 accent-fuchsia-500" />
                <span className="w-10 text-right font-semibold">{q}</span>
            </div>
        </div>
    );
}
