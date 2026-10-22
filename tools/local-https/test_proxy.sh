#!/usr/bin/env bash
# test_proxy.sh — behaviour tests for `local-https proxy` and
# plugins/local-https/scripts/tls-proxy.mjs. Each test builds a throwaway git
# repo named `myapp`, runs `setup` for its root, and talks to the proxy over
# TLS verified against the mkcert root CA (never --insecure). No hosts entry
# is needed: curl pins myapp-local to 127.0.0.1 with --resolve. Requires
# mkcert (CA installed), node, python3 and curl; skips cleanly without them.

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
SCRIPTS="$ROOT/plugins/local-https/scripts"
export PATH="$SCRIPTS:$PATH"

for tool in mkcert node python3 curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "SKIP local-https proxy tests: $tool not on PATH"
    exit 0
  fi
done

WORK=$(mktemp -d)
PIDS=()
cleanup() {
  local p
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT
cleanup_test() { # kill the servers one test started (its own copy of PIDS)
  local p
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}

CA="$(mkcert -CAROOT)/rootCA.pem"
pass=0; fail=0

fail_with() { echo "    $*"; return 1; }

new_repo() { # fresh repo at $WORK/<n>/myapp with certs for its root; prints its path
  local d="$WORK/$1/myapp"
  mkdir -p "$d"
  git -C "$d" init -q
  (cd "$d" && local-https setup) >/dev/null
  printf '%s\n' "$d"
}

free_port() { # a port the kernel just handed out for 127.0.0.1, then released
  python3 -I -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()'
}

wait_port() { # wait_port <port> <pid>: 0 once something accepts on it, 1 if <pid> died or 10s pass
  local i
  for i in $(seq 1 100); do
    kill -0 "$2" 2>/dev/null || return 1
    python3 -I -c 'import socket, sys
socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.2).close()' "$1" 2>/dev/null && return 0
    sleep 0.1
  done
  return 1
}

STARTED_PORT="" STARTED_PID=""
start_on_free_port() { # start_on_free_port <log> <cmd...>: "{port}" in cmd is the port; retries once
  local log=$1 attempt port pid a args; shift
  for attempt in 1 2; do
    port=$(free_port)
    args=()
    for a in "$@"; do args+=("${a//\{port\}/$port}"); done
    "${args[@]}" >"$log" 2>&1 &
    pid=$!
    PIDS+=("$pid")
    if wait_port "$port" "$pid"; then STARTED_PORT=$port STARTED_PID=$pid; return 0; fi
    kill "$pid" 2>/dev/null || true
    grep -q 'EADDRINUSE\|Address already in use' "$log" || break
  done
  echo "    could not start: $* ($(cat "$log"))"
  return 1
}

# Backend that answers GET with the request headers it saw, one per line.
ECHO_BACKEND='import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = "".join("%s: %s\n" % kv for kv in self.headers.items()).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()'

# Backend that accepts one WebSocket-style upgrade, answers 101, then echoes bytes.
UPGRADE_BACKEND='import socket, sys
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", int(sys.argv[1]))); srv.listen(8)
while True:
    c, _ = srv.accept()
    req = b""
    while b"\r\n\r\n" not in req:
        chunk = c.recv(4096)
        if not chunk: break
        req += chunk
    head = req.split(b"\r\n\r\n", 1)[0].decode("latin-1").lower()
    if "upgrade: websocket" not in head or "x-forwarded-proto: https" not in head:
        c.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"); c.close(); continue
    c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
    while True:
        data = c.recv(4096)
        if not data: break
        c.sendall(data)
    c.close()'

# TLS client: upgrade through the proxy, send "ping", expect "ping" back.
# Verifies the server cert against the mkcert root CA for servername myapp-local.
UPGRADE_CLIENT='import tls from "node:tls"; import fs from "node:fs";
const [port, ca] = process.argv.slice(1);
const s = tls.connect({ host: "127.0.0.1", port: Number(port), servername: "myapp-local", ca: fs.readFileSync(ca) });
let buf = ""; let upgraded = false;
const timer = setTimeout(() => { console.error("timeout; got: " + JSON.stringify(buf)); process.exit(1); }, 5000);
s.on("secureConnect", () => s.write("GET /_hmr HTTP/1.1\r\nHost: myapp-local:" + port + "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n"));
s.on("data", (d) => {
  buf += d.toString("latin1");
  if (!upgraded && buf.includes("\r\n\r\n")) {
    if (!buf.startsWith("HTTP/1.1 101")) { console.error("no 101: " + JSON.stringify(buf)); process.exit(1); }
    upgraded = true; buf = buf.slice(buf.indexOf("\r\n\r\n") + 4); s.write("ping");
  }
  if (upgraded && buf === "ping") { clearTimeout(timer); console.log("echoed ping"); s.end(); }
});
s.on("error", (e) => { console.error(e.message); process.exit(1); });'

start_proxy() { # start_proxy <repo> <log> <backend-port>: proxy via the tool on a free port
  start_on_free_port "$2" local-https proxy "{port}" "$3" "$1"
}

