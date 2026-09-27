// Port of notification_title.py (Cursor adapter only; the Windows port does not wire Codex).
// Builds "Cursor > workspace > chat title" from read-only Cursor state.vscdb metadata and
// caches the emoji form for the win-notify wrapper (notify-banner-title.ps1).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { cachePath, writeCache } from "./_cache.mjs";
import { cursorStateDb, openReadOnly } from "./_usage.mjs";

const MAX_TITLE_CHARS = 50;
const MAX_AGENT_CHARS = 10;
const MAX_WORKSPACE_CHARS = 20;
const HOME_WORKSPACE_LABEL = "Home";
const PLAIN_SEPARATOR = " > ";
const BANNER_ICONS = ["\u{1F4BB}", "\u{1F4C2}", "\u{1F4AC}"];
const banner = (parts) => parts.map((p, i) => `${BANNER_ICONS[i]} ${p}`).join(" ");

const cleanLabel = (v) => String(v ?? "").split(/\s+/).filter(Boolean).join(" ");

function parseJson(value) {
  if (value instanceof Uint8Array) value = Buffer.from(value).toString("utf8");
  try { return JSON.parse(value); } catch { return null; }
}

function titleFromRecord(record, conversationId) {
  if (!record || typeof record !== "object" || Array.isArray(record)) return "";
  const recordId = cleanLabel(record.composerId || record.conversationId || record.id);
  if (!recordId || recordId === conversationId) {
    const title = cleanLabel(record.name || record.title);
    if (title) return title;
  }
  for (const key of ["allComposers", "composers", "headers"]) {
    if (Array.isArray(record[key])) {
      for (const item of record[key]) {
        const title = titleFromRecord(item, conversationId);
        if (title) return title;
      }
    }
  }
  return "";
}

function tableColumns(db, table) {
  try {
    return new Set(db.prepare(`PRAGMA table_info('${table.replace(/'/g, "''")}')`).all().map((r) => r.name));
  } catch { return new Set(); }
}

function titleFromHeadersTable(db, conversationId) {
  const cols = tableColumns(db, "composerHeaders");
  const idCol = ["composerId", "conversationId", "id"].find((c) => cols.has(c));
  if (!idCol) return "";
  const selected = ["name", "title", "value", "data", "json"].filter((c) => cols.has(c));
  if (!selected.length) return "";
  let row;
  try {
    row = db.prepare(`SELECT ${selected.map((c) => `"${c}"`).join(", ")} FROM "composerHeaders" WHERE "${idCol}"=?`).get(conversationId);
  } catch { return ""; }
  if (!row) return "";
  for (const col of selected) {
    const title = col === "name" || col === "title" ? cleanLabel(row[col]) : titleFromRecord(parseJson(row[col]), conversationId);
    if (title) return title;
  }
  return "";
}

function titleFromKeyValueTables(db, conversationId) {
  const keys = [`composerData:${conversationId}`, `composer:${conversationId}`, conversationId, "composer.composerHeaders", "composerHeaders"];
  for (const table of ["cursorDiskKV", "ItemTable"]) {
    const cols = tableColumns(db, table);
    if (!cols.has("key") || !cols.has("value")) continue;
    for (const key of keys) {
      let row;
      try { row = db.prepare(`SELECT value FROM "${table}" WHERE key=?`).get(key); } catch { break; }
      if (!row) continue;
      const title = titleFromRecord(parseJson(row.value), conversationId);
      if (title) return title;
    }
  }
  return "";
}

// Cloud-agent chats are not composerHeaders rows; titles live under cloudAgentRepository.agents.*.
function titleFromCloudAgents(db, conversationId) {
  for (const table of ["ItemTable", "cursorDiskKV"]) {
    const cols = tableColumns(db, table);
    if (!cols.has("key") || !cols.has("value")) continue;
    let rows = [];
    try { rows = db.prepare(`SELECT value FROM "${table}" WHERE key LIKE ?`).all("cloudAgentRepository.agents.%"); } catch { continue; }
    for (const { value } of rows) {
      const payload = parseJson(value);
      if (!Array.isArray(payload)) continue;
      for (const item of payload) {
        if (!item || typeof item !== "object") continue;
        if (cleanLabel(item.bcId || item.id) !== conversationId) continue;
        const title = cleanLabel(item.name || item.title);
        if (title) return title;
      }
    }
  }
  return "";
}

