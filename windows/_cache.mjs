// Shared cache + log helpers for the Windows port of peon-extras.
// Mirrors _cache.py: cache files live next to the runtime in ./cache and expire after 14 days.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const CACHE_DIR = process.env.PEON_EXTRAS_CACHE_DIR || path.join(HERE, "cache");
const CACHE_TTL_MS = 14 * 86400 * 1000;

export function cachePath(kind, conversationId) {
  const safeId = String(conversationId ?? "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
  return safeId ? path.join(CACHE_DIR, `${kind}-${safeId}`) : "";
}

export function pruneStaleEntries() {
  const cutoff = Date.now() - CACHE_TTL_MS;
  let names = [];
  try { names = fs.readdirSync(CACHE_DIR); } catch { return; }
  for (const name of names) {
    const p = path.join(CACHE_DIR, name);
    try { if (fs.statSync(p).mtimeMs < cutoff) fs.rmSync(p, { force: true }); } catch {}
  }
}

export function writeCache(file, text) {
  if (!file) return;
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  pruneStaleEntries();
  fs.writeFileSync(file, text, "utf8");
}

export function readCache(file) {
  if (!file) return "";
  try { return fs.readFileSync(file, "utf8"); } catch { return ""; }
}

// Local-time decision log so titles and banners can be checked later.
export function log(message) {
  try {
    const dir = path.join(HERE, "logs");
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, "hooks.log");
    try { if (fs.statSync(file).size > 1_000_000) fs.renameSync(file, file + ".1"); } catch {}
    const stamp = new Date().toLocaleString("sv-SE");
    fs.appendFileSync(file, `${stamp} [${process.pid}] ${message}\n`);
  } catch {}
}
