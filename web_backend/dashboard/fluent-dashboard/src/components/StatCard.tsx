// components/StatCard.tsx
import React from "react";

type Dot = "green" | "red" | "yellow" | undefined;

export default function StatCard({
    title,
    value,
    dot,
}: {
    title: string;
    value: React.ReactNode;
    dot?: Dot;
}) {
    const dotCls =
        dot === "green"
            ? "bg-emerald-500"
            : dot === "yellow"
                ? "bg-amber-500"
                : dot === "red"
                    ? "bg-rose-500"
                    : "bg-neutral-400";

    return (
        <div className="rounded-2xl border p-4 bg-[var(--card-bg)] border-[var(--card-border)]">
            <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
                <span className={`h-2 w-2 rounded-full ${dotCls}`} />
                <span className="font-medium">{title}</span>
            </div>
            <div className="mt-2 text-3xl font-semibold leading-none text-[var(--text)]">
                {value}
            </div>
        </div>
    );
}
