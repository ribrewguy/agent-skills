#!/usr/bin/env bash
# guard.sh — PreToolUse hook for local-https.
#
# Fires on every Bash tool call; exits 0 instantly unless the command
# launches a server (or disables TLS verification).
#
#   BLOCK  NODE_TLS_REJECT_UNAUTHORIZED=0 anywhere, in any repo.
#   BLOCK  (declared repos) a launch whose declared, non-opted-out server
#          directory has no .cert/<project>.pem. The message names
#          `local-https copy` when a linked worktree's main checkout has the
#          cert, else `local-https setup <dir>`.
#   WARN   (allow with injected context) an undeclared repo's launch without a
#          cert; http://localhost|127.0.0.1:<declared port>; `-- --port|--host`
#          after pnpm|npm|yarn|bun run; a Node launch without
#          NODE_EXTRA_CA_CERTS; a worktree cert older than the main checkout's.
#
# Never fires on test, build, lint, install, docker compose or supabase
# commands, or outside a git repository. Block = exit 2, reason on stderr.
# Declaration values are untrusted: they are read only by decl.py (which
# validates them) and are used as data, never interpolated into commands.

set -uo pipefail
set -f

INPUT=$(cat)
HERE=$(cd "$(dirname "$0")" && pwd)

parsed=$(printf '%s' "$INPUT" | python3 -I -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("tool_input", {}).get("command", "").replace("\n", " "))
print(d.get("cwd", ""))' 2>/dev/null) || exit 0
CMD=$(printf '%s\n' "$parsed" | sed -n 1p)
CWD=$(printf '%s\n' "$parsed" | sed -n 2p)
[ -n "$CMD" ] || exit 0
[ -d "$CWD" ] || CWD=$(pwd)

