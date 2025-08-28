import type { ReactNode } from "react";

export default function StatCard({
    title, value, dot = "gray"
}: { title: string; value: ReactNode; dot?: "gray" | "green" | "yellow" | "red" }) {
    const dotColor = { gray: "bg-gray-500", green: "bg-emerald-500", yellow: "bg-amber-500", red: "bg-rose-500" }[dot];
    return (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center gap-2 text-sm text-white/70">
                <span>{title}</span>
                {dot && <span className={`h-2 w-2 rounded-full ${dotColor}`} />}
            </div>
            <div className="mt-2 text-3xl font-semibold">{value}</div>
        </div>
    );
}
