---
name: local-https
description: "Use whenever starting, configuring, or reviewing a locally run server or dev server in any stack, including requests like run the app, start the dev server, or spin up the API. Every local server listens on TLS with an mkcert certificate at the project hostname, named <project>-local, unless the owner opts that server out. Symptoms: login 401 after an apparent success, a Secure cookie dropped on plain http, a self signed certificate error from Node, curl -k or rejectUnauthorized false in a diff, http://localhost in a config or env file, a .local hostname with multi-second lookups. Covers certificates per server directory, the naming rule, the repo declaration, the local-https tool and launch guard, client trust per runtime, the TLS proxy for production builds, and fresh worktrees. Not for production TLS or deployment reverse proxies."
---

# Local HTTPS

## Overview

Every server an agent starts on this machine runs on TLS, with an mkcert
certificate, bound to the project hostname. Plain `http://localhost:3000` is
how a `Secure` cookie gets dropped and a login "succeeds" and then 401s with no
visible error, and how a backend ends up called through a trust bypass.

The plugin ships three parts: this skill (rule, conventions, recipes), the
`local-https` tool (the mechanical steps, done the same way every time), and a
PreToolUse guard that catches a launch about to break the rule.

## The rule

**Every locally launched server runs on TLS at `<project>-local` with an mkcert
cert, unless the owner says otherwise for that server, recorded in the
declaration with their words as the reason.**

- "Server" means a listener whose source lives in this repo: a web app, an API,
  a BFF, a mock. Infrastructure the repo runs but does not own (Supabase,
  Postgres, Redis, mail catchers, anything from `docker compose up`) is out of
  scope.
- Backends no browser touches are included. Their clients (Node, JVM, Python,
  containers) get the CA trusted once; nothing is ever told to skip verification.
- Verification-bypass tokens are never acceptable: `NODE_TLS_REJECT_UNAUTHORIZED=0`,
  `rejectUnauthorized: false`, `curl -k` or `--insecure`, `verify=False`,
  trust-all managers. The guard blocks the first outright.

## Naming

- Host: `<project>-local`, a single label. `<project>` is the repo directory
  name, lowercased, runs of non-alphanumerics turned into `-` (the declaration
  can override it). Services and tenants sit under it: `rest.myapp-local`,
  `acme.myapp-local`.
- Permitted alternative: `<project>.test`, when a domain-scoped cookie must be
  shared across subdomains (a single label cannot carry one). Say so in the
  declaration.
- Forbidden:
  - `.local`: reserved for multicast DNS (RFC 6762). macOS sends these lookups
    to Bonjour first and a hosts entry does not bypass that path. The owner
    measured roughly five seconds per request on `<app>.local` names; the stall
    disappeared on switching to `<app>-local`.
  - `.dev` and `.app`: real TLDs on the HSTS preload list; a missing hosts
    entry sends the lookup to the public internet.
  - `*.localhost`: browsers hard-code loopback, Safari and non-browser clients
    use the OS resolver, which only does so on recent macOS.
  - bare `localhost` for anything that sets a `Secure` cookie.
- The hosts file carries both `127.0.0.1 <host> ...` and `::1 <host> ...`. The
  IPv6-first resolver path is the other documented cause of multi-second
  stalls, and the cert covers `::1`.

## Certificate

- One cert per project from mkcert. SANs: `<host>`, `*.<host>`, every declared
  subdomain as `<sub>.<host>`, `localhost`, `127.0.0.1`, `::1`, plus
  `extraNames` (for example `host.docker.internal` when a container calls the host).
- Files live in each server's own source directory: `.cert/<project>.pem`,
  `.cert/<project>-key.pem`, and for JVM servers `.cert/<project>.p12`
  (`setup --jvm`; the mkcert password is `changeit`, read from an env var).
- `.cert/` is gitignored at the repo root. The mkcert root CA key stays in
  `mkcert -CAROOT` and is never copied.

## Declaration

Optional, tracked, at the repo root: `.local-https.json`.

```json
{
  "project": "myapp",
  "host": "myapp-local",
  "servers": [
    { "dir": "apps/web", "subdomains": ["acme"], "port": 3000 },
    { "dir": "apps/rest", "subdomain": "rest", "port": 8443 },
    { "dir": "apps/worker", "https": false, "reason": "no listener; consumes a queue" }
  ],
  "extraNames": []
}
```

- Absent file: the rule still applies; `project` and `host` are derived, and the
  guard warns instead of blocking. `setup` writes the file on first run, which
  is what makes a repo strict.
- `subdomain` and `subdomains` enumerate every name under the host (the hosts
  file cannot hold a wildcard). `port` lets the guard recognise an `http://`
  URL aimed at a declared server. `launch` adds regexes for custom launchers.
- Values are untrusted input (a cloned repo supplies them); the tool validates
  them before use. Hostnames and subdomains must be plain DNS names.

