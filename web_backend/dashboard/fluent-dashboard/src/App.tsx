import { Routes, Route, Navigate, Outlet } from "react-router-dom";
import { useState } from "react";
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

  return (
    <div className="min-h-dvh bg-gradient-to-b from-zinc-950 via-zinc-900 to-zinc-950 text-zinc-100">
      {/* Top bar (mobile) */}
      <header className="sticky top-0 z-30 border-b border-white/10 bg-zinc-950/70 backdrop-blur supports-[backdrop-filter]:backdrop-blur">
        <div className="mx-auto max-w-7xl px-3 sm:px-4 lg:px-6 h-14 flex items-center justify-between">
          <button
            className="md:hidden rounded-lg px-3 py-2 bg-white/10 text-white"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            ☰
          </button>
          <div className="font-semibold">Fluent Signal Copier</div>
          <div className="md:hidden" />
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
