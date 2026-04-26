# Recent Notifications — URL and Response Shape

The endpoint is small but the design choices matter, because "always 5" is a *policy bound*, not "we just don't paginate yet." Treat it that way and the shape becomes clear.

## URL

```
GET /api/notifications/recent
```

Plural noun, no verbs — `getNotifications`, `fetchRecent`, `latest` would all bake the action into the URL when the HTTP method already names it. The `/recent` segment is a sub-resource describing *which* notifications, not an action.

If `/recent` reads awkwardly, an alternative is:

```
GET /api/me/notifications
```

…where the rule "5 most recent for the current user" lives entirely in the route's documented behavior. Either is fine; pick one and don't expose both.

## Response shape

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Request-ID: req_01HX...

{
  "data": [
    {
      "id": "ntf_01HX...",
      "type": "comment.mention",
      "title": "Ada mentioned you in a comment",
      "createdAt": "2026-04-26T18:02:11Z",
      "readAt": null,
      "subjectUrl": "/api/tasks/task_01HX..."
    }
    /* …up to 4 more, never more than 5 */
  ]
}
```

A few deliberate choices:

- **`{ data: [...] }` envelope, not a bare array.** Bare arrays can't grow into a richer response without breaking every consumer. The envelope is the same shape we use for paginated lists, minus the `pagination` sub-object — so any "unwrap a list response" client helper still works.
- **No top-level resource name** (no `{ "notifications": [...] }`). Keeping the key generic across all list-shaped endpoints means clients write `response.data` once and never special-case per route.
- **No invented sibling fields.** No `unreadCount`, no `fetchedAt`, no `lastSeenId`. Those weren't asked for; adding them speculatively creates contract obligations (Hyrum's Law — once a field is observable, somebody depends on it). If unread count is needed later, it goes on its own dedicated endpoint or a clearly-named response field added intentionally.

## What's deliberately *missing*

This is the most important part of the design.

### No pagination

This is bounded by policy at 5 — it is not a growing list. Cursor / offset / page parameters don't belong here. Adding them would imply the bound is negotiable when it isn't.

### No `limit` / `count` / `take` query parameter

Do not let the client request fewer than 5, or — much more importantly — *more* than 5. The bound is server-enforced and fixed.

```http
GET /api/notifications/recent?limit=50    ← do not honor this
```

If the client could pass `limit=50`, then within a week you'll have a dashboard quietly relying on 50, and your "always 5" guarantee is dead. Refuse the parameter (treat it as an unknown field and ignore it, or `400` if you want to be loud about it). Either way, **the server returns at most 5**, period.

### No `total` field

The set is, by construction, at most 5. There's no pagination to drive a total against, and the client can `data.length` it anyway.

## Why "always 5" needs guardrails

Two reasons to write this rule down explicitly in the route's documentation, not just in the handler:

1. **Hyrum's Law.** As soon as the response always has 5 items, every consumer depends on exactly 5. A future change to "the 5 most recent in the last 24h" (which can produce fewer than 5) is now a breaking change to anyone who hard-coded `notifications[4]`. Document upfront that the array contains *up to* 5 items so clients don't hard-code length.
2. **Broadening the bound is a breaking change.** Going from "always 5" to "configurable, default 20" is not additive — it changes the response size, the latency profile, and the implied contract. If you ever need that, it's a new endpoint (`GET /api/notifications` with cursor pagination), and `/recent` stays exactly as it is. Don't try to evolve `/recent` into a paginated list.

## Summary

| | |
|---|---|
| **Method + URL** | `GET /api/notifications/recent` |
| **Auth** | Authenticated user (the "current user" comes from the session, not the URL) |
| **Query params** | None. Reject or ignore `limit`/`page`/`cursor`. |
| **Status** | `200 OK` always (empty array if the user has no notifications) |
| **Body** | `{ "data": Notification[] }` — at most 5 items |
| **Headers** | `X-Request-ID` on every response |
| **Errors** | `401 SessionExpired` if unauthenticated. The flat error envelope (`{ code, message, details?, requestId }`) applies. |

The smallest thing the route has to do, with no doors left open for the bound to drift later.
