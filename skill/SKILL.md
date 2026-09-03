---
name: peon-extras
description: >-
  Installs and repairs Cursor extras for PeonPing (overlay geometry, notify.sh
  title/body wrappers, hooks.json, config.json). Use when installing PeonPing
  extras on a new Mac, after brew upgrade peon-ping, after peon-ping-setup, or
  when restoring notify.sh, mac-overlay.js, or Cursor notification banner
  customizations.
---

# PeonPing Cursor extras

Runtime scripts in this repo (and `~/.cursor/peon-extras/` after install) are
the source of truth. Do not paste them into markdown. Do not rewrite the
wrappers to "simplify" them.

## When to run

- First install on a Mac that already has Homebrew `peon-ping` and has run
  `peon-ping-setup` once.
- Repair after `brew upgrade peon-ping` (Cellar updates; generated overlay may
  be stale).
- Repair after `peon-ping-setup` (it rewrites hook registration and may put
  hooks in the wrong file).

## Install / repair

1. Work from the git clone of this repo (not a megahandoff paste).
2. Confirm `peon-ping` is installed (`brew --prefix peon-ping`) and
   `~/.claude/hooks/peon-ping/peon.sh` exists. If `peon.sh` is missing, tell the
   human to run `peon-ping-setup`, then re-run the installer. Do not invent a
   second setup path.
3. Run `./install.sh` from the clone. It is idempotent. It copies scripts to
   `~/.cursor/peon-extras/`, merges user `hooks.json` and peon `config.json`,
   installs/uses the `peasant_fr` pack, runs `build-large-overlay.py`, installs
   the `$PEON_DIR/scripts/` symlinks, copies this skill to
   `~/.cursor/skills/peon-extras/`, and sets
   `cursor.composer.shouldChimeAfterChatFinishes` to `false`.
4. If `build-large-overlay.py` exits non-zero, **stop**. Upstream changed a
   patched line. Do not hand-edit `mac-overlay.js` or half-patch.

## Completion criteria

Print and satisfy all of:

- `~/.claude/hooks/peon-ping/scripts/notify.sh` → `notify-banner-title.sh`
- `~/.claude/hooks/peon-ping/scripts/mac-overlay.js` → `mac-overlay-large.js`
- `notification_title_script` is `cursor-notification-title.py` (filename plus
  a symlink under `$PEON_DIR/scripts/`)
- User hooks (`~/.cursor/hooks.json`, version 1) register:
  - `beforeSubmitPrompt` → `peon.sh` only (no title-capture wrapper)
  - `afterAgentResponse` → `capture-response.py` (cache only, no sound)
  - `stop` → `stop-excerpt.py`
  - `postToolUseFailure` → `peon.sh`
  - `preCompact` → `precompact.py` (never `peon.sh` directly)
- No peon commands on `sessionStart`, `sessionStop`, `subagentStart`,
  `subagentStop`. Drop them if `peon-ping-setup` added them back.
- `node --check` on the generated overlay succeeds.
- `peasant_fr` is installed and selected (`peon packs use peasant_fr`);
  `default_pack` is `peasant_fr`.
- `config.json` `categories` uses dotted CESP keys: `task.acknowledge` and
  `resource.limit` are `true`. Nested `categories.task.acknowledge` is ignored
  by `peon.sh` and leaves submit silent.
- Submit is **sound only** (`task.acknowledge`). Banners fire on `stop` and
  `preCompact`, not on `beforeSubmitPrompt`.
- The generated overlay contains no `ObjC.registerSubclass` (`grep -c` is 0).
  On macOS 26 that call hangs forever inside libffi, so upstream's overlay
  never draws and burns ~65% CPU until notify.sh's watchdog kills it. The
  generator swaps in a hand-pumped event loop and a `/tmp/peon-ping-popups/
  .dismiss-*` marker for sibling dismissal. Symptom to recognise: sounds play,
  no banner, `osascript ... mac-overlay.js` processes alive at high CPU.

## Two wrapper seams (do not remove)

1. **Title:** `peon.sh` sanitizes the project label to `[A-Za-z0-9 _.,-]`, so
   emoji and `>` never reach the overlay. `cursor-notification-title.py`
   prints the `>` form and caches match/emoji/fallback.
   `notify-banner-title.sh` restores emoji only when `$2` equals that cached
   sanitized match or the `>` fallback. Leave `peon-ping-rename`, `peon-label`,
   and `CLAUDE_SESSION_NAME` alone.
2. **Overlay file:** PeonPing prefers `$PEON_DIR/scripts/mac-overlay.js` over
   the Homebrew copy. That path is a symlink to the generated
   `mac-overlay-large.js`. Rebuild after every upgrade; abort if a replacement
   pattern is not unique.

The same notify wrapper also swaps the stock PreCompact body
(`compacting: Context compacting`) for the cached summarize line. Copy says
summarize; the hook name stays `preCompact`.

## Hard rules

- Never `subprocess.PIPE` `peon.sh` stdout. The overlay child inherits the pipe
  and Cursor kills the hook at 60s. Use `stdout=DEVNULL`.
- Never write Cursor `state.vscdb`. Title and after-summarize percent are
  read-only.
- Do not revive `capture-title.py`, `session-title.sh`, or `pretooluse-probe.py`.
- Do not add `subagentStart` / `subagentStop`. Keep
  `suppress_subagent_complete` true.
- There is no IDE hook for AskQuestion. Do not invent a workaround. After a
  Cursor upgrade, a temporary `preToolUse` probe is allowed; until it logs
  `tool_name: AskQuestion`, leave input-required banners blocked.
- Restore packaged notify/overlay only if the user asks to disable extras:

```bash
ln -sfn "$(brew --prefix peon-ping)/libexec/scripts/notify.sh" \
  ~/.claude/hooks/peon-ping/scripts/notify.sh
ln -sfn "$(brew --prefix peon-ping)/libexec/scripts/mac-overlay.js" \
  ~/.claude/hooks/peon-ping/scripts/mac-overlay.js
```

Intel Homebrew prefix is `/usr/local/opt/peon-ping` when `brew --prefix` is
unavailable.

## Testing summarize without a live session

Do not burn a real chat. Point `CURSOR_STATE_DB` at a throwaway SQLite file as
described in `HANDOFF.md`. Watcher pass condition: `cache/summarize-watch-<id>`
disappears. That exercises logic, not pixels; only a real `/summarize` proves
the banner on screen.
