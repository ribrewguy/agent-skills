# Review

Looks good to me — this is a clean, low-risk clarity refactor.

## What changed

- `d` → `date` (parameter)
- `x` → `isoString` (local variable)

The behavior is unchanged: `date.toISOString().split('T')[0]` produces the same `YYYY-MM-DD` string as before, and the function signature `(date: Date): string` is preserved.

## Why this is safe to merge

- Pure rename — no logic change.
- The exported name `formatDate` is unchanged, so no callers are affected.
- The existing test still passes per the author.
- The new names are more readable: `date` says what the parameter represents, and `isoString` documents the intermediate value's shape (which matters when you immediately call `.split('T')[0]` on it).

## Nits (optional)

None worth raising for a one-function clarity tweak. If you wanted to go further you could add a JSDoc/TSDoc block describing the output format (`YYYY-MM-DD`, UTC), but that's clearly out of scope here.

LGTM — ship it.
