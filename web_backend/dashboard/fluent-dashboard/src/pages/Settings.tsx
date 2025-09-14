// src/pages/Settings.tsx

// Licensed under the Fluent Signal Copier Limited Use License v1.0
// See LICENSE.txt for terms. No warranty; use at your own risk.
// Copyright (c) 2025 R4V3N. All rights reserved.

import { useEffect, useMemo, useState } from "react";
import { useThemeSettings } from "../theme/ThemeProvider";

type BridgeSettings = {
    api_id: string;
    api_hash: string;
    phone: string;
    mt5_dir: string;
    sources: string[]; // one per line in the UI
};

const EMPTY: BridgeSettings = {
    api_id: "",
    api_hash: "",
    phone: "",
    mt5_dir: "",
    sources: [],
};

export default function SettingsPage() {
    const { theme, setTheme, colors, setColors } = useThemeSettings();

    // ----- server-backed settings state -----
    const [form, setForm] = useState<BridgeSettings>(EMPTY);
    const [loaded, setLoaded] = useState(false);
    const [saving, setSaving] = useState(false);
    const [savedOk, setSavedOk] = useState<null | boolean>(null);

    useEffect(() => {
        document.title = "Fluent Signal Copier — Settings";
    }, []);

    // Load settings from backend
    useEffect(() => {
        (async () => {
            try {
                const r = await fetch("/api/settings");
                const j = await r.json();
                setForm({
                    api_id: j.api_id ?? "",
                    api_hash: j.api_hash ?? "",
                    phone: j.phone ?? "",
                    mt5_dir: j.mt5_dir ?? "",
                    sources: Array.isArray(j.sources) ? j.sources : [],
                });
            } catch {
                // ignore; keep EMPTY
            } finally {
                setLoaded(true);
            }
        })();
    }, []);

    const setField = <K extends keyof BridgeSettings>(k: K, v: BridgeSettings[K]) =>
        setForm(prev => ({ ...prev, [k]: v }));

    const sourcesTextarea = useMemo(() => (form.sources ?? []).join("\n"), [form.sources]);

    async function onSave() {
        setSaving(true);
        setSavedOk(null);
        try {
            const r = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(form),
            });
            setSavedOk(r.ok);
        } catch {
            setSavedOk(false);
        } finally {
            setSaving(false);
        }
    }

    async function onAutoDetect() {
        try {
            const r = await fetch("/api/mt5/auto_detect");
            const j = await r.json();
            if (j.ok && j.mt5_dir) setField("mt5_dir", j.mt5_dir);
        } catch {
            /* ignore */
        }
    }

    return (
        <div className="p-6 space-y-6">
            <h1 className="text-xl font-semibold">Settings</h1>

            {/* Connections */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">Connections</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <LabeledInput
                        label="Telegram API ID"
                        value={form.api_id}
                        onChange={v => setField("api_id", v)}
                        placeholder="e.g. 26404433"
                        inputMode="numeric"
                    />
                    <LabeledInput
                        label="Telegram API Hash"
                        value={form.api_hash}
                        onChange={v => setField("api_hash", v)}
                        placeholder="Paste your API hash"
                    />
                    <LabeledInput
                        label="Phone"
                        value={form.phone}
                        onChange={v => setField("phone", v)}
                        placeholder="+1..."
                    />
                </div>
            </section>

            {/* MT5 Files directory */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">MT5 • MQL5\\Files directory</h3>
                <div className="flex items-center gap-3">
                    <input
                        className="flex-1 rounded-lg border token-border bg-transparent px-3 py-2"
                        value={form.mt5_dir}
                        onChange={e => setField("mt5_dir", e.target.value)}
                        placeholder="C:\\Users\\...\\MQL5\\Files"
                    />
                    <button onClick={onAutoDetect} className="px-3 py-2 rounded-lg border token-border">
                        Auto-detect
                    </button>
                </div>
            </section>

            {/* Sources */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">Sources (Telegram chats to watch)</h3>
                <textarea
                    className="w-full min-h-[140px] rounded-lg border token-border bg-transparent p-3"
                    value={sourcesTextarea}
                    onChange={e =>
                        setField(
                            "sources",
                            e.target.value
                                .split(/\r?\n/)
                                .map(s => s.trim())
                                .filter(Boolean)
                        )
                    }
                    placeholder={`Saved Messages\n@meta5tradersignals\n@channel_one\n@channel_two`}
                />
                <p className="muted text-sm mt-2">One per line. Use <code>@username</code> for public channels.</p>
            </section>

            {/* Appearance */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">Appearance</h3>

                {/* Theme */}
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <div className="font-medium">Theme</div>
                        <div className="text-sm muted">Light or Dark</div>
                    </div>
                    <div className="inline-flex gap-2">
                        <button
                            onClick={() => setTheme("light")}
                            className={`px-3 py-1 rounded-full text-sm border ${theme === "light" ? "bg-white text-black" : "border-white/20"
                                }`}
                        >
                            Light
                        </button>
                        <button
                            onClick={() => setTheme("dark")}
                            className={`px-3 py-1 rounded-full text-sm border ${theme === "dark" ? "bg-black text-white border-white/40" : "border-white/20"
                                }`}
                        >
                            Dark
                        </button>
                    </div>
                </div>

                {/* Color pickers */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                    <ColorPicker
                        label="Recent Signal — BUY"
                        value={colors.signalBuy}
                        onChange={v => setColors({ signalBuy: v })}
                    />
                    <ColorPicker
                        label="Recent Signal — SELL"
                        value={colors.signalSell}
                        onChange={v => setColors({ signalSell: v })}
                    />
                    <ColorPicker
                        label="Recent Signal — MODIFY"
                        value={colors.signalModify}
                        onChange={v => setColors({ signalModify: v })}
                    />
                </div>
            </section>

            {/* Save */}
            <div className="flex items-center gap-3">
                <button
                    onClick={onSave}
                    disabled={!loaded || saving}
                    className="px-4 py-2 rounded-lg border token-border"
                >
                    {saving ? "Saving…" : "Save settings"}
                </button>
                {savedOk === true && <span className="text-green-600">Saved</span>}
                {savedOk === false && <span className="text-red-600">Failed to save</span>}
            </div>
        </div>
    );
}

/* ---- helpers ---- */

function LabeledInput(props: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
    inputMode?: "text" | "numeric";
}) {
    const { label, value, onChange, placeholder, inputMode = "text" } = props;
    return (
        <label className="block">
            <div className="text-sm font-medium mb-1">{label}</div>
            <input
                value={value}
                onChange={e => onChange(e.target.value)}
                placeholder={placeholder}
                inputMode={inputMode}
                className="w-full rounded-lg border token-border bg-transparent px-3 py-2"
            />
        </label>
    );
}

function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div className="card p-3">
            <div className="text-sm font-medium mb-1">{label}</div>
            <div className="muted text-xs mb-2">Pick a color</div>
            <input
                type="color"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                className="h-10 w-14 cursor-pointer rounded border token-border bg-transparent"
                aria-label={label}
            />
        </div>
    );
}
