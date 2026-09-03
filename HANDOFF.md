# Handoff: package PeonPing Cursor extras

Next session: turn the working laptop install into something a second Mac can install, and
that this Mac can repair after `brew upgrade peon-ping`.

Do **not** treat this file as the product. It is a pointer. The scripts alongside it in `~/.
cursor/peon-extras/` are the source of truth. Copy those files; do not paste them into
markdown. This file ships with them into the repo.

## Recommendation (already decided in conversation)

Ship a **small personal GitHub repo** that contains:

1. The helper scripts (the runtime).
2. An **idempotent install/repair shell script**: a human or agent can run with no further
thinking.
3. A **Cursor skill** (`SKILL.md`) whose job is: install, repair after PeonPing upgrade, and
explain the two wrapper seams.

A megahandoff that inlines every script is the wrong artifact: it goes stale the moment a
script changes, lives in `/tmp`, and cannot be re-run.

## What is live on this machine (2026-09-02)

User is happy with the overlay. Visual lock:

- Banner: `650x100` (upstream `500x80`)
- Icon: `72` (upstream `60`)
- Title font `18`, excerpt font `14`
- Row gap `10` (upstream `2`)
- Icon-to-text `textX = 10 + iconSize + 16` (upstream `+ 5`)
- Title and excerpt **left-aligned** (upstream centered)
- Row 1: `📁 <workspace> 💬 <chat-title>`
- Row 2: first non-empty line of the assistant response (not a later "substantial" line).
  Exception: `precompact` uses the summarize usage line below.
- `precompact` before: `Summarizing: ~287.1K / 300K Tokens (96% Full)`
- After summarize (watcher): `Done summarizing: ~31.4K / 300K Tokens (11% Full)` (after
  tokens estimated from SQLite percent x window)
- ASCII fallback if emoji cannot be restored: `<workspace> > <chat-title>` (not hyphen, not
  em-dash)
- Active pack: `neon` (the default overlay script, not glass/jarvis/sakura)
- Cursor native finish chime: `cursor.composer.shouldChimeAfterChatFinishes: false` in `~/
  Library/Application Support/Cursor/User/settings.json`

### Files to copy (source of truth)

All under `~/.cursor/peon-extras/` except generated overlay and cache:

```text
| Path | Role |
| --- | --- |
| `_cache.py` | Cache dir + 14-day prune |
| `cursor-notification-title.py` | `notification_title_script`; SQLite title; prints `> `
  form; caches match/emoji/fallback |
| `capture-response.py` | `afterAgentResponse`; first non-empty line, max 160 chars |
| `stop-excerpt.py` | `stop` hook; injects cached excerpt as `message`, then `peon.sh`
  (stdout DEVNULL) |
| `notify-banner-title.sh` | Wrapper: restore emoji/`>` title, swap stock PreCompact body for
  cached summarize line, then exec packaged `notify.sh` |
| `precompact.py` | `precompact` hook: cache before-line from payload, spawn watcher, then
  `peon.sh` (sound) |
| `_usage.py` | K-format (`287.1K` / `300K`) and read-only `contextUsagePercent` |
| `build-large-overlay.py` | **Generator:** Re-applies the overlay geometry patches and removes
  upstream's `ObjC.registerSubclass` calls (they hang forever on macOS 26, so no banner ever
  draws); **abort if a pattern is not unique** |

```

Do not ship `cache/` or `__pycache__/`.

### Wiring (must be recreated by installer)

#### 1. Event | Command |

`~/.cursor/hooks.json` (user hooks). The complete registration, **version: 1**, six entries:

```json
{
  "beforeSubmitPrompt": "~/.claude/hooks/peon-ping/peon.sh",
  "afterAgentResponse": "~/.cursor/peon-extras/capture-response.py",
  "stop": "~/.cursor/peon-extras/stop-excerpt.py",
  "postToolUseFailure": "~/.claude/hooks/peon-ping/peon.sh",
  "precompact": "~/.cursor/peon-extras/precompact.py",
  "sessionStart": "~/.claude/hooks/peon-ping/peon.sh"
}

```

