import { useEffect, useRef } from "react";

function makeWsUrl(): string {
    // 1) Allow explicit override
    const fromEnv = import.meta.env.VITE_WS_URL as string | undefined;
    if (fromEnv) return fromEnv;

    // 2) Default to same-origin (works with Vite proxy in dev, and with a unified backend in prod)
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}/ws`;
}

export function useWebSocketFeed(onMessage: (ev: any) => void) {
    const wsRef = useRef<WebSocket | null>(null);
    const retryRef = useRef(0);
    const timerRef = useRef<number | null>(null);

    useEffect(() => {
        let cancelled = false;

        const connect = () => {
            const url = makeWsUrl();
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                retryRef.current = 0; // reset backoff
            };

            ws.onmessage = (e) => {
                try {
                    onMessage(JSON.parse(e.data));
                } catch {
                    onMessage(e.data);
                }
            };

            ws.onerror = () => {
                // force close → onclose will schedule reconnect
                try { ws.close(); } catch { }
            };

            ws.onclose = () => {
                if (cancelled) return;
                // exponential backoff up to 8s
                const delay = Math.min(8000, 500 * 2 ** retryRef.current++);
                timerRef.current = window.setTimeout(connect, delay);
            };
        };

        connect();

        return () => {
            cancelled = true;
            if (timerRef.current) window.clearTimeout(timerRef.current);
            wsRef.current?.close();
            wsRef.current = null;
        };
    }, [onMessage]);
}