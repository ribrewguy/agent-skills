# Vite

## Approach

Vite serves TLS when `server.https` carries the pair. Set `server.host` to the
project host so the server binds and prints the right name, and read the files
relative to the config.

## Config

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import { readFileSync } from 'node:fs'

export default defineConfig({
  server: {
    host: 'myapp-local',
    port: 5173,
    https: {
      key: readFileSync(new URL('./.cert/myapp-key.pem', import.meta.url)),
      cert: readFileSync(new URL('./.cert/myapp.pem', import.meta.url)),
    },
  },
  preview: {
    host: 'myapp-local',
    https: {
      key: readFileSync(new URL('./.cert/myapp-key.pem', import.meta.url)),
      cert: readFileSync(new URL('./.cert/myapp.pem', import.meta.url)),
    },
  },
})
```

Proxy targets in `server.proxy` that point at a local TLS backend need the CA
trusted by the Node process running Vite: export `NODE_EXTRA_CA_CERTS`, and
never set `secure: false` on the proxy entry.

## Footguns

- `server.host: true` listens on every interface and loses the project host in
  the printed URL; name the host.
- `vite preview` has its own `preview` block; configuring only `server` leaves
  preview on plain HTTP.
- A `--` before `--port` or `--host` in an npm script (`pnpm dev -- --port 4000`)
  can drop the flag; pass it directly or set it in the config.
- `server.proxy` entries with `secure: false` are verification bypasses.
