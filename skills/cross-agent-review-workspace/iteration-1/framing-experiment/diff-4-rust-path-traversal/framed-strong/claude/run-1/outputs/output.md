- **Review Scope:** New file `api/handlers/upload.rs` implementing `upload_file(multipart)` handler for multipart file uploads to `/uploads`.
- **Process Used:** Static review of the supplied diff against the stated design/acceptance criteria; no execution, no repo browsing beyond the package.
- **Execution Context:** Closed-context review; only the package contents were read. No surrounding crate, routing, auth middleware, or filesystem layout were inspected.
- **Integration Target:** Axum-based HTTP API with a multipart endpoint writing into the `/uploads` directory on the host filesystem.
- **Governing Documents:** "File upload handler" design block in the package — accepts multipart, writes each named field to `/uploads/<filename>`, returns `{ status: 'ok' }`, MUST prevent path traversal, must fail gracefully on malformed input.
- **Reviewer:** Claude (Opus 4.7, 1M context), single-pass structured review.
- **Severity Scale:** Critical = production data corruption / RCE / privilege escalation. High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated. Medium = incorrect behavior on some inputs, unclear error handling, missing implied validation, performance degradation. Low = style, naming, nits.
- **Date:** 2026-04-26.

## Findings

### Critical

#### C1. Path traversal mitigation is trivially bypassable — design's MUST requirement is violated
- **Citation:** `api/handlers/upload.rs:36-37` (`let safe_name = filename.replace("..", ""); let path = PathBuf::from("/uploads").join(safe_name);`)
- **Problem:** `filename.replace("..", "")` is not a path-traversal defense. Two independent bypasses exist:
  1. **Recursive reconstruction:** Input `....//....//etc/passwd` becomes `..//..//etc/passwd` after a single non-recursive replace — the replace removes the inner `..` substrings and leaves new `..` sequences behind. Result: `PathBuf::from("/uploads").join("..//..//etc/passwd")` resolves to `/uploads/../../etc/passwd` → `/etc/passwd`.
  2. **Absolute-path join:** `PathBuf::join` with an argument that starts with `/` (e.g. filename `"/etc/passwd"` or, on Windows, `"C:\\Windows\\..."`) **discards the base** and returns the absolute argument. The `..` filter does not catch this at all. From the Rust stdlib docs for `Path::join`: "If path is absolute, it replaces the current path."
  Either bypass lets an authenticated (or unauthenticated, depending on routing) caller write attacker-controlled bytes anywhere the server process has write permission — `/etc/cron.d/`, `~/.ssh/authorized_keys`, the binary's own directory, systemd unit files, etc. That is arbitrary code execution / privilege escalation territory.
- **Why it matters:** The design states, verbatim, "MUST prevent path traversal: nothing should write outside `/uploads`" and "The handler must reject any input that would write outside that directory." This is the single hardest constraint in the spec, and the implementation fails it on the first adversarial input. The implementer note ("Confident this is safe") is wrong.
- **Source-of-truth reference:** Design block lines 16, 19-20 of the package ("MUST prevent path traversal…", "must reject any input that would write outside that directory").
- **Proposed fix:** Do not sanitize by substring removal. Instead:
  1. Extract only the final path component of the user-supplied filename and reject anything that is not a plain filename: reject empty, reject `.` / `..`, reject any name containing `/`, `\\`, or NUL, reject absolute paths, reject names starting with `.` if dotfiles are not desired.
  2. Canonicalize the resulting target and verify it is a descendant of the canonicalized `/uploads` base before writing. Roughly:
     ```rust
     use std::path::{Component, Path, PathBuf};

     fn safe_target(base: &Path, raw: &str) -> Result<PathBuf, UploadError> {
         let name = Path::new(raw)
             .file_name()
             .ok_or(UploadError::BadFilename)?;
         let candidate = base.join(name);
         // Reject any non-Normal component (covers .., ., RootDir, Prefix).
         if candidate.components().any(|c| !matches!(c, Component::Normal(_) | Component::RootDir | Component::Prefix(_))) {
             return Err(UploadError::BadFilename);
         }
         let base_canon = base.canonicalize()?;
         let parent_canon = candidate.parent().unwrap().canonicalize()?;
         if !parent_canon.starts_with(&base_canon) {
             return Err(UploadError::BadFilename);
         }
         Ok(candidate)
     }
     ```
  3. Open with `OpenOptions::new().write(true).create_new(true)` so an attacker cannot clobber an existing file, and consider `O_NOFOLLOW` semantics (e.g. via `cap-std` or `openat2(RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS)`) to defeat symlink-based escapes that pure string checks cannot see.

