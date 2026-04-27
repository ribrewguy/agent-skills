**Review Scope:** `api/handlers/upload.rs` — new `upload_file(multipart)` handler implementing multipart file uploads to `/uploads/<filename>` with path-traversal protection.

**Process Used:** Cold cross-vendor second-pass review. Re-derived all quality claims from the supplied source; no external gates assumed run. Inspected supplied diff against the stated design contract for path-traversal completeness, panic surface, error semantics, and design-requirement adherence.

**Execution Context:** Closed-context single-package review. Only the supplied package (`packages/redacted.md`) was read; no other repository files, no SKILL.md lookups, no test execution.

**Integration Target:** Axum HTTP handler module within an `api/handlers/` tree. Handler is to be wired into the router elsewhere (not shown). Filesystem target is the absolute path `/uploads`.

**Governing Documents:** Design / Acceptance criteria embedded in the package: handler must accept multipart, write each filename-bearing field to `/uploads/<filename>`, return `{status:'ok'}`, prevent any write outside `/uploads`, and fail gracefully on malformed input.

**Reviewer:** Cross-vendor reviewer (Claude), acting as second-pass.

**Severity Scale:** Critical = data corruption / RCE / privilege escalation / arbitrary write; High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated; Medium = incorrect behavior on some inputs, unclear error handling, missing validation implied by design; Low = style / nits.

**Date:** 2026-04-26.

## Findings

### Critical

**C1. Path-traversal filter is trivially bypassable — design's MUST-requirement is violated (arbitrary filesystem write).**
- Citation: `api/handlers/upload.rs:52-53`
  ```rust
  let safe_name = filename.replace("..", "");
  let path = PathBuf::from("/uploads").join(safe_name);
  ```
- Problem: `String::replace("..", "")` is a single non-recursive textual substitution and does not normalize paths. Multiple independent bypasses exist:
  1. **Recursive recombination:** `"....//"` becomes `"./"`, but more importantly `"....//....//etc/passwd"` collapses parts of `..` while leaving traversal intact via `PathBuf::join` semantics. `"...."` → `""` only removes the literal substring once per scan; `"..../"` → `"../"`. After one pass, `"a....b"` → `"ab"` but `".. ."` style variants and `"..%2f"` (URL-encoded) are untouched.
  2. **Absolute-path override:** If `filename` is `"/etc/passwd"` (or on Windows `"C:\\evil"`), `PathBuf::from("/uploads").join("/etc/passwd")` returns `/etc/passwd` — `Path::join` discards the base when the argument is absolute. This is an unconditional arbitrary-write primitive; no `..` is ever needed.
  3. **Backslash traversal:** `"..\\..\\etc\\passwd"` contains no `..` substring? It does — the `..` substring still matches, but `"\\..\\"` collapses to `"\\\\"` and the backslashes are untouched on Unix (treated as literal filename chars), while on Windows they are separators.
  4. **Null byte / control chars:** `"foo\0/etc/passwd"` is not stripped; while Rust paths can contain interior NULs only via `OsStr`, downstream consumers (FFI, logging, archivers) commonly truncate at NUL, producing log/sink mismatch.
  5. **Encoded forms:** `"%2e%2e%2fetc%2fpasswd"` is not decoded by axum's multipart `file_name()` (it returns the raw header value), and the filter never decodes — but if any upstream layer (proxy, client library) percent-decodes the filename field, traversal re-emerges.
  6. **Unicode look-alikes / overlong UTF-8:** not handled; depending on the underlying filesystem, sequences like U+2024 ("ONE DOT LEADER") are not `..` to the filter but may be treated specially by some tooling.
