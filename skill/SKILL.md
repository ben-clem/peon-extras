---
name: peon-extras
description: >-
  Installs and repairs Cursor and OpenAI Codex extras for PeonPing, including
  lifecycle hooks, request_user_input notifications, conversation titles,
  compaction banners, overlay geometry, and notify.sh wrappers. Use on a new
  Mac, after brew upgrade peon-ping or peon-ping-setup, or when those specific
  PeonPing customizations stop working.
---

# PeonPing extras

Runtime scripts in this repo, and `~/.local/share/peon-extras/` after install,
are the source of truth. Do not paste them into markdown or rewrite the wrapper
flow casually.

## Install or repair

1. Work from this git clone.
2. Confirm `brew --prefix peon-ping` succeeds and
   `~/.claude/hooks/peon-ping/peon.sh` exists. If it is missing, ask the human
   to run `peon-ping-setup`, then rerun this installer.
3. Run `./install.sh`. It is idempotent. It installs the runtime, merges Cursor
   and Codex hooks, merges PeonPing config, selects `peasant_fr`, rebuilds the
   overlay, installs the PeonPing script symlinks, and installs this skill for
   both agents.
4. If `build-large-overlay.py` exits nonzero, stop. Upstream changed a patched
   line. Do not hand-edit a partial `mac-overlay.js`.
5. After Codex hook changes, run `codex` in a terminal, enter `/hooks` in the
   Codex CLI, and trust the user hooks. The Codex Desktop composer does not
   resolve `/hooks`. Restart Codex Desktop after trusting the hooks. Non-managed
   hooks do not run until reviewed. If `codex` is missing from `PATH`, use the
   bundled `/Applications/ChatGPT.app/Contents/Resources/codex` when present,
   or follow OpenAI's official CLI installation instructions.
6. Ignore PeonPing's `detected (not set up)` Codex status when the user hooks
   below are present. Its detector searches only `config.toml`. Do not add a
   legacy `notify` callback to satisfy that detector; it duplicates completion
   events.

## Completion criteria

Satisfy all of these:

- `$PEON_DIR/scripts/notify.sh` points to `notify-banner-title.sh`.
- `$PEON_DIR/scripts/mac-overlay.js` points to `mac-overlay-large.js`.
- `notification_title_script` is an absolute
  `python3 …/notification_title.py` command.
- Cursor `~/.cursor/hooks.json` registers:
  - `beforeSubmitPrompt` to `peon.sh`;
  - `afterAgentResponse` to `capture-response.py`;
  - `stop` to `stop-excerpt.py`;
  - `postToolUseFailure` to `peon.sh`;
  - `preCompact` to `precompact.py`.
- Cursor has no peon command on `sessionStart`, `sessionStop`,
  `subagentStart`, or `subagentStop`. Cursor fires session start beside the
  first prompt submission, which causes duplicate sound.
- Codex `~/.codex/hooks.json` registers `codex_hook.py` for `SessionStart`,
  `SessionEnd`, `UserPromptSubmit`, `PermissionRequest`, `PreCompact`,
  `PostCompact`, `SubagentStart`, `SubagentStop`, and `Stop`.
- Codex `PreToolUse` matches only `^request_user_input$`.
- `node --check` succeeds on the generated overlay.
- `peasant_fr` is installed and selected.
- Config categories use dotted CESP keys: `session.start`,
  `task.acknowledge`, and `resource.limit` are true.
- Submit is sound only. Completion, question, and compaction events may show
  banners.
- `notification_templates.stop` and `notification_templates.question` are
  both `{summary}`.
- The generated overlay contains no `ObjC.registerSubclass`.

## Locked settings

`./install.sh` reapplies these choices:

- Overlay `650x100`, icon `72`, title font `18`, excerpt font `14`, gap `10`,
  icon-to-text `+16`, left aligned: `build-large-overlay.py`.
- Title `💻 agent 📂 workspace 💬 conversation`, with ASCII fallback
  `agent > workspace > conversation`: `notification_title.py`. Projectless
  Codex Desktop tasks use workspace `Recents`; named projects use their Codex
  project name. Cursor and Codex CLI use their working-directory name.
