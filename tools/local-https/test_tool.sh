#!/usr/bin/env bash
# test_tool.sh — behaviour tests for plugins/local-https/scripts/local-https
# (setup, check, copy, trust, doctor). Each test builds a fresh throwaway git repo named `myapp`
# with an `apps/web` server. Requires mkcert (and a CA installed with
# `mkcert -install`); skips cleanly when mkcert is absent.

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
export PATH="$ROOT/plugins/local-https/scripts:$PATH"

if ! command -v mkcert >/dev/null 2>&1; then
  echo "SKIP local-https tests: mkcert not on PATH"
  exit 0
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

pass=0; fail=0
IGNORE_ENV=hosts-v4,hosts-v6,node-ca

new_repo() { # fresh repo at $WORK/<n>/myapp; prints its path
  local d="$WORK/$1/myapp"
  mkdir -p "$d/apps/web"
  echo '{"name":"web"}' > "$d/apps/web/package.json"
  git -C "$d" init -q
  printf '%s\n' "$d"
}

edit_decl() { # edit_decl <repo> <python statement on d>
  python3 - "$1/.local-https.json" "$2" <<'PY'
import json, sys
p, stmt = sys.argv[1], sys.argv[2]
d = json.load(open(p))
exec(stmt)
json.dump(d, open(p, "w"), indent=2)
PY
}

fail_with() { echo "    $*"; return 1; }

test_setup_dry_run_prints_plan() {
  local r out; r=$(new_repo dry)
  out=$(cd "$r" && local-https setup apps/web --dry-run)
  [ ! -e "$r/apps/web/.cert" ] || fail_with ".cert created on dry run"
  [ ! -e "$r/.local-https.json" ] || fail_with "declaration written on dry run"
  [ ! -e "$r/.gitignore" ] || fail_with ".gitignore written on dry run"
  grep -qF ".cert/myapp.pem" <<<"$out" || fail_with "plan lacks cert path: $out"
  grep -qF ".cert/myapp-key.pem" <<<"$out" || fail_with "plan lacks key path: $out"
  grep -qF "myapp-local *.myapp-local localhost 127.0.0.1 ::1" <<<"$out" || fail_with "plan lacks SAN list: $out"
}

test_setup_creates_cert_and_declaration() {
  local r; r=$(new_repo create)
  (cd "$r" && local-https setup apps/web) >/dev/null
  [ -f "$r/apps/web/.cert/myapp.pem" ] || fail_with "cert missing"
  [ -f "$r/apps/web/.cert/myapp-key.pem" ] || fail_with "key missing"
  grep -qx '.cert/' "$r/.gitignore" || fail_with ".gitignore lacks .cert/"
  python3 - "$r/.local-https.json" <<'PY' || fail_with "declaration wrong: $(cat "$r/.local-https.json")"
import json, sys
d = json.load(open(sys.argv[1]))
assert d["project"] == "myapp", d
assert d["host"] == "myapp-local", d
assert [s["dir"] for s in d["servers"]] == ["apps/web"], d
PY
}

test_check_passes_after_setup() {
  local r out; r=$(new_repo pass)
  (cd "$r" && local-https setup apps/web) >/dev/null
  out=$(cd "$r" && local-https check apps/web --ignore "$IGNORE_ENV") || fail_with "check failed: $out"
  grep -qx 'OK sans' <<<"$out" || fail_with "no OK sans: $out"
  grep -qx 'SKIP node-ca' <<<"$out" || fail_with "ignored item not SKIP: $out"
}

test_check_reports_missing_san() {
  local r out rc=0; r=$(new_repo san)
  (cd "$r" && local-https setup apps/web) >/dev/null
  edit_decl "$r" 'd["servers"][0]["subdomains"] = ["admin"]'
  out=$(cd "$r" && local-https check apps/web --ignore "$IGNORE_ENV") || rc=$?
  [ "$rc" = 1 ] || fail_with "expected exit 1, got $rc: $out"
  grep -qF 'MISSING sans: admin.myapp-local' <<<"$out" || fail_with "no MISSING sans line: $out"
}

test_setup_regenerates_for_new_san() {
  local r out; r=$(new_repo regen)
  (cd "$r" && local-https setup apps/web) >/dev/null
  edit_decl "$r" 'd["servers"][0]["subdomains"] = ["admin"]'
  (cd "$r" && local-https setup apps/web) >/dev/null
  out=$(cd "$r" && local-https check apps/web --ignore "$IGNORE_ENV") || fail_with "check failed after regen: $out"
}

test_rejects_opt_out_without_reason() {
  local r out rc=0; r=$(new_repo optout)
  (cd "$r" && local-https setup apps/web) >/dev/null
  edit_decl "$r" 'd["servers"].append({"dir": "apps/worker", "https": False})'
  out=$(cd "$r" && local-https check apps/web 2>&1) || rc=$?
  [ "$rc" = 3 ] || fail_with "expected exit 3, got $rc: $out"
  grep -q '^INVALID ' <<<"$out" || fail_with "no INVALID line: $out"
}

