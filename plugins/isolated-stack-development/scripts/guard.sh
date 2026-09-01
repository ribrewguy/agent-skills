#!/usr/bin/env bash
# guard.sh — PreToolUse hook for isolated-stack-development.
#
# Fires on every Bash tool call; exits 0 instantly for repos with no
# .isolated-stack.json (a repo without a declaration is out of scope) and for
# commands that do not touch a stack.
#
# Teeth only where the damage is irreversible (data loss):
#   BLOCK  a reset/provision whose resolved target is a stack this directory
#          does not own (ownership), or the shared stack while any isolated
#          stack is live (live-stack).
#   BLOCK  `supabase stop` whose resolved target is not this directory's
#          stack — from a mispointed worktree it stops the shared stack for
#          everyone.
#   WARN   `supabase start` / dev servers from the main checkout while
#          worktrees exist, or from a worktree whose config is not yet
#          isolated. Recoverable and sometimes deliberate: inject context,
#          never block. An over-blocking hook is the kind people disable.
#
# Block = exit 2 with the reason (and the corrected command) on stderr.

set -uo pipefail

INPUT=$(cat)

parsed=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("tool_input", {}).get("command", "").replace("\n", " "))
print(d.get("cwd", ""))' 2>/dev/null) || exit 0
CMD=$(printf '%s\n' "$parsed" | sed -n 1p)
CWD=$(printf '%s\n' "$parsed" | sed -n 2p)
[ -n "$CMD" ] || exit 0
[ -d "$CWD" ] || CWD=$(pwd)

# --- classify the command; get out fast if it is not stack-affecting -------
is_reset=0; is_stop=0; is_start=0
case " $CMD " in
  *"supabase db reset"*|*" db:reset"*|*" db:provision"*) is_reset=1 ;;
esac
case " $CMD " in *"supabase stop"*) is_stop=1 ;; esac
case " $CMD " in
  *"supabase start"*|*"supabase:up"*|*"pnpm dev"*|*"npm run dev"*|*"yarn dev"*|*"pnpm run dev"*) is_start=1 ;;
esac
[ $((is_reset + is_stop + is_start)) -gt 0 ] || exit 0

# If the command cd's somewhere first, judge from where it will actually run.
first_cd=$(printf '%s' "$CMD" | sed -nE 's/^ *cd +("([^"]+)"|([^ ;&|]+)).*/\2\3/p')
if [ -n "$first_cd" ]; then
  case "$first_cd" in
    /*) CWD=$first_cd ;;
    *)  CWD="$CWD/$first_cd" ;;
  esac
fi

REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
DECL="$REPO_ROOT/.isolated-stack.json"
[ -f "$DECL" ] || exit 0   # no declaration: this repo has no stack story

json() { python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d=d[k]
print(d)' "$DECL" "$1" 2>/dev/null; }
PREFIX=$(json stackPrefix) || exit 0
CONFIG="$REPO_ROOT/$(json supabase.config)" 2>/dev/null
[ -f "$CONFIG" ] || exit 0

GIT_DIR=$(git -C "$CWD" rev-parse --absolute-git-dir 2>/dev/null)
# --git-common-dir can return a path relative to the queried directory;
# resolve it from there, not from the hook process's own cwd.
GIT_COMMON=$(cd "$CWD" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd)
[ -n "$GIT_DIR" ] && [ -n "$GIT_COMMON" ] || exit 0
if [ "$GIT_DIR" != "$GIT_COMMON" ]; then IS_WORKTREE=1; else IS_WORKTREE=0; fi

branch=$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ -n "$branch" ] && [ "$branch" != "HEAD" ]; then owner=$branch; else owner=$(basename "$REPO_ROOT"); fi
owner=$(printf '%s' "$owner" | tr '[:upper:]/' '[:lower:]-' | tr -c 'a-z0-9-' '-' | sed -e 's/--*/-/g' -e 's/^-//' -e 's/-$//' | cut -c1-40)
if [ "$IS_WORKTREE" = 1 ]; then OWNED="${PREFIX}-${owner}"; else OWNED="$PREFIX"; fi

