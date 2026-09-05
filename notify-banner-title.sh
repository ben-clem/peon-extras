#!/bin/bash
# Installed as ~/.claude/hooks/peon-ping/scripts/notify.sh, which peon.sh prefers
# over the packaged copy. Restores the cached emoji title, swaps the stock
# PreCompact body, and zeros the session stacking count so a second banner
# within 30s still replaces the live overlay without a "(N)" prefix.
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
script_path="${BASH_SOURCE[0]}"
if [ -L "$script_path" ]; then
  script_path="$(readlink "$script_path")"
fi
cache_dir="${PEON_EXTRAS_CACHE_DIR:-$(cd "$(dirname "$script_path")" && pwd)/cache}"
if [ -n "$safe_id" ]; then
  cache_file="$cache_dir/banner-title-${safe_id:0:64}"
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
    compact_file="$cache_dir/compact-body-${safe_id:0:64}"
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

# The packaged notify.sh prepends a "(N)" badge to both the title and the body
# once two notifications share a session, and with notification_dismiss_seconds
# at 30 that happens often. Resetting only the count field keeps the slot and
# pid fields, so the delegate still replaces the live overlay and still
# auto-dismisses on resume.
if [ -n "${PEON_SESSION_ID:-}" ] && [ "$safe_id" = "$PEON_SESSION_ID" ]; then
  stack_file="/tmp/peon-ping-popups/.session-${PEON_SESSION_ID}"
  if [ -f "$stack_file" ]; then
    IFS='|' read -r stack_slot stack_pids _ < "$stack_file" || true
    case "$stack_slot" in
      *[!0-9]*) ;;
      *) printf "%s|%s|0\n" "$stack_slot" "$stack_pids" > "$stack_file" || true ;;
    esac
  fi
fi

if [ "$#" -ge 2 ]; then
  set -- "$new_msg" "$new_title" "${@:3}"
elif [ "$#" -eq 1 ]; then
  set -- "$new_msg"
fi

exec bash "$delegate" "$@"