test_rejects_forbidden_host() {
  local r out rc=0; r=$(new_repo mdns)
  (cd "$r" && local-https setup apps/web) >/dev/null
  edit_decl "$r" 'd["host"] = "myapp.local"'
  out=$(cd "$r" && local-https check apps/web 2>&1) || rc=$?
  [ "$rc" = 3 ] || fail_with "expected exit 3, got $rc: $out"
  grep -q '^INVALID host: .*mDNS' <<<"$out" || fail_with "INVALID host line does not name mDNS: $out"
}

write_decl() { # write_decl <repo> <json>
  printf '%s\n' "$2" > "$1/.local-https.json"
}

assert_rejected_untouched() { # assert_rejected_untouched <repo> <label>
  local r=$1 out rc=0
  out=$(cd "$r" && local-https setup apps/web 2>&1) || rc=$?
  [ "$rc" = 3 ] || fail_with "$2: expected exit 3, got $rc: $out"
  grep -q '^INVALID ' <<<"$out" || fail_with "$2: no INVALID line: $out"
  [ ! -e "$r/apps/web/.cert" ] || fail_with "$2: .cert created"
  [ ! -e "$r/.gitignore" ] || fail_with "$2: .gitignore written"
}

test_rejects_injected_host() {
  local r; r=$(new_repo inject)
  write_decl "$r" '{"project":"myapp","host":"x; rm -rf /","servers":[{"dir":"apps/web"}]}'
  assert_rejected_untouched "$r" "injected host"
}

test_rejects_flag_extra_name() {
  local r; r=$(new_repo flag)
  write_decl "$r" '{"project":"myapp","host":"myapp-local","servers":[{"dir":"apps/web"}],"extraNames":["-flag"]}'
  assert_rejected_untouched "$r" "flag extra name"
}

test_rejects_traversal_project() {
  local r; r=$(new_repo traversal)
  write_decl "$r" '{"project":"../../escape","host":"myapp-local","servers":[{"dir":"apps/web"}]}'
  assert_rejected_untouched "$r" "traversal project"
}

test_rejects_scoped_ipv6_extra_name() {
  local r; r=$(new_repo scope)
  write_decl "$r" '{"project":"myapp","host":"myapp-local","servers":[{"dir":"apps/web"}],"extraNames":["::1%eth0"]}'
  assert_rejected_untouched "$r" "scoped IPv6 extra name"
}

test_rejects_line_protocol_injection() {
  local r; r=$(new_repo lineproto)
  write_decl "$r" '{"project":"myapp","host":"fe80::1%a\nproject=pwn","servers":[{"dir":"apps/web"}]}'
  assert_rejected_untouched "$r" "newline in host"
}

test_worktree_derives_main_checkout_name() {
  local r wt out; r=$(new_repo worktree)
  git -C "$r" -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m init
  wt="$WORK/worktree/feature-x"
  git -C "$r" worktree add -q "$wt" -b feature-x
  mkdir -p "$wt/apps/web"
  out=$(cd "$wt" && local-https setup apps/web --dry-run)
  grep -qF "host: myapp-local" <<<"$out" || fail_with "worktree did not derive myapp-local: $out"
}

test_setup_adds_new_server_to_declaration() {
  local r; r=$(new_repo addserver)
  mkdir -p "$r/apps/api"
  (cd "$r" && local-https setup apps/web) >/dev/null
  (cd "$r" && local-https setup apps/api) >/dev/null
  python3 - "$r/.local-https.json" <<'PY2' || fail_with "declaration wrong: $(cat "$r/.local-https.json")"
import json, sys
d = json.load(open(sys.argv[1]))
assert list(d)[:2] == ["project", "host"], d
assert d["project"] == "myapp" and d["host"] == "myapp-local", d
assert [s["dir"] for s in d["servers"]] == ["apps/web", "apps/api"], d
PY2
}

commit_all() { # commit_all <repo>
  git -C "$1" add -A
  git -C "$1" -c user.name=t -c user.email=t@example.invalid commit -q -m init
}

test_copy_from_worktree() {
  local r wt out; r=$(new_repo copywt)
  (cd "$r" && local-https setup apps/web) >/dev/null
  echo 'not a real key' > "$r/apps/web/.cert/rootCA-key.pem"
  commit_all "$r"
  wt="$WORK/copywt/wt"
  git -C "$r" worktree add -q "$wt" -b wt
  out=$(cd "$wt" && local-https copy 2>&1) || fail_with "copy failed: $out"
  [ -f "$wt/apps/web/.cert/myapp.pem" ] || fail_with "cert not copied: $out"
  [ -f "$wt/apps/web/.cert/myapp-key.pem" ] || fail_with "key not copied: $out"
  [ ! -e "$wt/apps/web/.cert/rootCA-key.pem" ] || fail_with "rootCA-key.pem copied: $out"
}