- Why it matters: This is the single MUST in the design. A POST with filename `"/etc/cron.d/pwn"` overwrites system files as whatever user the service runs as. With filename `"../etc/passwd"`, `replace("..", "")` yields `"/etc/passwd"`, then `PathBuf::from("/uploads").join("/etc/passwd")` returns `/etc/passwd` — overwrite. This is unauthenticated arbitrary file write, i.e. trivial RCE on most deployments (drop a unit file, an `authorized_keys`, a cron entry, a webroot script).
- Source-of-truth reference: Design — "MUST prevent path traversal: nothing should write outside `/uploads`." `std::path::Path::join` documented behavior: "If `path` is absolute, it replaces the current path."
- Proposed fix: Do not sanitize by substring replacement. Instead:
  1. Reject any filename that is not a single path component: parse with `Path::new(&filename).components()`, require exactly one `Component::Normal(_)`; reject `RootDir`, `Prefix`, `ParentDir`, `CurDir`, empty, or multi-component names.
  2. Additionally reject filenames containing `'/'`, `'\\'`, NUL, or control characters before parsing.
  3. Construct the target as `Path::new("/uploads").join(component)` and then canonicalize the **parent** (`/uploads`) once at startup, canonicalize the resulting path's parent at write time, and assert the canonical parent equals the canonical `/uploads` (defense in depth against symlinks inside `/uploads`).
  4. Open with `OpenOptions::new().write(true).create_new(true)` (or use `openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS)` on Linux) to defeat symlink races.

**C2. Symlink TOCTOU inside `/uploads` permits writes outside the directory even with a fixed filter.**
- Citation: `api/handlers/upload.rs:55` — `std::fs::write(&path, data).unwrap();`
- Problem: Even a perfectly validated single-component filename can resolve outside `/uploads` if `/uploads/foo` already exists as a symlink to `/etc/passwd`. `std::fs::write` follows symlinks. An attacker who can create a symlink in `/uploads` (e.g. via a prior upload, another process, or initial container layout) can redirect any subsequent upload anywhere the process can write.
- Why it matters: Same blast radius as C1 — arbitrary write — under any deployment where `/uploads` is writable by another user/container or where the handler itself can create symlinks via name encoding. Combined with `create_new` not being used, an attacker can also overwrite arbitrary existing files.
- Source-of-truth reference: Design's "nothing should write outside `/uploads`" applies to the effective filesystem destination, not the lexical path.
- Proposed fix: Use `OpenOptions::new().write(true).create_new(true).custom_flags(libc::O_NOFOLLOW)` on Unix, or `openat2` with `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS`. After opening, `fstat` and verify device/inode of the parent matches a canonicalized `/uploads` opened at startup.

### High

**H1. Three `unwrap()` calls turn malformed input into process panics — design's "fail gracefully" is violated and the request task aborts.**
- Citation: `api/handlers/upload.rs:47, 48, 49, 55`
  ```rust
  while let Some(field) = multipart.next_field().await.unwrap() { // L47
      let filename = field.file_name().unwrap().to_string();      // L48
      let data = field.bytes().await.unwrap();                    // L49
      ...
      std::fs::write(&path, data).unwrap();                       // L55
  ```
- Problem: Every error path panics:
  - L47: `next_field()` returns `Err` on protocol errors (truncated body, invalid boundary, oversize field) — handler panics, axum returns 500 (or aborts the task; client sees a connection reset depending on tower config).
  - L48: `field.file_name()` returns `Option<&str>` and is `None` for any field without a `filename=` parameter (e.g., a plain text form field, or a non-UTF-8 filename header). The design says only fields *with a filename* should be written — instead, the first field without one panics.
  - L49: `field.bytes().await` returns `Err` on body read errors or when the field exceeds configured limits — panic.
  - L55: `std::fs::write` returns `Err` on permission denied, ENOSPC, EISDIR (e.g., filename `"."` or `""` after sanitization), invalid path, ENOTDIR (intermediate not a directory), etc. — panic.
- Why it matters: Panics in async handlers are observable as 500s but more importantly poison spans, leak partial writes, and on some axum/tower configurations crash the worker or spam logs. The design explicitly requires "fail gracefully on malformed input"; a panic is the opposite. A trivial DoS: any client sending a non-file form field crashes the request.
- Source-of-truth reference: Design — "Should fail gracefully on malformed input."
- Proposed fix: Return `Result<Json<Value>, (StatusCode, Json<Value>)>`. Replace each `unwrap` with `?` after mapping to a typed error; skip fields where `file_name()` is `None` (per design: "for each field with a filename"); return 400 on multipart errors, 413 on size limit, 500 with a generic body on I/O errors (logged with detail server-side).

