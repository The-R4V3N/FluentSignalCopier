import React from "react";

export type Rec = {
    t?: number; action?: string; symbol?: string; side?: string;
    order_type?: string; entry?: number; entry_ref?: number;
    sl?: number; tps?: number[]; source?: string;
    confidence?: number;
    new_sl?: number; new_tps_csv?: string; tp_slot?: number; tp_to?: number;
};

export type RecentSignalsTableProps = { rows: Rec[] };

function actionColorVar(action?: string, side?: string): string {
    const A = (action || "").toUpperCase();
    const S = (side || "").toUpperCase();
    if (A === "OPEN") {
        if (S === "BUY") return "var(--signal-buy, #22c55e)";
        if (S === "SELL") return "var(--signal-sell, #ef4444)";
        return "var(--signal-open, #3b82f6)";
    }
    if (A === "CLOSE") return "var(--signal-close, #ef4444)";
    if (A === "MODIFY") return "var(--signal-modify, #3b82f6)";
    if (A === "MODIFY_TP") return "var(--signal-modify-tp, #9333ea)";
    if (A === "EMERGENCY_CLOSE_ALL") return "var(--signal-emergency, #dc267f)";
    return "var(--signal-neutral, rgba(255,255,255,0.8))";
}

function bgTintStyle(color: string, opacityPercent = 18): React.CSSProperties {
    return { backgroundColor: `color-mix(in srgb, ${color} ${opacityPercent}%, transparent)` };
}

const RecentSignalsTable: React.FC<RecentSignalsTableProps> = ({ rows }) => {
    return (
        <div className="rounded-xl border border-white/10 overflow-hidden">
            <table className="w-full text-sm leading-6">
                <thead className="sticky top-0 bg-black/40 backdrop-blur supports-[backdrop-filter]:bg-black/30">
                    <tr className="text-left text-white/70">
                        {["Time", "Action", "Symbol", "Side", "Entry/Type", "Details", "Channel"].map(h => (
                            <th key={h} className="px-3 py-2">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody className="[&>tr:nth-child(odd)]:bg-white/[0.02]">
                    {rows.map((r, i) => {
                        const time = r.t ? new Date(r.t * 1000).toLocaleTimeString() : "—";
                        const details = [
                            r.sl !== undefined ? `SL ${r.sl}` : "",
                            (r.tps?.length ? r.tps.map((v, idx) => `TP${idx + 1} ${v}`).join(", ") : "")
                        ].filter(Boolean).join(" | ");
                        const entry = r.order_type === "MARKET"
                            ? (r.entry_ref ? `MARKET (${r.entry_ref})` : "MARKET")
                            : r.order_type ? `${r.order_type} @ ${r.entry ?? ""}` : (r.entry ?? "");
                        const baseColor = actionColorVar(r.action, r.side);

                        return (
                            <tr key={i} className="border-t border-white/5 transition-colors" style={bgTintStyle(baseColor, 18)}>
                                <td className="px-3 py-2">{time}</td>
                                <td className="px-3 py-2 font-semibold" style={{ color: baseColor }}>{r.action}</td>
                                <td className="px-3 py-2">{r.symbol}</td>
                                <td className="px-3 py-2">{r.side || ""}</td>
                                <td className="px-3 py-2 tabular-nums">{entry}</td>
                                <td className="px-3 py-2 tabular-nums">{details}</td>
                                <td className="px-3 py-2">{r.source || ""}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

export default RecentSignalsTable;
