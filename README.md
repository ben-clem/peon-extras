# peon-extras

Unofficial Cursor and OpenAI Codex extras for
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
- installs the maintenance skill for both Cursor and Codex;
- rebuilds the macOS overlay and selects `peasant_fr`.

After a Codex install, run `codex` in a terminal, enter `/hooks` in the Codex
CLI, and trust the new user hooks. The Codex Desktop composer does not resolve
`/hooks`. Restart Codex Desktop after trusting the hooks; Codex does not run
unreviewed hooks.

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

## Codex events

The Codex adapter covers:

- session start, prompt submit, approval request, completion, and subagent
  lifecycle events through PeonPing's packaged Codex adapter;
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
