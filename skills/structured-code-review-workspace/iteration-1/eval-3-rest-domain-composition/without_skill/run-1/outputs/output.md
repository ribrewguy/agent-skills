# PR Review: `mark task complete` endpoint

A few REST conventions and reliability concerns worth addressing before this lands.

## URL design — use `PATCH` on the resource

```ts
router.post('/api/tasks/:id/complete', ...)
```

This is a sub-resource verb endpoint. The standard REST way to model "mark this task complete" is a partial update on the task itself:

```ts
router.patch('/api/tasks/:id', ...)  // body: { status: 'COMPLETED' }
```

That keeps the URL space resource-oriented, lets one handler serve any status transition, and avoids the slippery slope of `/complete`, `/reopen`, `/archive`, `/assign`, etc.

## Idempotency — required on a side-effectful POST

The handler updates the DB, sends an email, and writes an audit row. With no idempotency mechanism, any retry (network blip, double-click, proxy replay) will:

- send a second completion email,
- write a duplicate audit row,
- repeat the DB update (cheap but still wrong from a logging perspective).

Add an `Idempotency-Key` header requirement. Persist `(key, request_hash, response)` so the same key replays the cached response. A standard Express middleware can handle this generically.

## Wire naming — use camelCase

```ts
res.status(200).json({ task_id: req.params.id, status: 'COMPLETED' })
```

`task_id` is snake_case; the rest of your API surface is camelCase (presumably). Mixed conventions force clients to special-case parsing per endpoint and tend to leak DB-column names into the public contract. Same goes for `req.body.notify_user` — expect `notifyUser`.

```ts
res.status(200).json({ taskId: ..., status: 'COMPLETED' })
```

## Status code

`200 OK` is fine for a PATCH that returns the updated resource. After moving to `PATCH /api/tasks/:id`, return the full updated `Task` rather than `{ taskId, status }` — self-describing responses are easier on clients.

For illegal transitions (already completed, task not found, etc.), use `409 Conflict` / `404 Not Found` and the team's `{ code, message, details?, requestId }` envelope.

## Error handling

The handler has no `try/catch`. Any thrown error escapes Express and produces a default error page or stack trace, bypassing the team's standard error envelope. Wire the handler into the project's error middleware (or use `express-async-errors`) and throw typed `ApiError(code, message, status)` for known cases. Suggested codes:

- `task_not_found` (404)
- `task_already_completed` (409)
- `invalid_transition` (409)
- `unauthorized` (401)

## Transactional integrity

```ts
await db.update(...)        // (1)
await sendEmail(...)        // (2)
res.status(200).json(...)   // (3)
```

If `sendEmail` fails or times out, the task is `COMPLETED` in the DB but no email is sent and (per the design) no audit row is written. The design says all three effects must occur together. Use the outbox pattern:

1. In one DB transaction: update the task, insert the audit row, insert an outbox row representing the email.
2. A worker drains the outbox and calls `sendEmail`, retrying until success.
3. Combine with `Idempotency-Key` to dedupe at the request boundary.

## Authorization

There's no auth check. As written, any caller can mark any task complete. Add the project's auth middleware and verify the caller has permission on the target task (ownership or explicit role).

## Input validation

`req.body.notify_user` is read directly without validation. Schema-validate the body with zod/io-ts/typebox so a missing or wrong-typed field produces a clean `400` instead of `sendEmail(undefined)`.

## Suggested rewrite (sketch)

```ts
router.patch(
  '/api/tasks/:id',
  requireAuth,
  requireIdempotencyKey,
  validateBody(PatchTaskSchema),
  async (req, res, next) => {
    try {
      const { id } = req.params
      const { status } = req.body
      const task = await db.transaction(async (tx) => {
        const updated = await tx.tasks.update({ id, status })
        await tx.audit.insert({ taskId: id, action: 'complete', actorId: req.user.id })
        await tx.outbox.enqueue({ type: 'task.completed.email', taskId: id, to: req.user.email })
        return updated
      })
      res.status(200).json(task)
    } catch (err) {
      next(err)  // hits the canonical error envelope middleware
    }
  }
)
```

## Summary

The change works on the happy path but ships with a verb-in-URL, no idempotency, snake_case on the wire, no error envelope, and partial-failure risk between DB and email. None of these are subjective — they're all called out by the design (one email, one audit row), the team's error-envelope convention, and standard REST conventions. Worth fixing before merge.
