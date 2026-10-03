# peon-extras

Unofficial Cursor, OpenAI Codex, and OpenCode extras for
[peon-ping](https://github.com/PeonPing/peon-ping).

[peon-ping](https://peonping.com) already pings you when an agent starts,
finishes, or needs you. This repo adds a bigger neon overlay, banners that read
`💻 agent 📂 workspace 💬 conversation`, a completion excerpt, and compaction
banners with token counts.

Sounds use the French Warcraft peasant,
[Paysan Humain (FR)](https://openpeon.com/packs/peasant_fr). "Oui messire?" on
submit. "C'est fait!" when the job is done.

This is not a fork. Install peon-ping first.

## Install

Install Homebrew [peon-ping](https://github.com/PeonPing/homebrew-tap) and run
its setup once:

```bash
brew install PeonPing/tap/peon-ping
peon-ping-setup
```

Then:

```bash
git clone https://github.com/ben-clem/peon-extras.git
cd peon-extras
./install.sh
```

The installer:

- installs shared runtime scripts under `~/.local/share/peon-extras/`;
- merges Cursor hooks into `~/.cursor/hooks.json`;
- merges Codex hooks into `~/.codex/hooks.json`;
- installs and registers the OpenCode V2 plugin in `~/.config/opencode/opencode.json`;
- installs the maintenance skill for both Cursor and Codex;
- rebuilds the macOS overlay and selects `peasant_fr`.

The OpenCode installer adds the local plugin path to the `plugins` array. It
preserves other JSON settings and plugin entries, and does not edit
`opencode.jsonc`. Set `XDG_CONFIG_HOME` to use a different OpenCode config
directory. OpenCode V2 loads the plugin on startup; restart a running OpenCode
process after installing or updating it.

When the installer changes a Codex hook definition, run `codex` in a terminal,
enter `/hooks`, and trust the new or changed user hooks. The Codex Desktop
composer does not resolve `/hooks`. Codex records trust against the definition
hash, so runtime-only updates keep existing trust and take effect without a
restart. If Desktop does not pick up a newly trusted definition, restart it.

If the shell cannot find `codex`, install the CLI using OpenAI's official
instructions. Codex Desktop may also contain a bundled executable at
`/Applications/ChatGPT.app/Contents/Resources/codex`; the installer reports
that path when it is available but not on `PATH`.

Current PeonPing releases detect Codex setup only by searching
`~/.codex/config.toml` for the packaged adapter. Because peon-extras uses
Codex's supported `~/.codex/hooks.json` format, `peon status` may still say
`detected (not set up)`. Verify the hooks file or use `/hooks` in the Codex CLI;
do not add the legacy `notify` callback, which would duplicate completion
events.

Re-run `./install.sh` after `brew upgrade peon-ping` or `peon-ping-setup`. If
`build-large-overlay.py` fails, stop. Upstream overlay lines changed.

## Windows

`windows\` is a Node port for Cursor only. It needs Node 22.5 or later (for
`node:sqlite`) and peon-ping installed with its Windows `install.ps1`. From
the clone:

```powershell
node windows\install.mjs
```

The installer copies the runtime to `%USERPROFILE%\.local\share\peon-extras\`,
merges Cursor hooks into `%USERPROFILE%\.cursor\hooks.json`, and replaces
peon-ping's `scripts\win-notify.ps1` with a wrapper. It keeps the packaged
script as `win-notify.stock.ps1`. It backs up every file it rewrites. Re-run
it after re-running peon-ping's `install.ps1`, which overwrites the wrapper.
Execution policy can stay Restricted. The hooks set a process-level Bypass
(`-ExecutionPolicy Bypass` and `PSExecutionPolicyPreference`) for the scripts
they launch.

Banners are a WPF overlay (`win-overlay.ps1`) sized like the macOS one. They
are blue when a chat finishes and red for compaction, sit at top-center, and
stack up to five. A new banner from the same chat replaces the old one. Click a
banner to dismiss it, or it closes after `notification_dismiss_seconds`. The
overlay never takes focus. WPF draws emoji in monochrome. To use the stock
Windows toast instead, set this in
`%USERPROFILE%\.local\share\peon-extras\peon-extras.json`:

```json
{ "banner_style": "toast" }
```

Remove the key to go back to the overlay. The wrapper also falls back to the
toast if the overlay fails. [`windows/SKILL.md`](windows/SKILL.md) covers repair
and verification.

## Codex events

The Codex adapter covers:

- session start, prompt submit, human approval request, completion, and subagent
  lifecycle events through PeonPing's packaged Codex adapter; approval requests
  handled by Codex auto-review stay silent;
- `request_user_input` through a focused `PreToolUse` matcher, producing a blue
  input-required banner with the first question;
- before/after compaction banners through `PreCompact` and `PostCompact`;
- completion excerpts from Codex's stable `last_assistant_message` hook field.

Codex does not expose a conversation title or Desktop project membership in
hook input. The title provider reads `~/.codex/session_index.jsonl` by session
id and checks `~/.codex/state_5.sqlite` read-only. Projectless Codex Desktop
tasks use `Recents`; named projects use their Codex project name. CLI tasks and
failed lookups fall back to the working-directory name. Compaction counts come
from the latest token-count record near the end of the transcript. If an
internal format changes, notifications still fire with fallback copy.

## OpenCode V2 events

The V2 plugin listens to OpenCode's event stream and maps root-session events to
PeonPing notifications. Child sessions are suppressed. It covers prompt
submissions (including the first prompt in a session), completion with the
latest assistant excerpt, questions, permission requests, errors, and
before/after compaction banners. There is no session-start sound, so a blank
session stays quiet until its first prompt. Compaction
usage is estimated from the latest assistant token count and the active model's
context window. The shared title helper combines OpenCode's session title and
working directory into the banner title; the installer configures PeonPing to
use that helper while retaining Cursor and Codex title lookup. The plugin is installed under
`~/.local/share/peon-extras/opencode/`; its Python bridge calls the existing
PeonPing runtime under `~/.claude/hooks/peon-ping/`.

## Overlay on macOS 26

Stock peon-ping banners never appear on macOS 26. JXA's
`ObjC.registerSubclass` hangs in libffi at about 65% CPU until the watchdog
kills it. Sounds still play.

The generator here removes that call and uses a plain event loop instead. The
writeup is [PeonPing/peon-ping#589](https://github.com/PeonPing/peon-ping/issues/589).

## Agents

The maintenance entry point is [`skill/SKILL.md`](skill/SKILL.md), copied to
both `~/.cursor/skills/peon-extras/` and `~/.codex/skills/peon-extras/`.
Preferred settings, adapter boundaries, and verification steps live there.
