# Tool and hook reference

Run the tool as `"${CLAUDE_PLUGIN_ROOT}/scripts/local-https"`. It needs bash,
python3, openssl and mkcert; Node only for `proxy`. It never edits
`/etc/hosts` or a shell profile, and never copies `rootCA-key.pem`. Steps the
owner must take are printed prefixed `OWNER:`.

## Commands

| Command | What it does |
|---|---|
| `setup [dir] [--dry-run] [--jvm]` | Runs mkcert for `<dir>` (default cwd) with the project's SAN list, writes `.cert/<project>.pem` and `-key.pem` (plus `.p12` with `--jvm`), appends `.cert/` to the root `.gitignore`, writes `.local-https.json` if absent or adds the server, prints the missing hosts and trust lines. Regenerates when SANs are missing. |
| `check [dir] [--ignore a,b]` | One line per item in order `mkcert`, `ca-trusted`, `cert`, `key`, `sans`, `expiry`, `hosts-v4`, `hosts-v6`, `node-ca`: `OK <item>` or `MISSING <item>: <fix command>`. Exit 0 when nothing is MISSING, else 1. Validation failures print `INVALID <field>: <why>` and exit 3. |
| `copy [--dry-run]` | From a linked worktree: copies each `.cert/` directory of the main checkout to the same relative path. Refuses in the main checkout (exit 1). Never follows symlinks, never copies a CA key. |
| `trust` | Per-runtime trust lines, each `IN EFFECT` or `NOT SET`: system store, `NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, JVM keytool line. |
| `doctor [dir]` | `check` for every declared server, then `HOSTS` (both families for every name), `CERT` (expiry under 30 days is `WARN`; a forbidden suffix among the SANs is `WARN sans:` with the fix), `CA`, `INFO` (other projects' loopback entries, never failing). Exit 0 unless a check item is MISSING. |
| `proxy TLS_PORT HTTP_PORT [dir] [--dry-run]` | Runs `tls-proxy.mjs` with the dir's cert: TLS in front of a plain-HTTP server, `Host` preserved, `X-Forwarded-Proto: https` and `X-Forwarded-For` added, WebSocket upgrades forwarded. Exits non-zero with one line if the cert is missing. |

`INVALID` rules: `https: false` needs a `reason`; `host` may not end `.local`,
`.localhost`, `.dev` or `.app`; names are plain DNS names or IPs (no leading
`-`, no scope ids, no `=` or newlines).

## The hook

`scripts/guard.sh`, PreToolUse on Bash. It exits 0 at once unless the command
launches a server. Launch patterns: `nuxt dev`, `nuxi dev`, `next dev|start`,
`vite`, `pnpm|npm|yarn|bun (run) dev|start|serve|preview`, `node <file>` where
the file name holds `server`, `app`, `index` or `main`, `tsx`, `ts-node`,
`nodemon`, `mvn spring-boot:run`, `gradle bootRun`, `java -jar`, `uvicorn`,
`flask run`, `python -m http.server`, `manage.py runserver`, `deno run`.
`pnpm test`, `build`, `lint`, `npm install`, `supabase` and `docker compose`
never match.

A repo extends the list per server with regexes matched by `grep -E`:

```json
{ "dir": "apps/web", "launch": ["^make serve"] }
```

Resolution: a leading `cd` sets the directory; then the declared server whose
`dir` is that directory or an ancestor; a root launch in a workspace repo
checks every declared server and never demands a cert at the root.

| Situation | Result |
|---|---|
| `NODE_TLS_REJECT_UNAUTHORIZED=0` in the command | BLOCK, any repo |
| Declared, non-opted-out server has no `.cert/<project>.pem` | BLOCK, naming `local-https copy` (worktree whose main checkout has the cert) or `local-https setup <dir>` |
| Undeclared repo, no cert in the launch directory | WARN with the setup command |
| `http://localhost:<port>` or `127.0.0.1` at a declared port | WARN, use the project host |
| `--` before `--port` or `--host` after a package-manager run | WARN |
| Node launch with no `NODE_EXTRA_CA_CERTS` | WARN |
| Worktree cert older than the main checkout's | WARN, run `copy` |
| `https: false` with a reason | allowed silently |
| Invalid `.local-https.json` | WARN with the validation message |

Block messages carry the fix command in full. A block is a missing step, not a
reason to opt out: run the named command, then relaunch.
