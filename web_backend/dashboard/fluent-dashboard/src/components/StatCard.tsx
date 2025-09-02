import React from "react";

type Props = {
    title: string;
    value: React.ReactNode;
    subtitle?: React.ReactNode;
};

export default function StatCard({ title, value, subtitle }: Props) {
    return (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-5 shadow-sm">
            <div className="text-white/70 text-sm">{title}</div>
            <div className="mt-2 text-3xl font-semibold tracking-tight">{value}</div>
            {subtitle ? <div className="mt-1 text-xs text-white/60">{subtitle}</div> : null}
        </div>
    );
}
