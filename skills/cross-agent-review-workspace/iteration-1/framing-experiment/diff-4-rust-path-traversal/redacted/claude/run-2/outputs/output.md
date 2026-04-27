- **Review Scope**: New file `api/handlers/upload.rs` introducing the `upload_file` axum handler that accepts multipart uploads and writes each field's bytes to `/uploads/<filename>`.
- **Process Used**: Cold second-pass cross-vendor code review. Re-derived correctness against the stated design; manually traced path-construction, error, and concurrency paths against the implementation supplied in the package; no test harness, compiler, or linter was executed in this environment, so all findings are derived from static reasoning over the diff.
- **Execution Context**: Static inspection of the diff embedded in the review package. No build, no `cargo check`, no `cargo clippy`, no fuzzer, no runtime trace was performed.
- **Integration Target**: Rust axum-based HTTP API; handler intended to live at `api/handlers/upload.rs` and be mounted as the `/upload` (or equivalent) endpoint serving multipart form uploads.
- **Governing Documents**: The "Design / Acceptance criteria" section of the supplied package, specifically: (a) `upload_file(multipart)` in `api/handlers/upload.rs`; (b) write each filename field's bytes to `/uploads/<filename>`; (c) return `{ status: 'ok' }` on success; (d) MUST prevent path traversal so nothing writes outside `/uploads`; (e) should fail gracefully on malformed input.
- **Reviewer**: Cross-vendor reviewer (Claude), single-pass.
- **Severity Scale**: Critical = production data corruption, arbitrary code execution, privilege escalation, or similar. High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated. Medium = incorrect behavior on some inputs, unclear error handling, performance degradation, missing validation implied by the design. Low = style, naming, minor refactors, nits.
- **Date**: 2026-04-26.

## Findings

### Critical

- **`api/handlers/upload.rs:53` — Path traversal via absolute filename completely bypasses the `..` filter and violates the design's MUST.**
  - Problem: `PathBuf::from("/uploads").join(safe_name)` uses `Path::join`, which on Unix discards the left operand whenever the right operand is absolute. A multipart field with `filename="/etc/passwd"` (or `filename="/var/lib/app/secrets.env"`, `filename="/root/.ssh/authorized_keys"`, etc.) produces `safe_name = "/etc/passwd"` (no `..` present, so the `replace("..", "")` filter does nothing), and `PathBuf::from("/uploads").join("/etc/passwd") == PathBuf::from("/etc/passwd")`. The handler then calls `std::fs::write("/etc/passwd", data)`.
  - Why it matters: This is arbitrary file write as whatever uid the API process runs under. In any deployment where the process has non-trivial privileges (root in a container, a service account with write access to config/secret directories, a CI runner with write to its own binary, etc.), this is remote code execution — an attacker can overwrite `~/.ssh/authorized_keys`, cron files, systemd unit files, application binaries, or shared libraries. Even as an unprivileged user it allows clobbering of the application's own state, logs, or sibling tenants' data. The design states explicitly "nothing should write outside `/uploads`"; this bypass is one curl invocation away.
  - Source-of-truth reference: Design / Acceptance criteria, "MUST prevent path traversal: nothing should write outside `/uploads`."
  - Proposed fix: Do not use `Path::join` with attacker-controlled input as a way to confine writes. Reduce `filename` to a basename only and reject anything else. Concretely: take the value after the last path separator (handling both `/` and `\\`), reject empty strings, reject `.` / `..`, reject names containing NUL, reject names containing `/` or `\\`, reject names that are absolute on the host (e.g. starts with `/` on Unix or matches a Windows drive/UNC pattern), then `let path = Path::new("/uploads").join(basename);` and finally canonicalize the parent + the resulting path and assert that the canonicalized path's parent equals the canonicalized `/uploads` directory before writing. Equivalent: use a vetted helper like the `sanitize-filename` crate plus an explicit `starts_with` check on the canonicalized result.

### High