Deleted on purpose (do not revive): `capture-title.py` (first-prompt titles), `session-title. sh`, `pretooluse-probe.py` (3.18.25 AskQuestion hook test).

**Why this specific registration?**
`beforeSubmitPrompt` is **only** `peon.sh` (no title capture). `precompact` must **not** point at
`peon.sh` directly or the summarize numbers are lost.
`sessionStart` / `sessionStop`: Cursor fires it in the **same millisecond** as the first
`beforeSubmitPrompt`. Peonping's duplicate guard is a racy JSON read/write, so both sounds
play. Confirmed 2026-09-02: conversation `05473384` double-fired; `f91b9847` with
`sessionStart` removed played once (`UserPromptSubmit`, then later `Stop`). Keep `session. start` enabled in config so a future adapter can still emit it; just omit the Cursor hook.
**Do not register `subagentStart` or `subagentStop**`. Nested agents are not something the
user can act on, so both events are noise. Drop pack inheritance for subagent sessions. Also
set `suppress_subagent_complete` true so a re-added `subagentStop` stays quiet.

#### 2. `~/.claude/hooks/peon-ping/config.json` keys we own:

* `"notification_title_script": "cursor-notification-title.py"`
* `"notification_title_marker": " > "`
* `"notification_templates.stop": "{summary}"`
* `"notification_dismiss_seconds": 30` (upstream default is `4`)
* `"overlay_theme": "neon"`
* `"volume": 0.25`
* `"categories.task.acknowledge": true`
* `"categories.resource.limit": true` (the summarize banners ride this category)
* `"suppress_subagent_complete": true`
* `"default_pack": "peasant_fr"` (pack install is separate: Homebrew / `peon packs`
first):

**Symlinks** (PeonPing prefers over Homebrew's `find_bundled_script` checks `$PEON_DIR/scripts/`
first):

```bash
ln -sfn /opt/homebrew/opt/peon-ping/libexec/scripts/notify.sh \
  ~/.claude/hooks/peon-ping/scripts/notify.sh
ln -sfn ~/.cursor/peon-extras/notify-banner-title.sh \
  ~/.claude/hooks/peon-ping/scripts/notify.sh
ln -sfn ~/.cursor/peon-extras/mac-overlay-large.js \
  ~/.claude/hooks/peon-ping/scripts/mac-overlay.js

```

Packaged copies to restore:

```bash
ln -sfn /opt/homebrew/opt/peon-ping/libexec/scripts/notify.sh \
  ~/.claude/hooks/peon-ping/scripts/notify.sh
ln -sfn /opt/homebrew/opt/peon-ping/libexec/scripts/mac-overlay.js \
  ~/.claude/hooks/peon-ping/scripts/mac-overlay.js

```

Intel Homebrew: `/usr/local/opt/peon-ping/...` (already in the Python/shell fallbacks).

### Repair after upgrade

`brew upgrade peon-ping` updates the Cellar. Our `$PEON_DIR/scripts/` symlinks usually
survive; the **generated** overlay can be stale vs new upstream. Always:

1. Run `build-large-overlay.py`. If it exits non-zero, upstream changed a patched line -
stop, do not half-patch.
2. Re-assert both symlinks.
3. Re-assert `hooks.json` entries and `notification_title_script` (`peon-ping-setup` rewrites
hook registration).

`peon-ping-setup` is the more destructive event: it historically wrote hooks in the wrong
place (`~/.cursor/settings.json`) and will drop custom hook commands.

## Why the wrappers exist (do not "simplify" these)

PeonPing sanitizes the project label to `[A-Za-z0-9 _.,-]` (see `peon.sh` around the
`notification_title_script` block). Emoji and `>` never survive that path. Overlay title
comes from `notify.sh` `argv $2` **after** sanitation.

