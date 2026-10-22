---
title: local-https
parent: Skills
nav_order: 13
---

# local-https

TLS for every locally run server. Each server an agent starts listens on HTTPS with an mkcert certificate at `<project>-local`, unless the owner opts that server out and says why. The failure it targets is the plain `http://localhost:3000` launch that drops a `Secure` cookie and turns a successful login into a 401, and the backend whose client "fixes" the resulting certificate error with a verification bypass.

Like [isolated-stack-development](isolated-stack-development), it ships a skill, a tool and a hook together, because the mistake is made by an agent that did not think the topic was TLS: it thought the topic was "run the app".

## What makes this skill distinct

- **Backends are included.** A server no browser touches still gets TLS, and its clients (Node, JVM, Python, containers) get the CA trusted once per runtime. Nothing is ever told to skip verification; `NODE_TLS_REJECT_UNAUTHORIZED=0`, `rejectUnauthorized: false`, `curl -k`, `verify=False` and trust-all managers are review failures.
- **A naming rule with a measured reason.** The host is `<project>-local`. `.local` is reserved for multicast DNS and was measured at about five seconds per lookup; `.dev` and `.app` are HSTS-preloaded TLDs; `*.localhost` is not resolved uniformly. Hosts lines are required for both `127.0.0.1` and `::1`.
- **Opt-out is explicit.** Only the owner opts a server out, with `https: false` and a `reason` in the tracked `.local-https.json`. The tool rejects an opt-out without a reason.
- **Worktrees get certs by copy.** A fresh worktree has no `.cert/`; `local-https copy` lands the main checkout's certs at the same relative paths, and the guard names that command when it blocks.
- **Declaration values are untrusted input.** The file is tracked and can arrive with a clone, so values are validated before use and never interpolated into a command.

## What ships in the plugin

| Piece | What it does |
|---|---|
| `SKILL.md` | The rule, naming, certificate layout, declaration, trust summary, opt-out, worktrees, verification and severity ladder. |
| `scripts/local-https` | `setup`, `check`, `copy`, `trust`, `doctor`, `proxy`. Never edits `/etc/hosts` or a shell profile; prints `OWNER:` lines instead. |
| `scripts/guard.sh` + `hooks/hooks.json` | PreToolUse guard: blocks a declared server launching without its cert and any `NODE_TLS_REJECT_UNAUTHORIZED=0`, warns for the rest. Silent on tests, builds and installs. |
| `scripts/tls-proxy.mjs` | Dependency-free TLS front for plain-HTTP builds, with WebSocket upgrades. |
| `references/` | Nuxt and Nitro, Vite, Node, Spring, Python, other stacks, per-runtime trust, and the tool and hook reference. |

## Coverage limits

Claude Code gets all three layers; other agents get the skill and the tool but not the hook. macOS is the target and Linux is unverified. Production TLS is out of scope. Evaluation receipts have not been recorded yet.
