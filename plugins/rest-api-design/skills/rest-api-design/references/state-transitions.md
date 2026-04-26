# State Transitions — Detail

Reference for [State transitions are PATCH](../SKILL.md#state-transitions-are-patch-not-sub-resource-verbs) in the main SKILL.md. Read when you need to argue against a sub-resource verb proposal, set up the side-effect discipline for a transition handler, or decide whether a new operation should be `PATCH` or a sub-resource `POST`.

## State transitions use `PATCH`, not sub-resource verbs

Changing a field on a resource — including a `status` field that drives side effects — is an update. Use `PATCH` on the resource URI. **Don't invent sub-resource verbs like `/complete`, `/cancel`, `/activate`, `/publish`**. They read as RPC bolted onto REST, fragment the URL space (one per action × resource), and push behavior that belongs in the service layer into the URL.

| Anti-pattern | Correct |
|---|---|
| `POST /api/tasks/:id/complete` | `PATCH /api/tasks/:id` with `{ "status": "COMPLETED" }` |
| `POST /api/orders/:id/cancel` | `PATCH /api/orders/:id` with `{ "status": "CANCELLED" }` |
| `POST /api/users/:id/activate` | `PATCH /api/users/:id` with `{ "status": "ACTIVE" }` |
| `POST /api/posts/:id/publish` | `PATCH /api/posts/:id` with `{ "status": "PUBLISHED" }` |

## Side effects belong to the transition, not the URL

If `task.status` moving from `IN_PROGRESS` to `COMPLETED` must send an email, that's the service's responsibility on the state change — it doesn't matter which URL or verb triggered the transition. The handler detects the actual transition (not every PATCH that sets status to COMPLETED) and fires side effects exactly once per real transition.

Concretely:

```typescript
async function patchTask(id: TaskId, input: UpdateTaskInput): Promise<Task> {
  const old = await db.tasks.findOne({ id })
  if (!old) throw new TaskNotFoundError(id)

  // Apply the patch
  const updated = { ...old, ...input }
  await db.tasks.update({ id }, updated)

  // Detect the actual transition — don't fire on every PATCH that sets status
  const isCompletion = old.status !== 'COMPLETED' && updated.status === 'COMPLETED'
  if (isCompletion) {
    await sendCompletionEmail(updated)
    await writeAuditRow({ event: 'task.completed', taskId: id })
  }

  return updated
}
```

This is more robust than URL-coded semantics: a client retrying a PATCH after a network blip does the right thing (no duplicate emails) without you inventing a new endpoint.

## Forbidden transitions return an error

Attempting to move from `COMPLETED` to `IN_PROGRESS` returns a clear error (`409 CONFLICT` with `code: "InvalidStatusTransition"` or `"TaskAlreadyCompleted"`) so the client sees a real failure rather than a silent no-op:

```json
{
  "code": "InvalidStatusTransition",
  "message": "Cannot transition from COMPLETED to IN_PROGRESS",
  "details": { "from": "COMPLETED", "to": "IN_PROGRESS" },
  "requestId": "req_abc123"
}
```

The state machine encodes which transitions are allowed; the handler rejects everything else.

## When `POST` to a sub-collection IS correct

`POST /api/parent/:id/children` is appropriate when **a new resource with its own identity and lifecycle is created**, not when a field on the parent is being flipped.

| Legitimate `POST` to sub-collection | Why |
|---|---|
| `POST /api/accounts/:id/transfers` | A `Transfer` resource is created; it has its own `id`, `status`, history, and URL |
| `POST /api/orders/:id/refunds` | A `Refund` resource is created with its own lifecycle |
| `POST /api/pulls/:id/approvals` | An `Approval` resource is created per reviewer |
| `POST /api/tasks/:id/comments` | A `Comment` is a distinct resource with its own ID |
| `POST /api/users/:id/email-verifications` | An `EmailVerification` resource tracks the one-off send |

**The test:** does the operation produce a new resource with its own identity, URL, and lifecycle? Then `POST` to a sub-collection is correct. If the operation only changes fields on the parent, it's `PATCH` on the parent.

## Command-shaped endpoints — model the noun

Operations that don't fit either pattern (e.g., "resend welcome email") are usually hiding a resource. Make the noun explicit:

- "Resend welcome email" → `POST /api/email-sends` with body naming the template + recipient → creates an `EmailSend` resource.
- "Trigger nightly report" → `POST /api/report-runs` → creates a `ReportRun` resource.
- "Retry failed job" → `POST /api/jobs/:id/retries` → creates a new `Retry` (or appends to a retry log).

Modeling the noun gives you something to query (`GET /api/email-sends?recipient=...`), audit, and version. Command-shaped URLs leave you with no resource to inspect.

## Idempotency on `PATCH`

`PATCH` is expected to be idempotent in effect: repeating the same body produces the same server state. A second `PATCH { "status": "COMPLETED" }` on an already-completed task is a no-op on the resource. Side effects must deduplicate in the service layer (only fire on the real transition).

For high-stakes transitions where a client might retry and you want byte-identical response replay, `PATCH` can accept `Idempotency-Key` with the same semantics as `POST` — store `(key, payloadHash, response)` for a retention window. Stripe uses this pattern on `PATCH` for amount changes on subscriptions.

See the SKILL.md "Idempotency" section for the full pattern.
