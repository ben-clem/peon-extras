#!/usr/bin/env node
// Idempotent install/repair for the Windows port of peon-extras (Cursor only).
// Windows counterpart of ../install.sh. Safe to re-run after re-running PeonPing's install.ps1.
//   node install.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SRC = path.dirname(fileURLToPath(import.meta.url));
const HOME = os.homedir();
const DEST = process.env.PEON_EXTRAS_DIR || path.join(HOME, ".local", "share", "peon-extras");
const PEON_DIR = process.env.PEON_DIR || path.join(HOME, ".claude", "hooks", "peon-ping");
const HOOKS_JSON = process.env.CURSOR_HOOKS_JSON || path.join(HOME, ".cursor", "hooks.json");
const APPDATA = process.env.APPDATA || path.join(HOME, "AppData", "Roaming");
const SETTINGS_JSON = process.env.CURSOR_USER_SETTINGS || path.join(APPDATA, "Cursor", "User", "settings.json");
const SKILL_DEST = path.join(HOME, ".cursor", "skills", "peon-extras");
const PEON_PS1 = path.join(PEON_DIR, "peon.ps1");
const CONFIG_JSON = path.join(PEON_DIR, "config.json");
const NOTIFY_PS1 = path.join(PEON_DIR, "scripts", "win-notify.ps1");
const STOCK_NOTIFY = path.join(DEST, "win-notify.stock.ps1");
const WRAPPER_MARK = "PEON-EXTRAS-WIN-NOTIFY-WRAPPER";
const RUNTIME_FILES = ["_cache.mjs", "_usage.mjs", "_peon.mjs", "notification_title.mjs", "precompact.mjs", "cursor_hook.mjs", "notify-banner-title.ps1", "win-overlay.ps1"];
const STAMP = new Date().toLocaleString("sv-SE").replace(/[-: ]/g, "").replace(/^(\d{8})(\d{6})$/, "$1-$2");
const HOOK_COMMAND = `node --no-warnings "${path.join(DEST, "cursor_hook.mjs")}"`;

