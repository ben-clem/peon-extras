// Port of precompact.py: before/after "Summarizing" banners for Cursor preCompact.
// Cursor has no postCompact hook, so a detached watcher polls composerHeaders.contextUsagePercent
// (read-only) until it drops, then shows the "Done summarizing" line.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { cachePath, writeCache, readCache } from "./_cache.mjs";
import { usageLine, usagePercentFromDb } from "./_usage.mjs";
import { sendBanner } from "./_peon.mjs";

const DROP_POINTS = 5.0, POLL_MS = 1000, TIMEOUT_MS = 300000;
const num = (v) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));

export function storeBefore(conversationId, event) {
  const percent = num(event.context_usage_percent);
  const tokens = num(event.context_tokens);
  const windowSize = num(event.context_window_size);
  const body = usageLine("Summarizing", tokens, windowSize, percent) || "Summarizing this chat now";
  writeCache(cachePath("compact-body", conversationId), body + "\n");
  return { percent, tokens, windowSize };
}

export function startWatcher(conversationId, before) {
  if (before.percent === null || !before.windowSize) return;
  const watchPath = cachePath("summarize-watch", conversationId);
  if (!watchPath) return;
  let previous = {};
  try { previous = JSON.parse(readCache(watchPath)) || {}; } catch {}
  const generation = Number(previous.generation || 0) + 1;
  writeCache(watchPath, JSON.stringify({ conversation_id: conversationId, before_percent: before.percent, window_size: before.windowSize, before_tokens: before.tokens, generation }) + "\n");
  const child = spawn(process.execPath, ["--no-warnings", fileURLToPath(import.meta.url), "--watch", watchPath, String(generation)], { detached: true, stdio: "ignore", windowsHide: true });
  child.unref();
}

async function watchMain(watchPath, generation) {
  let payload = {};
  try { payload = JSON.parse(readCache(watchPath)) || {}; } catch {}
  const id = String(payload.conversation_id || "");
  const before = num(payload.before_percent), windowSize = num(payload.window_size);
  if (!id || before === null || !windowSize) return;
  const deadline = Date.now() + TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, POLL_MS));
    let latest = {};
    try { latest = JSON.parse(readCache(watchPath)) || {}; } catch {}
    if (latest.generation !== generation) return;
    const current = await usagePercentFromDb(id);
    if (current === null) continue;
    if (current <= before - DROP_POINTS) {
      const message = usageLine("Done summarizing", (windowSize * current) / 100, windowSize, current);
      if (message) sendBanner(id, message);
      try { fs.rmSync(watchPath, { force: true }); } catch {}
      return;
    }
  }
}

if (process.argv[2] === "--watch" && process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await watchMain(process.argv[3], Number(process.argv[4]));
}
