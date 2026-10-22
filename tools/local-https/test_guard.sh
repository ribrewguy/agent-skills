#!/usr/bin/env bash
# test_guard.sh — behaviour tests for plugins/local-https/scripts/guard.sh.
# Feeds the hook JSON on stdin from throwaway git repos named `myapp`. Cert
# files are stand-ins (the guard checks for presence only), so mkcert is not
# needed.

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
GUARD="$ROOT/plugins/local-https/scripts/guard.sh"
export NODE_EXTRA_CA_CERTS=/nonexistent/rootCA.pem   # set, so it never adds a warning

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
pass=0; fail=0
OUT="" ERR="" RC=0

fail_with() { echo "    $*"; return 1; }

new_repo() { # new_repo <name>: repo with apps/web and apps/rest servers
  local d="$WORK/$1/myapp"
  mkdir -p "$d/apps/web" "$d/apps/rest"
  echo '{"name":"web"}' > "$d/apps/web/package.json"
  echo '{"name":"rest"}' > "$d/apps/rest/package.json"
  git -C "$d" init -q
  git -C "$d" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m init
  printf '%s\n' "$d"
}

declare_servers() { # declare_servers <repo> <servers-json>
  printf '{"project":"myapp","host":"myapp-local","servers":%s}\n' "$2" > "$1/.local-https.json"
}

fake_cert() { mkdir -p "$1/.cert"; : > "$1/.cert/myapp.pem"; : > "$1/.cert/myapp-key.pem"; }

run_guard() { # run_guard <cwd> <command>: sets OUT ERR RC
  local json
  json=$(python3 -I -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]},"cwd":sys.argv[2]}))' "$2" "$1")
  RC=0
  OUT=$(printf '%s' "$json" | bash "$GUARD" 2>"$WORK/err") || RC=$?
  ERR=$(cat "$WORK/err")
}

expect_silent_allow() { [ "$RC" = 0 ] || fail_with "rc=$RC err=$ERR"; [ -z "$OUT" ] || fail_with "unexpected output: $OUT"; }

test_ignores_non_launch() {
  local r c; r=$(new_repo nonlaunch); declare_servers "$r" '[{"dir":"apps/web"}]'
  for c in 'pnpm test' 'pnpm build' 'npm install' 'supabase start' 'docker compose up' 'ls' \
           'pnpm lint' 'pnpm install --frozen-lockfile' 'vite build' 'npm run build'; do
    run_guard "$r/apps/web" "$c"
    expect_silent_allow || fail_with "command: $c"
  done
}

test_ignores_outside_git() {
  local d="$WORK/plain"; mkdir -p "$d"
  run_guard "$d" 'pnpm dev'
  expect_silent_allow
}

test_warns_undeclared_missing_cert() {
  local r; r=$(new_repo undeclared)
  run_guard "$r/apps/web" 'pnpm dev'
  [ "$RC" = 0 ] || fail_with "rc=$RC err=$ERR"
  grep -qF 'local-https setup apps/web' <<<"$OUT" || fail_with "no setup hint: $OUT"
  python3 -I -c 'import json,sys; json.loads(sys.argv[1])' "$OUT" || fail_with "not JSON: $OUT"
}

test_blocks_declared_missing_cert() {
  local r; r=$(new_repo declared); declare_servers "$r" '[{"dir":"apps/web"}]'
  run_guard "$r/apps/web" 'pnpm dev'
  [ "$RC" = 2 ] || fail_with "rc=$RC out=$OUT"
  grep -qF 'local-https setup apps/web' <<<"$ERR" || fail_with "stderr: $ERR"
}

test_allows_declared_with_cert() {
  local r; r=$(new_repo withcert); declare_servers "$r" '[{"dir":"apps/web"}]'; fake_cert "$r/apps/web"
  run_guard "$r/apps/web" 'pnpm dev'
  expect_silent_allow
}

test_cd_resolves_dir() {
  local r; r=$(new_repo cd); declare_servers "$r" '[{"dir":"apps/web"},{"dir":"apps/rest"}]'
  fake_cert "$r/apps/rest"
  run_guard "$r" 'cd apps/web && pnpm dev'
  [ "$RC" = 2 ] || fail_with "rc=$RC out=$OUT"
  grep -qF 'apps/web' <<<"$ERR" || fail_with "stderr: $ERR"
  ! grep -qF 'apps/rest' <<<"$ERR" || fail_with "judged the wrong dir: $ERR"
  fake_cert "$r/apps/web"
  run_guard "$r" 'cd apps/web && pnpm dev'
  expect_silent_allow
}

test_opt_out_allows() {
  local r; r=$(new_repo optout)
  declare_servers "$r" '[{"dir":"apps/web","https":false,"reason":"owner said plain http for this one"}]'
  run_guard "$r/apps/web" 'pnpm dev'
  expect_silent_allow
}