- Completion body is the first nonempty assistant line, up to 160 characters.
  Cursor caches it through `capture-response.py`; Codex supplies
  `last_assistant_message` on `Stop`.
- Compaction copy is `Summarizing:` or `Done summarizing:` plus K-format token
  usage when available: `_usage.py`.
- Neon overlay, `peasant_fr`, volume `0.25`, 30-second dismiss, subagent
  completion suppressed.
- Cursor's built-in finish chime is off.

## Adapter seams

Keep these interfaces small and stable:

1. `notification_title.py` is the only title provider exposed to PeonPing. It
   selects a read-only Cursor or Codex metadata adapter from `PEON_IDE` and the
   session id. Codex ids arrive as `codex-<session_id>` and must be normalized
   before reading `~/.codex/session_index.jsonl` and `~/.codex/state_5.sqlite`.
   Use the transcript originator plus the thread's `project_id` to distinguish
   a projectless Codex Desktop task from CLI and IDE sessions. If a lookup
   fails, keep the working-directory fallback.
2. `codex_hook.py` is the only custom Codex event adapter. Ordinary lifecycle
   events delegate to PeonPing's packaged `adapters/codex.sh`. It handles only
   the missing behavior: `request_user_input`, cached PreCompact body, the
   PostCompact banner, and suppression of `PermissionRequest` banners when the
   task transcript says Codex auto-review is the active reviewer.
3. `notify-banner-title.sh` restores the cached emoji title only when the
   sanitized incoming title matches. It also swaps PeonPing's stock
   `compacting: Context compacting` body and resets only the popup stacking
   count so a live banner is replaced without an `(N)` prefix.
4. PeonPing prefers `$PEON_DIR/scripts/mac-overlay.js` over the Homebrew copy.
   That path stays linked to the generated overlay.

Cursor cloud-agent conversations are not `composerHeaders` rows; their titles
live under `cloudAgentRepository.agents.*` in `ItemTable`.

Codex title and token-count formats are internal, read-only, best-effort
lookups. Keep generic fallbacks. Do not make notification delivery depend on a
successful internal lookup.

## Hard rules

- Never capture `peon.sh` or `adapters/codex.sh` stdout with
  `subprocess.PIPE`. The overlay child inherits the pipe. Cursor then kills the
  hook at its timeout, and Codex `Stop` also rejects plain-text hook output.
  Route stdout and stderr to `DEVNULL`.
- Never write Cursor `state.vscdb`, Codex `session_index.jsonl`, or Codex
  transcripts.
- Do not register all Codex `PreToolUse` events. Match only
  `request_user_input`.
- Do not add Cursor subagent start or stop hooks. Keep
  `suppress_subagent_complete` true for both agents.
- Do not revive `capture-title.py`, `session-title.sh`, or
  `pretooluse-probe.py`.
- `install_codex_hooks.py` owns user-level `~/.codex/hooks.json`. Preserve
  unrelated hook rules. If PeonPing hooks also exist inline in
  `~/.codex/config.toml`, warn about duplicate matching hooks instead of
  deleting unknown TOML.

Restore packaged notify and overlay scripts only when the human asks to
disable the extras:

```bash
ln -sfn "$(brew --prefix peon-ping)/libexec/scripts/notify.sh" \
  ~/.claude/hooks/peon-ping/scripts/notify.sh
ln -sfn "$(brew --prefix peon-ping)/libexec/scripts/mac-overlay.js" \
  ~/.claude/hooks/peon-ping/scripts/mac-overlay.js
```

Intel Homebrew uses `/usr/local/opt/peon-ping` when `brew --prefix` is
unavailable.

## Verification

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile ./*.py
bash -n install.sh notify-banner-title.sh
node --check mac-overlay-large.js
```

The generated overlay exists only after the installer runs.

For a live Codex check after restart and hook trust:

1. Submit a prompt and confirm the acknowledgement sound has no banner.
2. Trigger a `request_user_input` question and confirm a blue question banner.
3. Complete a turn and confirm the banner uses the assistant excerpt and
   `💻 agent 📂 workspace 💬 conversation` title.
4. Use `/compact` only when a real compaction test is warranted; unit tests use
   a synthetic transcript instead.
