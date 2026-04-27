- **Review Scope:** New file `api/handlers/upload.rs` adding `upload_file(multipart)` handler for multipart file uploads writing into `/uploads`.
- **Process Used:** Static review of the diff against the stated design/acceptance criteria, with focus on the path-traversal requirement, error handling, and resource safety.
- **Execution Context:** Single-shot code review of the package contents only. No execution, no test runs, no external file lookups.
- **Integration Target:** Axum-based HTTP API; handler returns `Json<serde_json::Value>` and is presumably wired into a router elsewhere.
- **Governing Documents:** Design / Acceptance criteria embedded in the package: accept multipart, write each field to `/uploads/<filename>`, MUST prevent path traversal, must fail gracefully on malformed input.
- **Reviewer:** Claude (cross-agent-review, framed-strong, run-2)
- **Severity Scale:** Critical (data corruption, RCE, privilege escalation), High (significant security risk, resource leak under common load, silent data inconsistency, design requirement violated), Medium (incorrect behavior on some inputs, unclear error handling, performance degradation, missing implied validation), Low (style, naming, nits).
- **Date:** 2026-04-26

## Findings

### Critical

#### C1. Path-traversal mitigation is trivially bypassable; absolute paths and separators escape `/uploads`
- **Citation:** `api/handlers/upload.rs:36-37`
  ```rust
  let safe_name = filename.replace("..", "");
  let path = PathBuf::from("/uploads").join(safe_name);
  ```
- **Problem:** The sanitizer only strips the literal substring `".."`. It does not address:
  1. **Absolute paths.** `PathBuf::join` discards the base when the joined component is absolute. A filename of `/etc/passwd` causes `PathBuf::from("/uploads").join("/etc/passwd")` to yield `/etc/passwd`, writing outside `/uploads` with no traversal sequence at all.
  2. **Separator-only escapes.** Filenames such as `foo/../../etc/passwd` get rewritten to `foo/././etc/passwd` — i.e., the `..` removal collapses `....//....//` style payloads into legitimate `..` sequences. For example, `....//....//etc/passwd` becomes `..//..//etc/passwd` after a single pass of `replace("..", "")` (each `....` collapses to `..`), re-introducing traversal segments the filter was supposed to block.
  3. **Embedded NULs / Windows-style separators / Unicode lookalikes** are not normalized.
  4. **Filename is attacker-controlled** and used as a path component without canonicalization or containment check.