### High

#### H1. Four `.unwrap()` calls panic the request task on malformed/expected input — violates "fail gracefully"
- **Citation:** `api/handlers/upload.rs:31, 32, 33, 39`
  - `multipart.next_field().await.unwrap()` (line 31)
  - `field.file_name().unwrap().to_string()` (line 32)
  - `field.bytes().await.unwrap()` (line 33)
  - `std::fs::write(&path, data).unwrap()` (line 39)
- **Problem:** Each of these is reachable from ordinary client behavior, not just exotic input:
  - `next_field()` returns `Err` on malformed multipart framing (truncated boundary, bad headers, oversized part). A client sending a half-uploaded body causes a panic.
  - `field.file_name()` returns `None` for any part without a `filename=` parameter in `Content-Disposition` (e.g. a plain text form field). The design says "For each field with a filename" — i.e. fields without one should be skipped, not crash the handler.
  - `field.bytes().await` returns `Err` on transport errors (client disconnect mid-upload, body too large) — common, not exceptional.
  - `std::fs::write` returns `Err` on full disk, EACCES, ENOSPC, EROFS, or if `/uploads` does not exist. None of these are programmer errors.
- **Why it matters:** The design says "Should fail gracefully on malformed input." Panicking in an Axum handler aborts the task and returns a 500 with no structured body, and in some deployments leaves connection state inconsistent. It also turns "client sent a non-file form field" into a denial-of-service primitive: any attacker can trigger panics at will.
- **Source-of-truth reference:** Design block line 17 of the package ("Should fail gracefully on malformed input.")
- **Proposed fix:** Return `Result<Json<Value>, (StatusCode, Json<Value>)>` (or a custom `IntoResponse` error type). Replace each `unwrap()` with `?` plus a mapping to `400 Bad Request` for client-side problems and `500` for server I/O failures. Skip fields whose `file_name()` is `None` rather than erroring.

#### H2. Existing files are silently overwritten
- **Citation:** `api/handlers/upload.rs:39` (`std::fs::write(&path, data).unwrap();`)
- **Problem:** `std::fs::write` truncates and overwrites any existing file at the target path. Combined with attacker-controlled (or even just colliding) filenames, two clients uploading `report.pdf` race-overwrite each other; an attacker who can guess or enumerate filenames can replace legitimate uploads. Even without the C1 traversal bug, this is silent data loss.
- **Why it matters:** "Silent data inconsistency" is explicitly called out as High severity in the rubric. Users expect that a successful 200 means their file was stored, not that someone else's file was destroyed.
- **Source-of-truth reference:** Implied by the design's intent that `/uploads` is the system's only write target — the design does not authorize destructive overwrite.
- **Proposed fix:** Open with `OpenOptions::new().write(true).create_new(true)` and on `ErrorKind::AlreadyExists` either reject with `409 Conflict` or generate a unique suffix (UUID, hash of bytes). Consider writing to a temp file in the same directory and `rename`-ing into place to make the operation atomic.

#### H3. No size limit — unbounded memory and disk consumption
- **Citation:** `api/handlers/upload.rs:33` (`let data = field.bytes().await.unwrap();`) and `:39` (`std::fs::write(&path, data)`)
- **Problem:** `field.bytes()` buffers the entire part into memory before the write. With Axum's default `DefaultBodyLimit` of 2 MiB this is bounded, but multipart handlers commonly raise or disable that limit, and even at 2 MiB an attacker that loops can fill `/uploads` until the disk is full (the loop has no per-request part count cap either). There is no streaming write, no per-field byte cap, and no total-request cap.
- **Why it matters:** The rubric flags "resource leak under common load" as High. A single curl loop can OOM the process or exhaust the disk partition holding `/uploads`, which on many deployments is the same partition as logs or the database.
- **Source-of-truth reference:** Design block line 17 ("Should fail gracefully on malformed input") and the general expectation that production handlers bound resources.
- **Proposed fix:** Apply `axum::extract::DefaultBodyLimit::max(N)` on the route, cap the number of fields per request, and stream each field with `field.chunk().await` into the file rather than `field.bytes()`. Reject early when a per-field or per-request byte budget is exceeded.

### Medium

