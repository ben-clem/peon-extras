#!/bin/bash
# Idempotent install/repair for Cursor PeonPing extras.
# Safe to re-run after `brew upgrade peon-ping` or `peon-ping-setup`.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${PEON_EXTRAS_DIR:-$HOME/.cursor/peon-extras}"
PEON_DIR="${PEON_DIR:-$HOME/.claude/hooks/peon-ping}"
HOOKS_JSON="${CURSOR_HOOKS_JSON:-$HOME/.cursor/hooks.json}"
SETTINGS_JSON="${CURSOR_USER_SETTINGS:-$HOME/Library/Application Support/Cursor/User/settings.json}"
SKILL_DEST="$HOME/.cursor/skills/peon-extras"
PEON_SH="$PEON_DIR/peon.sh"
CONFIG_JSON="$PEON_DIR/config.json"

RUNTIME_FILES=(
  _cache.py
  _usage.py
  build-large-overlay.py
  capture-response.py
  cursor-notification-title.py
  notify-banner-title.sh
  precompact.py
  stop-excerpt.py
)

die() {
  echo "install.sh: $*" >&2
  exit 1
}

find_brew_peon() {
  if command -v brew >/dev/null 2>&1; then
    prefix="$(brew --prefix peon-ping 2>/dev/null || true)"
    if [ -n "$prefix" ] && [ -d "$prefix" ]; then
      echo "$prefix"
      return 0
    fi
  fi
  for prefix in /opt/homebrew/opt/peon-ping /usr/local/opt/peon-ping; do
    if [ -d "$prefix" ]; then
      echo "$prefix"
      return 0
    fi
  done
  return 1
}

find_peon_cli() {
  if command -v peon >/dev/null 2>&1; then
    command -v peon
    return 0
  fi
  for candidate in \
    "${BREW_PEON:-}/bin/peon" \
    /opt/homebrew/bin/peon \
    /usr/local/bin/peon; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

echo "== require peon-ping =="
BREW_PEON="$(find_brew_peon || true)"
if [ -z "$BREW_PEON" ] || [ ! -d "$BREW_PEON" ]; then
  die "peon-ping Homebrew prefix not found. Install peon-ping, then re-run."
fi
[ -f "$PEON_SH" ] || die "missing $PEON_SH (run peon-ping-setup once, then re-run this script)"
[ -f "$CONFIG_JSON" ] || die "missing $CONFIG_JSON"

echo "brew prefix: $BREW_PEON"
echo "PEON_DIR:    $PEON_DIR"
echo "dest:        $DEST"

echo "== copy runtime scripts =="
mkdir -p "$DEST"
for name in "${RUNTIME_FILES[@]}"; do
  src="$REPO_DIR/$name"
  [ -f "$src" ] || die "missing $src (run from the peon-extras clone)"
  if [ "$src" != "$DEST/$name" ]; then
    cp "$src" "$DEST/$name"
  fi
done
rm -f "$DEST/HANDOFF.md"
chmod +x \
  "$DEST/build-large-overlay.py" \
  "$DEST/capture-response.py" \
  "$DEST/cursor-notification-title.py" \
  "$DEST/notify-banner-title.sh" \
  "$DEST/precompact.py" \
  "$DEST/stop-excerpt.py"

echo "== Cursor skill =="
if [ -f "$REPO_DIR/skill/SKILL.md" ]; then
  mkdir -p "$SKILL_DEST"
  cp "$REPO_DIR/skill/SKILL.md" "$SKILL_DEST/SKILL.md"
  echo "skill: $SKILL_DEST/SKILL.md"
fi

echo "== merge hooks.json =="
python3 - "$HOOKS_JSON" "$DEST" "$PEON_SH" <<'PY'
import json, os, sys

hooks_path, dest, peon_sh = sys.argv[1], sys.argv[2], sys.argv[3]
ours = {
    "beforeSubmitPrompt": peon_sh,
    "afterAgentResponse": os.path.join(dest, "capture-response.py"),
    "stop": os.path.join(dest, "stop-excerpt.py"),
    "postToolUseFailure": peon_sh,
    "preCompact": os.path.join(dest, "precompact.py"),
}
drop_events = ("sessionStart", "sessionStop", "subagentStart", "subagentStop")
peon_needles = ("peon-ping", "peon-extras", "peon.sh", "capture-title", "session-title", "pretooluse-probe")
alias_drop = ("precompact",)


def load(path):
    if not os.path.isfile(path):
        return {"version": 1, "hooks": {}}
    with open(path) as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"version": 1, "hooks": {}}
    if "hooks" not in data and any(k in data for k in list(ours) + ["precompact"]):
        migrated = {"version": int(data.get("version") or 1), "hooks": {}}
        for key, value in data.items():
            if key == "version":
                continue
            if isinstance(value, str):
                migrated["hooks"][key] = [{"command": value}]
            elif isinstance(value, list):
                migrated["hooks"][key] = value
        return migrated
    data.setdefault("version", 1)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        data["hooks"] = {}
    return data


def is_peon_cmd(command):
    text = str(command or "")
    return any(needle in text for needle in peon_needles)


def entries(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"command": item} for item in value]
    if isinstance(value, dict):
        return [value]
    return [{"command": value}]


data = load(hooks_path)
hooks = data["hooks"]

for alias in alias_drop:
    if alias in hooks and "preCompact" not in hooks:
        hooks["preCompact"] = hooks[alias]
    hooks.pop(alias, None)

for event, command in ours.items():
    kept = [item for item in entries(hooks.get(event)) if not is_peon_cmd(item.get("command"))]
    kept.append({"command": command})
    hooks[event] = kept

for event in drop_events:
    kept = [item for item in entries(hooks.get(event)) if not is_peon_cmd(item.get("command"))]
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)

