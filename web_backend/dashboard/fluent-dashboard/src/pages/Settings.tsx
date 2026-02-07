// src/pages/Settings.tsx
// Licensed under the Fluent Signal Copier Limited Use License v1.0
// See LICENSE.txt for terms. No warranty; use at your own risk.
// Copyright (c) 2025 R4V3N.

import { useEffect, useMemo, useState } from "react";
import { useThemeSettings } from "../theme/ThemeProvider";
import { api } from "../api";

/* -------------------- Bridge (Telegram/Paths) -------------------- */
type BridgeSettings = {
    api_id: string;
    api_hash: string;
    phone: string;
    mt5_dir: string;
    sources: string[];
};

const EMPTY_BRIDGE: BridgeSettings = {
    api_id: "",
    api_hash: "",
    phone: "",
    mt5_dir: "",
    sources: [],
};

/* -------------------- EA Parameters (full) -------------------- */
type EaSettings = Partial<{
    // FILE CONFIG
    InpDebug: boolean;
    InpSignalFileName: string;
    InpHeartbeatFileName: string;
    InpPositionsFileName: string;

    // BREAK-EVEN
    InpBE_Enable: boolean;
    InpBE_TriggerTP: number;
    InpBE_AutoOnTP1: boolean;
    InpBE_Logging: boolean;
    InpBE_CleanupEveryMin: number;
    InpBE_OffsetPoints: number;

    // SYMBOL
    InpSymbolPrefix: string;
    InpSymbolSuffix: string;
    InpSymbolSuffixVariants: string;

    // TRADING
    InpDefaultLots: number;
    InpRiskPercent: number;
    InpMagic: number;
    InpSlippagePoints: number;
    InpAllowBuys: boolean;
    InpAllowSells: boolean;
    InpCloseConflicts: boolean;

    // HEARTBEAT
    InpEnableHeartbeat: boolean;
    InpHeartbeatTimeout: number;
    InpSnapshotOnlyMagic: boolean;

    // MULTI-POS / CUSTOM LOTS
    InpMaxPositions: number;
    InpSkipBadTPs: boolean;
    InpPositionsToOpen: number;
    InpRiskPerLeg: boolean;
    InpUseCustomLots: boolean;
    InpTP1_Lots: number;
    InpTP2_Lots: number;
    InpTP3_Lots: number;
    InpTP4_Lots: number;
    InpTP5_Lots: number;

    // SAFETY CAPS
    InpMaxLotOverall: number;
    InpMaxLot_Metal: number;
    InpMaxLot_Oil: number;
    InpMaxLot_Index: number;
    InpMaxLot_FX: number;
    InpMaxLot_Crypto: number;
    InpRiskDollarCap: number;

    // SYSTEM & ALERTS
    InpWriteSnapshots: boolean;
    InpSoundAlerts: boolean;
    InpSourceTags: boolean;
    InpAlertOnOpen: boolean;
    InpAlertOnClose: boolean;
    InpAlertOnEmergency: boolean;
    InpAlertOnModify: boolean;

    // HEARTBEAT WARNING
    InpHeartbeatPopupAlerts: boolean;
    InpHeartbeatPrintWarnings: boolean;
    InpHeartbeatWarnInterval: number;

    // TIME MGMT
    InpTimeFilter: boolean;
    InpStartTimeHHMM: string;
    InpEndTimeHHMM: string;
    InpTradeMonday: boolean;
    InpTradeTuesday: boolean;
    InpTradeWednesday: boolean;
    InpTradeThursday: boolean;
    InpTradeFriday: boolean;
    InpTradeSaturday: boolean;
    InpTradeSunday: boolean;
}>;

