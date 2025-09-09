import React from "react";

export type Rec = {
    t?: number; action?: string; symbol?: string; side?: string;
    order_type?: string; entry?: number; entry_ref?: number;
    sl?: number; tps?: number[]; source?: string;
    confidence?: number;
    new_sl?: number; new_tps_csv?: string; tp_slot?: number; tp_to?: number;
    risk_percent?: number;
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

function fmtRisk(v: unknown): string {
    const n = typeof v === "number" ? v : Number(v);
    if (!Number.isFinite(n)) return "—";
    // Heuristic: small numbers are multipliers; larger look like percentages
    return n <= 3 ? `${n}×` : `${n}%`;
}

const RecentSignalsTable: React.FC<RecentSignalsTableProps> = ({ rows }) => {
    return (
        <div className="card overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm leading-6">
                <thead className="sticky top-0 table-header">
                    <tr className="text-left muted">
                        {["Time", "Action", "Symbol", "Side", "Entry/Type", "Risk", "Details", "Channel"].map(
                            (h) => (
                                <th key={h} className="px-3 py-2 whitespace-nowrap">
                                    {h}
                                </th>
                            )
                        )}
                    </tr>
                </thead>

                {/* stripe odd rows using theme token, no hard-coded whites */}
                <tbody className="[&>tr:nth-child(odd)]:[background:var(--surface-2)]">
                    {rows.map((r, i) => {
                        const time = r.t ? new Date(r.t * 1000).toLocaleTimeString() : "—";
                        const details = [
                            r.sl !== undefined ? `SL ${r.sl}` : "",
                            r.tps?.length ? r.tps.map((v, idx) => `TP${idx + 1} ${v}`).join(", ") : "",
                        ]
                            .filter(Boolean)
                            .join(" | ");

                        const entry =
                            r.order_type === "MARKET"
                                ? r.entry_ref
                                    ? `MARKET (${r.entry_ref})`
                                    : "MARKET"
                                : r.order_type
                                    ? `${r.order_type} @ ${r.entry ?? ""}`
                                    : (r.entry as any) ?? "";

                        const baseColor = actionColorVar(r.action, r.side);

                        return (
                            <tr
                                key={i}
                                className="border-t token-border transition-colors hover:[background:color-mix(in_srgb,var(--surface-2)_60%,transparent)]"
                                style={bgTintStyle(baseColor, 18)}
                            >
                                <td className="px-3 py-2">{time}</td>
                                <td className="px-3 py-2 font-semibold" style={{ color: baseColor }}>
                                    {r.action}
                                </td>
                                <td className="px-3 py-2">{r.symbol}</td>
                                <td className="px-3 py-2">{r.side || ""}</td>
                                <td className="px-3 py-2 tabular-nums">{entry}</td>
                                <td className="px-3 py-2 tabular-nums">{fmtRisk((r as any).risk_percent ?? (r as any).risk)}</td>
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