test_proxy_serves_file_over_verified_tls() {
  local r site out; r=$(new_repo file)
  site="$WORK/file/site"; mkdir -p "$site"
  echo 'hello from the fixture site' > "$site/index.html"
  start_on_free_port "$WORK/file/backend.log" python3 -m http.server --bind 127.0.0.1 --directory "$site" "{port}"
  start_proxy "$r" "$WORK/file/proxy.log" "$STARTED_PORT"
  out=$(curl --silent --show-error --fail --cacert "$CA" \
    --resolve "myapp-local:$STARTED_PORT:127.0.0.1" "https://myapp-local:$STARTED_PORT/") \
    || fail_with "curl failed: $out ($(cat "$WORK/file/proxy.log"))"
  [ "$out" = 'hello from the fixture site' ] || fail_with "wrong body: $out"
}

test_proxy_sets_forwarding_headers() {
  local r out port; r=$(new_repo headers)
  start_on_free_port "$WORK/headers/backend.log" python3 -I -c "$ECHO_BACKEND" "{port}"
  start_proxy "$r" "$WORK/headers/proxy.log" "$STARTED_PORT"
  port=$STARTED_PORT
  out=$(curl --silent --show-error --fail --cacert "$CA" \
    --resolve "myapp-local:$port:127.0.0.1" "https://myapp-local:$port/headers") \
    || fail_with "curl failed: $out ($(cat "$WORK/headers/proxy.log"))"
  grep -qix 'X-Forwarded-Proto: https' <<<"$out" || fail_with "no X-Forwarded-Proto: https: $out"
  grep -qix 'X-Forwarded-For: .*127\.0\.0\.1' <<<"$out" || fail_with "no X-Forwarded-For: $out"
  grep -qix "Host: myapp-local:$port" <<<"$out" || fail_with "Host not preserved: $out"
}

test_proxy_forwards_websocket_upgrade() {
  local r out; r=$(new_repo upgrade)
  start_on_free_port "$WORK/upgrade/backend.log" python3 -I -c "$UPGRADE_BACKEND" "{port}"
  start_proxy "$r" "$WORK/upgrade/proxy.log" "$STARTED_PORT"
  out=$(node --input-type=module -e "$UPGRADE_CLIENT" "$STARTED_PORT" "$CA" 2>&1) \
    || fail_with "upgrade failed: $out ($(cat "$WORK/upgrade/proxy.log"))"
  [ "$out" = 'echoed ping' ] || fail_with "unexpected client output: $out"
}

test_proxy_script_fails_on_missing_cert() {
  local out rc=0
  out=$(node "$SCRIPTS/tls-proxy.mjs" --cert "$WORK/none.pem" --key "$WORK/none-key.pem" \
    --listen 8443 --target 3000 2>&1) || rc=$?
  [ "$rc" != 0 ] || fail_with "exit 0 with missing cert: $out"
  [ "$(printf '%s\n' "$out" | wc -l | tr -d ' ')" = 1 ] || fail_with "not one line: $out"
  grep -qF "$WORK/none.pem" <<<"$out" || fail_with "message lacks the cert path: $out"
}

test_proxy_rejects_bad_ports() {
  local r out rc p; r=$(new_repo ports)
  for p in 0 65536 abc 8443x -1 ''; do
    rc=0; out=$(cd "$r" && local-https proxy "$p" 3000 2>&1) || rc=$?
    [ "$rc" = 1 ] || fail_with "tls port '$p': expected exit 1, got $rc: $out"
    rc=0; out=$(cd "$r" && local-https proxy 8443 "$p" 2>&1) || rc=$?
    [ "$rc" = 1 ] || fail_with "http port '$p': expected exit 1, got $rc: $out"
  done
}

test_proxy_dry_run_prints_command() {
  local r out; r=$(new_repo dry)
  out=$(cd "$r" && local-https proxy 8443 3000 --dry-run) || fail_with "dry run failed: $out"
  grep -qF "tls-proxy.mjs" <<<"$out" || fail_with "no script in plan: $out"
  grep -qF ".cert/myapp.pem" <<<"$out" || fail_with "no cert in plan: $out"
  grep -qF ".cert/myapp-key.pem" <<<"$out" || fail_with "no key in plan: $out"
  grep -qF -- "--listen 8443 --target 3000" <<<"$out" || fail_with "no ports in plan: $out"
}

test_proxy_requires_both_ports() {
  local r out rc=0; r=$(new_repo usage)
  out=$(cd "$r" && local-https proxy 8443 2>&1) || rc=$?
  [ "$rc" = 1 ] || fail_with "expected exit 1, got $rc: $out"
}

# set -e is suppressed inside `if`/`&&` conditions, so run each test in a
# subshell from plain context and inspect its status afterwards. Servers a
# test starts are killed when its subshell exits.
for t in \
  test_proxy_serves_file_over_verified_tls \
  test_proxy_sets_forwarding_headers \
  test_proxy_forwards_websocket_upgrade \
  test_proxy_script_fails_on_missing_cert \
  test_proxy_rejects_bad_ports \
  test_proxy_dry_run_prints_command \
  test_proxy_requires_both_ports
do
  set +e; ( set -e; trap cleanup_test EXIT; "$t" ); rc=$?; set -e
  if [ "$rc" = 0 ]; then echo "PASS $t"; pass=$((pass+1))
  else echo "FAIL $t"; fail=$((fail+1)); fi
done
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
