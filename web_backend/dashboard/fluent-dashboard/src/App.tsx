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

  // health info
  const [heartbeat, setHeartbeat] = useState<"ok" | "stale" | "dead" | "—">("—");
  const [version, setVersion] = useState<string>("—");
  const [py, setPy] = useState<string>("—");
  const [builtAt, setBuiltAt] = useState<string>("—");
  const [hbAge, setHbAge] = useState<number | null>(null);
  const [hbTs, setHbTs] = useState<number | null>(null);

  // about modal
  const [showAbout, setShowAbout] = useState(false);

  useEffect(() => {
    let alive = true;

    const fetchHealth = async () => {
      try {
        const r = await fetch("/api/health");
        const j = await r.json();
        if (!alive) return;
        setVersion(j?.version && j?.git_commit ? `${j.version} • ${j.git_commit}` : (j?.version ?? "—"));
        setHeartbeat(j?.heartbeat ?? "—");
        setHbAge(typeof j?.heartbeat_age_seconds === "number" ? j.heartbeat_age_seconds : null);
        setHbTs(typeof j?.heartbeat_ts === "number" ? j.heartbeat_ts : null);
        setPy(j?.py ?? "—");
        setBuiltAt(j?.built_at ?? "—");
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
    <div className="min-h-dvh app-bg">
      {/* Top bar (mobile) */}
      <header
        className="sticky top-0 z-30 border-b token-border backdrop-blur"
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

          {/* Health + version pill (clickable) */}
          <button
            type="button"
            onClick={() => setShowAbout(true)}
            className="items-center gap-2 rounded-full px-3 py-1 border token-border text-sm inline-flex"
            style={{ background: "var(--surface-2)" }}
            title="Click for details"
          >
            <span aria-hidden className="inline-block w-2 h-2 rounded-full" style={{ background: hbColor }} />
            <span className="whitespace-nowrap">{version}</span>
          </button>
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

      {/* About / status modal */}
      {showAbout && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setShowAbout(false)}
        >
          <div className="absolute inset-0 bg-black/40" />
          <div className="absolute inset-0" style={{ background: "var(--overlay)" }} />
          <div
            className="relative bg-white dark:bg-neutral-900 rounded-lg shadow-lg p-6 w-full max-w-lg"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-lg font-semibold">System Status & Version</h2>
              <button
                onClick={() => setShowAbout(false)}
                className="px-2 py-1 rounded-lg border token-border"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full" style={{ background: "var(--signal-buy, #22c55e)" }} />
                <span><b>OK</b> — heartbeat &lt; 15s old</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full" style={{ background: "var(--signal-modify, #3b82f6)" }} />
                <span><b>Stale</b> — heartbeat 15–60s old</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full" style={{ background: "var(--signal-sell, #ef4444)" }} />
                <span><b>Dead</b> — heartbeat missing or &gt; 60s old</span>
              </div>

              <hr className="my-2 border token-border" />

              {/* ⬇️ Inserted: last heartbeat details */}
              {(hbAge != null || hbTs != null) && (
                <div className="text-sm">
                  <div>
                    <span className="muted">Last heartbeat: </span>
                    <span className="font-medium">
                      {hbAge != null ? `${hbAge}s ago` : "—"}
                    </span>
                  </div>
                  {hbTs != null && (
                    <div>
                      <span className="muted">Heartbeat time (local): </span>
                      <span className="font-medium">
                        {new Date(hbTs * 1000).toLocaleString()}
                      </span>
                    </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mt-4">
                <div className="muted">Heartbeat:</div>
                <div className="font-medium">{heartbeat}</div>

                <div className="muted">Version:</div>
                <div className="font-medium">{version}</div>

                <div className="muted">Built at (UTC):</div>
                <div className="font-medium">{builtAt}</div>

                <div className="muted">Python runtime:</div>
                <div className="font-medium">{py}</div>
              </div>
            </div>

            <div className="mt-4 flex justify-end">
              <button
                className="px-3 py-1.5 rounded-lg border token-border"
                onClick={() => setShowAbout(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
