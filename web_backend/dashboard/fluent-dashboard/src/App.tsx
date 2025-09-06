// src/App.tsx
import { Routes, Route, Navigate, Outlet } from "react-router-dom";
import { useEffect,  useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import HistoryPage from "./pages/History";
import SettingsPage from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function Shell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [version, setVersion] = useState<string>("—");
  const [heartbeat, setHeartbeat] = useState<"ok" | "stale" | "dead" | "—">("—");

  useEffect(() => {
    let alive = true;

    const fetchHealth = async () => {
      try {
        const r = await fetch("/api/health");
        const j = await r.json();
        if (!alive) return;
        setVersion(j?.version && j?.git_commit ? `${j.version} • ${j.git_commit}` : (j?.version ?? "—"));
        setHeartbeat(j?.heartbeat ?? "—");
      } catch {
        if (!alive) return;
        setHeartbeat("dead");
      }
    };

    fetchHealth();
    const id = setInterval(fetchHealth, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const hbColor =
    heartbeat === "ok" ? "var(--signal-buy, #22c55e)" :
      heartbeat === "stale" ? "var(--signal-modify, #3b82f6)" :
        heartbeat === "dead" ? "var(--signal-sell, #ef4444)" :
          "var(--muted)";

  return (
    // Page canvas uses tokens: --bg / --text
    <div className="min-h-dvh app-bg">
      {/* Top bar (mobile) */}
      <header
        className="
          sticky top-0 z-30 border-b token-border backdrop-blur
        "
        style={{ background: "color-mix(in srgb, var(--surface) 92%, transparent)" }}
      >
        <div className="mx-auto max-w-7xl px-3 sm:px-4 lg:px-6 h-14 flex items-center justify-between gap-3">
          <button
            className="md:hidden rounded-lg px-3 py-2"
            style={{ background: "var(--surface-2)" }}
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            ☰
          </button>
          <div className="font-semibold">Fluent Signal Copier</div>

          {/* Health + version pill */}
          <div
            className="items-center gap-2 rounded-full px-3 py-1 border token-border text-sm"
            style={{ background: "var(--surface-2)" }}
            title={`Heartbeat: ${heartbeat}`}
          >
            <span
              aria-hidden
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: hbColor }}
            />
            <span className="whitespace-nowrap">{version}</span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl grid grid-cols-1 md:grid-cols-[18rem,1fr]">
        {/* Static sidebar (desktop) */}
        <Sidebar />

        {/* Drawer (mobile) */}
        <Sidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} />

        {/* Page content */}
        <main className="relative px-3 sm:px-4 lg:px-6 py-4 md:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
