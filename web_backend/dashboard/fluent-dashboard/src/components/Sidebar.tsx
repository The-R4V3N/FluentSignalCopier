import { NavLink } from "react-router-dom";

type SidebarProps = {
    /** If provided, acts like a mobile drawer; otherwise renders static sidebar (desktop). */
    open?: boolean;
    onClose?: () => void;
};

const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
        "block px-3 py-2 rounded-lg transition select-none",
        isActive
            ? "bg-[var(--surface)] text-[var(--text)] font-semibold"
            : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]",
    ].join(" ");

export default function Sidebar({ open, onClose }: SidebarProps) {
    // Static desktop sidebar when `open` is undefined
    if (open === undefined) {
        return (
            <aside className="w-56 shrink-0 p-4 border-r token-border bg-[var(--surface-2)] hidden md:block">
                <Brand />
                <Nav onClose={onClose} />
            </aside>
        );
    }

    // Mobile drawer + backdrop
    return (
        <>
            <div
                onClick={onClose}
                className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity md:hidden ${open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
                    }`}
            />
            <aside
                className={[
                    "fixed inset-y-0 left-0 z-50 w-64 p-4 border-r token-border bg-[var(--surface-2)]",
                    "transition-transform will-change-transform md:hidden",
                    open ? "translate-x-0" : "-translate-x-full",
                ].join(" ")}
                role="dialog"
                aria-modal="true"
            >
                <div className="mb-3 flex items-center justify-between">
                    <Brand />
                    <button
                        onClick={onClose}
                        className="rounded-lg px-3 py-1.5 bg-white/10 hover:bg-white/15 text-white"
                    >
                        Close
                    </button>
                </div>
                <Nav onClose={onClose} />
            </aside>
        </>
    );
}

function Brand() {
    return (
        <div className="mb-4 text-sm font-semibold text-[var(--muted)]">
            Fluent Signal Copier
        </div>
    );
}

function Nav({ onClose }: { onClose?: () => void }) {
    // Close the drawer after navigating on mobile
    const close = () => onClose?.();
    return (
        <nav className="space-y-2">
            <NavLink to="/dashboard" end className={linkClass} onClick={close}>
                Dashboard
            </NavLink>
            <NavLink to="/history" className={linkClass} onClick={close}>
                History
            </NavLink>
            <NavLink to="/settings" className={linkClass} onClick={close}>
                Settings
            </NavLink>
        </nav>
    );
}
