- **Review Scope:** New file `api/handlers/upload.rs` implementing `upload_file(multipart)` per the design/acceptance criteria for multipart upload handling into `/uploads`.
- **Process Used:** Static review of the supplied diff against the stated acceptance criteria, with focus on the explicit "MUST prevent path traversal" requirement, error handling, and Rust/axum idioms. No execution; tests not inspected.
- **Execution Context:** Closed-context review of a single package; no repository access beyond the supplied snippet.
- **Integration Target:** Axum-based HTTP handler returning JSON; writes uploaded bytes to the local filesystem under `/uploads`.
- **Governing Documents:** The design/acceptance criteria included in the package — specifically: writes confined to `/uploads`, must reject any input that would escape that directory, must fail gracefully on malformed input, returns `{ status: 'ok' }` on success.
- **Reviewer:** Claude (Opus 4.7, 1M context), automated code-review pass.
- **Severity Scale:** Critical / High / Medium / Low as defined in the package's "Review instructions" section.
- **Date:** 2026-04-26.

## Findings

### Critical

**1. Path-traversal mitigation is trivially bypassable — design requirement violated**
- **Citation:** `api/handlers/upload.rs:36-37`
- **Problem:** The "sanitization" is `let safe_name = filename.replace("..", "");` followed by `PathBuf::from("/uploads").join(safe_name)`. This does not prevent path traversal:
  - An absolute path in `filename` (e.g. `/etc/passwd`, or on Windows `C:\Windows\...`) makes `PathBuf::join` *replace* the base entirely, so the write goes to `/etc/passwd`, **not** `/uploads/etc/passwd`. This is documented Rust behavior for `Path::join` when the argument is absolute.
  - A filename containing forward slashes but no literal `..` segment (e.g. `subdir/evil.sh`, or `../etc/passwd` rewritten as `.../etc/passwd` won't help, but `....//....//etc/passwd` will: after replacing `..` with empty, we get `..//..//etc/passwd` — actually that still contains `..`; but the simple recursive bypass works: `....` becomes `` once `..` is removed, so input like `....//....//etc/passwd` reduces to `//etc/passwd`, an absolute path — again `join` discards `/uploads`).
  - More directly: `filename = "....//....//etc/passwd"` → after `.replace("..", "")` → `"//etc/passwd"` → `PathBuf::from("/uploads").join("//etc/passwd")` → `/etc/passwd`.
  - Even without absolute-path tricks, embedded slashes (`foo/../../etc/passwd` collapses to `foo///etc/passwd` after stripping `..`) can write under unexpected subdirectories the server may have permission to clobber.
- **Why it matters:** The design says "MUST prevent path traversal: nothing should write outside `/uploads`." This handler can be coerced into writing arbitrary files anywhere the process has write permission — a textbook arbitrary-file-write / RCE precursor (overwrite cron files, systemd units, SSH `authorized_keys`, web roots, etc.). This directly violates the explicit security requirement.
- **Source-of-truth reference:** Acceptance criteria, lines 16 and 19-20 of the package ("MUST prevent path traversal: nothing should write outside `/uploads`"; "The handler must reject any input that would write outside that directory.").
- **Proposed fix:** Do not attempt string-level sanitization. Instead:
  1. Reject filenames containing path separators or non-basename components outright.
  2. Take only the final basename via `std::path::Path::new(&filename).file_name()` and reject if `None`, empty, equal to `.`/`..`, or contains a NUL byte.
  3. Build the candidate path, then canonicalize the *parent* (`/uploads`) once at startup and verify that `candidate.parent().canonicalize()?` equals the canonical `/uploads`. Reject otherwise.
  4. Open the destination with `OpenOptions::new().write(true).create_new(true)` (or equivalent) under the canonicalized base directory to also prevent symlink-following surprises and accidental overwrite. Sketch:
     ```rust
     let name = std::path::Path::new(&filename)
         .file_name()
         .and_then(|s| s.to_str())
         .ok_or(StatusCode::BAD_REQUEST)?;
     if name.is_empty() || name == "." || name == ".." || name.contains('\0') {
         return Err(StatusCode::BAD_REQUEST);
     }
     let base = std::fs::canonicalize("/uploads")?;
     let path = base.join(name);
     // Optional: verify path.parent().canonicalize()? == base
     let mut f = std::fs::OpenOptions::new()
         .write(true).create_new(true).open(&path)?;
     f.write_all(&data)?;
     ```

### High

**2. `.unwrap()` on every fallible operation — handler panics on malformed input, violating "fail gracefully"**
- **Citation:** `api/handlers/upload.rs:31, 32, 33, 39`
  - `multipart.next_field().await.unwrap()` (line 31)
  - `field.file_name().unwrap().to_string()` (line 32)
  - `field.bytes().await.unwrap()` (line 33)
  - `std::fs::write(&path, data).unwrap()` (line 39)
- **Problem:** Any malformed multipart frame, missing `filename` parameter on a part (which is *expected* per the spec — only "fields with a filename" should be written), oversized body, I/O error, permission error, or disk-full condition will panic the request task. With axum, this aborts the connection (HTTP 500 with no body, or a hang depending on the runtime) instead of returning a structured error, and pollutes logs with panic backtraces. It also means a single malicious client can spam panics trivially.
- **Why it matters:** The acceptance criteria explicitly say "Should fail gracefully on malformed input." `.unwrap()` is the opposite of graceful. In particular, calling `.unwrap()` on `field.file_name()` for a non-file field (legitimate per RFC 7578) turns a normal request into a 500.
- **Source-of-truth reference:** Acceptance criteria, line 17 ("Should fail gracefully on malformed input.").
- **Proposed fix:** Change the return type to `Result<Json<Value>, (StatusCode, String)>` (or a custom error type implementing `IntoResponse`). Use `?` with explicit error mapping. Skip parts whose `file_name()` is `None` rather than panicking — the spec says "for each field *with a filename*", implying parts without filenames should be ignored, not crash the request.

**3. Silent overwrite of existing files under `/uploads`**
- **Citation:** `api/handlers/upload.rs:39`
- **Problem:** `std::fs::write` truncates and replaces any existing file at the target path. Two clients uploading `report.pdf` will silently clobber each other; a malicious client can deliberately overwrite known filenames (e.g. a previously uploaded user document, or any file in `/uploads` an attacker can guess).
- **Why it matters:** Silent data loss / data inconsistency. Even within `/uploads`, this is a denial-of-integrity and can be chained with other bugs (e.g. if `/uploads` is served back via a static handler, an attacker can replace another user's file). The design doesn't authorize overwrite semantics.
- **Source-of-truth reference:** Acceptance criteria implicitly — the design only authorizes a write target, not overwrite semantics; combined with the "fail gracefully" requirement, collisions should be a defined error rather than silent data loss.
- **Proposed fix:** Use `OpenOptions::new().write(true).create_new(true).open(&path)` so that an existing file produces an `ErrorKind::AlreadyExists` error, returned as a 409 Conflict. Alternatively, namespace uploads (e.g. per-user subdirectory or UUID prefix) — but that's a design decision, not a bug fix.

### Medium

**4. No size limit on uploaded parts — memory/disk DoS**
- **Citation:** `api/handlers/upload.rs:33`
- **Problem:** `field.bytes().await` buffers the entire field body into memory before writing. There is no size cap, no streaming write, and no per-request body limit configured at the route. A single multi-GB upload can exhaust RAM; many concurrent uploads compound the issue.
- **Why it matters:** Resource exhaustion under common load and a trivial DoS vector. Falls under Medium because it's not a confidentiality/integrity break, but in production it will cause outages.
- **Source-of-truth reference:** Implicit in the acceptance criteria ("fail gracefully" applies to oversized as well as malformed input).
- **Proposed fix:** Stream the field with `field.chunk().await` in a loop, writing each chunk to the destination file as it arrives, while accumulating a byte count and returning `413 Payload Too Large` if a configured maximum is exceeded. Also apply axum's `DefaultBodyLimit` or `RequestBodyLimit` layer at the router level.

**5. Filename character validation is missing (NUL bytes, control chars, reserved names, hidden files)**
- **Citation:** `api/handlers/upload.rs:32, 36`
- **Problem:** Beyond traversal, the code accepts arbitrary bytes from the client as the on-disk filename: NUL bytes (which Rust's `PathBuf` will reject at the syscall but only after string handling), control characters, leading dots (creating hidden files like `.htaccess` or `.bashrc`), Windows-reserved names if the deployment is cross-platform (`CON`, `PRN`, `AUX`, etc.), and very long names exceeding `NAME_MAX`.
- **Why it matters:** Even after fixing the traversal bug, client-controlled filenames need a positive allowlist (or at minimum: reject empty, leading-dot, non-UTF-8, length > 255 bytes, characters outside a safe set). Otherwise the upload directory becomes a foothold for further misuse (writing `.htaccess` in a directory served by Apache, etc.).
- **Source-of-truth reference:** Implicit in the security intent of the path-traversal requirement.
- **Proposed fix:** After basename extraction, validate against an explicit pattern such as `^[A-Za-z0-9._-]{1,255}$` and reject leading `.`. Generate a server-side filename (UUID + sanitized extension) if the design permits.

**6. Partial-success semantics are undefined**
- **Citation:** `api/handlers/upload.rs:30-42`
- **Problem:** The `while` loop processes fields sequentially. If field 3 of 5 fails (or panics, see Finding 2), fields 1 and 2 have already been written; fields 4 and 5 won't be. The handler currently returns `{ status: 'ok' }` only if *all* succeed, but on failure (once `unwrap` is removed) the caller has no way to know which files were written. There's no transactional rollback or per-field status reporting.
- **Why it matters:** Silent data inconsistency between client and server state.
- **Source-of-truth reference:** Acceptance criteria don't explicitly cover partial failure, but "fail gracefully" implies a meaningful response.
- **Proposed fix:** Either (a) write each field to a temp file and atomically rename only after all fields have been validated and staged, rolling back on any error; or (b) return per-field results in the JSON body (`{ status: 'partial', written: [...], failed: [...] }`) and use an appropriate non-2xx status when any field failed.

### Low

**7. Hard-coded absolute path `/uploads`**
- **Citation:** `api/handlers/upload.rs:37`
- **Problem:** The upload root is a string literal, not configurable per environment. Tests, CI, and dev machines either need root-writable `/uploads` or have to monkey-patch this.
- **Why it matters:** Maintainability and testability nit; not a correctness issue on its own.
- **Source-of-truth reference:** N/A (style/maintainability).
- **Proposed fix:** Inject the upload directory via configuration (axum `State`, env var, or a constant module) and canonicalize once at startup.

**8. Blocking filesystem I/O inside an async handler**
- **Citation:** `api/handlers/upload.rs:39`
- **Problem:** `std::fs::write` is synchronous and blocks the tokio worker thread for the duration of the disk write. Under load this starves the runtime.
- **Why it matters:** Performance/scalability concern; not incorrect, but axum handlers should use `tokio::fs` or `tokio::task::spawn_blocking` for filesystem writes — especially given Finding 4 (large uploads).
- **Source-of-truth reference:** N/A (axum/tokio idiom).
- **Proposed fix:** Use `tokio::fs::File` and `tokio::io::AsyncWriteExt::write_all`, ideally streaming chunks as in Finding 4.

**9. Response uses untyped `serde_json::Value` instead of a typed struct**
- **Citation:** `api/handlers/upload.rs:30, 41`
- **Problem:** Returning `Json<serde_json::Value>` loses schema information and makes the contract harder to evolve (e.g. adding error variants per Finding 6).
- **Why it matters:** Style / maintainability nit.
- **Source-of-truth reference:** N/A.
- **Proposed fix:** Define `#[derive(Serialize)] struct UploadResponse { status: &'static str, ... }` and return `Json<UploadResponse>`.

**10. "Tests pass" claim is unverifiable from this diff and unlikely to cover the security requirement**
- **Citation:** Implementer note (package line 5).
- **Problem:** No tests are included in the diff. Given the bypasses in Finding 1, any passing test must be using benign filenames; the security-critical path is almost certainly untested.
- **Why it matters:** Coverage gap on the most important acceptance criterion.
- **Source-of-truth reference:** Acceptance criteria, line 16.
- **Proposed fix:** Add tests covering at minimum: absolute-path filename, `..`-only filename, double-traversal (`....//....//etc/passwd`), embedded slashes, NUL byte, empty filename, missing `filename` parameter, oversized body, and successful happy path.
