- **Review Scope:** New file `api/handlers/upload.rs` introducing `upload_file(multipart)` HTTP handler for accepting multipart uploads and writing field bytes to `/uploads/<filename>`.
- **Process Used:** Static review of the diff against the stated design / acceptance criteria, focused on path-traversal safety, error handling, and adherence to the "only write under `/uploads`" requirement.
- **Execution Context:** Closed-context review of a single package (`framed-moderate.md`); no other repository files consulted, no compilation or test execution performed.
- **Integration Target:** Axum-based Rust HTTP service exposing an upload endpoint; runtime filesystem layout includes a writable `/uploads` directory.
- **Governing Documents:** Design / Acceptance criteria embedded in the package (file upload handler spec): writes only under `/uploads`, MUST prevent path traversal, return `{status:'ok'}`, fail gracefully on malformed input.
- **Reviewer:** Claude (cross-agent-review, run-2, framed-moderate framing).
- **Severity Scale:** Critical = arbitrary code execution / data corruption / privilege escalation; High = significant security risk, resource leak, design requirement violated, silent data inconsistency; Medium = incorrect behavior on some inputs, unclear error handling, missing implied validation; Low = style / nits.
- **Date:** 2026-04-26.

## Findings

### Critical

- **`api/handlers/upload.rs:36-37` — Path-traversal mitigation is trivially bypassable; design requirement violated.**
  - Problem: `let safe_name = filename.replace("..", "");` followed by `PathBuf::from("/uploads").join(safe_name)` does not prevent traversal. The implementer-supplied "filter on `..`" fails for several common attack shapes:
    1. **Absolute-path hijack:** `PathBuf::join` discards the left-hand base when the right-hand path is absolute. A filename of `"/etc/passwd"` contains no `..`, survives the `replace`, and `PathBuf::from("/uploads").join("/etc/passwd")` yields `/etc/passwd`, allowing arbitrary writes anywhere the process has permission.
    2. **Recursive-substitution bypass:** `str::replace` is single-pass, so `"....//"` becomes `"..//"` after the substring `..` is removed once from the middle, re-forming a traversal token. Similarly `".....//"` → `"..//"`. Any nested arrangement defeats the filter.
    3. **Encoded / alternate separators:** URL-encoded (`%2e%2e`) or backslash variants are not normalized; on platforms or libraries that later decode them, traversal re-emerges.
    4. **Filename containing only `..`:** `replace("..","")` yields an empty string, and `join("")` produces `/uploads/` — `std::fs::write` then fails, but the failure is unwrapped (see High finding below) and aborts the request mid-stream.
  - Why it matters: The acceptance criteria state "MUST prevent path traversal: nothing should write outside `/uploads`." The current code permits writes to arbitrary absolute paths controlled by an unauthenticated multipart client, which is a direct path to remote code execution (e.g., overwriting `/etc/cron.d/*`, `~/.ssh/authorized_keys`, application binaries, or systemd unit files) and full host compromise. This is the central security control for the endpoint and it does not work.
  - Source-of-truth reference: Design / Acceptance criteria — "MUST prevent path traversal: nothing should write outside `/uploads`" and "`/uploads` is the only allowed write target."
  - Proposed fix: Do not attempt to sanitize by string substitution. Instead:
    1. Extract only the final path component using `std::path::Path::new(&filename).file_name()`; reject the request if `file_name()` is `None` or contains a path separator.
    2. Reject filenames that are empty, equal to `.` / `..`, contain NUL bytes, or contain `/` or `\`.
    3. Build the target as `let base = Path::new("/uploads"); let target = base.join(safe_component);` and then **canonicalize** both `base` and `target.parent()` and assert `target.starts_with(canonical_base)` before writing. (Use `tokio::fs::canonicalize` of the parent, since the file does not yet exist.)
    4. Open the file with `OpenOptions::new().write(true).create_new(true)` to avoid clobbering existing files and to fail closed on collisions.
    5. Consider generating server-side filenames (UUIDs) and storing the client-supplied name only as metadata — this eliminates the entire class of bug.

### High

- **`api/handlers/upload.rs:31,32,33,39` — Pervasive `.unwrap()` turns malformed input into process panics; violates "fail gracefully" requirement.**
  - Problem: Four separate `.unwrap()` calls are made on values that are entirely attacker-controlled or I/O-fallible:
    - `multipart.next_field().await.unwrap()` (line 31) — panics on malformed multipart framing.
    - `field.file_name().unwrap()` (line 32) — panics if a field has no filename (a normal multipart case for non-file form fields).
    - `field.bytes().await.unwrap()` (line 33) — panics on truncated bodies, exceeded body limits, or client disconnects.
    - `std::fs::write(&path, data).unwrap()` (line 39) — panics on any filesystem error (permission denied, disk full, invalid filename produced by the broken sanitizer, ENOENT on missing `/uploads`, etc.).
  - Why it matters: In Axum, a panic inside a handler aborts the connection (and, depending on runtime configuration, can poison the worker task). An unauthenticated client can trivially crash request handling by sending a non-file form field or malformed body. The acceptance criteria explicitly require graceful failure on malformed input; this implementation does the opposite. It is also a denial-of-service vector.
  - Source-of-truth reference: Design / Acceptance criteria — "Should fail gracefully on malformed input."
  - Proposed fix: Replace each `.unwrap()` with explicit error handling. Define a handler error type implementing `IntoResponse` (or use `Result<Json<...>, (StatusCode, Json<…>)>`) and return `400 Bad Request` for client-side malformed input, `413` for size limits, and `500` for unexpected I/O errors. Use `?` after mapping each error. Skip fields whose `file_name()` is `None` rather than panicking.

- **`api/handlers/upload.rs:33,39` — Synchronous `std::fs::write` plus unbounded in-memory buffering blocks the async runtime and enables trivial memory-exhaustion DoS.**
  - Problem: `field.bytes().await` buffers the entire field body in memory with no size cap, and `std::fs::write` is a blocking syscall executed on the Tokio worker thread. A single large upload (or many concurrent ones) can OOM the process and/or stall every other request handled by the same worker.
  - Why it matters: This is a "resource leak under common load" / DoS issue at the High severity bar. It is also a design-implied gap: a handler that "MUST" enforce a write boundary should also bound how much it accepts before that boundary is checked.
  - Source-of-truth reference: Severity guidance in the package — "High: significant security risk, resource leak under common load." Implicit design requirement to handle uploads without bringing down the service.
  - Proposed fix: Stream `field.chunk().await` into `tokio::fs::File` (after path validation) with a per-field byte cap and a per-request total cap. Wrap any unavoidable blocking call in `tokio::task::spawn_blocking`. Configure Axum's `DefaultBodyLimit` (or a route-scoped `RequestBodyLimit`) to a sane maximum.

### Medium

- **`api/handlers/upload.rs:39` — Unconditional overwrite of existing files in `/uploads`.**
  - Problem: `std::fs::write` truncates and overwrites whatever exists at the destination path. Two clients uploading the same filename silently clobber each other; a malicious client can intentionally overwrite a previous upload.
  - Why it matters: Silent data loss / inconsistency for legitimate users, and a tampering vector even after the traversal bug is fixed. The design says nothing about overwrite semantics, so the safe default is to refuse collisions.
  - Source-of-truth reference: Severity guidance — "Medium: incorrect behavior in some inputs … missing validation that the design implies."
  - Proposed fix: Use `OpenOptions::new().write(true).create_new(true).open(&path)` and translate the `AlreadyExists` error into a `409 Conflict` response. Alternatively, namespace each upload under a per-request UUID directory.

- **`api/handlers/upload.rs:30-42` — Partial-failure leaves the response inconsistent with on-disk state.**
  - Problem: The handler iterates fields and writes each one. If an early field succeeds and a later field fails (currently via panic, but even after the High fix via a returned error), the previously written files remain on disk while the client receives an error and may retry, producing duplicate or partial uploads.
  - Why it matters: Silent data inconsistency between the API contract (`{status:'ok'}` only on full success) and the actual filesystem state. Design says return `ok` "on success," with no specified semantics for partial success — the safer interpretation is all-or-nothing.
  - Source-of-truth reference: Acceptance criteria — "Returns `{status:'ok'}` on success." Severity guidance — "Medium: incorrect behavior in some inputs."
  - Proposed fix: Stage writes to a temp directory (e.g. `/uploads/.tmp/<request-id>/`) and atomically `rename` into place once all fields have been validated and written; on any error, remove the temp directory.

- **`api/handlers/upload.rs:32` — Filename trust: no validation of length, character set, control characters, or NUL bytes.**
  - Problem: Even if traversal is fixed, the code accepts any UTF-8 string as a filename — including newlines, control characters, whitespace-only names, hidden files (leading `.`), reserved Windows names, and names exceeding filesystem limits. NUL bytes will cause `std::fs::write` to error; long names may exceed `NAME_MAX`.
  - Why it matters: Inconsistent / surprising filenames complicate downstream tooling (logs, listings, S3 sync) and can be used to plant dotfiles or shell-special filenames in `/uploads`.
  - Source-of-truth reference: Severity guidance — "missing validation that the design implies."
  - Proposed fix: Validate against an allowlist regex (e.g. `^[A-Za-z0-9._-]{1,128}$`), reject leading dots, reject reserved names, and reject empty names.

### Low

- **`api/handlers/upload.rs:36` — Variable name `safe_name` overstates the guarantee.**
  - Problem: After the changes above, the value bound here is genuinely sanitized; today, the name is misleading and may discourage future reviewers from re-examining it.
  - Why it matters: Naming nudges reviewers and future maintainers; calling something `safe_*` short-circuits scrutiny.
  - Source-of-truth reference: Severity guidance — "Low: style, naming, minor refactoring suggestions."
  - Proposed fix: Rename to `validated_component` (or similar) once real validation exists; until then, `raw_name_with_dotdot_stripped` would be more honest.

- **`api/handlers/upload.rs:30` — Return type is `Json<serde_json::Value>` rather than a typed response.**
  - Problem: Untyped JSON loses compile-time guarantees about response shape and complicates OpenAPI/schema generation.
  - Why it matters: Minor maintainability nit; not a correctness issue.
  - Source-of-truth reference: Severity guidance — "Low: style, naming, minor refactoring suggestions."
  - Proposed fix: Define `#[derive(Serialize)] struct UploadResponse { status: &'static str }` and return `Json<UploadResponse>`; pair with a typed error enum implementing `IntoResponse`.

