export type Metrics = {
    heartbeat: "ok" | "stale" | "dead";
    counts: {
        open: number; close: number; modify: number; modify_tp: number; emergency: number;
        open_positions: number;
    };
    state: { running: boolean; paused: boolean; quality: number };
    open_positions: number;
    pnl_30d: number;
    pnl: number;
    pnl30: number;
    win_rate_30d?: number;
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

export type SignalAction =
    | "OPEN"
    | "CLOSE"
    | "MODIFY"
    | "MODIFY_TP"
    | "EMERGENCY_CLOSE_ALL";

export type OrderType = "MARKET" | "LIMIT" | "STOP";

export interface Signal {
    // common
    action: SignalAction;
    t: number;                 // unix seconds
    id?: string;
    gid?: string;
    source?: string;
    source_id?: string;
    original_event_id?: string;
    confidence?: number;

    // symbol/side
    symbol?: string;
    side?: "BUY" | "SELL";

    // OPEN
    order_type?: OrderType;
    entry?: number | null;     // null for MARKET
    entry_ref?: number | null; // reference only for MARKET
    sl?: number | null;
    tp?: number | null;
    tps?: number[];
    tps_csv?: string;
    be_on_tp?: 0 | 1;

    // NEW: risk for OPEN (1.0 = normal, 0.5 = half, 2.0 = double…)
    risk_percent?: number;

    // MODIFY
    new_sl?: number | null;
    new_tps_csv?: string;

    // MODIFY_TP
    tp_slot?: number;
    tp_to?: number;

    // CLOSE
    oid?: string;

    // optional, may be filled by EA
    lots?: number | null;
    profit?: number | null;
}

export type State = {
    running: boolean;
    paused: boolean;
    quality: number; // 0..100
    heartbeat?: "ok" | "stale" | "dead";
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
    getSignals: (limit = 200) => get<Signal[]>(`/api/signals?limit=${limit}`),
    getPositions: () => get<any[]>("/api/positions"),
    getSettings: () => get<any>("/api/settings"),
    saveSettings: (s: any) => post<any>("/api/settings", s),
    // Controls state's
    getState: () => get<State>("/api/state"),
    start: () => post<any>("/api/start"),
    stop: () => post<any>("/api/stop"),
    pause: (paused: boolean) => post<any>("/api/pause", { paused }),
    setQuality: (threshold: number) => post<any>("/api/set-quality", { threshold }),
    emergencyCloseAll: () => post<any>("/api/emergency-close-all"),
};