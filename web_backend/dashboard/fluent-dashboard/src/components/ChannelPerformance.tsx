import { useEffect, useMemo, useState } from "react";

export type ChanRow = {
    channel: string;
    signal_score: number | null;
    win_rate: number | null;
    opens: number;
    closes: number;
    avg_confidence: number | null;
    last_signal: string | null;
};

export default function ChannelPerformance({
    selected,
    onSelect,
    onSummary,
}: {
    selected?: string | null;
    onSelect?: (channel: string | null) => void;
    onSummary?: (s: {
        bestByWin?: ChanRow | null;
        bestByScore?: ChanRow | null;
        totals: { opens: number; closes: number; channels: number };
    }) => void;
}) {
    const [rows, setRows] = useState<ChanRow[]>([]);

    useEffect(() => {
        fetch("http://127.0.0.1:8000/api/channel-performance")
            .then(r => r.json())
            .then((d) => setRows(Array.isArray(d) ? d : []))
            .catch(() => setRows([]));
    }, []);

    const summary = useMemo(() => {
        const validWin = rows.filter(r => typeof r.win_rate === "number");
        const validScore = rows.filter(r => typeof r.signal_score === "number");

        const bestByWin = validWin.length
            ? [...validWin].sort((a, b) => (b.win_rate! - a.win_rate!))[0]
            : null;
        const bestByScore = validScore.length
            ? [...validScore].sort((a, b) => (b.signal_score! - a.signal_score!))[0]
            : null;

        const totals = {
            opens: rows.reduce((s, r) => s + (r.opens || 0), 0),
            closes: rows.reduce((s, r) => s + (r.closes || 0), 0),
            channels: rows.length,
        };
        return { bestByWin, bestByScore, totals };
    }, [rows]);

    useEffect(() => {
        onSummary?.(summary);
    }, [summary]); // eslint-disable-line

    const isBestWin = (r: ChanRow) => summary.bestByWin && r.channel === summary.bestByWin.channel;
    const isBestScore = (r: ChanRow) => summary.bestByScore && r.channel === summary.bestByScore.channel;

    const rowTint = (r: ChanRow) =>
        selected === r.channel
            ? "bg-white/15"
            : isBestWin(r) || isBestScore(r)
                ? "bg-emerald-500/10"
                : "";

    const fmtPct = (v: number | null | undefined) =>
        typeof v === "number" ? `${v.toFixed(1)}%` : "—";

    const onRowClick = (r: ChanRow) => {
        onSelect?.(selected === r.channel ? null : r.channel);
    };

    return (
        <div className="space-y-2">
            <h2 className="text-white/80">Channel Performance</h2>
            <div className="overflow-hidden rounded-2xl border border-white/10">
                <table className="w-full text-sm leading-6">
                    <thead className="sticky top-0 bg-black/40 backdrop-blur supports-[backdrop-filter]:bg-black/30">
                        <tr className="text-left text-white/70">
                            {["Channel", "Signal Score", "Win %", "Opens", "Closes", "Avg Conf", "Last Signal"].map(h => (
                                <th key={h} className="px-3 py-2">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="[&>tr:nth-child(odd)]:bg-white/[0.02]">
                        {rows.map((r, i) => (
                            <tr
                                key={i}
                                onClick={() => onRowClick(r)}
                                className={`border-t border-white/10 hover:bg-white/10 transition-colors cursor-pointer ${rowTint(r)}`}
                                title="Click to filter Recent Signals by this channel"
                            >
                                <td className="px-3 py-2">
                                    <div className="flex items-center gap-2">
                                        <span>{r.channel}</span>
                                        {isBestWin(r) && (
                                            <span className="rounded px-1.5 py-0.5 text-[11px] bg-emerald-600/20 text-emerald-300">
                                                Top Win%
                                            </span>
                                        )}
                                        {isBestScore(r) && (
                                            <span className="rounded px-1.5 py-0.5 text-[11px] bg-sky-600/20 text-sky-300">
                                                Top Score
                                            </span>
                                        )}
                                        {selected === r.channel && (
                                            <span className="rounded px-1.5 py-0.5 text-[11px] bg-white/20 text-white/90">
                                                Selected
                                            </span>
                                        )}
                                    </div>
                                </td>
                                <td className="px-3 py-2 tabular-nums">{fmtPct(r.signal_score)}</td>
                                <td className="px-3 py-2 tabular-nums">{fmtPct(r.win_rate)}</td>
                                <td className="px-3 py-2 tabular-nums">{r.opens}</td>
                                <td className="px-3 py-2 tabular-nums">{r.closes}</td>
                                <td className="px-3 py-2 tabular-nums">{typeof r.avg_confidence === "number" ? r.avg_confidence.toFixed(1) : "—"}</td>
                                <td className="px-3 py-2">{r.last_signal ?? "—"}</td>
                            </tr>
                        ))}
                        {!rows.length && (
                            <tr className="border-t border-white/10">
                                <td className="px-3 py-6 text-white/60" colSpan={7}>No data yet.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
