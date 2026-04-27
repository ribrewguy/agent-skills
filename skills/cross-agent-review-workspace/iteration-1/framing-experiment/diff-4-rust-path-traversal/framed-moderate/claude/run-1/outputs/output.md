- **Review Scope:** New file `api/handlers/upload.rs` implementing `upload_file(multipart)` for multipart file uploads writing to `/uploads/<filename>`.
- **Process Used:** Manual static review of the diff against the stated design/acceptance criteria, with focus on path-traversal safety, error handling, and design conformance.
- **Execution Context:** Closed-context single-pass review; no compilation, test execution, or fuzzing performed. Only the package contents were consulted.
- **Integration Target:** Rust HTTP handler built atop `axum` `Multipart` extractor, returning JSON; intended to be mounted under an Axum router.
- **Governing Documents:** "Design / Acceptance criteria" section of the package: writes restricted to `/uploads`, MUST prevent path traversal, MUST fail gracefully on malformed input, returns `{ status: 'ok' }` on success.
- **Reviewer:** Claude (Opus 4.7, 1M context) — automated code reviewer.
- **Severity Scale:** Critical = data corruption / RCE / privilege escalation; High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated; Medium = incorrect behavior on some inputs, unclear error handling, missing validation implied by design; Low = style, naming, minor refactors, nits.
- **Date:** 2026-04-26

## Findings

### Critical