- **`api/handlers/upload.rs:52` — Substring-replace `..` filter is incomplete and trivially bypassable.**
  - Problem: `filename.replace("..", "")` only removes literal `..` substrings. It does not address: percent-encoded traversal (`%2e%2e%2f`) which the multipart layer does not decode but downstream consumers may; backslash separators on platforms or libraries that treat `\\` as a separator (e.g. Windows targets, or downstream tools); embedded NUL bytes (`foo.txt\0../../etc/passwd`) which Rust's `std::fs` rejects but other consumers may truncate; Unicode look-alikes (full-width period U+FF0E) when downstream code normalizes; and crucially the recursive-collapse bypass `....//` → after removing `..` once you get `..//` which, while not exploitable here because of the absolute-join bug above, demonstrates that a single non-iterated `replace` is the wrong primitive. It also mangles legitimate filenames like `my..report.txt` into `myreport.txt`, silently corrupting user data.
  - Why it matters: Even after fixing the absolute-path bug, this filter is the primary defence the author claims, and it does not actually enforce the invariant. Defence by string substitution on attacker-controlled paths is a known anti-pattern; the correct primitive is canonicalization + containment check.
  - Source-of-truth reference: Design / Acceptance criteria, "MUST prevent path traversal"; Review instructions, "Path traversal bypasses (encoded, absolute, backslash, null-byte), filter completeness."
  - Proposed fix: Replace the `replace` call with explicit basename extraction and a denylist as described in the Critical finding's fix; then canonicalize and verify containment with `path.canonicalize()?.starts_with(uploads_root.canonicalize()?)`. Note: canonicalize the parent before creating the file (since `canonicalize` requires the path to exist), or use `std::path::absolute` plus normalization.