test_copy_refuses_in_main() {
  local r out rc=0; r=$(new_repo copymain)
  (cd "$r" && local-https setup apps/web) >/dev/null
  commit_all "$r"
  out=$(cd "$r" && local-https copy 2>&1) || rc=$?
  [ "$rc" = 1 ] || fail_with "expected exit 1, got $rc: $out"
}

test_hosts_file_override() {
  local r out hosts; r=$(new_repo hostsfile)
  (cd "$r" && local-https setup apps/web) >/dev/null
  hosts="$WORK/hostsfile/hosts"
  printf '127.0.0.1 localhost\n127.0.0.1 myapp-local\n' > "$hosts"
  out=$(cd "$r" && LOCAL_HTTPS_HOSTS_FILE=$hosts local-https check apps/web --ignore node-ca) && fail_with "check passed without ::1 line: $out"
  grep -qx 'OK hosts-v4' <<<"$out" || fail_with "no OK hosts-v4: $out"
  grep -q '^MISSING hosts-v6: ' <<<"$out" || fail_with "no MISSING hosts-v6: $out"
  printf '::1 myapp-local\n' >> "$hosts"
  out=$(cd "$r" && LOCAL_HTTPS_HOSTS_FILE=$hosts local-https check apps/web --ignore node-ca) || fail_with "check failed with both lines: $out"
  grep -qx 'OK hosts-v6' <<<"$out" || fail_with "no OK hosts-v6: $out"
}

test_doctor_reports_sections() {
  local r out hosts; r=$(new_repo doctor)
  (cd "$r" && local-https setup apps/web) >/dev/null
  hosts="$WORK/doctor/hosts"
  printf '127.0.0.1 localhost\n127.0.0.1 myapp-local otherapp-local\n' > "$hosts"
  out=$(cd "$r" && LOCAL_HTTPS_HOSTS_FILE=$hosts local-https doctor 2>&1) || true
  grep -qx 'CHECK apps/web' <<<"$out" || fail_with "no CHECK apps/web: $out"
  grep -qx 'HOSTS' <<<"$out" || fail_with "no HOSTS heading: $out"
  grep -qx 'INFO' <<<"$out" || fail_with "no INFO heading: $out"
  grep -q '^INFO .*otherapp-local' <<<"$out" || fail_with "other project's entry not INFO: $out"
}

test_doctor_warns_forbidden_san() {
  local r out; r=$(new_repo legacy)
  (cd "$r" && local-https setup apps/web) >/dev/null
  (cd "$r/apps/web" && mkcert -cert-file .cert/myapp.pem -key-file .cert/myapp-key.pem \
    myapp-local '*.myapp-local' localhost 127.0.0.1 ::1 legacy.local) >/dev/null 2>&1
  out=$(cd "$r" && local-https doctor apps/web 2>&1) || true
  grep -q '^WARN sans: legacy.local' <<<"$out" || fail_with "no WARN sans: legacy.local: $out"
}

test_doctor_checks_undeclared_server_once() {
  local r out; r=$(new_repo undeclared)
  out=$(cd "$r" && local-https doctor apps/web 2>&1) || true
  [ "$(grep -cx 'CHECK apps/web' <<<"$out")" = 1 ] || fail_with "expected one CHECK apps/web: $out"
}

test_trust_reports_node_env() {
  local out caroot; caroot=$(mkcert -CAROOT)
  out=$(NODE_EXTRA_CA_CERTS="$caroot/rootCA.pem" local-https trust)
  grep -q '^IN EFFECT NODE_EXTRA_CA_CERTS' <<<"$out" || fail_with "NODE_EXTRA_CA_CERTS not IN EFFECT: $out"
  out=$(env -u NODE_EXTRA_CA_CERTS local-https trust)
  grep -q '^NOT SET NODE_EXTRA_CA_CERTS' <<<"$out" || fail_with "NODE_EXTRA_CA_CERTS not NOT SET: $out"
}

# set -e is suppressed inside `if`/`&&` conditions, so run each test in a
# subshell from plain context and inspect its status afterwards.
for t in \
  test_setup_dry_run_prints_plan \
  test_setup_creates_cert_and_declaration \
  test_check_passes_after_setup \
  test_check_reports_missing_san \
  test_setup_regenerates_for_new_san \
  test_rejects_opt_out_without_reason \
  test_rejects_forbidden_host \
  test_rejects_injected_host \
  test_rejects_flag_extra_name \
  test_rejects_traversal_project \
  test_rejects_scoped_ipv6_extra_name \
  test_rejects_line_protocol_injection \
  test_worktree_derives_main_checkout_name \
  test_setup_adds_new_server_to_declaration \
  test_copy_from_worktree \
  test_copy_refuses_in_main \
  test_hosts_file_override \
  test_doctor_reports_sections \
  test_doctor_warns_forbidden_san \
  test_doctor_checks_undeclared_server_once \
  test_trust_reports_node_env
do
  set +e; ( set -e; "$t" ); rc=$?; set -e
  if [ "$rc" = 0 ]; then echo "PASS $t"; pass=$((pass+1))
  else echo "FAIL $t"; fail=$((fail+1)); fi
done
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