**H2. No upload size limit — unbounded memory and disk consumption per request.**
- Citation: `api/handlers/upload.rs:49` — `let data = field.bytes().await.unwrap();`
- Problem: `field.bytes()` buffers the entire field in memory before writing. There is no per-field limit, no per-request limit, and no streaming. A single request can OOM the process; many concurrent requests trivially do.
- Why it matters: Production resource leak / DoS under common load; arguably a design violation since "fail gracefully on malformed input" implies bounded behavior on adversarial input.
- Source-of-truth reference: axum `Multipart` docs note no built-in body limit; users must set `DefaultBodyLimit` or use `field.chunk()` for streaming. Design implicitly forbids unbounded buffering on a public endpoint.
- Proposed fix: Stream with `field.chunk().await` into the file with `tokio::fs::File`/`BufWriter`, enforce a per-field byte cap, and apply `axum::extract::DefaultBodyLimit::max(N)` at router level.

**H3. Synchronous filesystem I/O in an async handler blocks the runtime.**
- Citation: `api/handlers/upload.rs:55` — `std::fs::write(&path, data).unwrap();`
- Problem: `std::fs::write` is blocking. Inside a Tokio worker thread it stalls all other tasks scheduled on that worker for the duration of the write. With slow disks, NFS, or large uploads, this directly degrades tail latency for unrelated requests.
- Why it matters: Silent performance degradation; under load, request throughput collapses. Borderline High because it is a foreseeable production failure mode rather than a correctness bug.
- Source-of-truth reference: Tokio docs — blocking calls must use `tokio::fs` or `spawn_blocking`.
- Proposed fix: Use `tokio::fs::File` with async writes, or wrap the write in `tokio::task::spawn_blocking`.

**H4. Files overwrite silently — no `create_new`, no collision policy.**
- Citation: `api/handlers/upload.rs:55`
- Problem: `std::fs::write` truncates and replaces any existing file at the target path. Two clients uploading `report.pdf` race; one wins, the other's data is lost with no indication. Combined with C2, this becomes an arbitrary-overwrite primitive.
- Why it matters: Silent data inconsistency; design says "writes the bytes to `/uploads/<filename>`" but does not authorize overwriting existing files. Even if intentional, it should be explicit.
- Source-of-truth reference: Design ambiguity resolved conservatively in favor of no-overwrite.
- Proposed fix: Use `OpenOptions::new().write(true).create_new(true)` and return 409 Conflict on `ErrorKind::AlreadyExists`, or generate server-side unique names (UUID) and return them.

### Medium

**M1. Empty / dot-only filenames produce wrong target paths.**
- Citation: `api/handlers/upload.rs:52-53`
- Problem: After `replace("..", "")`:
  - `".."` → `""` → `PathBuf::from("/uploads").join("")` → `/uploads/` → `fs::write` returns EISDIR — panic via L55.
  - `"."` is unchanged → `/uploads/.` → write to the directory itself — EISDIR — panic.
  - `"...."` → `""` (one pass removes both `..` substrings non-overlapping? actually `replace` is non-overlapping left-to-right, so `"...."` → `""`) → same as above.
- Why it matters: Adversarial-input crash; missing validation the design implies.
- Source-of-truth reference: Design — must accept fields with a filename and either write the file or fail gracefully.
- Proposed fix: Reject empty / `.` / `..` / whitespace-only filenames with 400.