const die = (msg) => { console.error(`install.mjs: ${msg}`); process.exit(1); };
const readJson = (p) => JSON.parse(fs.readFileSync(p, "utf8").replace(/^\uFEFF/, ""));
// ASCII-only JSON so Windows PowerShell 5.1 (Get-Content without -Encoding) reads it correctly.
const asciiJson = (data) => JSON.stringify(data, null, 2).replace(/[\u007f-\uffff]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")) + "\n";
function backup(p) {
  if (!fs.existsSync(p)) return null;
  const b = `${p}.bak-${STAMP}`;
  fs.copyFileSync(p, b);
  console.log(`backup: ${b}`);
  return b;
}

console.log("== require peon-ping ==");
if (!fs.existsSync(PEON_PS1)) die(`missing ${PEON_PS1} (run PeonPing's install.ps1 first)`);
if (!fs.existsSync(CONFIG_JSON)) die(`missing ${CONFIG_JSON}`);
console.log(`PEON_DIR: ${PEON_DIR}\ndest:     ${DEST}\nnode:     ${process.version}`);

console.log("== copy runtime scripts ==");
fs.mkdirSync(DEST, { recursive: true });
for (const name of RUNTIME_FILES) fs.copyFileSync(path.join(SRC, name), path.join(DEST, name));
const settingsFile = path.join(DEST, "peon-extras.json");
if (!fs.existsSync(settingsFile)) fs.writeFileSync(settingsFile, asciiJson({}));
// Overlay icon fallback, same as notify.sh on macOS ($PEON_DIR/docs/peon-icon.png). The Windows
// installer does not copy docs\, so also look in a peon-ping clone next to this repo.
{
  const iconDest = path.join(DEST, "peon-icon.png");
  const iconSrc = [path.join(PEON_DIR, "docs", "peon-icon.png"), path.resolve(SRC, "..", "..", "peon-ping", "docs", "peon-icon.png")].find((p) => fs.existsSync(p));
  if (iconSrc) fs.copyFileSync(iconSrc, iconDest);
  console.log(`overlay icon: ${iconSrc ? iconDest + " (from " + iconSrc + ")" : "none found (overlay shows without icon)"}`);
}
console.log(`settings: ${settingsFile} ${fs.readFileSync(settingsFile, "utf8").trim().replace(/\s+/g, " ")}`);

console.log("== agent skill ==");
fs.mkdirSync(SKILL_DEST, { recursive: true });
backup(path.join(SKILL_DEST, "SKILL.md"));
fs.copyFileSync(path.join(SRC, "SKILL.md"), path.join(SKILL_DEST, "SKILL.md"));
console.log(`skill: ${path.join(SKILL_DEST, "SKILL.md")}`);

console.log("== merge Cursor hooks.json ==");
{
  const ours = ["beforeSubmitPrompt", "afterAgentResponse", "stop", "postToolUseFailure", "preCompact"];
  const dropEvents = ["sessionStart", "sessionStop", "sessionEnd", "subagentStart", "subagentStop"];
  const needles = ["peon-ping", "peon-extras", "peon.sh", "peon.ps1", "hook-handle-use", "capture-title", "session-title", "pretooluse-probe"];
  const isPeon = (c) => needles.some((n) => String(c || "").includes(n));
  const entries = (v) => (v == null ? [] : Array.isArray(v) ? v.map((i) => (i && typeof i === "object" ? i : { command: i })) : typeof v === "object" ? [v] : [{ command: v }]);
  let data = { version: 1, hooks: {} };
  if (fs.existsSync(HOOKS_JSON)) {
    backup(HOOKS_JSON);
    data = readJson(HOOKS_JSON);
    if (!data || typeof data !== "object" || Array.isArray(data)) die("hooks.json is not an object");
    if (Array.isArray(data.hooks)) die("hooks.json uses the flat-array format; convert it to {\"hooks\": {event: [...]}} first");
    data.version ??= 1;
    if (!data.hooks || typeof data.hooks !== "object") data.hooks = {};
  }
  const hooks = data.hooks;
  if (hooks.precompact && !hooks.preCompact) hooks.preCompact = hooks.precompact;
  delete hooks.precompact;
  // PeonPing's install.ps1 (8ef3766) writes {"command": null} for Cursor beforeSubmitPrompt when
  // Claude Code is absent ($beforeSubmitCmd is only set inside its Claude block). Drop such entries.
  const valid = (i) => {
    const ok = typeof i.command === "string" && i.command.trim() !== "";
    if (!ok) console.log(`dropped invalid hook entry: ${JSON.stringify(i)}`);
    return ok;
  };
  for (const event of ours) hooks[event] = [...entries(hooks[event]).filter(valid).filter((i) => !isPeon(i.command)), { command: HOOK_COMMAND }];
  for (const event of dropEvents) {
    const kept = entries(hooks[event]).filter(valid).filter((i) => !isPeon(i.command));
    if (kept.length) hooks[event] = kept; else delete hooks[event];
  }
  fs.mkdirSync(path.dirname(HOOKS_JSON), { recursive: true });
  fs.writeFileSync(HOOKS_JSON, JSON.stringify(data, null, 2) + "\n");
  console.log(`wrote ${HOOKS_JSON}`);
}

console.log("== merge peon-ping config.json ==");
{
  backup(CONFIG_JSON);
  const cfg = readJson(CONFIG_JSON);
  // Same values as ../install.sh. notification_title_script is not set: peon.ps1 does not read it;
  // the title is restored by the win-notify wrapper instead. overlay_theme is macOS-only (kept for parity).
  cfg.notification_title_marker = " > ";
  cfg.notification_dismiss_seconds = 30;
  cfg.overlay_theme = "neon";
  cfg.volume = 0.25;
  cfg.suppress_subagent_complete = true;
  cfg.default_pack = "peasant_fr";
  cfg.notification_templates = { ...(cfg.notification_templates && typeof cfg.notification_templates === "object" ? cfg.notification_templates : {}), stop: "{summary}", question: "{summary}" };
  const cats = cfg.categories && typeof cfg.categories === "object" ? cfg.categories : {};
  cats["session.start"] = true;
  cats["task.acknowledge"] = true;
  cats["resource.limit"] = true;
  delete cats.task; delete cats.resource;
  cfg.categories = cats;
  fs.writeFileSync(CONFIG_JSON, asciiJson(cfg));
  console.log(`wrote ${CONFIG_JSON}`);
}

console.log("== peasant_fr pack ==");
{
  const peonCmd = path.join(HOME, ".local", "bin", "peon.cmd");
  if (!fs.existsSync(peonCmd)) die(`peon CLI not found at ${peonCmd}`);
  const env = { ...process.env, PSExecutionPolicyPreference: "Bypass" };
  const r = spawnSync("cmd.exe", ["/d", "/c", peonCmd, "packs", "use", "--install", "peasant_fr"], { stdio: "inherit", env, windowsHide: true });
  if (r.status !== 0) die("failed to install/use peasant_fr");
  const cfg = readJson(CONFIG_JSON);
  if (cfg.default_pack !== "peasant_fr") die(`default_pack is ${cfg.default_pack}, expected peasant_fr`);
  // The CLI rewrites config.json; make sure it stays ASCII for PowerShell 5.1.
  fs.writeFileSync(CONFIG_JSON, asciiJson(cfg));
  console.log("pack: peasant_fr (use --install)");
}

console.log("== win-notify wrapper ==");
{
  if (!fs.existsSync(NOTIFY_PS1)) die(`missing ${NOTIFY_PS1}`);
  const current = fs.readFileSync(NOTIFY_PS1, "utf8");
  if (!current.includes(WRAPPER_MARK)) {
    fs.copyFileSync(NOTIFY_PS1, STOCK_NOTIFY);
    console.log(`stock copy: ${STOCK_NOTIFY}`);
  } else if (!fs.existsSync(STOCK_NOTIFY)) {
    die(`wrapper installed but ${STOCK_NOTIFY} is missing; re-run PeonPing's install.ps1, then this script`);
  }
  fs.copyFileSync(path.join(SRC, "notify-banner-title.ps1"), NOTIFY_PS1);
  console.log(`wrapper: ${NOTIFY_PS1}`);
}

console.log("== Cursor finish chime ==");
{
  let data = {};
  let ok = true;
  if (fs.existsSync(SETTINGS_JSON) && fs.statSync(SETTINGS_JSON).size) {
    try { data = readJson(SETTINGS_JSON); } catch { ok = false; console.log("skip chime: settings.json is not strict JSON"); }
    if (ok && (!data || typeof data !== "object" || Array.isArray(data))) { ok = false; console.log("skip chime: settings.json is not an object"); }
  }
  if (ok) {
    backup(SETTINGS_JSON);
    data["cursor.composer.shouldChimeAfterChatFinishes"] = false;
    fs.mkdirSync(path.dirname(SETTINGS_JSON), { recursive: true });
    fs.writeFileSync(SETTINGS_JSON, JSON.stringify(data, null, 4) + "\n");
    console.log(`wrote ${SETTINGS_JSON}`);
  }
}

console.log("\n== verification ==");
{
  const claudeSettings = path.join(HOME, ".claude", "settings.json");
  if (fs.existsSync(claudeSettings) && /peon\.(ps1|sh)/.test(fs.readFileSync(claudeSettings, "utf8"))) {
    console.log(`warning: ${claudeSettings} has peon hooks; Cursor's third-party hooks may load them too (duplicate sounds)`);
  }
  if (fs.existsSync(path.join(HOME, ".codex"))) console.log("note: ~/.codex exists; the Windows port does not wire Codex yet");
  const hooks = readJson(HOOKS_JSON).hooks;
  for (const e of ["beforeSubmitPrompt", "afterAgentResponse", "stop", "postToolUseFailure", "preCompact", "sessionStart", "subagentStart", "subagentStop"]) console.log(`hook ${e}: ${JSON.stringify(hooks[e] ?? null)}`);
  const cfg = readJson(CONFIG_JSON);
  for (const k of ["default_pack", "volume", "notification_dismiss_seconds", "notification_title_marker", "overlay_theme", "suppress_subagent_complete"]) console.log(`${k}: ${JSON.stringify(cfg[k])}`);
  console.log(`notification_templates: ${JSON.stringify(cfg.notification_templates)}`);
  console.log(`categories: ${JSON.stringify(cfg.categories)}`);
  console.log(`win-notify wrapper: ${fs.readFileSync(NOTIFY_PS1, "utf8").includes(WRAPPER_MARK)} (stock at ${STOCK_NOTIFY}: ${fs.existsSync(STOCK_NOTIFY)})`);
  let sqlite = false;
  try { await import("node:sqlite"); sqlite = true; } catch {}
  console.log(`node:sqlite available (chat titles): ${sqlite}`);
  console.log("install/repair complete.");
}
