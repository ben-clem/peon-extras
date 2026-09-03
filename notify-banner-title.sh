#!/bin/bash
# Installed as ~/.claude/hooks/peon-ping/scripts/notify.sh, which peon.sh prefers
# over the packaged copy. peon.sh strips emoji from the banner title, so restore
# the cached emoji title before delegating to the real notifier.
# Restore the stock behaviour with:
#   ln -sfn /opt/homebrew/opt/peon-ping/libexec/scripts/notify.sh \
#     ~/.claude/hooks/peon-ping/scripts/notify.sh
set -uo pipefail

# The packaged notify.sh reads config.json and packs from PEON_DIR; without this
# it would resolve PEON_DIR to the Homebrew libexec and lose the pack icon.
export PEON_DIR="${PEON_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

delegate="${PEON_NOTIFY_SCRIPT:-}"
if [ -z "$delegate" ]; then
  for candidate in \
    /opt/homebrew/opt/peon-ping/libexec/scripts/notify.sh \
    /usr/local/opt/peon-ping/libexec/scripts/notify.sh; do
    if [ -f "$candidate" ]; then
      delegate="$candidate"
      break
    fi
  done
fi
[ -n "$delegate" ] || exit 0

match_title=""
banner_title=""
fallback_title=""
safe_id="${PEON_SESSION_ID:-}"
safe_id="${safe_id//[^A-Za-z0-9_-]/}"
if [ -n "$safe_id" ]; then
  cache_file="$HOME/.cursor/peon-extras/cache/banner-title-${safe_id:0:64}"
  if [ -f "$cache_file" ]; then
    { IFS= read -r match_title
      IFS= read -r banner_title
      IFS= read -r fallback_title
    } < "$cache_file" || true
  fi
fi

# Swap only the title this session cached, so a .peon-label or /peon-ping-rename
# title still reaches the banner untouched. peon.sh strips ">", so $2 matches
# the sanitized key; restore emoji, or the ">" fallback if the emoji row is empty.
incoming_title="${2:-}"
new_title="$incoming_title"
display_title="$banner_title"
[ -n "$display_title" ] || display_title="$fallback_title"
if [ -n "$display_title" ] && {
     { [ -n "$match_title" ] && [ "$incoming_title" = "$match_title" ]; } \
  || { [ -n "$fallback_title" ] && [ "$incoming_title" = "$fallback_title" ]; }
}; then
  new_title="$display_title"
fi

# peon.sh hardcodes the PreCompact body and offers no template key for it.
# precompact.py caches the real Summarizing line; fall back to a short phrase
# if that file is missing. Any other body reaches the banner untouched.
new_msg="${1:-}"
if [ "$new_msg" = "compacting: Context compacting" ]; then
  compact_body=""
  if [ -n "$safe_id" ]; then
    compact_file="$HOME/.cursor/peon-extras/cache/compact-body-${safe_id:0:64}"
    if [ -f "$compact_file" ]; then
      IFS= read -r compact_body < "$compact_file" || true
    fi
  fi
  if [ -n "$compact_body" ]; then
    new_msg="$compact_body"
  else
    new_msg="Summarizing this chat now"
  fi
fi

if [ "$#" -ge 2 ]; then
  set -- "$new_msg" "$new_title" "${@:3}"
elif [ "$#" -eq 1 ]; then
  set -- "$new_msg"
fi

exec bash "$delegate" "$@"
