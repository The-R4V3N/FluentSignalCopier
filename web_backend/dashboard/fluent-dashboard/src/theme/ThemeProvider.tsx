// src/theme/ThemeProvider.tsx
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

type Theme = "light" | "dark";

type Colors = {
    signalBuy: string;
    signalSell: string;
    signalModify: string;
    signalModifyTp: string;
    signalClose: string;
    signalEmergency: string;
    signalNeutral: string; // rgba allowed
};

type ThemeCtxValue = {
    theme: Theme;
    setTheme: (t: Theme) => void;
    colors: Colors;
    setColors: (partial: Partial<Colors>) => void;
};

const ThemeCtx = createContext<ThemeCtxValue | null>(null);

// helpers
const LS_THEME_KEY = "fsc.theme";
const LS_COLORS_KEY = "fsc.colors";

function readCssVar(name: string, fallback: string): string {
    try {
        const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    } catch {
        return fallback;
    }
}

function applyCssVars(colors: Partial<Colors>) {
    const root = document.documentElement;
    for (const [k, v] of Object.entries(colors)) {
        if (v == null) continue;
        const cssName = `--${k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase())}` // signalBuy -> --signal-buy
            .replace(/^--signal-/, "--signal-"); // keep prefix
        root.style.setProperty(cssName, v);
    }
}

export const ThemeProvider: React.FC<{ children: React.ReactNode; defaultTheme?: Theme }> = ({
    children,
    defaultTheme = "dark",
}) => {
    // initial theme (localStorage -> OS preference -> default)
    const initialTheme: Theme = useMemo(() => {
        const saved = (localStorage.getItem(LS_THEME_KEY) as Theme | null) || null;
        if (saved === "light" || saved === "dark") return saved;
        const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)").matches;
        return prefersLight ? ("light" as Theme) : defaultTheme;
    }, [defaultTheme]);

    const [theme, setThemeState] = useState<Theme>(initialTheme);

    // colors: read from localStorage if present, otherwise from current CSS variables
    const [colors, setColorsState] = useState<Colors>(() => {
        const saved = localStorage.getItem(LS_COLORS_KEY);
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                return {
                    signalBuy: parsed.signalBuy ?? "#22c55e",
                    signalSell: parsed.signalSell ?? "#ef4444",
                    signalModify: parsed.signalModify ?? "#3b82f6",
                    signalModifyTp: parsed.signalModifyTp ?? "#9333ea",
                    signalClose: parsed.signalClose ?? "#ef4444",
                    signalEmergency: parsed.signalEmergency ?? "#dc267f",
                    signalNeutral: parsed.signalNeutral ?? "rgba(255,255,255,0.8)",
                };
            } catch {
                /* fall through */
            }
        }
        // pull current values from CSS (backed by your index.css defaults)
        return {
            signalBuy: readCssVar("--signal-buy", "#22c55e"),
            signalSell: readCssVar("--signal-sell", "#ef4444"),
            signalModify: readCssVar("--signal-modify", "#3b82f6"),
            signalModifyTp: readCssVar("--signal-modify-tp", "#9333ea"),
            signalClose: readCssVar("--signal-close", "#ef4444"),
            signalEmergency: readCssVar("--signal-emergency", "#dc267f"),
            signalNeutral: readCssVar("--signal-neutral", "rgba(255,255,255,0.8)"),
        };
    });

    // apply theme to <html> and persist
    useEffect(() => {
        const root = document.documentElement;
        root.setAttribute("data-theme", theme);
        root.classList.toggle("dark", theme === "dark");
        localStorage.setItem(LS_THEME_KEY, theme);

        // hint the UA for form controls
        let meta = document.querySelector('meta[name="color-scheme"]') as HTMLMetaElement | null;
        if (!meta) {
            meta = document.createElement("meta");
            meta.name = "color-scheme";
            document.head.appendChild(meta);
        }
        meta.content = theme === "dark" ? "dark light" : "light dark";
    }, [theme]);

    // ensure CSS variables reflect current colors (initial mount)
    useEffect(() => {
        applyCssVars(colors);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // public setters
    function setTheme(t: Theme) {
        setThemeState(t);
    }

    function setColors(partial: Partial<Colors>) {
        setColorsState((prev) => {
            const next = { ...prev, ...partial };
            applyCssVars(partial);
            localStorage.setItem(LS_COLORS_KEY, JSON.stringify(next));
            return next;
        });
    }

    const ctx: ThemeCtxValue = { theme, setTheme, colors, setColors };

    return <ThemeCtx.Provider value={ctx}>{children}</ThemeCtx.Provider>;
};

// primary hook
export function useTheme() {
    const ctx = useContext(ThemeCtx);
    if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
    return ctx;
}

// ✅ compatibility alias for existing code (Settings.tsx expects this)
export { useTheme as useThemeSettings };
