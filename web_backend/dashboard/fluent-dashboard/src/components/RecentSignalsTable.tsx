export type Rec = {
    t?: number; action?: string; symbol?: string; side?: string;
    order_type?: string; entry?: number; entry_ref?: number;
    sl?: number; tps?: number[]; source?: string;
    // add fields used elsewhere:
    confidence?: number;
    new_sl?: number; new_tps_csv?: string; tp_slot?: number; tp_to?: number;
};

export default function RecentSignalsTable({ rows }: { rows: Rec[] }) {

    const tint = (a?: string) => {
        switch ((a || "").toUpperCase()) {
            case "OPEN": return "bg-[rgba(34,197,94,0.2)]";                 // green
            case "CLOSE": return "bg-[rgba(239,68,68,0.2)]";                // red
            case "MODIFY": return "bg-[rgba(59,130,246,0.2)]";              // blue
            case "MODIFY_TP": return "bg-[rgba(147,51,234,0.2)]";           // purple
            case "EMERGENCY_CLOSE_ALL": return "bg-[rgba(220,38,127,0.2)]"; // pink
            default: return "";
        }
    };

    const actionClass = (a?: string) => {
        switch ((a || "").toUpperCase()) {
            case "OPEN": return "font-semibold text-[rgb(34,197,94)]";          // green-500
            case "CLOSE": return "font-semibold text-[rgb(239,68,68)]";         // red-500
            case "MODIFY": return "font-semibold text-[rgb(59,130,246)]";       // blue-500
            case "MODIFY_TP": return "font-semibold text-[rgb(147,51,234)]";    // purple-600
            case "EMERGENCY_CLOSE_ALL": return "font-semibold text-[rgb(220,38,127)]"; // pink-600
            default: return "font-semibold text-white/80";
        }
    };

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

                        return (
                            <tr
                                key={i}
                                className={`border-t border-white/5 ${tint(r.action)} hover:bg-white/10 transition-colors`}
                            >
                                <td className="px-3 py-2">{time}</td>
                                <td className={`px-3 py-2 ${actionClass(r.action)}`}>{r.action}</td>
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
}