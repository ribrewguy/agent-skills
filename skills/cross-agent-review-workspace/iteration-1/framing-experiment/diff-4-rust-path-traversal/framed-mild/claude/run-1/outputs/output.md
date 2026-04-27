- **Review Scope:** New file `api/handlers/upload.rs` containing the `upload_file(multipart)` Axum handler that accepts multipart uploads and writes files to `/uploads/`.
- **Process Used:** Manual static review of the supplied diff against the stated design/acceptance criteria. No code execution, no test review, no dependency analysis.
- **Execution Context:** Closed-context review based solely on the package contents at `framed-mild.md`. No surrounding repository, build configuration, or test suite was consulted.
- **Integration Target:** Axum-based HTTP API; handler is intended to be mounted on a route accepting multipart form uploads, writing to the server-local `/uploads` directory.
- **Governing Documents:** The "Design / Acceptance criteria" section of the package, which mandates: writing each named field to `/uploads/<filename>`, returning `{ status: 'ok' }`, preventing path traversal outside `/uploads`, and failing gracefully on malformed input.
- **Reviewer:** Claude (cross-agent-review, framed-mild framing, run-1).
- **Severity Scale:** Critical (data corruption, RCE, privilege escalation), High (significant security risk, resource leak, silent inconsistency, design requirement violated), Medium (incorrect behavior on some inputs, unclear error handling, missing implied validation), Low (style, naming, nits).
- **Date:** 2026-04-26.

## Findings

### Critical

- **`api/handlers/upload.rs:36-37` — Path-traversal mitigation is trivially bypassable.**
  - Problem: The sanitizer is `let safe_name = filename.replace("..", "");` followed by `PathBuf::from("/uploads").join(safe_name)`. `String::replace` is a single non-overlapping pass, so an input like `....//....//etc/passwd` becomes `../../etc/passwd` after one substitution and then resolves outside `/uploads` via `Path::join`. Worse, an absolute filename (e.g. `/etc/passwd` on Unix or `C:\Windows\...` on Windows) is not affected by the `..` replace at all, and `PathBuf::join` documents that joining an absolute path replaces the base — so `Path::new("/uploads").join("/etc/passwd")` is `/etc/passwd`. The `field.file_name()` value comes directly from the untrusted `Content-Disposition` header, so an attacker can write arbitrary files anywhere the process has permission to write.
  - Why it matters: This is arbitrary file write as the server user. It allows overwriting binaries, configuration, SSH keys, cron files, web roots, etc., leading directly to remote code execution and privilege escalation. The design's central security requirement ("MUST prevent path traversal: nothing should write outside `/uploads`") is violated.
  - Source-of-truth reference: Design/Acceptance criteria, lines 16 and 19-20 of the package ("MUST prevent path traversal", "The handler must reject any input that would write outside that directory"). Rust standard library docs for `Path::join` (absolute-path replacement semantics) and `String::replace` (single pass).
  - Proposed fix: Do not attempt to "sanitize" by string replacement. Instead:
    1. Extract only the final path component from the supplied filename (e.g. `Path::new(&filename).file_name()`); reject the request if `file_name()` is `None`, empty, equals `.`/`..`, or contains a path separator/NUL.
    2. Optionally apply an allowlist regex (e.g. `^[A-Za-z0-9._-]{1,255}$`).
    3. Build the destination as `uploads_dir.join(component)`, then canonicalize both `uploads_dir` and the parent of the destination and verify with `starts_with(&uploads_dir)` before opening the file. Use `OpenOptions::new().write(true).create_new(true)` to avoid clobbering and symlink-following surprises (and resolve symlinks explicitly on platforms where `O_NOFOLLOW` matters).

### High

- **`api/handlers/upload.rs:31` — `multipart.next_field().await.unwrap()` panics on malformed input.**
  - Problem: A malformed multipart body (bad boundary, truncated stream, oversize header, etc.) returns `Err(MultipartError)` from `next_field`. `unwrap()` panics the task; Axum will translate that into a 500 with a dropped connection, and depending on runtime configuration may take down the worker. This directly violates the "Should fail gracefully on malformed input" criterion.
  - Why it matters: An unauthenticated remote attacker can trigger panics at will (DoS, log spam, possible request smuggling fallout). Errors are also indistinguishable from success from the client's point of view because there is no error response body.
  - Source-of-truth reference: Design/Acceptance criteria line 17 ("Should fail gracefully on malformed input").
  - Proposed fix: Change the return type to `Result<Json<Value>, (StatusCode, Json<Value>)>` (or a custom `IntoResponse` error enum) and propagate errors with `?`, returning a 400 for client-side multipart errors and 500 only for genuine server errors.

- **`api/handlers/upload.rs:32` — `field.file_name().unwrap()` panics on fields without a filename.**
  - Problem: The acceptance criterion says "For each field with a filename, writes the bytes" — implying fields without a filename should be skipped. The code instead unwraps `Option<&str>`, which panics whenever a multipart part lacks a `filename=` parameter (e.g. ordinary form text fields, or a file part where the client omitted the filename). Same DoS / graceful-failure problem as above, and additionally a correctness bug because non-file fields are not tolerated.
  - Why it matters: Trivial remote DoS and a violation of the stated handling rule for fields without filenames.
  - Source-of-truth reference: Design/Acceptance criteria lines 13 ("For each field with a filename") and 17 ("Should fail gracefully").
  - Proposed fix: `let Some(filename) = field.file_name().map(str::to_owned) else { continue; };` and apply the validation/canonicalization described in the Critical finding before writing.

