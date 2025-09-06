import { useEffect, useRef } from "react";

function makeWsUrl(): string {
    // 1) Full URL override wins
    const full = (import.meta as any).env?.VITE_WS_URL as string | undefined;
    if (full) return full;

    // 2) Host/path overrides (useful behind proxies or when UI runs on 5173)
    const host = (import.meta as any).env?.VITE_WS_HOST as string | undefined; // e.g. "100.75.198.6:8000"
    const path = (import.meta as any).env?.VITE_WS_PATH as string | undefined; // e.g. "/ws"

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const h = host || window.location.host;
    const p = path || "/ws";
    return `${proto}://${h}${p}`;
}

export function useWebSocketFeed(onMessage: (ev: any) => void) {
    const wsRef = useRef<WebSocket | null>(null);
    const retryRef = useRef(0);
    const timerRef = useRef<number | null>(null);
    const onMsgRef = useRef(onMessage);
    useEffect(() => { onMsgRef.current = onMessage; }, [onMessage]);

    useEffect(() => {
        let cancelled = false;

        const connect = () => {
            const url = makeWsUrl();
            let ws: WebSocket | null = null;
            try {
                ws = new WebSocket(url);
                wsRef.current = ws;
            } catch {
                scheduleReconnect();
                return;
            }

            ws.onopen = () => {
                retryRef.current = 0; // reset backoff
            };

            ws.onmessage = (e) => {
                const data = (() => { try { return JSON.parse(e.data); } catch { return e.data; } })();
                onMsgRef.current?.(data);
            };

            ws.onerror = () => {
                // let onclose handle reconnect
            };

            ws.onclose = () => {
                if (cancelled) return;
                scheduleReconnect();
            };
        };

        const scheduleReconnect = () => {
            const delay = Math.min(8000, 500 * 2 ** retryRef.current++);
            if (timerRef.current) window.clearTimeout(timerRef.current);
            timerRef.current = window.setTimeout(connect, delay);
        };

        connect();

        return () => {
            cancelled = true;
            if (timerRef.current) window.clearTimeout(timerRef.current);
            try { wsRef.current?.close(); } catch { }
            wsRef.current = null;
        };
    }, []);
}