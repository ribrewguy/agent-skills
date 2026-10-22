# Nuxt and Nitro

## Approach

Nuxt's dev server takes the cert pair through `devServer`. Resolve the paths
from the config file's own location so they hold from any working directory,
bind the project host, and keep the pair in the app's own directory (the one
holding `nuxt.config.ts`), where `local-https setup <dir>` writes it.

## Dev server

```ts
// nuxt.config.ts
import { fileURLToPath } from 'node:url'

export default defineNuxtConfig({
  devServer: {
    host: 'myapp-local',
    port: 3000,
    https: {
      key: fileURLToPath(new URL('./.cert/myapp-key.pem', import.meta.url)),
      cert: fileURLToPath(new URL('./.cert/myapp.pem', import.meta.url)),
    },
  },
})
```

Open the app at the project host and port, on https. The hosts file must carry
`127.0.0.1` and `::1` lines for `myapp-local` (the tool prints them).

Server routes that call another local service (for example an orders API at
`rest.myapp-local`) run in Node: set `NODE_EXTRA_CA_CERTS` in the launching
shell so they trust the mkcert CA. See the trust reference.

## Footguns

- `pnpm dev -- --port 3001`: the `--` reaches nuxt as end-of-flags and the
  `devServer` block can be ignored, so the server comes up on plain HTTP. Pass
  the flag without it: `pnpm exec nuxt dev --port 3001`, or change `devServer.port`.
- Setting `NUXT_PUBLIC_*` base URLs to `http://localhost:3000` in `.env`
  reintroduces plain HTTP for cookies. Use `https://myapp-local:3000`.
- A cert generated for `localhost` only fails on the project host: run
  `local-https check` and regenerate if `sans` is MISSING.

## Production build

`node .output/server/index.mjs` has no TLS option. Front it with the proxy:

```bash
PORT=3100 node .output/server/index.mjs
local-https proxy 3000 3100 apps/web
```

The proxy preserves `Host`, adds `X-Forwarded-Proto: https`, and forwards
WebSocket upgrades. Browse `https://myapp-local:3000`.
