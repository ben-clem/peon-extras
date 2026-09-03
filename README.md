# peon-extras

Cursor-side extras for Homebrew `peon-ping`: larger neon overlay,
workspace + chat title, stop excerpt, and summarize banners.

## Install / repair

On a Mac that already has Homebrew `peon-ping` and has run `peon-ping-setup`:

```bash
git clone https://github.com/ben-clem/peon-extras.git
cd peon-extras
./install.sh
```

Re-run `./install.sh` after `brew upgrade peon-ping` or `peon-ping-setup`.
The installer also installs and selects the `peasant_fr` sound pack.

If `build-large-overlay.py` fails, stop; upstream overlay lines changed.

The generated overlay also works around a macOS 26 bug: JXA's
`ObjC.registerSubclass` hangs forever there, so the stock peon-ping banner
never appears. The generator replaces it with a plain event loop.

Agent entry point: `skill/SKILL.md` (copied to `~/.cursor/skills/peon-extras/`).
Why the wrappers exist: `HANDOFF.md`.
