# Order-to-warehouse sync

Add `SyncOrderToWarehouse(ctx, db, httpClient, order)` in
`services/orders/sync.go` that:

- Marks the order `sync_status='pending'` with `sync_started_at` timestamp.
- POSTs the order to `https://warehouse.example.com/orders`.
- On 200, marks the order `sync_status='synced'` with `sync_completed_at`.
- On any failure, the order's `sync_status` is left in a state that lets a
  retry succeed (not stuck in 'pending' forever).
- All DB writes happen in a single transaction.
- Honors context cancellation.
- 5 unit tests cover happy path, http failure, db begin failure, marshal
  failure, and warehouse non-200.