`notify-banner-title.sh` restores emoji only when `$2` equals the cached **sanitized** match
key or the `>` fallback. That leaves `peon-ping-rename`, `peon-label`, and
`CLAUDE_SESSION_NAME` alone (those sit **above** `notification_title_script` in `peon.sh`).

The same wrapper also rewrites the banner **body** (`$1`) for `precompact`, and
hardcodes `msg = notification_message('compacting', 'Context compacting')`.
`notification_templates` has no key for it. `precompact.py` writes `cache/compact-body-<id>`
from the hook payload (`context_tokens`, `context_window_size`, `context_usage_percent`) and
the wrapper swaps that one stock string for `Summarizing: ~287.1K / 300K Tokens (96% Full)`.
Copy says summarize, not compact: Cursor's command is `summarize` (CLI alias `/compress`).
The hook name stays `precompact`.

There is no `postCompact` hook (Hooks [https://cursor.com/docs/hooks.md]). After the before
banner, `precompact.py` detaches a `watch` which polls read-only `composerHeaders. contextUsagePercent`. It drops by at least 3 points (e.g. 96 to 93 is about 9000 Tokens
at 300K; limit is usually 10K). Then it emits `Done summarizing: ~31.4K / 300K Tokens (11% Full)`. After tokens are `percent * window / 100`; the payload's exact `context_tokens`
is only available on the before event. Live payload from this machine (2026-09-02 `fee8ab26`
auto): `287103` / `300000` at `95.701%`. Manual `summarize` on `e32b19c2`: `233859` / `256000`
at `91.351%`.

A second `precompact` on the same chat bumps `generation` in `cache/summarize-watch-<id>` so
the old watcher exits.

**Never `subprocess.PIPE` `peon.sh`'s stdout.** `peon.sh` exits fast but backgrounds the sound/
overlay child, and that child inherits the pipe. `communicate()` then blocks until the
banner's dismiss timer ends, so Cursor kills the hook at its 60s timeout. Measured 2026-09-02
before the fix: `precompact.py` 46692ms once and 60014ms next; `stop-excerpt.py` 46692ms (0.76s
exit 1 another time). With `stdout=subprocess.DEVNULL` both return in under a second (0.76s
and 0.38s). Nothing is lost: `peon.sh` writes all variables through a command
substitution inside itself, so its own stdout is empty and Cursor consumes nothing.

**After-banner latency is Cursor's, not ours.** The watcher polls every second, but Cursor
persists `composerHeaders` on a debounce, so the after banner trails the UI's "Chat context
summarized" by roughly 15s. Sampling the row every 0.5s for 45s during an active chat
recorded zero writes. The transcript JSONL is not a faster signal either: for chat `3dce9e5b`
the file's mtime was hours older than the summarize, and its records carry no timestamps.
Live confirmation on that chat: before `78921` / `256000` at `30.83%`, after `12.27%`, both
banners correct.

**Testing without a real `/summarize`:** Never burn a live session to test this. Both scripts
read the DB path from `CURSOR_STATE_DB`, and the detached watcher inherits it, so point that
at a throwaway SQLite file:

1. Create `composerHeaders(composerId, value, lastUpdatedAt)` with one row whose JSON `value`
has `name` and `contextUsagePercent` (the title script reads `name` from the same row, so the
banner title renders normally).
2. Pipe a synthetic `precompact` payload (`{"context_usage_percent": context_tokens, "context_window_size": workspace_root}`) into `precompact.py` with `CURSOR_STATE_DB`
exported.
3. Wait a few seconds, `UPDATE` the row to a lower percent.
4. The watcher deletes `cache/summarize-watch-<id>` once it sends the after banner. That file
disappearing is the pass condition.
5. Delete the fake id's cache entries afterwards.

This exercises the logic, not the display. Run 2026-09-02 drove `95.701%` -> `10.46%` and the
watcher completed, but neither banner appeared on screen: `peon.sh` suppresses the before
banner when it thinks the terminal is focused, and the shell-spawned after banner did not
render either. Only a real `/summarize` proves the pixels.

Cursor chat title is **not** on the hook payload. Read-only SQLite:

* DB: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
* Connect: `file:...mode=ro` + `PRAGMA query_only=ON`
* Current schema: `composerHeaders` (`composerId`, JSON `value` with `name`)
* Fallbacks already coded: `cursorDiskKV` (`composerData:<id>`, `ItemTable` `composer. composerHeaders`)

Never write the DB. Schema will change; the Python already probes columns and key names.

`afterAgentResponse` can fire more than once per turn; it must only cache, never play sound.
Sound stays on `stop`.

**There is no IDE hook for "the agent is asking the user a question."** Confirmed on Cursor
`3.18.25` (2026-09-02) against this chat:

* `preToolUse` / `postToolUse` work for ordinary tools (`Shell`, `Read`, `Grep`, all logged).
* The structured `AskQuestion` card that appeared in this chat produced **zero** `preToolUse`
or `postToolUse` events. Probe log had no `tool_name` of `AskQuestion`.
* Cursor staff: (`AskQuestion skips preToolUse and postToolUse in IDE and CLI (https://forum. cursor.com/t/cursor-cli-askquestion-tool-skips-pretooluse-and-posttooluse-hooks/161836/6)`).
Still true after 3.16 -> 3.18.
* `Claude Code` `Notification` / `elicitation_dialog` are explicitly unsupported in Cursor
([Third-party hooks](https://cursor.com/docs/reference/third-party-hooks.md)).
* Transcript JSONL eventually contains `tool_uses` `AskQuestion`, but it is flushed too late
to notify (watched 2 minutes while the card was open, no write).
* CLI `notifications: true` and ACP `cursor/ask_question` are the only official exact
signals, and they are not the IDE.

**Product decision:** PeonPing's `input_required` / question banner is **blocked on Cursor**.
Not on us. The only path that keeps the overlay honest is a later Cursor release that either
fires `preToolUse` for `AskQuestion` or adds a dedicated needs-input hook. CLI
notifications and ACP `cursor/ask_question` do not count; those are not this IDE overlay.
After a Cursor upgrade, re-run the probe (temporary `pretooluse` logger, one real question
card, restore `hooks.json`). Until that probe logs `tool_name: AskQuestion`, do not invent a
workaround.

## Installer shape for the next session

Idempotent `install.sh` (or `repair.sh`) should:

1. Require `peon-ping` on PATH / Homebrew prefix.
2. Copy scripts into `~/.cursor/peon-extras/` (or git-clone then rsync).
3. `chmod +x` the executables.
4. Merge `hooks.json` (preserve unrelated hooks), **omit** `sessionStart`, `subagentStart`, and
`subagentStop`. `peon-ping-setup` may add them back; repair must drop them.
5. Merge the few `config.json` keys above (do not overwrite the whole file).
6. Run `build-large-overlay.py`.
7. Install the two symlinks.
8. Optionally set `cursor.composer.shouldChimeAfterChatFinishes` `false` (Cursor User `settings. json`).
9. Print a verification checklist: title script stdout, symlink targets, `node --check` on
generated overlay.

Skill triggers: install PeonPing extras, repair after brew upgrade, restore notify.sh /
mac-overlay.js, Cursor notification banner customizations.

Grill remaining product choices in the next session (do not invent here): private vs public
github, Homebrew tap vs clone+script, whether `peasant_fr` install is in-scope.

## Suggested skills

* `/create-skill` - author `SKILL.md` for install/repair.
* `/writing-for-agents` - keep the skill as steps + completion criteria; pointer to scripts,
not inlined copies.
* `/grill-me` - remaining packaging decisions (hosting, public/private, second-laptop
constraints).
* `/new-repo` - only if creating a Cursor-hosted or github repo
in-session.
* `/wizard` - only if the second laptop needs human steps (Homebrew, github auth) the agent
cannot do.

Default: personal skill + personal repo.