#### C1. `replace("..", "")` does NOT prevent path traversal — design requirement violated, arbitrary filesystem write
- **Citation:** `api/handlers/upload.rs:36-39`
- **Problem:** The "safety" filter is `let safe_name = filename.replace("..", "");` followed by `PathBuf::from("/uploads").join(safe_name)`. This is bypassable in multiple ways:
  1. **Absolute paths:** `PathBuf::join` with an absolute path *replaces* the base. A filename like `/etc/passwd` (no `..` present) yields `path = /etc/passwd`, completely escaping `/uploads`. On Windows, prefixes like `C:\...` or `\\server\share` behave similarly.
  2. **Recursive-substring evasion:** `replace("..", "")` is a single non-overlapping pass. The input `....//....//etc/passwd` collapses to `../../etc/passwd` after the single replace, re-introducing traversal segments. Similarly `.....///` → `..//`.
  3. **Encoded / alternate separators:** Backslashes (`..\..\etc\passwd`) on platforms that treat `\` as a separator, or URL-encoded forms passed through upstream layers, are not handled. (Less critical on Linux, but the code makes no platform assumption.)
  4. **Nested directories:** Even without `..`, a `filename` like `subdir/../../etc/passwd` is dangerous; a single `..` token slipping through after the replace (see #2) is enough.
- **Why it matters:** The acceptance criteria state explicitly: "MUST prevent path traversal: nothing should write outside `/uploads`." This is a **Critical** violation — an unauthenticated multipart upload (judging by the handler signature taking only `Multipart`) can write attacker-controlled bytes to arbitrary filesystem locations the server process can write to (e.g., `/etc/cron.d/`, `~/.ssh/authorized_keys`, web root, systemd unit files), trivially escalating to remote code execution / privilege escalation on most deployments.
- **Source-of-truth reference:** Design / Acceptance criteria, lines 16 and 19-20 of the package: "MUST prevent path traversal: nothing should write outside `/uploads`. … The handler must reject any input that would write outside that directory."
- **Proposed fix:** Replace the substring filter with a robust validation that (a) extracts only the basename, (b) rejects empty / dotfile / non-ASCII-controlled filenames per policy, and (c) canonicalizes and verifies the resulting path is inside `/uploads`. Sketch:
  ```rust
  use std::path::{Component, Path, PathBuf};

  const UPLOAD_ROOT: &str = "/uploads";

  fn safe_upload_path(raw: &str) -> Result<PathBuf, &'static str> {
      // Reject empty, absolute, or anything containing path separators / parent refs.
      let candidate = Path::new(raw);
      let mut comps = candidate.components();
      let only = comps.next().ok_or("empty filename")?;
      if comps.next().is_some() {
          return Err("filename must not contain path separators");
      }
      let name = match only {
          Component::Normal(s) => s,
          _ => return Err("invalid filename component"),
      };
      let name_str = name.to_str().ok_or("non-utf8 filename")?;
      if name_str.starts_with('.') || name_str.is_empty() {
          return Err("invalid filename");
      }
      let joined = PathBuf::from(UPLOAD_ROOT).join(name_str);
      // Defense in depth: canonicalize the parent and re-verify.
      let parent = std::fs::canonicalize(UPLOAD_ROOT).map_err(|_| "uploads dir missing")?;
      if !joined.starts_with(&parent) {
          return Err("path escapes uploads dir");
      }
      Ok(joined)
  }
  ```
  Then return `400 Bad Request` (e.g., via `(StatusCode::BAD_REQUEST, Json(...))`) when validation fails, instead of writing or panicking.

### High

#### H1. Multiple `.unwrap()` calls panic the request task on malformed input — violates "fail gracefully"
- **Citation:** `api/handlers/upload.rs:31-33, 39`
- **Problem:** Four unwraps in the hot path:
  - `multipart.next_field().await.unwrap()` — panics on a malformed multipart stream (boundary errors, premature EOF, oversized headers).
  - `field.file_name().unwrap()` — panics on any field that lacks a `filename` parameter (e.g., a regular form field). The spec only says "for each field with a filename"; non-file fields are valid multipart input and must not crash the handler.
  - `field.bytes().await.unwrap()` — panics on body-read errors (client disconnect, size cap, IO error).
  - `std::fs::write(&path, data).unwrap()` — panics on any IO failure (disk full, permission denied, target is a directory, parent missing).
- **Why it matters:** Acceptance criteria require "Should fail gracefully on malformed input." `.unwrap()` panics propagate through the Axum task and are returned as `500 Internal Server Error` (or worse, depending on panic strategy). This is also a denial-of-service vector: a single crafted upload can be repeated to flood logs and abort in-flight work, and may abort the runtime entirely if `panic = "abort"` is configured.
- **Source-of-truth reference:** Acceptance criteria, line 17: "Should fail gracefully on malformed input."
- **Proposed fix:** Change the return type to `Result<Json<Value>, (StatusCode, Json<Value>)>` (or similar `IntoResponse`) and replace each unwrap with `?`/explicit error mapping:
  ```rust
  while let Some(field) = multipart.next_field().await
      .map_err(|e| bad_request(format!("multipart error: {e}")))? {
      let Some(filename) = field.file_name().map(str::to_owned) else { continue; };
      let data = field.bytes().await
          .map_err(|e| bad_request(format!("body error: {e}")))?;
      let path = safe_upload_path(&filename).map_err(bad_request)?;
      tokio::fs::write(&path, &data).await
          .map_err(|e| internal(format!("write failed: {e}")))?;
  }
  ```

#### H2. Unbounded upload size — memory exhaustion DoS
- **Citation:** `api/handlers/upload.rs:33`
- **Problem:** `field.bytes().await` buffers the entire field into memory with no size cap. Axum's default multipart limit is ~2 MiB per field, but applying `DefaultBodyLimit::disable()` or any larger override (common when accepting "uploads") removes this protection. A single attacker with a multi-GB body or many concurrent uploads can OOM the process.
- **Why it matters:** Resource exhaustion under common load — explicitly listed as a High criterion in the review instructions. Combined with the panic-on-error behaviour in H1, this also enables trivial DoS.
- **Source-of-truth reference:** Review instructions severity guide ("resource leak under common load"); design implies handling uploads safely.
- **Proposed fix:** Either (a) enforce an explicit per-field byte cap by streaming `field.chunk()` into the file and bailing past a configured maximum, or (b) wire a `RequestBodyLimit`/`DefaultBodyLimit::max(...)` middleware and document it. Streaming is preferred so peak memory is bounded:
  ```rust
  let mut file = tokio::fs::File::create(&path).await.map_err(internal)?;
  let mut total = 0usize;
  while let Some(chunk) = field.chunk().await.map_err(bad_request)? {
      total = total.checked_add(chunk.len()).ok_or_else(|| bad_request("overflow"))?;
      if total > MAX_UPLOAD_BYTES { return Err(bad_request("file too large")); }
      file.write_all(&chunk).await.map_err(internal)?;
  }
  ```

#### H3. Blocking `std::fs::write` inside an async handler stalls the executor
- **Citation:** `api/handlers/upload.rs:39`
- **Problem:** `std::fs::write` is synchronous and blocking. Calling it from an async Axum handler blocks the Tokio worker thread for the duration of the disk write, starving other tasks scheduled on that worker and harming tail latency under load.
- **Why it matters:** Reliability/perf regression under common load. With Tokio's default multi-threaded runtime this manifests as latency spikes; on a single-threaded runtime it stalls all other requests.
- **Source-of-truth reference:** Tokio/Axum best practice; review instructions ("performance degradation" / "resource leak under common load").
- **Proposed fix:** Use `tokio::fs::write` (or `tokio::fs::File` + `AsyncWriteExt::write_all`) — see H2's snippet — or wrap the sync call in `tokio::task::spawn_blocking`.

#### H4. Silent file overwrite — no collision detection
- **Citation:** `api/handlers/upload.rs:37-39`
- **Problem:** `std::fs::write` truncates and overwrites any existing file at the target path. Two clients uploading the same `filename` (or one client overwriting another's content, or a server-side file with a guessable name) silently destroys data.
- **Why it matters:** "Silent data inconsistency" — explicitly called out as a High criterion. Also a security concern: an attacker who can predict any filename in `/uploads` can clobber it.
- **Source-of-truth reference:** Review instructions severity guide.
- **Proposed fix:** Generate a server-side unique name (e.g., UUID) or open with `OpenOptions::new().create_new(true).write(true)` and surface a 409 Conflict on collision. Preserve the user-supplied basename only as metadata, not as on-disk identity.

### Medium

#### M1. Partial-success semantics: handler returns `ok` even if a later field fails (after fix) or after panic mid-loop
- **Citation:** `api/handlers/upload.rs:30-42`
- **Problem:** The loop processes fields sequentially and only emits `{"status":"ok"}` after the loop completes. Today, a panic mid-loop drops everything written so far without rollback or status. After H1 is fixed, an early `?` return will leave previously-written files on disk while reporting failure to the client. There is no transactional contract or per-file status report.
- **Why it matters:** Ambiguous success/failure semantics for clients; orphaned files accumulate. Design says "Returns `{ status: 'ok' }` on success" but does not define partial-failure behaviour.
- **Source-of-truth reference:** Design, line 14 (per-field write) and line 16 (return shape).
- **Proposed fix:** Either (a) return a per-field result array, e.g., `{"status":"ok","files":[{"name":..,"bytes":..}, ...]}`, or (b) on first error, delete files written earlier in the same request to provide all-or-nothing semantics, or (c) document that writes are best-effort and return `207`-like granularity.

#### M2. No validation that `/uploads` exists / is a directory / is writable
- **Citation:** `api/handlers/upload.rs:37-39`
- **Problem:** The handler assumes `/uploads` exists. If it does not, the underlying `open(2)` fails and (today) panics; after H1's fix, every request returns 500. There is no startup-time check or `create_dir_all` to make the contract explicit.
- **Why it matters:** Operational fragility; misconfiguration becomes a per-request runtime error rather than a startup error.
- **Source-of-truth reference:** Design, lines 19-20: `/uploads` is the only allowed write target.
- **Proposed fix:** During app initialization, call `std::fs::create_dir_all("/uploads")` (or assert it exists and is a writable directory) and fail fast otherwise. Make the path configurable via env/config rather than hard-coded.

#### M3. Hard-coded absolute path `/uploads` reduces portability and testability
- **Citation:** `api/handlers/upload.rs:37`
- **Problem:** `/uploads` is a literal in handler code. This makes the handler untestable in CI without root or a writable `/uploads`, and prevents per-environment configuration (dev vs prod, container volume mounts).
- **Why it matters:** Testability and deployment hygiene; violates separation of configuration from code.
- **Source-of-truth reference:** Standard Rust/12-factor practice.
- **Proposed fix:** Inject the upload root through application state (`State<AppConfig>`) or read once from config at startup, defaulting to `/uploads`.

#### M4. Filename used verbatim — no length, charset, or reserved-name validation
- **Citation:** `api/handlers/upload.rs:32, 36-37`
- **Problem:** Even after the basename-only fix in C1, attackers can supply pathological names: extremely long (>255 bytes filesystem limit → IO error), control characters, NUL bytes (which would error out earlier in PathBuf, but still surface as 500), Windows-reserved names (`CON`, `AUX`, `NUL.txt`) if the upload root is ever mounted from a Windows host, leading dot for hidden files, or a name beginning with `-` that confuses CLI tooling later.
- **Why it matters:** Missing validation implied by design ("only allowed write target" + traversal protection). Some classes (e.g., NUL) become 500s; others enable secondary exploits in downstream tooling.
- **Source-of-truth reference:** Design's traversal/safety intent.
- **Proposed fix:** Apply an allowlist regex (e.g., `^[A-Za-z0-9._-]{1,128}$`) plus explicit length cap, reject leading-dot names, and strip/replace anything else with a 400.

#### M5. No `Content-Type` or content-sniffing controls
- **Citation:** `api/handlers/upload.rs:30-42`
- **Problem:** Handler accepts arbitrary bytes under arbitrary names. If `/uploads` is later served statically (a common pattern), this becomes a stored-XSS / arbitrary-file-serve sink. The handler trusts the client-declared filename for both naming and (implicitly) extension/MIME.
- **Why it matters:** Cross-cutting security risk that often pairs with upload handlers; the design does not explicitly require it but the spirit ("only allowed write target") implies caution.
- **Source-of-truth reference:** Design intent + standard secure-upload practice.
- **Proposed fix:** Validate `field.content_type()` against an allowlist or sniff the leading bytes; store under a server-controlled extension; if `/uploads` is web-served, set `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

