// src/components/StatCard.tsx
import React from "react";

type Props = {
    title: string;
    value: React.ReactNode;
    subtitle?: React.ReactNode;
};

export default function StatCard({ title, value, subtitle }: Props) {
    return (
        <div className="rounded-2xl border token-border bg-[var(--surface)] p-5 shadow-sm">
            <div className="text-[var(--muted)] text-sm">{title}</div>
            <div className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text)]">
                {value}
            </div>
            {subtitle ? (
                <div className="mt-1 text-xs text-[var(--muted)]">{subtitle}</div>
            ) : null}
        </div>
    );
}
