# Review of `feature/fix-paginator-offset`

Yep, the fix is right. `Array.prototype.slice(start, end)` uses an exclusive end index, so to return `limit` items starting at `offset`, the end argument must be `offset + limit`. The old code returned `limit - 1` items — classic off-by-one.

## Sanity check

| Call | Old result | New result |
|---|---|---|
| `paginate([a,b,c,d,e], 0, 2)` | `[a]` (wrong) | `[a, b]` (correct) |
| `paginate([a,b,c,d,e], 2, 2)` | `[c]` (wrong) | `[c, d]` (correct) |
| `paginate([a,b,c,d,e], 0, 5)` | `[a,b,c,d]` (wrong) | `[a,b,c,d,e]` (correct) |

## Suggestions before you merge

1. **Add a regression test.** Even one assertion (`expect(paginate([1,2,3,4,5], 0, 2)).toEqual([1, 2])`) would lock this in.
2. **Check for callers compensating for the bug.** A quick grep for `paginate(` — if anyone was passing `limit + 1` to work around the old behavior, they'll now over-fetch by one.
3. **Optional:** consider adding input validation for `offset < 0` or `limit < 0`, since `slice` will silently produce odd results for negatives. Out of scope for this fix.

Otherwise looks good — safe to merge to `main`.