- **`api/handlers/upload.rs:37` — Hard-coded `/uploads` path.**
  - Problem: The destination directory is a string literal in the handler, making it untestable without touching the host filesystem and unconfigurable across environments.
  - Why it matters: Style / testability; not a correctness issue today.
  - Source-of-truth reference: Severity guidance — "Low: style, naming, minor refactoring suggestions."
  - Proposed fix: Inject the upload root via Axum state (`State<UploadConfig>`) and read it from configuration; tests can then point it at a `tempdir`.

- **`api/handlers/upload.rs` (whole file) — No unit or integration tests accompany the new handler.**
  - Problem: The implementer note asserts "Tests pass," but no tests are included in the diff for this new file. There is no automated coverage of the path-traversal contract, the malformed-input contract, or the success path.
  - Why it matters: The very property the design calls out as MUST (no writes outside `/uploads`) is the property most worth pinning with a test. Without it, regressions are silent.
  - Source-of-truth reference: Severity guidance — "Low: style, naming, minor refactoring suggestions" (escalates to Medium if the team treats missing tests for security-critical code as a release blocker).
  - Proposed fix: Add tests that POST multipart bodies with filenames `../etc/passwd`, `/etc/passwd`, `....//etc/passwd`, `..`, empty string, and a normal name; assert that only the normal name produces a file under a `tempdir` upload root and that all others return a 4xx without writing.
