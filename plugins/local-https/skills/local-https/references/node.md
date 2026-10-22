# Node servers

## Approach

Node's TLS options take the pair as buffers. Read the files relative to the
module, bind the project host, and keep the pair in the server's own directory.

## Raw https

```js
import https from 'node:https'
import { readFileSync } from 'node:fs'

const options = {
  key: readFileSync(new URL('./.cert/myapp-key.pem', import.meta.url)),
  cert: readFileSync(new URL('./.cert/myapp.pem', import.meta.url)),
}
https.createServer(options, handler).listen(8443, 'myapp-local')
```

## h3 and Nitro-style listeners

```js
import { createServer } from 'node:https'
import { toNodeListener } from 'h3'
createServer(options, toNodeListener(app)).listen(8443, 'myapp-local')
```

## Express

```js
https.createServer(options, app).listen(8443, 'myapp-local')
```

## Fastify

```js
const app = Fastify({ https: options })
await app.listen({ port: 8443, host: 'myapp-local' })
```

## Clients

A Node process that calls another local TLS server trusts the mkcert CA via
`NODE_EXTRA_CA_CERTS`, set before the process starts. Never use
`rejectUnauthorized: false`, an `https.Agent` with it, or
`NODE_TLS_REJECT_UNAUTHORIZED=0`. If a library needs a CA explicitly, read
`rootCA.pem` from `mkcert -CAROOT` and pass it as `ca`.

## Footguns

- `npm run start -- --port 9000` hands the flag to the script only if the script
  forwards it; a `--` before `--port` or `--host` is often swallowed. Read the
  port from an env var instead.
- A server on `0.0.0.0` is reachable by name only through the hosts entry; bind
  the project host or `127.0.0.1` and `::1` deliberately.
- Calling `http://localhost:<port>` from a sibling service bypasses TLS; use
  `https://myapp-local:<port>`.
