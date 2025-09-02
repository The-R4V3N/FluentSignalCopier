export type Metrics = {
    heartbeat: "ok" | "stale" | "dead";
    counts: {
        open: number;
        close: number;
        modify: number;
        modify_tp: number;
        emergency: number;
        open_positions: number;
    };
    state: { running: boolean; paused: boolean; quality: number };
    open_positions: number;
    pnl_30d: number;
    pnl: number;
    pnl30: number;
};

export type Paths = {
    mt5_files_dir: string;
    signals: string;
    heartbeat: string;
    positions: string;
    heartbeat_status: string;
    signals_exists: boolean;
    heartbeat_exists: boolean;
    positions_exists: boolean;
    env_MT5_FILES_DIR: string;
    saved_settings: Record<string, unknown>;
};

// Prefer the page origin; fall back to env if provided.
const ORIGIN = (import.meta as any)?.env?.VITE_API_BASE?.trim() || window.location.origin;
const API = ORIGIN.replace(/\/$/, "");

async function get<T>(path: string): Promise<T> {
    const r = await fetch(`${API}${path}`, {
        method: "GET",
        cache: "no-store",
        headers: { "Accept": "application/json" },
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
    const r = await fetch(`${API}${path}`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
}

export const api = {
    getMetrics: () => get<Metrics>("/api/metrics"),
    getPaths: () => get<Paths>("/api/paths"),
    getSignals: (limit = 200) => get<any[]>(`/api/signals?limit=${limit}`),
    getPositions: () => get<any[]>("/api/positions"),
    getSettings: () => get<any>("/api/settings"),
    saveSettings: (s: any) => post<any>("/api/settings", s),
    start: () => post<any>("/api/start"),
    stop: () => post<any>("/api/stop"),
    pause: (paused: boolean) => post<any>("/api/pause", { paused }),
    setQuality: (threshold: number) => post<any>("/api/set-quality", { threshold }),
    emergencyCloseAll: () => post<any>("/api/emergency-close-all"),
};