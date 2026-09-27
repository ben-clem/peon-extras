// Context-window numbers for summarize banners (port of _usage.py). Read-only SQLite.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function cursorStateDb() {
  if (process.env.CURSOR_STATE_DB) return process.env.CURSOR_STATE_DB;
  const appData = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
  return path.join(appData, "Cursor", "User", "globalStorage", "state.vscdb");
}

// Never writes: readOnly connection, callers only SELECT.
export async function openReadOnly(file) {
  if (!file || !fs.existsSync(file)) return null;
  let DatabaseSync;
  try { ({ DatabaseSync } = await import("node:sqlite")); } catch { return null; }
  try { return new DatabaseSync(file, { readOnly: true, timeout: 500 }); } catch {}
  try { return new DatabaseSync(file, { readOnly: true }); } catch { return null; }
}

export function formatK(count) {
  const value = Number(count);
  if (count === null || count === undefined || count === "" || !Number.isFinite(value) || value < 0) return "";
  if (value >= 1000) {
    const thousands = value / 1000;
    if (Math.abs(thousands - Math.round(thousands)) < 0.05) return `${Math.round(thousands)}K`;
    return `${thousands.toFixed(1)}K`;
  }
  return String(Math.round(value));
}

export function formatPercent(value) {
  const n = Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n)) return "";
  return String(Math.round(n));
}

export function usageLine(prefix, usedTokens, windowTokens, percent) {
  const used = formatK(usedTokens), win = formatK(windowTokens), pct = formatPercent(percent);
  if (!used || !win || !pct) return "";
  return `${prefix}: ${used} / ${win} Tokens (${pct}% Full)`;
}

function parseJson(value) {
  if (value instanceof Uint8Array) value = Buffer.from(value).toString("utf8");
  try { return JSON.parse(value); } catch { return null; }
}

export async function usagePercentFromDb(conversationId) {
  if (!conversationId) return null;
  const db = await openReadOnly(cursorStateDb());
  if (!db) return null;
  try {
    const row = db.prepare('SELECT value FROM "composerHeaders" WHERE "composerId"=?').get(conversationId);
    if (!row) return null;
    const record = parseJson(row.value);
    if (!record || typeof record !== "object") return null;
    const raw = record.contextUsagePercent ?? record.context_usage_percent;
    const n = Number(raw);
    return raw === null || raw === undefined || !Number.isFinite(n) ? null : n;
  } catch { return null; } finally { try { db.close(); } catch {} }
}
