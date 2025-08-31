// src/components/Sidebar.tsx
import React from "react";
import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
        "block px-3 py-2 rounded-lg transition select-none",
        isActive
            ? "bg-[var(--surface)] text-[var(--text)] font-semibold"
            : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]",
    ].join(" ");

export default function Sidebar() {
    return (
        <aside className="w-56 shrink-0 p-4 border-r token-border bg-[var(--surface-2)]">
            <div className="mb-4 text-sm font-semibold text-[var(--muted)]">
                Fluent Signal Copier
            </div>

            <nav className="space-y-2">
                <NavLink to="/dashboard" end className={linkClass}>
                    Dashboard
                </NavLink>
                <NavLink to="/history" className={linkClass}>
                    History
                </NavLink>
                <NavLink to="/settings" className={linkClass}>
                    Settings
                </NavLink>
            </nav>
        </aside>
    );
}
