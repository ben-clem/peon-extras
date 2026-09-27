// peon.ps1 invocation for the Windows port of peon-extras.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

export const PEON_DIR = process.env.PEON_DIR || path.join(os.homedir(), ".claude", "hooks", "peon-ping");
export const PEON_PS1 = path.join(PEON_DIR, "peon.ps1");
export const NOTIFY_PS1 = path.join(PEON_DIR, "scripts", "win-notify.ps1");
const PS = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"];

export function loadPeonConfig() {
  try { return JSON.parse(fs.readFileSync(path.join(PEON_DIR, "config.json"), "utf8").replace(/^\uFEFF/, "")); } catch { return {}; }
}

// Never PIPE peon.ps1 stdout/stderr: it Start-Process'es the sound and toast children.
export function runPeon(payload, sessionId) {
  if (!fs.existsSync(PEON_PS1)) return 0;
  const env = { ...process.env, PEON_SESSION_ID: String(sessionId || ""), PSExecutionPolicyPreference: "Bypass" };
  const r = spawnSync("powershell.exe", [...PS, "-File", PEON_PS1], {
    input: JSON.stringify(payload), stdio: ["pipe", "ignore", "ignore"], windowsHide: true, env, timeout: 30000,
  });
  return r.status ?? 0;
}

// Direct toast for the "Done summarizing" after-banner (the Mac version calls notify.sh the same way).
export function sendBanner(sessionId, message) {
  if (!message || !fs.existsSync(NOTIFY_PS1)) return;
  const cfg = loadPeonConfig();
  const dismiss = String(cfg.notification_dismiss_seconds || 4);
  const env = { ...process.env, PEON_SESSION_ID: String(sessionId || ""), PEON_EXTRAS_FORCE_TITLE: "1", PSExecutionPolicyPreference: "Bypass" };
  spawnSync("powershell.exe", [...PS, "-File", NOTIFY_PS1, "-body", message, "-title", "peon-ping", "-dismissSeconds", dismiss, "-parentPid", "0"], {
    stdio: ["ignore", "ignore", "ignore"], windowsHide: true, env, timeout: 60000,
  });
}