TARGET=$(grep -E '^ *project_id *=' "$CONFIG" | head -1 | sed -E 's/.*= *"?([^"]*)"?.*/\1/')
[ -n "$TARGET" ] || exit 0

isolated_live() {
  docker ps --format '{{.Label "com.supabase.cli.project"}}' 2>/dev/null \
    | grep -E "^${PREFIX}-" | sort -u
}

live_worktrees() {
  git -C "$REPO_ROOT" worktree list --porcelain 2>/dev/null | awk '/^worktree /{n++} END{print n+0}'
}

block() { printf '%s\n' "$*" >&2; exit 2; }
warn() {
  printf '%s' "$1" | python3 -c '
import json, sys
msg = sys.stdin.read()
print(json.dumps({
  "systemMessage": msg,
  "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                          "additionalContext": msg}}))'
  exit 0
}

# ------------------------------------------------------------- reset (BLOCK)
if [ $is_reset = 1 ]; then
  if [ "$TARGET" != "$OWNED" ]; then
    if [ "$TARGET" = "$PREFIX" ]; then
      block "BLOCKED: this reset would hit the SHARED stack '$PREFIX' — this worktree's config is not isolated yet, so the reset resolves to the shared database and destroys state every workstream depends on. Stand up this worktree's own stack first: \"\${CLAUDE_PLUGIN_ROOT}/scripts/stack\" up — then re-run the reset against it."
    else
      block "BLOCKED: this reset resolves project_id '$TARGET' but the current directory owns '$OWNED'. A database reset destroys that stack's data and it is not yours. Run it from the checkout that owns '$TARGET', with the cd and the command in ONE invocation."
    fi
  fi
  if [ "$TARGET" = "$PREFIX" ]; then
    live=$(isolated_live)
    if [ -n "$live" ]; then
      block "BLOCKED: this would reset the SHARED stack '$PREFIX' while isolated stack(s) are live ($(printf '%s' "$live" | tr '\n' ' ')). The shared stack is the trunk-parity reference for that in-flight work; resetting it now destroys state others depend on. Tear the isolated stacks down first, or reset your own isolated stack from its worktree instead."
    fi
  fi
  exit 0
fi

# -------------------------------------------------------------- stop (BLOCK)
if [ $is_stop = 1 ]; then
  if [ "$TARGET" != "$OWNED" ]; then
    block "BLOCKED: 'supabase stop' resolves its config from the current directory, and here that is project_id '$TARGET' — a stack this directory does not own (it owns '$OWNED'). From a worktree still pointed at the shared config this stops the shared stack for EVERYONE. Fix the config (or run the teardown tool, which asserts ownership) before stopping: \"\${CLAUDE_PLUGIN_ROOT}/scripts/stack\" down"
  fi
  exit 0
fi

# ------------------------------------------------------------ start (WARN)
if [ $is_start = 1 ]; then
  if [ "$IS_WORKTREE" = 0 ] && [ "$(live_worktrees)" -gt 1 ]; then
    warn "Heads-up from the stack guard: this starts the SHARED stack/app from the main checkout while linked worktrees exist. If this run is for worktree work, it is pointed at the wrong stack — run it from the worktree with an isolated stack (\"\${CLAUDE_PLUGIN_ROOT}/scripts/stack\" up from the worktree). If shared-stack use is deliberate, proceed."
  fi
  if [ "$IS_WORKTREE" = 1 ] && [ "$TARGET" = "$PREFIX" ]; then
    warn "Heads-up from the stack guard: you are in a worktree but $CONFIG still carries the SHARED project_id '$PREFIX' — this start would collide with (or impersonate) the shared stack. Stand up an isolated stack first: \"\${CLAUDE_PLUGIN_ROOT}/scripts/stack\" up"
  fi
  exit 0
fi

exit 0
