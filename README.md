# peon-extras

Unofficial Cursor extras for [peon-ping](https://github.com/PeonPing/peon-ping).

[peon-ping](https://peonping.com) already pings you when the agent starts, finishes, or needs you. This repo is what I run on top of it in Cursor: a bigger neon overlay, banners that read `📂 workspace 💬 chat-title`, a stop excerpt from the reply, and summarize banners with token counts.

Sounds are the French Warcraft peasant, [Paysan Humain (FR)](https://openpeon.com/packs/peasant_fr). "Oui messire?" on submit. "C'est fait!" when the job is done.

Not a fork. Install peon-ping first.

## Install

Homebrew [peon-ping](https://github.com/PeonPing/homebrew-tap) and one `peon-ping-setup` run:

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

Re-run `./install.sh` after `brew upgrade peon-ping` or `peon-ping-setup`. The installer copies scripts, wires Cursor hooks, rebuilds the overlay, and installs `peasant_fr`.

If `build-large-overlay.py` fails, stop. Upstream overlay lines changed.

## Overlay on macOS 26

Stock peon-ping banners never appear on macOS 26. JXA's `ObjC.registerSubclass` hangs in libffi at about 65% CPU until the watchdog kills it. Sounds still play.

The generator here drops that call and uses a plain event loop instead. Writeup is [PeonPing/peon-ping#589](https://github.com/PeonPing/peon-ping/issues/589).

## Agents

Entry point is [`skill/SKILL.md`](skill/SKILL.md), copied to `~/.cursor/skills/peon-extras/`. Preferred settings and wrapper seams live there. `./install.sh` reapplies them.
