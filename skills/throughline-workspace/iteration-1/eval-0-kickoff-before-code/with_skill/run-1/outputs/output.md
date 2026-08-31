# Picking up tf-18: Add per-IP rate limiting to POST /api/login

Here is exactly what I will do, in order, between now and the first line of code I change. Nothing gets implemented — not even a test file — until every step below has appeared in the transcript.

## 0. Triage: full process, not lightweight

First call: is this a trivial change that could take a lightweight path? No — it touches authentication abuse controls, has a PRD section and architectural guardrails attached, and is externally visible behavior (clients will start receiving 429s). This gets the full process. If you'd rather I take a lightweight path anyway, that's your call to make explicitly — say so and I'll adjust.

## 1. Load procedural memory

Before touching anything, I check whether this repo has curated procedural context for work like this:

- `which cm` — if the CASS CLI is present, run `cm context "per-IP rate limiting on POST /api/login" --json` and fold any surfaced rules (e.g., prior lessons about the middleware chain, proxy IP handling, test conventions) into my plan.
- If `cm` is not installed, I skip this and note the gap rather than pretending it happened.

## 2. Read the task — and cite it

Read tf-18 in the tracker (using whatever command or UI the repo's docs/CLAUDE.md establish for our tracker — I don't invent CLI syntax that isn't documented). I quote into the conversation:

- The full task description and any acceptance criteria.
- Whether tf-18 has a parent task (that changes the branch/integration topology; I'm assuming standalone until the tracker says otherwise).
- Any linked discussion or prior attempts.

## 3. Read the requirements — `docs/prds/authentication.md`, section "Abuse controls"

This is the business source of truth. I read the section and extract, with quotes:

- The limit itself: requests per window, per IP, and whether the PRD specifies exact numbers or leaves them to configuration.
- Required behavior on limit breach: status code (429?), `Retry-After` semantics, response body shape, logging/alerting expectations.
- Scope questions: does "Abuse controls" ask for per-IP only, or also per-account/lockout behavior that tf-18 deliberately excludes? I note the boundary so I implement the task, not the whole section.

## 4. Read the architecture — `docs/architecture/edge.md`, section "Middleware chain"

This is the technical guardrail layer. I read it and extract, with quotes:

- Where rate limiting is allowed to live in the chain (before/after body parsing, auth, logging middleware; app-level vs. edge/proxy-level).
- How client IP is derived — trust-proxy configuration, `X-Forwarded-For` handling. This is the classic correctness trap for per-IP limiting behind a load balancer, so I want the documented answer, not an assumption.
- Sanctioned state/store choices (in-memory vs. Redis or similar), existing middleware conventions, and any library the architecture already blesses.

## 5. Reconcile — or stop

Now I check the layers against each other, in precedence order: PRD → architecture → task.

- If the PRD and the architecture doc conflict (e.g., the PRD implies per-account lockout while the task says per-IP; or the architecture says limiting belongs at the edge proxy, not in app middleware), I **stop, quote both passages with file + heading, explain the impact, offer 1–3 resolution options, and ask you to choose**. No silent reinterpretation.
- If anything essential is unspecified (no thresholds anywhere, no breach behavior defined), I ask before proceeding rather than inventing policy.
- I will not edit anything under `docs/prds/` or `docs/architecture/` — those are source of truth, and changing them requires your explicit permission.

Assuming the layers agree, I proceed.

## 6. Emit the Kickoff Declaration

Before any implementation tool call, this block appears in the conversation (values confirmed by steps 2–4):

```
### Kickoff Declaration
- Process: single-agent
- Requirements: docs/prds/authentication.md § Abuse controls
- Architecture: docs/architecture/edge.md § Middleware chain
- Parent task: N/A (per tracker; revisit if tf-18 has a parent)
- Task: tf-18
- Worktree: N/A (single-agent; feature branch in this clone)
- Branch: feature/tf-18_login_rate_limit
- Integration target: develop
```

## 7. Claim the task atomically

Mark tf-18 as claimed/in-progress in the tracker so no other session or agent picks it up, using the tracker's own claim operation. If the project tracks per-task AI spend, this is also where I record a token estimate and start the stopwatch — measured actuals only exist if the clock starts now.

## 8. Create the branch

From the clean `develop` checkout:

```bash
git pull --ff-only            # make sure develop is current before branching
git checkout -b feature/tf-18_login_rate_limit
```

Single-agent work doesn't need a separate worktree; the feature branch in this clone is the isolation boundary. `develop` is the trunk and the eventual integration target — and nothing merges back into it without your explicit acceptance later, regardless of how green the gates are.

## 9. Codebase reconnaissance (read-only, on the branch)

Now — and only now — I read code:

- The `POST /api/login` route handler and how it's registered.
- The actual middleware chain as implemented, to find the insertion point the architecture doc prescribes.
- Existing dependencies (`package.json`) — is a rate-limiting library already in use elsewhere? Reuse beats introducing a new one; introducing a new dependency is a decision I'll surface, not bury.
- Configuration conventions (env vars, config module) for where thresholds belong.
- The test harness and existing tests around `/api/login`, so new tests match house style.

## 10. Write the implementation plan

A short plan, posted for the transcript before code changes, mapping each requirement from step 3 to a concrete decision constrained by step 4: middleware placement, IP derivation, store choice, threshold configuration, breach response shape, and the test list — including the failing tests I'll write first (429 after N requests in window, window reset, `Retry-After` header, correct IP attribution behind the proxy, and the happy path staying untouched).

---

**Then, and only then, the first line of code** — which will be a failing test, not the middleware itself.

For visibility on what comes after (not part of this ask): implementation → quality gates run with real output → a UAT check-in with you before commit since this is externally visible → commit on the feature branch with the task id → an implementation summary that ends at "ready to merge, awaiting your acceptance" → merge to `develop` only on your explicit yes → close tf-18 only after the branch lands → cleanup and closeout summary, with 1–3 learned rules recorded back into procedural memory.