export default function SettingsPage() {
    const { theme, setTheme, colors, setColors } = useThemeSettings();

    /* ---------- Bridge state ---------- */
    const [bridge, setBridge] = useState<BridgeSettings>(EMPTY_BRIDGE);
    const [bridgeLoaded, setBridgeLoaded] = useState(false);
    const [bridgeSaving, setBridgeSaving] = useState(false);
    const [bridgeSavedOk, setBridgeSavedOk] = useState<null | boolean>(null);

    /* ---------- EA state ---------- */
    const [ea, setEa] = useState<EaSettings | null>(null);
    const [eaSaving, setEaSaving] = useState(false);
    const [eaMsg, setEaMsg] = useState<string | null>(null);

    useEffect(() => { document.title = "Fluent Signal Copier — Settings"; }, []);

    /* ---------- Load both on mount ---------- */
    useEffect(() => {
        (async () => {
            try {
                const j = await api.getSettings();
                setBridge({
                    api_id: j?.api_id ?? "",
                    api_hash: j?.api_hash ?? "",
                    phone: j?.phone ?? "",
                    mt5_dir: j?.mt5_dir ?? "",
                    sources: Array.isArray(j?.sources) ? j.sources : [],
                });
            } catch { /* keep defaults */ }
            finally { setBridgeLoaded(true); }

            try {
                const e = await api.getEaSettings();
                setEa(e ?? {});
            } catch { setEa({}); }
        })();
    }, []);

    /* ---------- Bridge helpers ---------- */
    const setBridgeField = <K extends keyof BridgeSettings>(k: K, v: BridgeSettings[K]) =>
        setBridge(prev => ({ ...prev, [k]: v }));

    const sourcesTextarea = useMemo(() => (bridge.sources ?? []).join("\n"), [bridge.sources]);

    async function onSaveBridge() {
        setBridgeSaving(true);
        setBridgeSavedOk(null);
        try {
            const r = await api.saveSettings(bridge);
            setBridgeSavedOk(!!r?.ok || r === true || (r && typeof r === "object" && !("ok" in r)));
        } catch {
            setBridgeSavedOk(false);
        } finally {
            setBridgeSaving(false);
        }
    }

    async function onAutoDetect() {
        try {
            const r = await fetch("/api/mt5/auto_detect");
            const j = await r.json();
            if (j?.ok && j?.mt5_dir) setBridgeField("mt5_dir", j.mt5_dir);
        } catch {/* ignore */ }
    }

    /* ---------- EA helpers ---------- */
    const setEaField = <K extends keyof EaSettings>(k: K, v: EaSettings[K]) =>
        setEa(prev => ({ ...(prev || {}), [k]: v }));

    const setEaBool = (k: keyof EaSettings) =>
        (val: boolean) => setEaField(k, val as any);

    const saveEA = async () => {
        if (!ea) return;
        setEaSaving(true);
        setEaMsg(null);
        try {
            const r = await api.saveEaSettings(ea);
            setEaMsg(r?.ok ? `✅ Saved to ${r?.path ?? "MQL5\\Files\\Fluent_ea_settings.json"}` : `❌ Save failed`);
        } catch (e: any) {
            setEaMsg(`❌ Save failed: ${e?.message ?? String(e)}`);
        } finally {
            setEaSaving(false);
        }
    };

    return (
        <div className="p-6 space-y-6">
            <h1 className="text-xl font-semibold">Settings</h1>

            {/* Connections */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">Connections</h3>
                {!bridgeLoaded ? (
                    <div className="muted">Loading…</div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <LabeledInput
                            label="Telegram API ID"
                            value={bridge.api_id}
                            onChange={v => setBridgeField("api_id", v)}
                            placeholder="e.g. 26404433"
                            inputMode="numeric"
                        />
                        <LabeledInput
                            label="Telegram API Hash"
                            value={bridge.api_hash}
                            onChange={v => setBridgeField("api_hash", v)}
                            placeholder="Paste your API hash"
                        />
                        <LabeledInput
                            label="Phone"
                            value={bridge.phone}
                            onChange={v => setBridgeField("phone", v)}
                            placeholder="+1..."
                        />
                    </div>
                )}
            </section>

            {/* MT5 Files directory */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">MT5 • MQL5\\Files directory</h3>
                <div className="flex items-center gap-3">
                    <input
                        className="flex-1 rounded-lg border token-border bg-transparent px-3 py-2"
                        value={bridge.mt5_dir}
                        onChange={e => setBridgeField("mt5_dir", e.target.value)}
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
                        setBridgeField(
                            "sources",
                            e.target.value
                                .split(/\r?\n/)
                                .map(s => s.trim())
                                .filter(Boolean)
                        )
                    }
                    placeholder={`Saved Messages\n@meta5tradersignals\n@channel_one\n@channel_two`}
                />
                <p className="muted text-sm mt-2">
                    One per line. Use <code>@username</code> for public channels.
                </p>
            </section>

            {/* Appearance */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">Appearance</h3>

                <div className="flex items-center justify-between mb-4">
                    <div>
                        <div className="font-medium">Theme</div>
                        <div className="text-sm muted">Light or Dark</div>
                    </div>
                    <div className="inline-flex gap-2">
                        <button
                            onClick={() => setTheme("light")}
                            className={`px-3 py-1 rounded-full text-sm border ${theme === "light" ? "bg-white text-black" : "border-white/20"}`}
                        >
                            Light
                        </button>
                        <button
                            onClick={() => setTheme("dark")}
                            className={`px-3 py-1 rounded-full text-sm border ${theme === "dark" ? "bg-black text-white border-white/40" : "border-white/20"}`}
                        >
                            Dark
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                    <ColorPicker label="Recent Signal — BUY" value={colors.signalBuy} onChange={v => setColors({ signalBuy: v })} />
                    <ColorPicker label="Recent Signal — SELL" value={colors.signalSell} onChange={v => setColors({ signalSell: v })} />
                    <ColorPicker label="Recent Signal — MODIFY" value={colors.signalModify} onChange={v => setColors({ signalModify: v })} />
                </div>
            </section>

            {/* EA Parameters */}
            <section className="card p-4">
                <h3 className="text-lg font-semibold mb-3">EA Parameters</h3>

                {!ea ? (
                    <div className="muted">Loading EA parameters…</div>
                ) : (
                    <div className="space-y-6">

                        <SubSection title="General">
                            <CheckboxRow label="Debug logs (InpDebug)" checked={!!ea.InpDebug} onChange={setEaBool("InpDebug")} />
                            <LabeledInput label="Signal file (InpSignalFileName)" value={ea.InpSignalFileName || "Fluent_signals.jsonl"} onChange={v => setEaField("InpSignalFileName", v)} />
                            <LabeledInput label="Heartbeat file (InpHeartbeatFileName)" value={ea.InpHeartbeatFileName || "Fluent_heartbeat.txt"} onChange={v => setEaField("InpHeartbeatFileName", v)} />
                            <LabeledInput label="Positions file (InpPositionsFileName)" value={ea.InpPositionsFileName || "Fluent_positions.json"} onChange={v => setEaField("InpPositionsFileName", v)} />
                        </SubSection>

                        <SubSection title="Time Filter">
                            <CheckboxRow label="Enable time filter (InpTimeFilter)" checked={!!ea.InpTimeFilter} onChange={setEaBool("InpTimeFilter")} />
                            <LabeledInput label="Start (HH:MM) (InpStartTimeHHMM)" value={ea.InpStartTimeHHMM || "01:00"} onChange={v => setEaField("InpStartTimeHHMM", v)} />
                            <LabeledInput label="End (HH:MM) (InpEndTimeHHMM)" value={ea.InpEndTimeHHMM || "23:59"} onChange={v => setEaField("InpEndTimeHHMM", v)} />
                            <CheckboxRow label="Mon" checked={!!ea.InpTradeMonday} onChange={setEaBool("InpTradeMonday")} />
                            <CheckboxRow label="Tue" checked={!!ea.InpTradeTuesday} onChange={setEaBool("InpTradeTuesday")} />
                            <CheckboxRow label="Wed" checked={!!ea.InpTradeWednesday} onChange={setEaBool("InpTradeWednesday")} />
                            <CheckboxRow label="Thu" checked={!!ea.InpTradeThursday} onChange={setEaBool("InpTradeThursday")} />
                            <CheckboxRow label="Fri" checked={!!ea.InpTradeFriday} onChange={setEaBool("InpTradeFriday")} />
                            <CheckboxRow label="Sat" checked={!!ea.InpTradeSaturday} onChange={setEaBool("InpTradeSaturday")} />
                            <CheckboxRow label="Sun" checked={!!ea.InpTradeSunday} onChange={setEaBool("InpTradeSunday")} />
                        </SubSection>

                        <SubSection title="Risk & Caps">
                            <LabeledNumber label="Default Lots (InpDefaultLots)" value={ea.InpDefaultLots ?? 0.01} onChange={v => setEaField("InpDefaultLots", v)} step={0.01} />
                            <LabeledNumber label="Risk % (InpRiskPercent)" value={ea.InpRiskPercent ?? 1.0} onChange={v => setEaField("InpRiskPercent", v)} step={0.1} />
                            <LabeledNumber label="Max Lot Overall (InpMaxLotOverall)" value={ea.InpMaxLotOverall ?? 0.05} onChange={v => setEaField("InpMaxLotOverall", v)} step={0.01} />
                            <LabeledNumber label="Max Lot Metals (InpMaxLot_Metal)" value={ea.InpMaxLot_Metal ?? 0.05} onChange={v => setEaField("InpMaxLot_Metal", v)} step={0.01} />
                            <LabeledNumber label="Max Lot Oil (InpMaxLot_Oil)" value={ea.InpMaxLot_Oil ?? 0.05} onChange={v => setEaField("InpMaxLot_Oil", v)} step={0.01} />
                            <LabeledNumber label="Max Lot Index (InpMaxLot_Index)" value={ea.InpMaxLot_Index ?? 0.05} onChange={v => setEaField("InpMaxLot_Index", v)} step={0.01} />
                            <LabeledNumber label="Max Lot FX (InpMaxLot_FX)" value={ea.InpMaxLot_FX ?? 0.05} onChange={v => setEaField("InpMaxLot_FX", v)} step={0.01} />
                            <LabeledNumber label="Max Lot Crypto (InpMaxLot_Crypto)" value={ea.InpMaxLot_Crypto ?? 0.05} onChange={v => setEaField("InpMaxLot_Crypto", v)} step={0.01} />
                            <LabeledNumber label="Risk $ Cap (InpRiskDollarCap)" value={ea.InpRiskDollarCap ?? 15} onChange={v => setEaField("InpRiskDollarCap", v)} step={1} />
                        </SubSection>

                        <SubSection title="Custom Lots per TP">
                            <CheckboxRow label="Enable custom lots (InpUseCustomLots)" checked={!!ea.InpUseCustomLots} onChange={setEaBool("InpUseCustomLots")} />
                            <LabeledNumber label="TP1 Lots (InpTP1_Lots)" value={ea.InpTP1_Lots ?? 0.02} onChange={v => setEaField("InpTP1_Lots", v)} step={0.01} />
                            <LabeledNumber label="TP2 Lots (InpTP2_Lots)" value={ea.InpTP2_Lots ?? 0.01} onChange={v => setEaField("InpTP2_Lots", v)} step={0.01} />
                            <LabeledNumber label="TP3 Lots (InpTP3_Lots)" value={ea.InpTP3_Lots ?? 0.01} onChange={v => setEaField("InpTP3_Lots", v)} step={0.01} />
                            <LabeledNumber label="TP4 Lots (InpTP4_Lots)" value={ea.InpTP4_Lots ?? 0.01} onChange={v => setEaField("InpTP4_Lots", v)} step={0.01} />
                            <LabeledNumber label="TP5+ Lots (InpTP5_Lots)" value={ea.InpTP5_Lots ?? 0.01} onChange={v => setEaField("InpTP5_Lots", v)} step={0.01} />
                        </SubSection>

                        <SubSection title="Trading / Misc">
                            <LabeledNumber label="Magic (InpMagic)" value={ea.InpMagic ?? 20250810} onChange={v => setEaField("InpMagic", v)} step={1} />
                            <LabeledNumber label="Slippage points (InpSlippagePoints)" value={ea.InpSlippagePoints ?? 50} onChange={v => setEaField("InpSlippagePoints", v)} step={1} />
                            <CheckboxRow label="Allow Buys (InpAllowBuys)" checked={!!ea.InpAllowBuys} onChange={setEaBool("InpAllowBuys")} />
                            <CheckboxRow label="Allow Sells (InpAllowSells)" checked={!!ea.InpAllowSells} onChange={setEaBool("InpAllowSells")} />
                            <CheckboxRow label="Close conflicts (InpCloseConflicts)" checked={!!ea.InpCloseConflicts} onChange={setEaBool("InpCloseConflicts")} />
                            <CheckboxRow label="Write snapshots (InpWriteSnapshots)" checked={!!ea.InpWriteSnapshots} onChange={setEaBool("InpWriteSnapshots")} />
                            <CheckboxRow label="Sound alerts (InpSoundAlerts)" checked={!!ea.InpSoundAlerts} onChange={setEaBool("InpSoundAlerts")} />
                            <CheckboxRow label="Source tags (InpSourceTags)" checked={!!ea.InpSourceTags} onChange={setEaBool("InpSourceTags")} />
                        </SubSection>

                        <SubSection title="Heartbeat">
                            <CheckboxRow label="Enable (InpEnableHeartbeat)" checked={!!ea.InpEnableHeartbeat} onChange={setEaBool("InpEnableHeartbeat")} />
                            <LabeledNumber label="Timeout sec (InpHeartbeatTimeout)" value={ea.InpHeartbeatTimeout ?? 60} onChange={v => setEaField("InpHeartbeatTimeout", v)} step={1} />
                            <CheckboxRow label="Snapshot only EA magic (InpSnapshotOnlyMagic)" checked={!!ea.InpSnapshotOnlyMagic} onChange={setEaBool("InpSnapshotOnlyMagic")} />
                            <CheckboxRow label="Popup alerts (InpHeartbeatPopupAlerts)" checked={!!ea.InpHeartbeatPopupAlerts} onChange={setEaBool("InpHeartbeatPopupAlerts")} />
                            <CheckboxRow label="Print warnings (InpHeartbeatPrintWarnings)" checked={!!ea.InpHeartbeatPrintWarnings} onChange={setEaBool("InpHeartbeatPrintWarnings")} />
                            <LabeledNumber label="Warn interval sec (InpHeartbeatWarnInterval)" value={ea.InpHeartbeatWarnInterval ?? 300} onChange={v => setEaField("InpHeartbeatWarnInterval", v)} step={1} />
                        </SubSection>

                        <SubSection title="Break-Even">
                            <CheckboxRow label="Enable BE (InpBE_Enable)" checked={!!ea.InpBE_Enable} onChange={setEaBool("InpBE_Enable")} />
                            <LabeledNumber label="Trigger TP (InpBE_TriggerTP)" value={ea.InpBE_TriggerTP ?? 1} onChange={v => setEaField("InpBE_TriggerTP", v)} step={1} />
                            <CheckboxRow label="Auto on TP1 (InpBE_AutoOnTP1)" checked={!!ea.InpBE_AutoOnTP1} onChange={setEaBool("InpBE_AutoOnTP1")} />
                            <CheckboxRow label="Verbose logs (InpBE_Logging)" checked={!!ea.InpBE_Logging} onChange={setEaBool("InpBE_Logging")} />
                            <LabeledNumber label="Cleanup every min (InpBE_CleanupEveryMin)" value={ea.InpBE_CleanupEveryMin ?? 60} onChange={v => setEaField("InpBE_CleanupEveryMin", v)} step={1} />
                            <LabeledNumber label="Offset points (InpBE_OffsetPoints)" value={ea.InpBE_OffsetPoints ?? 0} onChange={v => setEaField("InpBE_OffsetPoints", v)} step={1} />
                        </SubSection>

                        <SubSection title="Symbol Mapping">
                            <LabeledInput label="Prefix (InpSymbolPrefix)" value={ea.InpSymbolPrefix || ""} onChange={v => setEaField("InpSymbolPrefix", v)} />
                            <LabeledInput label="Suffix (InpSymbolSuffix)" value={ea.InpSymbolSuffix || ""} onChange={v => setEaField("InpSymbolSuffix", v)} />
                            <LabeledInput label="Suffix variants CSV (InpSymbolSuffixVariants)" value={ea.InpSymbolSuffixVariants || ""} onChange={v => setEaField("InpSymbolSuffixVariants", v)} />
                        </SubSection>

                        <div className="flex items-center gap-3">
                            <button
                                onClick={saveEA}
                                disabled={eaSaving}
                                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50"
                            >
                                {eaSaving ? "Saving…" : "Save EA Parameters"}
                            </button>
                            {eaMsg && <span className="text-sm opacity-80">{eaMsg}</span>}
                        </div>
                    </div>
                )}
            </section>

            {/* Save Bridge button */}
            <div className="flex items-center gap-3">
                <button
                    onClick={onSaveBridge}
                    disabled={!bridgeLoaded || bridgeSaving}
                    className="px-4 py-2 rounded-lg border token-border"
                >
                    {bridgeSaving ? "Saving…" : "Save settings"}
                </button>
                {bridgeSavedOk === true && <span className="text-green-600">Saved</span>}
                {bridgeSavedOk === false && <span className="text-red-600">Failed to save</span>}
            </div>
        </div>
    );
}

/* ---------------- helpers / UI atoms ---------------- */

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div className="rounded-lg border token-border p-4">
            <h4 className="font-semibold mb-2">{title}</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{children}</div>
        </div>
    );
}

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
                value={value ?? ""}
                onChange={e => onChange(e.target.value)}
                placeholder={placeholder}
                inputMode={inputMode}
                className="w-full rounded-lg border token-border bg-transparent px-3 py-2"
            />
        </label>
    );
}

function LabeledNumber({
    label, value, onChange, step = 0.01,
}: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
    return (
        <label className="block">
            <div className="text-sm font-medium mb-1">{label}</div>
            <input
                type="number"
                step={step}
                value={Number.isFinite(value as number) ? (value as number) : 0}
                onChange={e => onChange(Number(e.target.value))}
                className="w-full rounded-lg border token-border bg-transparent px-3 py-2"
            />
        </label>
    );
}

function CheckboxRow({ label, checked, onChange }: {
    label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
    return (
        <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
            <span>{label}</span>
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
