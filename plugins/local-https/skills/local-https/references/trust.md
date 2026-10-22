# Client trust

A TLS server only works for clients that trust the mkcert root CA. Do this
once per runtime, never per request. `local-https trust` prints each line below
with `IN EFFECT` or `NOT SET`. Edits to the shell profile are the owner's:
print the line and ask.

## System, browsers, curl

```bash
mkcert -install
```

Verify: `local-https check` reports `OK ca-trusted`, and
`curl https://myapp-local:3000/` succeeds with no `-k`.

## Node

```bash
export NODE_EXTRA_CA_CERTS="$(mkcert -CAROOT)/rootCA.pem"
```

Node reads this at process start, so a `.env` the app loads is too late. It
belongs in the shell profile (or the launcher's environment). Verify:
`local-https check` reports `OK node-ca`, and in the launching shell
`echo "$NODE_EXTRA_CA_CERTS"` prints the root path. A Nuxt server route
calling a local API with `$fetch` is the usual consumer.

## JVM

`mkcert -install` with `JAVA_HOME` set imports the root into that JDK's
cacerts. For another JDK, import explicitly:

```bash
"$JAVA_HOME/bin/keytool" -importcert -noprompt -cacerts -storepass changeit \
  -alias mkcert-rootCA -file "$(mkcert -CAROOT)/rootCA.pem"
```

Or point one process at a store: `-Djavax.net.ssl.trustStore=<path>`. Verify:
`"$JAVA_HOME/bin/keytool" -list -cacerts -storepass changeit -alias mkcert-rootCA`.

## Python

```bash
export REQUESTS_CA_BUNDLE="$(mkcert -CAROOT)/rootCA.pem"
export SSL_CERT_FILE="$(mkcert -CAROOT)/rootCA.pem"
```

Both replace the default bundle. When the process also calls public hosts, use
a bundle that holds the public roots plus the mkcert root. Verify with
`local-https trust`, which checks that the named file holds the root.

## Docker

A container that calls the host mounts the root read-only and sets the
runtime's variable inside the container:

```bash
docker run -v "$(mkcert -CAROOT)/rootCA.pem:/certs/rootCA.pem:ro" \
  -e NODE_EXTRA_CA_CERTS=/certs/rootCA.pem myapp-image
```

When it calls the host as `host.docker.internal`, add that name to
`extraNames` in `.local-https.json` and rerun `local-https setup` so the cert
covers it. Verify from inside the container with the runtime's own client, no
bypass flags.

## Never

Each of these is a review failure, Critical severity:

- `NODE_TLS_REJECT_UNAUTHORIZED=0` (the guard blocks it)
- `rejectUnauthorized: false`, or an agent or proxy entry with `secure: false`
- `curl -k` or `--insecure`
- `verify=False`
- trust-all `TrustManager` or `HostnameVerifier` in a JVM client

The fix is always the same: trust the CA for that runtime, as above.