**M2. Filename character set is unconstrained — control characters, slashes, separators reach the filesystem.**
- Citation: `api/handlers/upload.rs:48, 52`
- Problem: `field.file_name()` returns whatever the client sent in the `Content-Disposition` filename parameter. Newlines, NUL, leading dots (hidden files), spaces, or names like `.htaccess`, `.bashrc`, `web.config` are accepted. On case-insensitive filesystems, `Foo.txt` and `FOO.TXT` collide.
- Why it matters: Filesystem pollution, hidden-file creation, web-server config injection if `/uploads` is served, log-injection via newlines in filenames printed downstream.
- Source-of-truth reference: Design implies a safe, constrained mapping from filename to path.
- Proposed fix: Whitelist `[A-Za-z0-9._-]` (or generate names server-side) and cap length (e.g. 255 bytes after UTF-8 encoding, allowing for filesystem limits).

**M3. Always returns `{status:'ok'}` even after partial failure or on no-op.**
- Citation: `api/handlers/upload.rs:46-58`
- Problem: Because errors panic rather than propagate, the success response is the only non-panic path. After fixing H1 (returning errors), there is still a logic gap: a request with zero filename-bearing fields would return `ok` having written nothing — likely not intended. Also, no list of written files is returned, so clients cannot reconcile.
- Why it matters: Unclear success semantics; clients may assume a write happened when it did not.
- Source-of-truth reference: Design — return `{status:'ok'}` "on success." Success of *what* is undefined; a stricter contract is needed.
- Proposed fix: Return `{status:'ok', files:[…]}` listing the written filenames, and 400 if the request contained no file fields.

**M4. No `Content-Type` or extension validation.**
- Citation: `api/handlers/upload.rs:46-58`
- Problem: Accepts any bytes under any name. If `/uploads` is later served statically, this is XSS / drive-by; if scanned, this is malware staging.
- Why it matters: Missing validation the design implies for a public-facing upload endpoint, even though the design does not enumerate it.
- Source-of-truth reference: Reasonable interpretation of "fail gracefully on malformed input."
- Proposed fix: Validate against an allowlist of MIME types and/or extensions appropriate to the application; document the policy.

**M5. Race in directory existence — `/uploads` is assumed to exist with correct permissions.**
- Citation: `api/handlers/upload.rs:53-55`
- Problem: If `/uploads` does not exist or is not writable, every request panics at L55. There is no startup check, no `create_dir_all`.
- Why it matters: Operational fragility; first-deploy crash loop.
- Source-of-truth reference: Design treats `/uploads` as a precondition without specifying who creates it.
- Proposed fix: Verify (and optionally create with restrictive mode) at handler-construction time; surface a typed startup error.

### Low

**L1. `PathBuf::from("/uploads")` hardcoded — not configurable, not testable.**
- Citation: `api/handlers/upload.rs:53`
- Problem: The upload root is a literal. Tests cannot redirect it to a tempdir without filesystem mocking; environments with `/uploads` mounted differently cannot be supported.
- Proposed fix: Inject the upload root via handler state (`State<UploadConfig>`).

**L2. No tracing / structured logging.**
- Citation: `api/handlers/upload.rs:46-58`
- Problem: No `tracing::info!`/`error!` spans around field iteration or writes. Failures will be invisible.
- Proposed fix: Add `#[tracing::instrument(skip_all)]` and log per-field outcomes (without logging filenames verbatim — see M2 log-injection).

**L3. `serde_json::json!` allocation on the hot path.**
- Citation: `api/handlers/upload.rs:57`
- Problem: Minor: a `'static` `&str` body or a typed `serde::Serialize` struct avoids per-request allocation and gives a stable schema.
- Proposed fix: Define `#[derive(Serialize)] struct UploadResponse { status: &'static str }`.

**L4. Function signature returns `Json<serde_json::Value>` only — no error type.**
- Citation: `api/handlers/upload.rs:46`
- Problem: Forces panic-or-200; precludes idiomatic `?`-based error handling.
- Proposed fix: `-> Result<Json<UploadResponse>, ApiError>` where `ApiError: IntoResponse`.

**L5. `to_string()` on filename allocates even when it will be rejected.**
- Citation: `api/handlers/upload.rs:48`
- Minor; allocate after validation.

**L6. No documentation comment on the public handler.**
- Citation: `api/handlers/upload.rs:46`
- Add `///` doc explaining the contract, limits, and rejected inputs.
