"use client";

import { useEffect, useState } from "react";
import { THEME_STORAGE_KEY } from "../lib/theme";

export default function ThemeControls() {
  const [preference, setPreference] = useState("system");

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    let current = document.documentElement.dataset.themePreference || "system";

    function apply(value) {
      current = ["light", "dark"].includes(value) ? value : "system";
      const theme = current === "system" ? (media.matches ? "dark" : "light") : current;
      document.documentElement.dataset.theme = theme;
      document.documentElement.dataset.themePreference = current;
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f5f7fc" : "#0a0e1a");
      setPreference(current);
    }

    const onSystemChange = () => apply(current);
    const onStorage = (event) => {
      if (event.key === THEME_STORAGE_KEY || event.key === null) apply(event.newValue);
    };
    const onSelection = (event) => apply(event.detail);

    apply(current);
    media.addEventListener("change", onSystemChange);
    window.addEventListener("storage", onStorage);
    window.addEventListener("promption-theme-change", onSelection);
    return () => {
      media.removeEventListener("change", onSystemChange);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("promption-theme-change", onSelection);
    };
  }, []);

  function changeTheme(event) {
    const value = event.target.value;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, value);
    } catch {}
    window.dispatchEvent(new CustomEvent("promption-theme-change", { detail: value }));
  }

  return (
    <div className="theme-toolbar">
      <label htmlFor="appearance-theme">Apariencia</label>
      <select id="appearance-theme" className="select theme-select" value={preference} onChange={changeTheme}>
        <option value="system">Sistema</option>
        <option value="light">Claro</option>
        <option value="dark">Oscuro</option>
      </select>
    </div>
  );
}