block() { printf '%s\n' "$*" >&2; exit 2; }
emit_warn() {
  printf '%s' "$1" | python3 -I -c '
import json, sys
msg = sys.stdin.read()
print(json.dumps({
  "systemMessage": msg,
  "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                          "additionalContext": msg}}))'
}

# Verification bypass: always blocked, in any repo.
case "$CMD" in
  *NODE_TLS_REJECT_UNAUTHORIZED=0*|*'NODE_TLS_REJECT_UNAUTHORIZED="0"'*|*"NODE_TLS_REJECT_UNAUTHORIZED='0'"*)
    block "local-https: NODE_TLS_REJECT_UNAUTHORIZED=0 turns off certificate verification for the whole process. Trust the mkcert CA instead: export NODE_EXTRA_CA_CERTS=\"\$(mkcert -CAROOT)/rootCA.pem\" (see: local-https trust)." ;;
esac

# --- classify: is this a server launch? (cheap pattern list first) ----------
SEP='(^|[;&|(]|&&)[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^ ]*[[:space:]]+)*'
PM='(pnpm|npm|yarn|bun)'
launch_re=(
  "${SEP}(npx +|pnpm +(exec +)?|yarn +|bunx? +)?(nuxt|nuxi) +dev"
  "${SEP}(npx +|pnpm +(exec +)?|yarn +|bunx? +)?next +(dev|start)"
  "${SEP}(npx +|pnpm +(exec +)?|yarn +|bunx? +)?vite( +(dev|preview|serve))?([[:space:]]+-|[[:space:]]*($|[;&|]))"
  "${SEP}${PM}[[:space:]]+((run|exec|-[-A-Za-z]+([ =][^ ;&|-][^ ;&|]*)?)[[:space:]]+)*(dev|start|serve|preview)([[:space:]]|$|[;&|])"
  "${SEP}(node|bun|deno)[[:space:]]+(-[^ ]+ +)*[^ ;&|]*(server|app|index|main)[^ ;&|]*\\.(m|c)?(js|ts)"
  "${SEP}(npx +)?(tsx|ts-node|nodemon)([[:space:]]|$)"
  "(mvnw?|\\./mvnw)[[:space:]].*spring-boot:run"
  "(gradlew?|\\./gradlew)[[:space:]].*bootRun"
  "${SEP}java[[:space:]].*-jar"
  "${SEP}(python3? +-m +)?uvicorn"
  "${SEP}(python3? +-m +)?flask +run"
  "python3?[[:space:]]+-m[[:space:]]+http\\.server"
  "manage\\.py[[:space:]]+runserver"
  "${SEP}deno[[:space:]]+run"
)
is_launch=0
for re in "${launch_re[@]}"; do
  if [[ "$CMD" =~ $re ]]; then is_launch=1; break; fi
done
# Resolve the directory the command runs from (a leading cd).
first_cd=$(printf '%s' "$CMD" | sed -nE 's/^ *cd +("([^"]+)"|([^ ;&|]+)).*/\2\3/p')
if [ -n "$first_cd" ]; then
  case "$first_cd" in
    /*) CWD=$first_cd ;;
    *)  CWD="$CWD/$first_cd" ;;
  esac
fi
CWD=$(cd "$CWD" 2>/dev/null && pwd -P) || exit 0
REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
REPO_ROOT=$(cd "$REPO_ROOT" && pwd -P)
DECL="$REPO_ROOT/.local-https.json"

# Declared per-server launch patterns (grep -E) extend the list.
if [ $is_launch = 0 ] && [ -f "$DECL" ]; then
  while IFS= read -r rx; do
    [ -n "$rx" ] || continue
    if printf '%s' "$CMD" | grep -Eq -- "$rx" 2>/dev/null; then is_launch=1; break; fi
  done < <(python3 -I -c '
import json, sys
try:
    for s in json.load(open(sys.argv[1])).get("servers", []):
        for rx in s.get("launch", []):
            if isinstance(rx, str): print(rx.replace("\n", " "))
except Exception:
    pass' "$DECL" 2>/dev/null)
fi
[ $is_launch = 1 ] || exit 0

case "$CWD/" in "$REPO_ROOT"/*) ;; *) exit 0 ;; esac
REL=${CWD#"$REPO_ROOT"}; REL=${REL#/}; REL=${REL:-.}
GIT_DIR=$(git -C "$CWD" rev-parse --absolute-git-dir 2>/dev/null)
GIT_COMMON=$(cd "$CWD" && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)
MAIN_ROOT=$(dirname "$GIT_COMMON")
IS_WORKTREE=0
[ -n "$GIT_DIR" ] && [ -n "$GIT_COMMON" ] && [ "$(cd "$GIT_DIR" && pwd -P)" != "$GIT_COMMON" ] && IS_WORKTREE=1

# --- declaration facts (validated by decl.py) -------------------------------
out=$(python3 -I "$HERE/lib/decl.py" "$REPO_ROOT" --main-root "$MAIN_ROOT" --server "$REL" 2>&1); rc=$?
if [ $rc -ne 0 ]; then
  emit_warn "local-https: .local-https.json is invalid, so the TLS rule could not be checked: $(printf '%s' "$out" | tr '\n' ' ')"
  exit 0
fi
DECLARED=0 PROJECT="" SERVER_HTTPS=true; SERVERS=()
while IFS='=' read -r k v; do
  case "$k" in
    declared) DECLARED=$v ;; project) PROJECT=$v ;; server_https) SERVER_HTTPS=$v ;;
    server) SERVERS+=("$v") ;;
  esac
done <<<"$out"
[ -n "$PROJECT" ] || exit 0

has_workspaces=0
[ -f "$REPO_ROOT/pnpm-workspace.yaml" ] && has_workspaces=1
grep -q '"workspaces"' "$REPO_ROOT/package.json" 2>/dev/null && has_workspaces=1

# Which server dirs does this launch concern?
TARGETS=(); is_root_launch=0
if [ "$REL" = . ] && { [ $has_workspaces = 1 ] || [ ${#SERVERS[@]} -gt 0 ]; }; then
  is_root_launch=1
  TARGETS=(${SERVERS[@]+"${SERVERS[@]}"})
else
  matched=""
  for d in ${SERVERS[@]+"${SERVERS[@]}"}; do
    case "$REL/" in "$d"/*) matched=$d; break ;; esac
  done
  if [ -n "$matched" ]; then TARGETS=("$matched")
  elif [ "$DECLARED" = 1 ] && [ "$SERVER_HTTPS" = false ]; then exit 0   # opted out
  else TARGETS=("$REL"); fi
fi

# An opted-out dir launched directly is allowed silently.
if [ $is_root_launch = 0 ] && [ "$DECLARED" = 1 ] && [ "$SERVER_HTTPS" = false ]; then exit 0; fi

has_cert() { [ -f "$REPO_ROOT/$1/.cert/$PROJECT.pem" ]; }
main_has_cert() { [ $IS_WORKTREE = 1 ] && [ -f "$MAIN_ROOT/$1/.cert/$PROJECT.pem" ]; }

declared_dir() { local d; for d in ${SERVERS[@]+"${SERVERS[@]}"}; do [ "$d" = "$1" ] && return 0; done; return 1; }

if [ $is_root_launch = 1 ] && [ ${#TARGETS[@]} -eq 0 ]; then
  # Undeclared monorepo root: name each candidate server directory.
  set +f
  for d in apps/*/package.json services/*/package.json; do
    [ -f "$REPO_ROOT/$d" ] && TARGETS+=("$(dirname "$d")")
  done
  set -f
fi

blocks=""; warns=""
for d in ${TARGETS[@]+"${TARGETS[@]}"}; do
  [ "$d" = . ] && q=. || printf -v q '%q' "$d"
  if has_cert "$d"; then
    if main_has_cert "$d" && [ "$MAIN_ROOT/$d/.cert/$PROJECT.pem" -nt "$REPO_ROOT/$d/.cert/$PROJECT.pem" ]; then
      warns+="The cert in $d/.cert is older than the main checkout's: run local-https copy. "
    fi
    continue
  fi
  if main_has_cert "$d"; then fix="local-https copy"; else fix="local-https setup $q"; fi
  if [ "$DECLARED" = 1 ] && { declared_dir "$d" || [ $is_root_launch = 1 ]; }; then
    blocks+="Server $d has no .cert/$PROJECT.pem (TLS is required for every local server). Run: $fix. If the hosts entry is missing, the tool prints the line for the owner to add; the owner can opt this server out with https:false and a reason in .local-https.json. "
  else
    warns+="No TLS cert for $d (the rule: every local server runs on TLS at ${PROJECT}-local). Run: $fix, then start the server with the generated .cert/ pair. "
  fi
done
[ -z "$blocks" ] || block "local-https: $blocks"

# --- warnings that apply once the cert exists --------------------------------
if [[ "$CMD" =~ http://(localhost|127\.0\.0\.1):([0-9]+) ]]; then
  port=${BASH_REMATCH[2]}
  hit=$(python3 -I -c '
import json, sys
try:
    for s in json.load(open(sys.argv[1])).get("servers", []):
        if s.get("port") == int(sys.argv[2]) and s.get("https") is not False: print("1")
except Exception:
    pass' "$DECL" "$port" 2>/dev/null)
  [ -z "$hit" ] || warns+="http://localhost:$port points at a declared HTTPS server: use https://${PROJECT}-local:$port. "
fi
dd_re="${PM}[[:space:]]+(run[[:space:]]+)?[^;&|]*[[:space:]]--[[:space:]]+--(port|host)"
if [[ "$CMD" =~ $dd_re ]]; then
  warns+="A bare -- before --port/--host can make the framework ignore its TLS config; pass the flag without the -- (for example: pnpm exec nuxt dev --port N). "
fi
if [[ "$CMD" =~ (node|tsx|ts-node|nodemon|nuxt|nuxi|vite|next|pnpm|npm|yarn|bun) ]] \
   && [[ "$CMD" != *NODE_EXTRA_CA_CERTS* ]] && [ -z "${NODE_EXTRA_CA_CERTS:-}" ]; then
  warns+="NODE_EXTRA_CA_CERTS is not set: Node clients will not trust the mkcert CA. Add to the shell profile (owner's edit): export NODE_EXTRA_CA_CERTS=\"\$(mkcert -CAROOT)/rootCA.pem\". "
fi
[ -z "$warns" ] || { emit_warn "local-https: $warns"; exit 0; }
exit 0