os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
with open(hooks_path, "w") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
print("wrote", hooks_path)
PY

echo "== merge peon-ping config.json =="
python3 - "$CONFIG_JSON" "$DEST" <<'PY'
import json, os, sys

path = sys.argv[1]
dest = sys.argv[2]
with open(path) as handle:
    data = json.load(handle)
if not isinstance(data, dict):
    raise SystemExit("config.json is not an object")

# peon.sh runs this with shell=True from the workspace, not $PEON_DIR/scripts.
# A bare filename is "command not found" and the banner falls back to the repo name.
title_script = os.path.join(dest, "cursor-notification-title.py")
data["notification_title_script"] = "python3 {}".format(json.dumps(title_script))
data["notification_title_marker"] = " > "
data["notification_dismiss_seconds"] = 30
data["overlay_theme"] = "neon"
data["volume"] = 0.25
data["suppress_subagent_complete"] = True
data["default_pack"] = "peasant_fr"

templates = data.get("notification_templates")
if not isinstance(templates, dict):
    templates = {}
templates["stop"] = "{summary}"
data["notification_templates"] = templates

categories = data.get("categories")
if not isinstance(categories, dict):
    categories = {}
# peon.sh reads dotted CESP keys (cats.get("task.acknowledge")), not nested
# dicts. Nested task/acknowledge is ignored and submit stays silent.
categories["session.start"] = True
categories["task.acknowledge"] = True
categories["resource.limit"] = True
categories.pop("task", None)
categories.pop("resource", None)
data["categories"] = categories

with open(path, "w") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
print("wrote", path)
PY

echo "== peasant_fr pack =="
PEON_CLI="$(find_peon_cli || true)"
[ -n "$PEON_CLI" ] || die "peon CLI not on PATH; cannot install peasant_fr"
if "$PEON_CLI" packs use --install peasant_fr; then
  echo "pack: peasant_fr (use --install)"
elif "$PEON_CLI" packs install peasant_fr && "$PEON_CLI" packs use peasant_fr; then
  echo "pack: peasant_fr (install + use)"
else
  die "failed to install/use peasant_fr via $PEON_CLI"
fi

echo "== generate overlay =="
python3 "$DEST/build-large-overlay.py"

echo "== symlinks =="
mkdir -p "$PEON_DIR/scripts"
ln -sfn "$DEST/cursor-notification-title.py" "$PEON_DIR/scripts/cursor-notification-title.py"
ln -sfn "$DEST/notify-banner-title.sh" "$PEON_DIR/scripts/notify.sh"
ln -sfn "$DEST/mac-overlay-large.js" "$PEON_DIR/scripts/mac-overlay.js"
ls -l "$PEON_DIR/scripts/cursor-notification-title.py" "$PEON_DIR/scripts/notify.sh" "$PEON_DIR/scripts/mac-overlay.js"

echo "== Cursor finish chime =="
python3 - "$SETTINGS_JSON" <<'PY'
import json, os, sys

path = sys.argv[1]
os.makedirs(os.path.dirname(path), exist_ok=True)
data = {}
if os.path.isfile(path) and os.path.getsize(path):
    try:
        with open(path) as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            data = loaded
        else:
            print("skip chime: settings.json is not an object")
            raise SystemExit(0)
    except json.JSONDecodeError:
        print("skip chime: settings.json is not strict JSON")
        raise SystemExit(0)
data["cursor.composer.shouldChimeAfterChatFinishes"] = False
with open(path, "w") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
print("wrote", path)
PY

echo
echo "== verification =="
echo "peon.sh: $PEON_SH"
echo "title script stdout (no session; exit 1 is ok):"
set +e
PEON_CWD="$DEST" PEON_SESSION_ID="" python3 "$DEST/cursor-notification-title.py"
title_rc=$?
set -e
echo "title script exit: $title_rc"
echo "notify.sh -> $(readlink "$PEON_DIR/scripts/notify.sh")"
echo "mac-overlay.js -> $(readlink "$PEON_DIR/scripts/mac-overlay.js")"
echo "title script -> $(readlink "$PEON_DIR/scripts/cursor-notification-title.py")"
if command -v node >/dev/null 2>&1; then
  node --check "$DEST/mac-overlay-large.js"
  echo "node --check: ok"
else
  echo "node --check: skipped (node not on PATH)"
fi
python3 - "$HOOKS_JSON" "$CONFIG_JSON" <<'PY'
import json, sys
hooks = json.load(open(sys.argv[1])).get("hooks", {})
cfg = json.load(open(sys.argv[2]))
for event in (
    "beforeSubmitPrompt",
    "afterAgentResponse",
    "stop",
    "postToolUseFailure",
    "preCompact",
    "sessionStart",
    "subagentStart",
    "subagentStop",
):
    print("hook {}: {}".format(event, hooks.get(event)))
print("notification_title_script:", cfg.get("notification_title_script"))
print("notification_title_marker:", cfg.get("notification_title_marker"))
print("notification_templates.stop:", (cfg.get("notification_templates") or {}).get("stop"))
print("notification_dismiss_seconds:", cfg.get("notification_dismiss_seconds"))
print("overlay_theme:", cfg.get("overlay_theme"))
print("volume:", cfg.get("volume"))
print("suppress_subagent_complete:", cfg.get("suppress_subagent_complete"))
print("default_pack:", cfg.get("default_pack"))
print("categories.session.start:", (cfg.get("categories") or {}).get("session.start"))
print("categories.task.acknowledge:", (cfg.get("categories") or {}).get("task.acknowledge"))
print("categories.resource.limit:", (cfg.get("categories") or {}).get("resource.limit"))
PY
echo "install/repair complete."
