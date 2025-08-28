import { NavLink } from "react-router-dom";

export default function Sidebar() {
    const linkBase = "block w-full text-left px-3 py-2 rounded-lg transition";
    const active = "bg-white/10 text-white";
    const idle = "text-white/70 hover:text-white hover:bg-white/5";

    return (
        <aside className="w-56 shrink-0 p-4 border-r border-white/10 bg-black/20">
            <div className="mb-4 text-sm font-semibold text-white/70">
                Fluent Signal Copier
            </div>

            {/* force vertical layout */}
            <nav className="flex flex-col gap-2">
                <NavLink to="/dashboard" end
                    className={({ isActive }) => `${linkBase} ${isActive ? active : idle}`}>
                    Dashboard
                </NavLink>

                <NavLink to="/history"
                    className={({ isActive }) => `${linkBase} ${isActive ? active : idle}`}>
                    History
                </NavLink>

                <NavLink to="/settings"
                    className={({ isActive }) => `${linkBase} ${isActive ? active : idle}`}>
                    Settings
                </NavLink>
            </nav>
        </aside>
    );
}
