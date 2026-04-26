# Recent Notifications Endpoint

Since the requirement is fixed at 5 and there's no pagination, you can keep this very simple.

## URL

```
GET /api/notifications/recent
```

Or alternatively `GET /api/notifications?limit=5` — but a dedicated `/recent` endpoint is cleaner since the count is fixed. The current user is inferred from the auth token, no need to put a user id in the URL.

## Response shape

```json
{
  "notifications": [
    {
      "id": "ntf_abc123",
      "type": "comment_mention",
      "title": "Sam mentioned you in a comment",
      "body": "...",
      "createdAt": "2026-04-26T18:02:11Z",
      "isRead": false,
      "linkUrl": "/tasks/123"
    }
  ],
  "unreadCount": 3,
  "fetchedAt": "2026-04-26T18:05:00Z"
}
```

I included a couple of useful extras:

- **`unreadCount`** — handy for the badge in the UI without having to make a second call.
- **`fetchedAt`** — lets the client decide when the data is stale and trigger a refetch.

## Status codes

- `200 OK` — array returned (may be empty if the user has no notifications yet).
- `401 Unauthorized` — no session.

## TypeScript

```ts
interface Notification {
  id: string
  type: NotificationType
  title: string
  body: string
  createdAt: string
  isRead: boolean
  linkUrl: string
}

interface RecentNotificationsResponse {
  notifications: Notification[]
  unreadCount: number
  fetchedAt: string
}
```

That should be enough. Keep the array length capped at 5 server-side regardless of any client query params.
