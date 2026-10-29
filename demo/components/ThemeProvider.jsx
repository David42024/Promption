"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

const ThemeContext = createContext(null);
const STORAGE_KEY = "promption-shop-theme";
const choices = new Set(["light", "dark", "system"]);

export default function ThemeProvider({ children }) {
  const [preference, setPreference] = useState("system");
  const current = useRef("system");

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = value => {
      const next = choices.has(value) ? value : "system";
      current.current = next;
      setPreference(next);
      document.documentElement.dataset.theme = next === "system" ? (media.matches ? "dark" : "light") : next;
    };
    const read = () => {
      try { apply(localStorage.getItem(STORAGE_KEY)); }
      catch { apply("system"); }
    };
    const onStorage = event => { if (event.key === STORAGE_KEY || event.key === null) read(); };
    const onSystem = () => { if (current.current === "system") apply("system"); };
    read();
    media.addEventListener("change", onSystem);
    window.addEventListener("storage", onStorage);
    return () => {
      media.removeEventListener("change", onSystem);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  function change(value) {
    if (!choices.has(value)) return;
    current.current = value;
    setPreference(value);
    document.documentElement.dataset.theme = value === "system"
      ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : value;
    try { localStorage.setItem(STORAGE_KEY, value); } catch {}
  }

  return <ThemeContext.Provider value={{ preference, change }}>{children}</ThemeContext.Provider>;
}

export function ThemeSwitcher() {
  const theme = useContext(ThemeContext);
  if (!theme) return null;
  return (
    <label className="theme-switcher">
      <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
      </svg>
      <span className="sr-only">Tema de la interfaz</span>
      <select aria-label="Tema de la interfaz" value={theme.preference} onChange={event => theme.change(event.target.value)}>
        <option value="system">Sistema</option>
        <option value="light">Claro</option>
        <option value="dark">Oscuro</option>
      </select>
    </label>
  );
}