export async function cursorChatTitle(conversationId) {
  if (!conversationId) return "";
  const db = await openReadOnly(cursorStateDb());
  if (!db) return "";
  try {
    return titleFromHeadersTable(db, conversationId) || titleFromKeyValueTables(db, conversationId) || titleFromCloudAgents(db, conversationId);
  } catch { return ""; } finally { try { db.close(); } catch {} }
}

function truncate(value, length) {
  if (value.length <= length) return value;
  const cut = value.slice(0, length);
  const i = cut.lastIndexOf(" ");
  return (i >= 0 ? cut.slice(0, i) : cut) || cut;
}

function titleParts(agent, workspace, chat) {
  agent = cleanLabel(agent); workspace = cleanLabel(workspace); chat = cleanLabel(chat);
  if (!agent || !workspace) return null;
  agent = truncate(agent, MAX_AGENT_CHARS);
  workspace = truncate(workspace, MAX_WORKSPACE_CHARS);
  // Chats Cursor has not named yet still get agent and workspace. The only other title here is
  // peon.ps1's "<marker> <folder>", which carries neither.
  if (!chat) return [agent, workspace];
  const available = MAX_TITLE_CHARS - agent.length - workspace.length - 2 * PLAIN_SEPARATOR.length;
  if (available < 1) return null;
  return [agent, workspace, truncate(chat, available)];
}

export function normalizeCwd(cwd) {
  let p = cleanLabel(cwd);
  if (/^\/[A-Za-z]:[\\/]/.test(p)) p = p.slice(1); // "/c:/dev/x" -> "c:/dev/x"
  if (/^[A-Za-z]:[\\/]/.test(p)) p = path.win32.normalize(p).replace(/[\\/]+$/, "");
  if (/^[A-Za-z]:$/.test(p)) p += "\\";
  return p;
}

function workspaceLabel(cwd) {
  if (!cwd) return HOME_WORKSPACE_LABEL;
  const p = normalizeCwd(cwd);
  if (p.toLowerCase() === path.win32.normalize(os.homedir()).replace(/[\\/]+$/, "").toLowerCase()) return HOME_WORKSPACE_LABEL;
  return path.win32.basename(p) || HOME_WORKSPACE_LABEL;
}

// What peon.ps1 puts after its marker: Split-Path -Leaf of cwd, stripped to [a-zA-Z0-9 ._-], else "claude".
export function peonProjectName(cwd) {
  const p = normalizeCwd(cwd);
  const leaf = (p ? path.win32.basename(p) : "").replace(/[^a-zA-Z0-9 ._-]/g, "");
  return leaf || "claude";
}

export async function computeTitle(sessionId, cwd) {
  const parts = titleParts("Cursor", workspaceLabel(cwd), await cursorChatTitle(sessionId));
  const file = cachePath("banner-title", sessionId);
  if (!parts) {
    if (file) { try { fs.rmSync(file, { force: true }); } catch {} }
    return null;
  }
  const plain = parts.join(PLAIN_SEPARATOR);
  const emoji = banner(parts);
  if (file) writeCache(file, `${peonProjectName(cwd)}\n${emoji}\n${plain}\n`);
  return { plain, banner: emoji };
}

// CLI: PEON_SESSION_ID=<id> PEON_CWD=<dir> node notification_title.mjs  -> prints the plain title
if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const result = await computeTitle(cleanLabel(process.env.PEON_SESSION_ID), cleanLabel(process.env.PEON_CWD));
  if (!result) process.exit(1);
  console.log(result.plain);
}
