// ===================================================================
// Persistencia simple para el estado del filtro (ON / OFF)
// -------------------------------------------------------------------
// Estado se guarda en un archivo JSON plano bajo demo/data/.
// No es una DB real, es suficiente para la demo y para alternar
// rápidamente el filtro desde el panel de administración.
// ===================================================================

import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const DATA_DIR = join(__dirname, "..", "data");
const STATE_FILE = join(DATA_DIR, "filter-state.json");

const DEFAULT_STATE = Object.freeze({
  filterEnabled: true,          // si false: NO pasamos por filter API de entrada ni output-guard
  outputGuardEnabled: true,     // se puede desactivar independientemente
  updatedAt: new Date().toISOString(),
  updatedBy: null,
  history: [],                  // últimas 20 conmutaciones (para mostrar en admin)
});

function _ensureFile() {
  try {
    if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
    if (!existsSync(STATE_FILE)) {
      writeFileSync(STATE_FILE, JSON.stringify(DEFAULT_STATE, null, 2), "utf8");
    }
  } catch (e) {
    // En entornos sin FS (Vercel edge) fallback a memoria.
    return false;
  }
  return true;
}

let _memoryState = { ...DEFAULT_STATE };

function _readRaw() {
  const ok = _ensureFile();
  if (!ok) return { ..._memoryState };
  try {
    const raw = readFileSync(STATE_FILE, "utf8");
    return JSON.parse(raw);
  } catch {
    return { ...DEFAULT_STATE };
  }
}

function _writeRaw(state) {
  const ok = _ensureFile();
  if (!ok) {
    _memoryState = { ...state };
    return true;
  }
  try {
    writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), "utf8");
    return true;
  } catch {
    return false;
  }
}

export function getFilterState() {
  const s = _readRaw();
  return {
    filterEnabled: Boolean(s.filterEnabled ?? true),
    outputGuardEnabled: Boolean(s.outputGuardEnabled ?? true),
    updatedAt: s.updatedAt || null,
    updatedBy: s.updatedBy || null,
    history: Array.isArray(s.history) ? s.history.slice(0, 20) : [],
  };
}

export function setFilterEnabled(enabled, updatedBy = "admin") {
  const prev = _readRaw();
  const next = {
    filterEnabled: Boolean(enabled),
    outputGuardEnabled: Boolean(prev.outputGuardEnabled ?? enabled),
    updatedAt: new Date().toISOString(),
    updatedBy,
    history: [
      {
        action: enabled ? "filter:ON" : "filter:OFF",
        at: new Date().toISOString(),
        by: updatedBy,
      },
      ...(Array.isArray(prev.history) ? prev.history : []),
    ].slice(0, 20),
  };
  _writeRaw(next);
  return getFilterState();
}

export function setOutputGuardEnabled(enabled, updatedBy = "admin") {
  const prev = _readRaw();
  const next = {
    filterEnabled: Boolean(prev.filterEnabled ?? true),
    outputGuardEnabled: Boolean(enabled),
    updatedAt: new Date().toISOString(),
    updatedBy,
    history: [
      {
        action: enabled ? "output-guard:ON" : "output-guard:OFF",
        at: new Date().toISOString(),
        by: updatedBy,
      },
      ...(Array.isArray(prev.history) ? prev.history : []),
    ].slice(0, 20),
  };
  _writeRaw(next);
  return getFilterState();
}

export function resetFilterState(updatedBy = "admin") {
  const next = {
    ...DEFAULT_STATE,
    updatedAt: new Date().toISOString(),
    updatedBy,
    history: [
      { action: "filter:RESET", at: new Date().toISOString(), by: updatedBy },
    ],
  };
  _writeRaw(next);
  return getFilterState();
}
