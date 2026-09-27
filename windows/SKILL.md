---
name: peon-extras
description: >-
  Installs and repairs the Windows port of peon-extras (Cursor extras for
  PeonPing) on Windows: Cursor lifecycle hooks, the neon-style
  overlay banner with chat titles, completion excerpts, and compaction banners.
  Use after re-running PeonPing's install.ps1, or when the peon sounds or
  banners from Cursor stop working on Windows.
---

# PeonPing extras (Windows)

The macOS original is `../skill/SKILL.md` in the `ben-clem/peon-extras` clone.
This port lives in `windows\` of that clone and installs to
`%USERPROFILE%\.local\share\peon-extras\`. Runtime is Node 22.5+ (for
`node:sqlite`, no Python needed); PeonPing's native Windows runtime is `peon.ps1`.

## Install or repair

1. PeonPing must be installed with its Windows installer (from a peon-ping
   clone, run `powershell -ExecutionPolicy Bypass -File .\install.ps1`).
   That creates `%USERPROFILE%\.claude\hooks\peon-ping\peon.ps1` and the
   `peon` CLI at `%USERPROFILE%\.local\bin\peon.cmd`.
2. Run `node windows\install.mjs` from the peon-extras clone. It is idempotent and backs
   up `hooks.json`, `config.json`, Cursor `settings.json` and this skill as
   `*.bak-<yyyyMMdd-HHmmss>` before writing.
3. Re-run step 2 every time PeonPing's `install.ps1` is re-run: that installer
   overwrites `scripts\win-notify.ps1` and re-adds a Cursor
   `beforeSubmitPrompt` entry for `hook-handle-use.ps1`.

## Completion criteria

- `~/.cursor/hooks.json` registers `node --no-warnings "...\peon-extras\cursor_hook.mjs"`
  for `beforeSubmitPrompt`, `afterAgentResponse`, `stop`, `postToolUseFailure`,
  `preCompact`, and has no peon command on `sessionStart`, `sessionEnd`,
  `subagentStart`, `subagentStop`.
- `peon-ping\scripts\win-notify.ps1` contains `PEON-EXTRAS-WIN-NOTIFY-WRAPPER`
  and `peon-extras\win-notify.stock.ps1` exists.
- `config.json`: `default_pack` `peasant_fr`, `volume` 0.25,
  `notification_dismiss_seconds` 30, templates `stop`/`question` = `{summary}`,
  dotted categories `session.start`, `task.acknowledge`, `resource.limit` true.
- Cursor `cursor.composer.shouldChimeAfterChatFinishes` is false.

## How it differs from macOS

- `peon.ps1` ignores `notification_title_script`, so the title is restored by
  the win-notify wrapper from the cache that `notification_title.mjs` writes
  (`cache\banner-title-<conversation>`), keyed by `PEON_SESSION_ID`, which the
  runner sets and `Start-Process` children inherit. Unlike macOS, a chat
  Cursor has not named yet still caches `💻 Cursor 📂 <workspace>`. The wrapper
  strips `notification_title_marker` from titles it passes through, because
  `peon.ps1` puts the marker in the banner title and `peon.sh` does not.
- Banners are drawn by `win-overlay.ps1` (WPF from Windows PowerShell 5.1), a
  port of peon-ping's `mac-overlay.js` at the peon-extras size: 650x100,
  rounded 12, 95% opaque, blue for Stop and red for PreCompact, pack icon (or
  `peon-icon.png`) 72, bold 18 title over a 14 excerpt, top-center of every
  screen, 5 stacked slots, a newer banner from the same chat replaces the
  live one, click to dismiss, never takes focus. The wrapper falls back to the
  stock Windows toast if the overlay throws; `"banner_style": "toast"` in
  `peon-extras.json` forces the toast. WPF draws emoji in monochrome.
- `peon.ps1` maps `UserPromptSubmit` only to `user.spam`, so the submit hook
  sends `SubagentStart` (= `task.acknowledge`, no banner) to get the
  acknowledgement line. The 3-prompts-in-10s `user.spam` line is lost.
- `peon.ps1` reads `cwd` only; Cursor sends `workspace_roots`, so the hook
  injects `cwd` from `workspace_roots[0]`.
- Codex and Claude Code are not wired.

## Cursor worker sessions

A Cursor self-hosted worker runs as the same user in the interactive
session and its hook loader includes `~/.cursor/hooks.json`, so worker-agent
chats ping exactly like local ones. That is intended: the user answers worker
chats from Cursor Desktop. Do not add worker filtering. Never restart or edit
the worker.

## Hard rules

- Never pipe `peon.ps1` stdout/stderr; it `Start-Process`es sound and toast
  children. Spawn with stdout/stderr ignored and `-ExecutionPolicy Bypass`
  (the machine policy is otherwise Restricted).
- Never write Cursor `state.vscdb`; title and usage lookups open it read-only.
- Do not add Cursor `sessionStart` or subagent hooks (duplicate sounds).
- Keep JSON written for PowerShell 5.1 ASCII-only (`\uXXXX` escapes).

## Verification

Send a sample stop payload and watch `logs\hooks.log`:

```powershell
'{"hook_event_name":"afterAgentResponse","conversation_id":"test-1","text":"Test excerpt"}' | node --no-warnings "$env:USERPROFILE\.local\share\peon-extras\cursor_hook.mjs"
'{"hook_event_name":"stop","conversation_id":"test-1","status":"completed","workspace_roots":["C:\\dev\\peon-extras"]}' | node --no-warnings "$env:USERPROFILE\.local\share\peon-extras\cursor_hook.mjs"
```

Expect a "C'est fait"-style peasant_fr line and a blue overlay banner at the
top-center of each screen. `logs\hooks.log` shows an `overlay title=...` line
(or `overlay failed, falling back to toast` plus a `toast` line). The title is
`💻 Cursor 📂 peon-extras` for `test-1`, since Cursor has no name for it; a
named chat adds `💬 <chat title>`. A title starting with `>` or `●` means the
wrapper passed peon.ps1's stock title through. Set
`PEON_EXTRAS_OVERLAY_SNAPSHOT=<dir>` before the test to save PNG proofs.