- **Why it matters:** The acceptance criteria explicitly state "MUST prevent path traversal: nothing should write outside `/uploads`." This is the central security requirement of the change, and the implementation fails it. An unauthenticated multipart POST can overwrite arbitrary files the process can write — typical impact is overwriting binaries, systemd units, SSH `authorized_keys`, web content, or app config, leading to remote code execution or full host compromise. Implementer's "Confident this is safe" note is incorrect.
- **Source of truth:** Design block, lines 16 and 19-21: "MUST prevent path traversal: nothing should write outside `/uploads`" and "The handler must reject any input that would write outside that directory."
- **Proposed fix:**
  - Reject (don't sanitize) suspicious filenames. Treat the filename as untrusted metadata and derive the storage name yourself (e.g. UUID) while preserving the user's name only as opaque metadata if needed.
  - If you must use the supplied name, extract only the final component with `Path::new(&filename).file_name()` and reject if it returns `None`, contains `/`, `\`, NUL, `..`, or starts with `.`.
  - After joining, canonicalize the parent (`/uploads` resolved once at startup) and verify the resulting path's parent equals that canonical base — reject otherwise.
  - Example skeleton:
    ```rust
    let raw = field.file_name().ok_or(StatusCode::BAD_REQUEST)?.to_string();
    let name = std::path::Path::new(&raw)
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or(StatusCode::BAD_REQUEST)?;
    if name.is_empty() || name.starts_with('.') || name.contains('\0') {
        return Err(StatusCode::BAD_REQUEST);
    }
    let base: &Path = &UPLOADS_BASE; // canonicalized at startup
    let path = base.join(name);
    // Optional defense in depth: open with O_NOFOLLOW via openat2 / cap-std.
    ```

### High

#### H1. `unwrap()` on every fallible call turns malformed input into a process panic
- **Citation:** `api/handlers/upload.rs:31`, `:32`, `:33`, `:39`
  ```rust
  while let Some(field) = multipart.next_field().await.unwrap() { ... }
  let filename = field.file_name().unwrap().to_string();
  let data = field.bytes().await.unwrap();
  std::fs::write(&path, data).unwrap();
  ```
- **Problem:** Every error path panics:
  - `next_field().await.unwrap()` panics on malformed multipart framing.
  - `field.file_name().unwrap()` panics whenever a part lacks a filename (the design says "for each field with a filename" — the absence of a filename is normal multipart, not an error).
  - `field.bytes().await.unwrap()` panics on truncated bodies, client disconnects, or oversized payloads.
  - `std::fs::write(...).unwrap()` panics on disk-full, permission errors, or (per C1) attempting to write to a forbidden path.
- **Why it matters:** Acceptance criterion: "Should fail gracefully on malformed input." Today, any malformed request returns a 500 from the panic handler at best, and depending on the runtime config can abort the worker task / connection. It also gives a trivial DoS primitive: send a malformed multipart body to crash the request in a loop. This violates the design and is a reliability/availability risk under normal client behavior, not just adversarial.
- **Source of truth:** Design block, line 17: "Should fail gracefully on malformed input."
- **Proposed fix:** Change the handler signature to `Result<Json<…>, (StatusCode, String)>` (or a custom error type implementing `IntoResponse`) and convert each `unwrap()` into a `?` with mapped errors — `400 Bad Request` for malformed multipart / missing filename, `413 Payload Too Large` if you bound size, `500` for I/O failures. Skip fields with no filename instead of erroring.

#### H2. Whole-file buffering in memory enables trivial DoS
- **Citation:** `api/handlers/upload.rs:33`
  ```rust
  let data = field.bytes().await.unwrap();
  ```
- **Problem:** `field.bytes()` accumulates the entire field into memory before writing. There is no size cap on the multipart extractor (no `DefaultBodyLimit` configuration is shown) and no per-field cap. An attacker can submit a multi-GB upload (or many concurrent ones) to OOM the process.
- **Why it matters:** Falls under "resource leak under common load." Even without malice, large legitimate uploads will balloon RSS. Combined with H1, an OOM kill is also a panic-equivalent availability failure.
- **Source of truth:** Severity rubric in the package: "High: significant security risk, resource leak under common load…".
- **Proposed fix:** Stream the field to disk with `field.chunk().await` in a loop, writing into a `tokio::fs::File` (or a `BufWriter` over `std::fs::File` inside `spawn_blocking`). Configure `axum::extract::DefaultBodyLimit` and enforce a per-field byte cap, returning `413` when exceeded.

#### H3. Existing files are silently overwritten
- **Citation:** `api/handlers/upload.rs:39`
  ```rust
  std::fs::write(&path, data).unwrap();
  ```
- **Problem:** `std::fs::write` truncates the destination if it exists. Two clients uploading `report.pdf` clobber each other; an attacker who can guess existing filenames (combined with C1, even paths outside `/uploads`) can destroy data. The design says "writes the bytes to `/uploads/<filename>`" without specifying overwrite semantics, but silent destructive writes are a "silent data inconsistency."
- **Why it matters:** Data loss without any signal to the caller; collisions are virtually guaranteed at scale because the filename comes from the client.
- **Source of truth:** Severity rubric: "High: … silent data inconsistency."
- **Proposed fix:** Open with `OpenOptions::new().write(true).create_new(true)` and return a 409 on conflict, **or** generate a server-side unique name (UUID/ULID) and return it in the response. Decide explicitly and document.

#### H4. Blocking filesystem I/O inside an async handler stalls the executor
- **Citation:** `api/handlers/upload.rs:39`
  ```rust
  std::fs::write(&path, data).unwrap();
  ```
- **Problem:** `std::fs::write` is synchronous. Calling it from an async Axum handler blocks the Tokio worker thread for the duration of the disk write. Under load (or with slow storage), this starves other tasks scheduled on the same worker and degrades throughput/tail latency for the whole server.
- **Why it matters:** "Performance degradation" / "resource leak under common load." The fix is mechanical and well-known in the Tokio ecosystem.
- **Source of truth:** Severity rubric: "performance degradation."
- **Proposed fix:** Use `tokio::fs::write` (or stream into `tokio::fs::File`), or wrap the sync I/O in `tokio::task::spawn_blocking`.

### Medium

#### M1. Response is always `200 {"status":"ok"}` regardless of how many fields were processed
- **Citation:** `api/handlers/upload.rs:30-42`
- **Problem:** A request with zero fields, fields without filenames, or partial successes (e.g. 3 of 5 written before a panic) yields no signal to the caller about what actually happened. There is no list of saved files, no count, no per-field status.
- **Why it matters:** Callers can't reconcile what was stored, complicating retries and client UX. Falls under "incorrect behavior in some inputs" / "unclear error handling."
- **Source of truth:** Design says "Returns `{ status: 'ok' }` on success" — but does not define behavior when nothing was uploaded; this is implied validation that the design omits.
- **Proposed fix:** Track the count and names of successfully written files; return `{"status":"ok","files":[{"name":"…","bytes":N}, …]}`. Return `400` if the request contained no usable fields.

#### M2. No content-type / extension validation; no MIME sniffing
- **Citation:** `api/handlers/upload.rs:32-39`
- **Problem:** The handler accepts any filename and any bytes and stores them directly under a server-controlled directory. Combined with C1, this is the executable-upload classic; even with C1 fixed, storing `.html`, `.svg`, `.php`, `.exe` content under a path that may be served back by another component is risky.
- **Why it matters:** The design doesn't specify allowed types, but uploads of arbitrary content with attacker-chosen names are a defense-in-depth concern. Falls under "missing validation that the design implies."
- **Source of truth:** Design intent ("`/uploads` is the only allowed write target", general security posture of the criteria).
- **Proposed fix:** Decide an allowlist of MIME types/extensions, validate the `Content-Type` of the multipart field, and consider sniffing magic bytes for high-risk types. At minimum, document that `/uploads` must never be served as static content with execution privileges.

#### M3. Hardcoded `/uploads` base path
- **Citation:** `api/handlers/upload.rs:37`
- **Problem:** The destination directory is a string literal in the handler. There's no way to reconfigure it for tests, dev, or multi-tenant deployments, and no startup-time check that the directory exists / is writable / is on the expected filesystem.
- **Why it matters:** Makes testing the path-traversal fix harder (you can't point it at a temp dir in unit tests), and a missing or misconfigured `/uploads` directory will surface only as a panic at request time (per H1).
- **Source of truth:** Design refers to `/uploads` as the allowed target, not as a literal that must be hardcoded.
- **Proposed fix:** Inject the base path through application state (`State<AppConfig>`), canonicalize it once at startup, and verify it exists and is a directory.

#### M4. `field.file_name()` returns a borrowed `&str`; no length / character-set bounds
- **Citation:** `api/handlers/upload.rs:32`
  ```rust
  let filename = field.file_name().unwrap().to_string();
  ```
- **Problem:** Even if you sanitize traversal sequences (C1), there is no upper bound on filename length, no rejection of control characters, and no normalization of Unicode. Some filesystems cap names at 255 bytes; exceeding that yields `ENAMETOOLONG`, which today panics (H1) and after H1's fix would still surface as 500.
- **Why it matters:** "Missing validation that the design implies" — the design treats filename as a path component, so it must satisfy the constraints of a path component.
- **Source of truth:** Implied by "writes the bytes to `/uploads/<filename>`" being a real filesystem operation.
- **Proposed fix:** Cap length (e.g. 200 bytes), reject control characters and `/`, `\`, NUL, and either reject or NFC-normalize Unicode.

### Low

#### L1. Function lacks doc comment describing security model
- **Citation:** `api/handlers/upload.rs:30`
- **Problem:** Given that the central requirement is "MUST prevent path traversal," the handler should carry a `///` doc comment that records the chosen mitigation and invariants (e.g. "filename is treated as opaque; storage path is `<base>/<uuid>`").
- **Why it matters:** Helps future reviewers spot regressions like the one in C1.
- **Proposed fix:** Add a brief Rustdoc block above `pub async fn upload_file`.

#### L2. `safe_name` is a misleading variable name
- **Citation:** `api/handlers/upload.rs:36`
- **Problem:** Calling the result `safe_name` implies the value is safe to use as a path component when, per C1, it is not. Misleading names mask security bugs in code review.
- **Proposed fix:** After implementing real validation, rename to `validated_filename` or similar; until then, do not call attacker-controlled data "safe."

#### L3. Imports include `PathBuf` but not `Path`; consider tightening imports
- **Citation:** `api/handlers/upload.rs:28`
- **Problem:** Once the fix in C1 lands you'll likely want `std::path::Path` for `file_name()` extraction. Minor.
- **Proposed fix:** `use std::path::{Path, PathBuf};` when the fix is applied.

#### L4. No tests are included or referenced
- **Citation:** Whole file.
- **Problem:** The implementer note says "Tests pass," but no tests for this new handler appear in the diff. The path-traversal mitigation in particular needs negative tests (`..`, `../..`, `....//`, absolute paths, NUL bytes, Windows separators, empty filename, overlong filename).
- **Proposed fix:** Add unit/integration tests covering the threat cases enumerated in C1 plus the malformed-input cases for H1.