## The tool

```
local-https setup [dir] [--dry-run] [--jvm]   mint dir/.cert/, declare the server, gitignore .cert/
local-https check [dir]                        OK or MISSING per item; exit 0 only if nothing MISSING
local-https copy [--dry-run]                   linked worktree: copy the main checkout's .cert/ dirs
local-https trust                              per-runtime trust lines: IN EFFECT / NOT SET
local-https doctor [dir]                       check every declared server, hosts, expiry, suffixes
local-https proxy TLS_PORT HTTP_PORT [dir]     TLS in front of a plain-HTTP server (production builds)
```

Run it as `"${CLAUDE_PLUGIN_ROOT}/scripts/local-https"`. It never edits
`/etc/hosts` or a shell profile: those steps are printed prefixed `OWNER:` and
you ask the owner to run them. Full options and output format are in
`references/tool-and-hook.md`.

## The hook

`guard.sh` runs on every Bash call and exits at once unless the command
launches a server. It blocks `NODE_TLS_REJECT_UNAUTHORIZED=0` anywhere, and in
a declared repo blocks a launch whose server directory has no cert (the message
names `local-https copy` in a worktree whose main checkout has one, else
`setup <dir>`). It warns, never blocks, for undeclared repos, `http://localhost`
URLs aimed at a declared port, a `--` that swallows `--port`, a Node launch
without `NODE_EXTRA_CA_CERTS`, and a stale worktree cert. It never fires on
tests, builds, installs, `docker compose` or `supabase`. Pattern list and
extension in `references/tool-and-hook.md`.

## Trust

A TLS server is useless to a client that does not trust the CA. Once per
machine: `mkcert -install` (system store, browsers, curl). Then per runtime:
Node needs `NODE_EXTRA_CA_CERTS` set in the launcher's environment (a `.env`
the app loads is too late); JVM needs the root imported into the JDK in use;
Python needs `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`; containers need the root
mounted. Exact lines and how to verify each are in `references/trust.md`.

## Stack recipes

Find the framework's TLS option, feed it the pair, bind the project host, then
verify. Worked config and footguns per stack:

- Nuxt and Nitro: `references/nuxt-nitro.md`
- Vite: `references/vite.md`
- Raw Node, h3, Express, Fastify: `references/node.md`
- Spring MVC and WebFlux: `references/spring.md`
- Python (uvicorn, Flask, Django): `references/python.md`
- Anything else: `references/other.md`

## Opting out

Only the owner opts a server out. When they say a server should stay plain
HTTP, set `"https": false` and `"reason"` to their words, quoted, in
`.local-https.json` for that server. Never add it on your own judgment, and
never infer it from "it is only a backend". An opt-out without a reason is
rejected by `check` and `setup`. The reason is how the next agent knows the
decision was made, not forgotten.

## Worktrees

A fresh linked worktree has no `.cert/`. Run `local-https copy`: it copies each
`.cert/` from the main checkout to the same relative path. Do not regenerate,
and never create a `.cert/` at the repo root for a server that lives in a
subdirectory. `isolated-stack-development` handles the stack; certs are this
skill's step.

## Verification

1. `local-https check <dir>` passes for every server (or `doctor` for all).
2. `curl https://<host>:<port>/` succeeds with no `-k`.
3. A browser shows a valid padlock on `https://<host>`.
4. Every server-to-server call succeeds with no bypass in code, env, or flags.
5. `doctor` reports no forbidden suffix and both hosts families present.

## Red flags and rationalizations

| Thought | Reality |
|---|---|
| "It is just a backend, nobody sets cookies on it" | Its client still needs trust configured and its URL becomes the habit. Do it once now. |
| "I'll use http for now and switch later" | Later is when the cookie is already dropped and the config is copied. |
| "localhost is a secure context, so it is fine" | Not for `Secure` cookies across names, nor for the cert-trusting clients behind it. |
| "-k is only for local" | Local is where the bypass gets committed. Trust the CA. |
| ".local is the standard for local hosts" | It is the mDNS TLD; the owner measured multi-second lookups. Use `-local`. |
| "The backend is only called by the frontend over loopback" | Its client still needs trust; configure it once now. |

Red flags in a diff: `rejectUnauthorized: false`, `verify=False`, `-k`,
`http://localhost` or `http://127.0.0.1` in a config or env file, a hostname
ending `.local`, a server option block gated behind an env flag that defaults off.

## How to present findings

- Critical: a verification bypass in a diff.
- High: a server launched on plain HTTP with no declared opt-out.
- Medium: a forbidden hostname suffix, or a missing `::1` hosts line.
- Low: naming nits (a project name not derived from the repo, extra SANs unused).

Give each finding with its file, the corrected line, and the command to verify.
Say what is already right as well.
