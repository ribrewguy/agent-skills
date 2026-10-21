PLANTED BUG: Path traversal via insufficient filter (multiple bypasses)

The filter `filename.replace("..", "")` catches the literal substring `..`
but misses many bypasses:

1. **Absolute paths**: `PathBuf::from("/uploads").join("/etc/passwd")` returns
   `/etc/passwd`, not `/uploads/etc/passwd`. PathBuf::join, when given an
   absolute path on its right, REPLACES the left. The filter doesn't catch
   absolute paths at all.
2. URL-encoded variants: `%2e%2e/etc/passwd` survives the filter.
3. Backslash variants on systems that interpret backslash as a separator.
4. Embedded null bytes: `..\0/etc/passwd`.
5. Unicode dot equivalents.

Severity: CRITICAL (arbitrary file write outside /uploads)

The fix is to canonicalize the resolved path and verify it's still within
/uploads, OR to allowlist a safe character set in the filename and reject
the request if anything else appears.

OTHER REAL BUGS:
- The four `.unwrap()` calls (multipart.next_field, file_name, bytes,
  fs::write) panic on malformed input, taking down the worker thread
  on every adversarial request. Should return a 4xx instead.
  Severity: HIGH (DOS via crafted input).
- No file size limit. A multi-GB upload exhausts memory.
  Severity: HIGH (DOS).
- No content-type validation. An attacker can upload an executable.
  Severity: MEDIUM.
