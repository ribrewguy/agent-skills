Findings:
Review Scope: Task task-103
Process Context: Full process
Execution Context: Unable to determine
Integration Target: Unable to determine
Design Reference: Add endpoint to mark a task complete; sends notification email and writes audit row.
Architecture Reference: None applicable
Feature Specification Reference: None applicable
PRD Reference: None applicable

- `High` [api/routes/tasks.ts:1]
  Problem: State transition is modeled as `POST /api/tasks/:id/complete` — a sub-resource action verb instead of a `PATCH` on the task resource.
  Why it matters: REST URLs name resources, not actions. Sub-resource verb endpoints fragment the API surface (today `/complete`, tomorrow `/reopen`, `/archive`, `/assign`, ...), break uniform interface assumptions, and prevent clients from reasoning about state from the resource alone. The transition is "set status to COMPLETED" — that's a partial update on `/api/tasks/:id`.
  Source of truth: REST conventions for state transitions; design intent ("mark a task complete") is a state change on the existing resource.
  Proposed fix: Replace with `PATCH /api/tasks/:id` accepting `{ "status": "COMPLETED" }` (or `merge-patch+json`). Validate that the requested transition is legal in a single transactional unit.

- `High` [api/routes/tasks.ts:2-4]
  Problem: No `Idempotency-Key` handling on a side-effectful, non-GET request that updates state, sends an email, and writes an audit row.
  Why it matters: Network retries, double-clicks, and proxy replays will execute this handler more than once. Without an idempotency mechanism, the user receives multiple completion emails and the audit table grows duplicate rows for a single logical action — a contract and a data-integrity problem.
  Source of truth: Side-effect discipline for non-GET endpoints; design intent (one notification per completion, one audit row per completion).
  Proposed fix: Require `Idempotency-Key` header. Persist `(idempotency_key, request_hash, response)` so retried keys return the cached response. Wrap the DB update + email enqueue + audit write in a single unit such that the email is enqueued only once per key.

- `High` [api/routes/tasks.ts:2-3]
  Problem: DB update, email send, and audit write are not transactional. The handler updates the row, then awaits `sendEmail` (a network call); a failure or timeout there leaves the task `COMPLETED` in the DB with no email and no audit trail, and a retry (without idempotency) repeats the update.
  Why it matters: Design specifies all three effects ("sends notification email and writes audit row"). The current code can satisfy any subset. Audit logs that miss completions defeat the purpose of having them.
  Source of truth: Task task-103 design — all three effects must occur together.
  Proposed fix: Inside a DB transaction: update the task row, insert the audit row, and enqueue the email via an outbox table. A separate worker drains the outbox, giving you at-least-once email delivery decoupled from the request path. Combine with `Idempotency-Key` to dedupe at the request boundary.

- `Medium` [api/routes/tasks.ts:4]
  Problem: Response uses `task_id` (snake_case) on the wire, inconsistent with the rest of the API surface which is camelCase.
  Why it matters: Mixed naming conventions on the wire force clients to special-case fields per endpoint and tend to leak DB-column conventions into the public contract (Hyrum's Law). Consumers will start depending on the snake_case shape and it becomes a breaking change to fix.
  Source of truth: Conventional JSON API field naming; consistency with the broader API surface.
  Proposed fix: Return `{ "taskId": ..., "status": "COMPLETED" }`. If a wider audit shows other endpoints already mix conventions, file a follow-up to normalize.

- `Medium` [api/routes/tasks.ts:4]
  Problem: Returns `200 OK` with no `Location` semantics for what is effectively a state transition; combined with the verb URL, the response shape doesn't reflect the resource state in a discoverable way.
  Why it matters: For a `PATCH` on `/api/tasks/:id`, `200 OK` returning the updated resource is correct. For a state-transition action endpoint, conventions vary, but `200` here masks the fact that the operation is non-idempotent and stateful. After moving to `PATCH /api/tasks/:id`, returning the full updated `Task` (not just `{taskId, status}`) keeps the response self-describing.
  Source of truth: HTTP status discipline for state-changing operations; principle that responses should be self-describing.
  Proposed fix: After moving to `PATCH`, respond `200 OK` with the full updated `Task` object. Reject illegal transitions with `409 Conflict` and the team's standard error envelope.

- `Medium` [api/routes/tasks.ts:1-5]
  Problem: No error handling — any thrown error escapes the handler and Express returns a default error response that bypasses the team's canonical `{ code, message, details?, requestId }` envelope.
  Why it matters: A consistent error envelope is a hard contract for clients (typed parsers, retry classifiers, log scrapers depend on it). One handler emitting raw stack traces or default Express HTML on failure breaks every consumer that assumed the envelope.
  Source of truth: Team error-envelope convention (flat `{ code, message, details?, requestId }`).
  Proposed fix: Wrap the body in `try/catch` and forward to the project's error middleware (or use `express-async-errors` + a typed `ApiError(code, message, status)` thrown for known cases). Add domain codes like `task_not_found`, `task_already_completed`, `invalid_transition`.

- `Medium` [api/routes/tasks.ts:3]
  Problem: `req.body.notify_user` is read without input validation and is also snake_case in the request body.
  Why it matters: Same naming-consistency issue as the response, and a missing-field or wrong-type input here results in `sendEmail(undefined)` rather than a 4xx with a useful error code.
  Source of truth: Validate-at-the-boundary practice; consistent wire naming.
  Proposed fix: Validate the request body with a schema (zod/io-ts/typebox) using `notifyUser: string` (camelCase, email format). Reject malformed input with `400` and the canonical error envelope.

- `Medium` [api/routes/tasks.ts:2]
  Problem: No authorization check — any caller who can hit this route can mark any task complete by guessing IDs.
  Why it matters: "Mark complete" is a privileged action; without an auth check the endpoint is a horizontal-privilege-escalation vector across users' tasks.
  Source of truth: Standard authz practice for stateful endpoints; design implies a real user is "marking" their own task.
  Proposed fix: Require an authenticated user via the existing auth middleware and verify ownership (or an explicit permission) on the target task before the update.

- `Low` [api/routes/tasks.ts:2]
  Problem: `req.params.id` is passed straight into `db.update` with no ID format validation.
  Why it matters: Polish — depending on `db.update`'s implementation this might be safe, but explicit validation produces clearer 4xxs and makes injection/format-confusion bugs harder to introduce later.
  Source of truth: Validate-at-the-boundary practice.
  Proposed fix: Validate `id` against the project's ID format (UUID, ULID, branded string) before using it.

Residual Risks / Gaps:
- The full `Task` type / response envelope conventions weren't shown; the fix recommendations assume a typed `Task` model and a paginated/typed envelope exist already.
- Whether the project already has an outbox pattern, idempotency middleware, or auth middleware was not verified — recommendations assume these are project-standard.
- No tests are included in the diff; recommend at least: happy path, double-submit with same `Idempotency-Key`, illegal transition (already-completed task), unauthorized caller, malformed body.
- `Execution Context` and `Integration Target` weren't stated in the prompt; fill these in before merge.