### Low

#### L1. `Json<serde_json::Value>` return type is loose; prefer a typed response
- **Citation:** `api/handlers/upload.rs:30, 41`
- **Problem:** Returning `Json<serde_json::Value>` skips compile-time guarantees about the response shape. A small `#[derive(Serialize)] struct UploadResponse { status: &'static str }` is clearer and self-documenting.
- **Why it matters:** Maintainability/readability nit.
- **Source-of-truth reference:** Idiomatic Axum/serde practice.
- **Proposed fix:** Define a typed response struct (and a typed error struct) and return `Json<UploadResponse>`.

#### L2. `filename.replace("..", "")` naming is misleading (`safe_name`)
- **Citation:** `api/handlers/upload.rs:36`
- **Problem:** The variable `safe_name` and the comment "Strip path traversal attempts" overstate the guarantee provided. After fixing C1, also rename the variable to reflect what it actually is (e.g., `validated_basename`).
- **Why it matters:** Misleading names lead future readers to trust the value; this is exactly what produced the C1 bug.
- **Source-of-truth reference:** Code-clarity nit.
- **Proposed fix:** Rename and add a doc comment describing the validation guarantee.

#### L3. Missing module/handler documentation
- **Citation:** `api/handlers/upload.rs:30`
- **Problem:** No `///` doc comment on `upload_file` describing the contract (request shape, response shape, error cases). Public handlers benefit from rustdoc that mirrors the OpenAPI surface.
- **Why it matters:** Discoverability/onboarding nit.
- **Source-of-truth reference:** Rust API guidelines.
- **Proposed fix:** Add `///` doc comment summarising inputs, outputs, and error responses.

#### L4. Implementer note overstates safety
- **Citation:** Package preamble line 5 ("Path safety is addressed via the .. filter on filenames.")
- **Problem:** This claim is incorrect (see C1). Worth flagging in PR discussion to align reviewer/implementer mental models and to encourage a test that demonstrates the bypass.
- **Why it matters:** Accurate self-reporting reduces review friction and prevents repeat regressions.
- **Source-of-truth reference:** N/A (process nit).
- **Proposed fix:** Add a unit/integration test exercising the bypass cases listed in C1 and update the PR description after fixing.
