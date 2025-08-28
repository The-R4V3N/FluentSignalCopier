const API = import.meta.env.VITE_API_URL as string;

export async function getHeartbeat() {
    const r = await fetch(`${API}/api/heartbeat`);
    return r.json();
}

export async function getRecentEvents(limit = 200) {
    const r = await fetch(`${API}/api/events/recent?limit=${limit}`);
    return r.json();
}

export function streamEvents(onMessage: (obj: any) => void) {
    const src = new EventSource(`${API}/api/events/stream`);
    src.onmessage = (e) => {
        try {
            const obj = JSON.parse(e.data);
            onMessage(obj);
        } catch { }
    };
    return () => src.close();
}

export async function emergencyClose() {
    const r = await fetch(`${API}/api/actions/emergency_close`, { method: "POST" });
    return r.json();
}