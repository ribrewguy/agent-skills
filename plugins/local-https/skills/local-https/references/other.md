# Other stacks

## Approach

1. Find the framework's TLS option (a key and cert pair, a PKCS12 key store, or
   none).
2. Run `local-https setup <server dir>` (add `--jvm` for a key store). It writes
   `.cert/<project>.pem`, `.cert/<project>-key.pem`, declares the server, and
   prints the hosts and trust lines for the owner.
3. Feed the pair to the framework's option and bind the project host.
4. If the framework has no TLS option, run it on a plain local port and front it
   with `local-https proxy <tls-port> <http-port> <dir>`.
5. Make every client of the server trust the mkcert CA for its runtime (see the
   trust reference).

## Verify

```bash
local-https check <dir>
curl https://myapp-local:<port>/
```

The curl must succeed with no `-k`. If the hostname does not resolve, the hosts
entry is missing: ask the owner to run the printed `OWNER:` line. A test needing
a name without a hosts entry can use `curl --resolve myapp-local:<port>:127.0.0.1`.

## Footguns

- Frameworks that read TLS options only from a config file ignore flags after a
  bare `--`; pass them directly.
- A hostname ending `.local` stalls on mDNS; always `<project>-local`.
