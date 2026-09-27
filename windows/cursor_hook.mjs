// Single entry point for the Cursor hooks registered in ~/.cursor/hooks.json (Windows port of
// capture-response.py, stop-excerpt.py, precompact.py and the direct peon.sh hooks).
//
//   beforeSubmitPrompt -> ack sound only (peon.ps1 via the SubagentStart route = task.acknowledge)
//   afterAgentResponse -> cache the first assistant line for the stop banner
//   stop               -> peon.ps1 Stop with the cached excerpt as the banner body + chat title
//   postToolUseFailure -> peon.ps1 (task.error sound)
//   preCompact         -> "Summarizing: ..." body, after-watcher, peon.ps1 PreCompact
//
// The hook process answers Cursor quickly and hands the slow part (title
// lookup, peon.ps1) to a detached runner, so prompt submission is not delayed.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { cachePath, writeCache, readCache, log } from "./_cache.mjs";
import { computeTitle, normalizeCwd } from "./notification_title.mjs";
import { runPeon } from "./_peon.mjs";
import { storeBefore, startWatcher } from "./precompact.mjs";

const SELF = fileURLToPath(import.meta.url);
const MAX_EXCERPT_CHARS = 160;

function readStdin() {
  try { return fs.readFileSync(0, "utf8"); } catch { return ""; }
}

function toSingleLine(text) {
  const withoutFences = String(text || "").replace(/```[\s\S]*?```/g, "");
  for (const line of withoutFences.split(/\r?\n/)) {
    const condensed = line.trim().replace(/^[\s#\-*>|]+|[\s#\-*>|]+$/g, "").replace(/\s+/g, " ").trim();
    if (condensed) return condensed.slice(0, MAX_EXCERPT_CHARS);
  }
  return "";
}

function takeCachedExcerpt(conversationId) {
  const file = cachePath("response", conversationId);
  const excerpt = readCache(file).trim();
  if (file) { try { fs.rmSync(file, { force: true }); } catch {} }
  return excerpt;
}

function conversationOf(event) {
  return String(event.conversation_id || event.session_id || "");
}

function cwdOf(event) {
  const roots = Array.isArray(event.workspace_roots) ? event.workspace_roots : [];
  return normalizeCwd(event.cwd || roots[0] || process.env.CURSOR_PROJECT_DIR || "");
}

function handOff(job) {
  const child = spawn(process.execPath, ["--no-warnings", SELF, "--run"], { detached: true, stdio: ["pipe", "ignore", "ignore"], windowsHide: true });
  child.on("error", () => {});
  child.stdin.on("error", () => {});
  child.stdin.end(JSON.stringify(job));
  child.unref();
}

function hookMain() {
  const raw = readStdin();
  let event = {};
  try { event = JSON.parse(raw) || {}; } catch {}
  const name = String(event.hook_event_name || "");
  const id = conversationOf(event);
  const reply = name === "beforeSubmitPrompt" ? '{"continue":true}' : "{}";
  try {
    if (name === "afterAgentResponse") {
      const excerpt = toSingleLine(event.text);
      if (excerpt) writeCache(cachePath("response", id), excerpt + "\n");
    } else if (["beforeSubmitPrompt", "stop", "postToolUseFailure", "preCompact"].includes(name)) {
      const cwd = cwdOf(event);
      const payload = { ...event };
      if (cwd && !payload.cwd) payload.cwd = cwd;
      if (name === "beforeSubmitPrompt") payload.hook_event_name = "SubagentStart"; // peon.ps1: SubagentStart -> task.acknowledge, no banner
      if (name === "stop") payload.message = takeCachedExcerpt(id) || "Done";
      let before = null;
      if (name === "preCompact") before = storeBefore(id, event);
      handOff({ name, id, cwd, payload, before });
    }
  } catch (e) { log(`hook error ${name}: ${e && e.message}`); }
  process.stdout.write(reply + "\n");
}

async function runMain() {
  let job = {};
  try { job = JSON.parse(readStdin()) || {}; } catch { return; }
  const { name, id, cwd, payload, before } = job;
  let title = null;
  if (name === "stop" || name === "preCompact") title = await computeTitle(id, cwd);
  if (name === "preCompact" && before) startWatcher(id, before);
  const status = runPeon(payload, id);
  log(`${name} -> peon.ps1 ${payload.hook_event_name} conv=${id} cwd=${cwd} title=${title ? JSON.stringify(title.plain) : "(stock)"}${payload.message ? ` body=${JSON.stringify(payload.message)}` : ""} exit=${status}`);
}

if (process.argv.includes("--run")) await runMain();
else hookMain();