- **`api/handlers/upload.rs:33` — `field.bytes().await.unwrap()` panics and buffers entire upload in memory.**
  - Problem: Two issues. (a) `field.bytes()` returns `Result<Bytes, MultipartError>`; `unwrap` panics on any read error (network reset, size-limit breach, decoding error). (b) `bytes()` accumulates the whole field into memory before writing, so a large upload (or many concurrent uploads) trivially exhausts process memory — there is no apparent body-size limit applied.
  - Why it matters: Remote DoS via either crafted disconnects or oversized uploads. Combined with the lack of `DefaultBodyLimit` or per-field size cap, a single request can OOM the server.
  - Source-of-truth reference: Design/Acceptance criteria line 17 ("fail gracefully"); Axum docs on `Multipart` and `DefaultBodyLimit`.
  - Proposed fix: Stream the field with `field.chunk().await?` into the destination file; enforce a per-field byte cap (return 413 if exceeded); apply `DefaultBodyLimit` at the router level for an overall ceiling.

- **`api/handlers/upload.rs:39` — `std::fs::write(&path, data)` blocks the async runtime and unwraps on I/O error.**
  - Problem: `std::fs::write` is synchronous; calling it from an async handler blocks the executor thread, degrading throughput under load. In addition, any I/O error (permission denied, disk full, target is a directory) panics the task instead of returning an HTTP error. `fs::write` also truncates and overwrites any existing file at the path with no consent check.
  - Why it matters: Performance regression and uncontrolled overwrite of files in `/uploads` (a logged-in user can replace another user's previously uploaded file by re-using the filename). Combined with the path-traversal flaw, this becomes silent overwrite of arbitrary system files.
  - Source-of-truth reference: Design/Acceptance criteria line 17; Tokio guidance against blocking calls in async tasks; POSIX semantics of `O_TRUNC`.
  - Proposed fix: Use `tokio::fs::File` opened with `OpenOptions::new().write(true).create_new(true)` (or generate a unique name), write asynchronously, propagate errors via `?`, and map them to appropriate status codes.

### Medium

- **`api/handlers/upload.rs:30-42` — Handler always returns `200 OK` with `{"status":"ok"}` regardless of how many files were processed.**
  - Problem: There is no way for the caller to know how many parts succeeded, what filenames were stored, or whether any were rejected. Even if the panics above are fixed, partial success will be reported as full success.
  - Why it matters: Silent data inconsistency for clients and operators; difficult to debug; encourages clients to assume success.
  - Source-of-truth reference: Design/Acceptance criteria line 15 ("Returns `{ status: 'ok' }` on success") read together with the implied need to surface failures.
  - Proposed fix: Return a structured response listing accepted/rejected filenames and use HTTP status codes that reflect outcome (`207`/`400`/`413` etc., depending on policy).

- **`api/handlers/upload.rs:37` — `/uploads` directory is assumed to exist and be writable.**
  - Problem: There is no `create_dir_all` or startup check; if `/uploads` is missing, every write fails (currently as a panic, see High finding above). The hard-coded absolute path also makes the handler untestable and non-portable (will not work on Windows or in containers without that path mounted).
  - Why it matters: Operational fragility; tests likely pass only because they avoid the filesystem write or run as root with `/uploads` pre-created.
  - Source-of-truth reference: Implementer note ("Tests pass") combined with the design's silence on directory provisioning.
  - Proposed fix: Inject the upload directory via configuration/state (e.g. `State<AppConfig>`), ensure it exists at startup, and canonicalize it once for use in the traversal check.

- **`api/handlers/upload.rs:36` — Sanitizer silently mutates the filename instead of rejecting bad input.**
  - Problem: Even if `replace("..", "")` worked, silently transforming a hostile filename hides the attack from logs and from the client. The design says the handler "must reject any input that would write outside that directory" — reject, not sanitize.
  - Why it matters: Loses audit signal for security monitoring; encourages buggy clients.
  - Source-of-truth reference: Design/Acceptance criteria lines 16 and 19-20 ("must reject any input that would write outside that directory").
  - Proposed fix: On any failed validation, return `400 Bad Request` with an explanatory error and log the offending filename.

### Low

- **`api/handlers/upload.rs:28` — Unused/over-broad import.**
  - Problem: `use std::path::PathBuf;` is the only `std::path` import, but the proper fix above will need `Path` and `Component` as well. Worth tightening when the handler is rewritten.
  - Why it matters: Minor cleanliness; flagged only because the file will be touched anyway.
  - Source-of-truth reference: Rust style conventions.
  - Proposed fix: Replace with `use std::path::{Path, PathBuf, Component};` (or whatever the rewritten handler needs).

- **`api/handlers/upload.rs:30` — Handler is `pub` but lacks any doc comment.**
  - Problem: A public Axum handler with security-sensitive behavior should document its contract (allowed filename charset, max size, error semantics).
  - Why it matters: Future maintainers may re-introduce the same bugs.
  - Source-of-truth reference: Rust API guidelines (C-CRATE-DOC, C-EXAMPLE).
  - Proposed fix: Add a `///` doc block describing inputs, validation rules, and error responses.

- **`api/handlers/upload.rs:41` — `Json(json!({"status": "ok"}))` uses ad-hoc JSON.**
  - Problem: Using `serde_json::json!` for the response means the response shape is not type-checked and not discoverable from the function signature.
  - Why it matters: Drift risk between handler and clients/tests.
  - Source-of-truth reference: General Rust/serde best practice.
  - Proposed fix: Define a small `#[derive(Serialize)] struct UploadResponse { status: &'static str, accepted: Vec<String>, rejected: Vec<RejectedFile> }` and return `Json(UploadResponse { ... })`.
