import { useEffect } from "react";

export default function SettingsPage() {
    useEffect(() => {
        document.title = "Fluent Signal Copier — Settings";
    }, []);

    return (
        <div className="p-6 space-y-4">
            <h1 className="text-xl font-semibold">Settings</h1>
            <div className="rounded-2xl border border-white/10 p-4 bg-white/5">
                <p className="text-white/70">Settings will live here (API URLs, themes, defaults, etc.).</p>
            </div>
        </div>
    );
}