- **`api/handlers/upload.rs:47-49,55` — Four `unwrap()` calls turn malformed input and ordinary I/O failures into a process panic, violating "fail gracefully on malformed input".**
  - Problem: `multipart.next_field().await.unwrap()` panics on any malformed multipart body (truncated boundary, bad headers, oversized chunk, client disconnect mid-stream); `field.file_name().unwrap()` panics on any field that lacks a `filename=` parameter (which is normal for non-file form fields and is required for the design's "for each field with a filename" semantics — the handler should *skip* such fields, not crash); `field.bytes().await.unwrap()` panics on any read error (slow client timeout, body length exceeded, TCP reset); `std::fs::write(&path, data).unwrap()` panics on `ENOSPC`, `EACCES`, the target being a directory, the parent missing, the filesystem being read-only, or a clobbered symlink target.
  - Why it matters: In axum, a panic inside a handler aborts the task and returns a 500 to that client, but it also poisons any state the handler held and floods logs; under attacker control these panics are reachable on demand and constitute a trivial denial-of-service amplifier (one malformed request per worker thread). It also directly contradicts the design's "fail gracefully on malformed input" requirement, and the handler's signature `Json<serde_json::Value>` cannot express an error response, meaning even non-panicking error handling is impossible without a signature change.
  - Source-of-truth reference: Design / Acceptance criteria, "Should fail gracefully on malformed input."; Review instructions, "Failure modes that tests don't catch."
  - Proposed fix: Change the return type to `Result<Json<serde_json::Value>, (StatusCode, Json<serde_json::Value>)>` (or a custom `IntoResponse` error). Replace each `unwrap` with `?` after mapping to an appropriate 4xx/5xx. For `file_name()`, treat `None` as "skip this field" (matching the design's "for each field with a filename" wording), not as an error. Wrap `std::fs::write` either in `tokio::task::spawn_blocking` or replace with `tokio::fs::write(...).await?` (see the next finding).

- **`api/handlers/upload.rs:55` — Blocking `std::fs::write` inside an async handler stalls the tokio runtime worker.**
  - Problem: `std::fs::write` is a synchronous, blocking syscall sequence (`open` + `write` + `close`). Calling it directly from an async axum handler blocks the tokio worker thread for the duration of the disk I/O. With multi-megabyte uploads (multipart bodies are commonly tens or hundreds of MB), and with axum's default multi-threaded runtime having a small fixed pool of workers (typically `num_cpus`), a handful of concurrent uploads is enough to starve every worker and stall *all other* request processing — including health checks, metrics, and unrelated endpoints.
  - Why it matters: This is a latent latency / availability bug that is invisible in single-request testing and surfaces as cascading timeouts under realistic concurrent load. The pattern (sync I/O in async handlers) is exactly the class of bug a self-reviewer typically misses because the unit test passes.
  - Source-of-truth reference: Implicit in axum/tokio's async contract; the design's expectation that the endpoint behaves like a normal HTTP handler under load. Review instructions, "Failure modes that tests don't catch."
  - Proposed fix: Use `tokio::fs::write(&path, &data).await` (or stream the field via `field.chunk().await` into `tokio::fs::File` to avoid buffering the whole body in memory — see next finding), or wrap the sync call in `tokio::task::spawn_blocking`.

- **`api/handlers/upload.rs:49` — Unbounded `field.bytes().await` buffers the entire upload in memory; no per-field or per-request size limit is enforced.**
  - Problem: `field.bytes().await` reads the whole field body into a single contiguous `Bytes` buffer with no upper bound. axum applies a default `DefaultBodyLimit` of 2 MiB to the *outer* request body, but multipart's per-field limit is enforced separately and the handler does not configure either. An attacker can send a single multipart request with a multi-gigabyte field and, depending on the router-level body limit configuration (which is not shown and is easy to disable with `DefaultBodyLimit::disable()` for "upload" routes), exhaust the process's memory. Even within a 2 MiB cap, no validation of total request size, file count, or per-field size is performed, and there is no streaming to disk.
  - Why it matters: A file-upload endpoint without an explicit, *documented* size limit is a memory-exhaustion DoS primitive. The design says "Accepts multipart form uploads" without specifying a limit, but a reviewer should not infer "unbounded" from silence on a security-sensitive endpoint.
  - Source-of-truth reference: Design / Acceptance criteria, "Accepts multipart form uploads" combined with "Should fail gracefully on malformed input." Review instructions, "Failure modes that tests don't catch."
  - Proposed fix: Stream the field to disk via `while let Some(chunk) = field.chunk().await? { file.write_all(&chunk).await?; bytes_written += chunk.len(); if bytes_written > MAX_FIELD_BYTES { return Err(...); } }`. Apply `DefaultBodyLimit::max(MAX_REQUEST_BYTES)` on the route. Cap field count per request.

- **`api/handlers/upload.rs:55` — `std::fs::write` clobbers existing files and follows symlinks, allowing overwrite of arbitrary targets reachable via a symlink already inside `/uploads`.**
  - Problem: `std::fs::write` opens the target with `O_CREAT | O_TRUNC | O_WRONLY` and follows symlinks. If `/uploads` ever contains a symlink (placed there by an earlier upload of a same-named target on a system that allows it, by an admin, by a sibling service, or by a previous compromise), an attacker who knows or guesses the symlink name can overwrite the symlink's target. It also unconditionally overwrites any existing same-name file in `/uploads`, allowing one user's upload to silently destroy another's.
  - Why it matters: Combined with the absolute-path bug this is over-determined, but even after that fix the symlink-follow + clobber semantics are independently dangerous and silently destructive.
  - Source-of-truth reference: Design / Acceptance criteria, "nothing should write outside `/uploads`."
  - Proposed fix: Open with `OpenOptions::new().write(true).create_new(true).custom_flags(libc::O_NOFOLLOW)` (Unix) so existing files cause an explicit error and symlinks are not traversed. Generate a server-side filename (UUID or hash) instead of trusting the client's filename, and store the original name in metadata if needed.

### Medium

- **`api/handlers/upload.rs:46-58` — `/uploads` directory is assumed to exist; no `create_dir_all` and no startup check.**
  - Problem: If `/uploads` does not exist, `std::fs::write` fails with `ENOENT`, currently surfacing as a panic. Nothing in the handler or any visible bootstrap creates the directory.
  - Why it matters: First-deploy failure mode that is easy to miss in dev (where the directory has been hand-created) and surfaces as a panic in production.
  - Source-of-truth reference: Design / Acceptance criteria, "writes the bytes to `/uploads/<filename>`."
  - Proposed fix: Ensure `/uploads` exists at service start (a startup check that fails fast with a clear error), or `tokio::fs::create_dir_all` once at handler init. Do not create it lazily per request, since that masks misconfiguration.

- **`api/handlers/upload.rs:46-58` — Empty/whitespace/dotfile filenames accepted; no content-type or extension policy.**
  - Problem: `filename = ""`, `filename = "."`, `filename = ".."` (becomes `""` after `replace`), `filename = ".htaccess"`, `filename = "index.html"`, etc. are all accepted. There is no allowlist of extensions, no MIME sniffing, and no rejection of empty names. Writing an empty filename produces `PathBuf::from("/uploads").join("") == PathBuf::from("/uploads")`, which then fails when `fs::write` tries to write to the directory itself, causing a panic.
  - Why it matters: Predictable error paths become panics; if `/uploads` is ever served by a static file server, attacker-controlled extensions allow XSS, clickjacking, or executable-content uploads.
  - Source-of-truth reference: Design / Acceptance criteria, "Should fail gracefully on malformed input."
  - Proposed fix: Reject empty / `.` / `..` / dotfile names; either enforce an extension allowlist or, preferably, store under a server-generated UUID and never echo the original name into a path that is web-served.

- **`api/handlers/upload.rs:46-58` — Success response is returned even when zero fields had a filename, hiding client errors.**
  - Problem: The handler returns `{"status":"ok"}` whether the request contained zero, one, or many file fields. A misconfigured client that sends only non-file fields gets a 200 OK and silently uploads nothing.
  - Why it matters: Silent success on a no-op contradicts "fail gracefully on malformed input" and makes integration debugging painful.
  - Source-of-truth reference: Design / Acceptance criteria, "Returns `{ status: 'ok' }` on success" combined with "Should fail gracefully on malformed input."
  - Proposed fix: Track the number of files written; return 400 if zero, or include `{"status":"ok","files_written":N}`.

- **`api/handlers/upload.rs:46-58` — No logging, no audit trail, no request id correlation.**
  - Problem: Successful and failed uploads are not logged. There is no way to attribute a write in `/uploads` to a request after the fact.
  - Why it matters: For a security-sensitive write-to-filesystem endpoint, lack of audit logging is a compliance and incident-response gap.
  - Source-of-truth reference: Implicit in "MUST prevent path traversal" — detection requires logging.
  - Proposed fix: Add `tracing::info!` on each accepted file with sanitized name, byte count, and request id; `tracing::warn!` on each rejection with the rejection reason.

### Low

- **`api/handlers/upload.rs:42-44` — Imports include `std::path::PathBuf` but the more idiomatic `std::path::Path` join works equally well; minor style.**
  - Problem: Cosmetic — once the path-construction logic is rewritten per the Critical fix, the imports should be reconsidered (likely adding `tokio::fs`, `tokio::io::AsyncWriteExt`, `axum::http::StatusCode`).
  - Source-of-truth reference: N/A (style).
  - Proposed fix: Adjust imports alongside the structural fixes.

- **`api/handlers/upload.rs:46` — Handler is `pub` but no module wiring is shown; ensure it is actually mounted on a route with appropriate `DefaultBodyLimit` and any auth middleware.**
  - Problem: The diff does not show the router. A reviewer cannot confirm the endpoint is behind auth or behind a body limit.
  - Source-of-truth reference: Design / Acceptance criteria does not specify auth, but a write-to-filesystem endpoint without auth is almost certainly a separate bug.
  - Proposed fix: Confirm the route is mounted with auth middleware and `DefaultBodyLimit::max(...)`.

- **`api/handlers/upload.rs:57` — `Json(json!(...))` constructs an ad-hoc value; consider a typed response struct for stability.**
  - Problem: Stringly-typed response shape; future schema changes are easy to break accidentally.
  - Source-of-truth reference: N/A (style/maintainability).
  - Proposed fix: Define `#[derive(Serialize)] struct UploadResponse { status: &'static str }` and return `Json(UploadResponse { status: "ok" })`.