#### M1. `/uploads` is hard-coded — non-portable and untestable
- **Citation:** `api/handlers/upload.rs:37` (`PathBuf::from("/uploads")`)
- **Problem:** The base directory is a string literal at the call site. This breaks tests (which cannot redirect writes to a temp dir), breaks Windows entirely (`/uploads` is interpreted relative to the current drive root), and prevents per-environment configuration.
- **Why it matters:** Makes the secure-target check in C1's fix harder (you cannot canonicalize a non-existent dir on a dev machine) and couples the handler to a specific deployment layout.
- **Source-of-truth reference:** Design block line 14 names `/uploads` as the location, but does not require it be a literal — standard practice is configuration.
- **Proposed fix:** Inject the base directory via Axum state (`State<UploadConfig>`) or a once-initialized `PathBuf`. Resolve and canonicalize at startup; the handler then operates on a known-good base.

#### M2. No `Content-Type` or filename character-set validation
- **Citation:** `api/handlers/upload.rs:32-37`
- **Problem:** The handler accepts any filename string the client provides. Even after fixing C1, names like `"\u{202E}cod.exe"` (right-to-left override), embedded newlines, control characters, very long names (>255 bytes — ENAMETOOLONG), or shell-meta characters can cause downstream surprises (log injection, display spoofing, breaking sync tools). `Content-Type` is also never checked.
- **Why it matters:** Falls under "missing validation that the design implies" — the design's spirit is "safely accept user uploads."
- **Source-of-truth reference:** Design block line 16 (path-traversal prevention) and general defense-in-depth.
- **Proposed fix:** Restrict filenames to a known-safe character class (e.g. `[A-Za-z0-9._-]{1,128}`) or hash the bytes and store under a server-generated name while remembering the original in metadata.

#### M3. Partial-success semantics are undefined
- **Citation:** `api/handlers/upload.rs:30-42` (the whole `while` loop returning `{status: "ok"}` unconditionally on line 41)
- **Problem:** Once `unwrap()`s are replaced with proper error returns (per H1), the question becomes: if field 3 of 5 fails, should fields 1-2 remain on disk while the response is 4xx? The current code answers "yes" by accident. The design does not say.
- **Why it matters:** Unclear error handling — the rubric's Medium definition. Users will get inconsistent state and no way to know which files made it.
- **Source-of-truth reference:** Design block lines 13-15 (per-field write, single status response) — ambiguous.
- **Proposed fix:** Decide and document the contract. Either (a) write each field to a temp file, then rename all on success / unlink all on any failure (atomic batch), or (b) return a per-field result array `{ accepted: [...], rejected: [{name, reason}, ...] }` so the client knows what happened.

### Low

#### L1. Response shape uses single quotes in the spec but JSON requires double quotes — consider documenting the actual shape
- **Citation:** Design block line 15 (`Returns { status: 'ok' } on success.`) vs `api/handlers/upload.rs:41` (`Json(json!({"status": "ok"}))`)
- **Problem:** Implementation is correct JSON; the design used JS-style single quotes. Worth a one-line comment or OpenAPI entry so future readers don't think the wire format is `'ok'`.
- **Why it matters:** Nit — but trivial to address while you are in the file.
- **Source-of-truth reference:** Design block line 15.
- **Proposed fix:** Add a doc comment on `upload_file` describing the response schema, or add a typed response struct with `#[derive(Serialize)]` instead of `json!`.

#### L2. `to_string()` allocation is unnecessary
- **Citation:** `api/handlers/upload.rs:32` (`field.file_name().unwrap().to_string()`)
- **Problem:** `file_name()` returns `Option<&str>`; the code clones it into an owned `String` only to feed it into `replace`, which itself returns a new `String`. After fixing C1 with `Path::file_name()`, this allocation goes away naturally.
- **Why it matters:** Style.
- **Source-of-truth reference:** N/A.
- **Proposed fix:** Operate on `&str` until the validated `PathBuf` is constructed.

#### L3. `use std::path::PathBuf` is unused if a stricter helper replaces line 37
- **Citation:** `api/handlers/upload.rs:28`
- **Problem:** Cosmetic — once C1 is fixed via a helper that returns `PathBuf`, the import stays, but if the helper lives in another module the direct import here may become dead.
- **Why it matters:** Style; `cargo clippy` would catch it.
- **Source-of-truth reference:** N/A.
- **Proposed fix:** Re-run `cargo clippy --all-targets -- -D warnings` after restructuring.
