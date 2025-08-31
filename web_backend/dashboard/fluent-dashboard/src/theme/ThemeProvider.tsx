import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

type Theme = "light" | "dark";

type ColorPrefs = {
    signalBuy: string;
    signalSell: string;
    signalModify: string;
};

type ThemeState = {
    theme: Theme;
    setTheme: (t: Theme) => void;
    colors: ColorPrefs;
    setColors: (c: Partial<ColorPrefs>) => void;
};

const DEFAULTS: { theme: Theme; colors: ColorPrefs } = {
    theme: "dark",
    colors: {
        signalBuy: "#22c55e",
        signalSell: "#ef4444",
        signalModify: "#3b82f6",
    },
};

const KEY = "fluent-settings-theme";
const ThemeCtx = createContext<ThemeState | null>(null);
export const useThemeSettings = () => {
    const ctx = useContext(ThemeCtx);
    if (!ctx) throw new Error("useThemeSettings must be used inside <ThemeProvider>");
    return ctx;
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [theme, setTheme] = useState<Theme>(() => {
        const raw = localStorage.getItem(KEY);
        return raw ? (JSON.parse(raw).theme as Theme) : DEFAULTS.theme;
    });

    const [colors, setColorsState] = useState<ColorPrefs>(() => {
        const raw = localStorage.getItem(KEY);
        return raw ? (JSON.parse(raw).colors as ColorPrefs) : DEFAULTS.colors;
    });

    // ✅ correct merge impl
    const setColors = (patch: Partial<ColorPrefs>) =>
        setColorsState(prev => ({ ...prev, ...patch }));

    // ✅ persist + apply to <html>
    useEffect(() => {
        localStorage.setItem(KEY, JSON.stringify({ theme, colors }));

        const root = document.documentElement;
        // attribute + class (both, for maximum compatibility)
        root.setAttribute("data-theme", theme);
        root.classList.remove("light", "dark");
        root.classList.add(theme);

        // update configurable signal colors
        root.style.setProperty("--signal-buy", colors.signalBuy);
        root.style.setProperty("--signal-sell", colors.signalSell);
        root.style.setProperty("--signal-modify", colors.signalModify);
    }, [theme, colors]);

    const value = useMemo(() => ({ theme, setTheme, colors, setColors }), [theme, colors]);
    return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
};