test_blocks_reject_unauthorized() {
  local r; r=$(new_repo reject)
  run_guard "$r" 'NODE_TLS_REJECT_UNAUTHORIZED=0 node server.js'
  [ "$RC" = 2 ] || fail_with "rc=$RC out=$OUT"
  grep -qF 'NODE_EXTRA_CA_CERTS' <<<"$ERR" || fail_with "stderr: $ERR"
  run_guard "$WORK" 'NODE_TLS_REJECT_UNAUTHORIZED=0 node x.js'
  [ "$RC" = 2 ] || fail_with "outside git: rc=$RC"
}

test_warns_double_dash_port() {
  local r; r=$(new_repo dashdash); declare_servers "$r" '[{"dir":"apps/web"}]'; fake_cert "$r/apps/web"
  run_guard "$r/apps/web" 'pnpm dev -- --port 3001'
  [ "$RC" = 0 ] || fail_with "rc=$RC err=$ERR"
  grep -qF -- '--' <<<"$OUT" && grep -qF 'ignore its TLS config' <<<"$OUT" || fail_with "no -- warning: $OUT"
}

test_warns_http_url_to_declared_port() {
  local r; r=$(new_repo httpurl); declare_servers "$r" '[{"dir":"apps/web","port":3000}]'; fake_cert "$r/apps/web"
  run_guard "$r/apps/web" 'API_URL=http://localhost:3000 pnpm dev'
  grep -qF 'https://myapp-local:3000' <<<"$OUT" || fail_with "no url warning: $OUT"
}

test_warns_without_node_extra_ca() {
  local r; r=$(new_repo noca); declare_servers "$r" '[{"dir":"apps/web"}]'; fake_cert "$r/apps/web"
  RC=0; OUT=$(printf '%s' "{\"tool_input\":{\"command\":\"pnpm dev\"},\"cwd\":\"$r/apps/web\"}" \
    | env -u NODE_EXTRA_CA_CERTS bash "$GUARD" 2>&1) || RC=$?
  grep -qF 'NODE_EXTRA_CA_CERTS' <<<"$OUT" || fail_with "no CA warning: $OUT"
}

test_worktree_names_copy() {
  local r wt; r=$(new_repo wt); declare_servers "$r" '[{"dir":"apps/web"}]'; fake_cert "$r/apps/web"
  git -C "$r" add .local-https.json
  git -C "$r" -c user.email=t@example.com -c user.name=t commit -q -m decl
  wt="$WORK/wt/wt"; git -C "$r" worktree add -q "$wt" -b wt; mkdir -p "$wt/apps/web"
  run_guard "$wt/apps/web" 'pnpm dev'
  [ "$RC" = 2 ] || fail_with "rc=$RC out=$OUT"
  grep -qF 'local-https copy' <<<"$ERR" || fail_with "stderr: $ERR"
  ! grep -qF 'local-https setup' <<<"$ERR" || fail_with "named setup: $ERR"
  [ ! -e "$wt/.cert" ] || fail_with "repo-root .cert created"
}

test_root_launcher_checks_all() {
  local r; r=$(new_repo root); declare_servers "$r" '[{"dir":"apps/web"},{"dir":"apps/rest"}]'
  echo 'packages: ["apps/*"]' > "$r/pnpm-workspace.yaml"
  fake_cert "$r/apps/web"
  run_guard "$r" 'pnpm dev'
  [ "$RC" = 2 ] || fail_with "rc=$RC out=$OUT"
  grep -qF 'apps/rest' <<<"$ERR" || fail_with "stderr: $ERR"
  ! grep -qF 'Server apps/web' <<<"$ERR" || fail_with "named the ready server: $ERR"
  ! grep -qE 'Server \. ' <<<"$ERR" || fail_with "demanded root cert: $ERR"
}

test_declared_launch_pattern_extends() {
  local r; r=$(new_repo launch)
  declare_servers "$r" '[{"dir":"apps/web","launch":["^make serve"]}]'
  run_guard "$r/apps/web" 'make serve'
  [ "$RC" = 2 ] || fail_with "rc=$RC out=$OUT"
}

test_non_launch_is_fast() {
  local r s e; r=$(new_repo fast)
  s=$(python3 -I -c 'import time; print(time.time())')
  for _ in 1 2 3 4 5; do run_guard "$r" 'ls'; done
  e=$(python3 -I -c 'import time; print(time.time())')
  python3 -I -c 'import sys; per=(float(sys.argv[2])-float(sys.argv[1]))/5; print("%.0f ms per call (includes test harness)" % (per*1000)); sys.exit(0 if per < 0.25 else 1)' "$s" "$e"
}

for t in \
  test_ignores_non_launch test_ignores_outside_git test_warns_undeclared_missing_cert \
  test_blocks_declared_missing_cert test_allows_declared_with_cert test_cd_resolves_dir \
  test_opt_out_allows test_blocks_reject_unauthorized test_warns_double_dash_port \
  test_warns_http_url_to_declared_port test_warns_without_node_extra_ca \
  test_worktree_names_copy test_root_launcher_checks_all test_declared_launch_pattern_extends \
  test_non_launch_is_fast
do
  set +e; ( set -e; "$t" ); rc=$?; set -e
  if [ "$rc" = 0 ]; then echo "PASS $t"; pass=$((pass+1))
  else echo "FAIL $t"; fail=$((fail+1)); fi
done
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
