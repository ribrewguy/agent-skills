# Picking up tf-18: Add per-IP rate limiting to POST /api/login

Here is exactly what I would do, in order, from right now until the first line of code I change. Nothing below modifies source; the first code change (a failing test) is where this process ends.

## 1. Claim the task and read it completely

- Move tf-18 to "in progress" in the tracker and assign it to me, so the board reflects reality even though I'm solo.
- Read the full ticket, not just the title: description, acceptance criteria, comments, linked tickets (e.g. a prior incident or a parent epic on abuse controls), and any attached discussion. I'm looking for constraints that never made it into the docs — "must ship behind a flag", "ops wants a metric", "don't break the mobile client's retry loop".
- Note the ticket's definition of done, if it has one. If it doesn't, I'll write one myself in step 5.

## 2. Read the business requirements: `docs/prds/authentication.md`, section "Abuse controls"

I read this before touching any code, and I extract concrete, testable parameters into a scratch list:

- **The limit itself**: how many attempts, per what window (e.g. 10 per 5 minutes)? Fixed numbers or "configurable"?
- **Keying**: the ticket says per-IP — does the PRD agree, or does it also mention per-account or per-IP+username? (Per-IP alone has known gaps: shared NATs, distributed attacks.)
- **Behavior when the limit is hit**: reject with what status (429?), what error body, is a `Retry-After` header required, is there a lockout vs. a rolling throttle, does the counter reset on successful login?
- **Exemptions**: allowlisted IPs, internal health checks, trusted partners?
- **Observability requirements**: does the business want limited requests logged, alerted on, or surfaced to the user in any specific wording?
- **Anything the PRD requires that the ticket doesn't mention** — if the "Abuse controls" section also demands e.g. CAPTCHA after N failures, I note it and confirm scope (that's likely a separate ticket, but I won't silently drop it).

Anything ambiguous goes on an "open questions" list, not into my head.

## 3. Read the technical guardrails: `docs/architecture/edge.md`, section "Middleware chain"

This tells me *where* and *how* the implementation is allowed to exist:

- **Position in the chain**: where does rate limiting belong relative to body parsing, auth, logging, CORS? (Typically as early as possible — before we do expensive work — but the doc's ordering is authoritative.)
- **Existing conventions**: is there already a middleware pattern, a shared rate-limiter utility, or a designated place (`src/middleware/`?) new middleware must live?
- **Client IP derivation**: how does this service run — behind a load balancer/CDN? What does the doc say about `X-Forwarded-For` / `trust proxy`? Getting this wrong means rate-limiting the LB's IP, which is the classic failure mode of this exact task.
- **State/storage constraints**: are we multi-instance? Does the doc mandate a shared store (Redis?) or permit in-memory? Fail-open vs. fail-closed if the store is down?
- **Any prohibitions**: banned dependencies, latency budgets for the middleware chain, config/env-var conventions.

## 4. Recon the actual code (read-only)

Docs drift; the code is the ground truth I reconcile against:

- Find the `POST /api/login` route handler and read it end to end, including what middleware already wraps it.
- Identify the framework (Express? Fastify? Hono?) and the middleware registration point — the file where the chain from `edge.md` is actually assembled — and check whether the real order matches the doc.
- Search for existing rate limiting anywhere in the repo (`grep -ri "rate" --include="*.ts" --include="*.js"`, look for `express-rate-limit`, `rate-limiter-flexible`, etc. in `package.json`). If a limiter already exists for another route, I reuse its pattern and store rather than inventing a second one.
- Check what shared infrastructure exists: is there a Redis client already configured? A config module where limits/env vars live? A logger/metrics facility I'm expected to use?
- Read the test setup: test runner, where route/middleware tests live, how the app is instantiated in tests (supertest against a built app?), whether there's a way to fake time (important for window-based limits).
- Run the existing test suite once to confirm a green baseline before I change anything.

## 5. Reconcile and write a short plan; resolve or record open questions

Now I collapse steps 1–4 into a small design note (a comment on tf-18, so the decision trail lives with the task):

- **Approach**: algorithm (fixed window / sliding window / token bucket — chosen to match the PRD's wording), library vs. hand-rolled (prefer an established library unless the guardrails or existing patterns say otherwise).
- **Key derivation**: exactly how the client IP is obtained given the proxy setup, including IPv6 handling.
- **Store**: shared (Redis) if multi-instance per `edge.md`, with an explicit fail-open/fail-closed decision and rationale.
- **Placement**: where in the middleware chain, scoped to `POST /api/login` only — not globally.
- **Response contract**: status code, body shape (matching the service's existing error envelope), `Retry-After`.
- **Config**: limit and window as configuration with the PRD's values as defaults.
- **Observability**: log line and/or metric per the PRD and existing conventions.
- **Out of scope**: anything the PRD hinted at that this ticket doesn't cover, listed explicitly.
- **Test list**: under-limit passes through; over-limit gets 429 with correct headers/body; window expiry restores access; keying is actually per-IP (two IPs don't share a bucket); proxy-header handling; store-outage behavior; existing login behavior unchanged.

For each open question from steps 2–3: since I'm solo, I decide which are **blocking** (e.g. the PRD gives no numbers at all — I'd ask the ticket owner/stakeholder and pause) versus **safely assumable** (e.g. exact error copy — I choose, and record the assumption in the ticket comment so it's visible and reversible).

## 6. Prepare the workspace

- `git fetch` and fast-forward `develop` so I'm building on the latest trunk (status is clean, so this is safe).
- Create a feature branch named after the task: `git switch -c tf-18-login-rate-limit`.
- `npm ci` (or the repo's package-manager equivalent) so my dependency state matches the lockfile; re-run the test suite on the branch to confirm the baseline is still green.

## 7. First change

With requirements extracted, guardrails understood, approach written down, and a green baseline on a clean branch — the first line of code I change is a **failing test**: an integration test asserting that the (N+1)th login attempt from one IP within the window returns 429. Then, and only then, do I start implementing the middleware to make it pass.
