Review Scope: `api/handlers/upload.rs` new upload handler  
Process Used: Closed-context structured code review; no tools or filesystem reads used  
Execution Context: Multipart upload handler for Axum  
Integration Target: `/uploads`-only file write behavior  
Governing Documents: Design / Acceptance criteria in review package  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: 2026-04-27

## Critical Findings

None.

## High Findings

### HIGH-1: Path traversal prevention is incomplete

Citation: `api/handlers/upload.rs:11`

Problem statement: The implementation removes `..` substrings, then joins the result onto `/uploads`. This does not reliably confine writes to `/uploads`. For example, an absolute filename such as `/tmp/pwned` can cause `PathBuf::join` to ignore the `/uploads` base on Unix-like systems. Filenames containing path separators can also create unintended nested paths.

Why it matters: The acceptance criteria explicitly require that nothing write outside `/uploads` and that inputs attempting to do so be rejected. This implementation can still write outside the allowed directory.

Source-of-truth reference: Design: “MUST prevent path traversal: nothing should write outside `/uploads`” and “must reject any input that would write outside that directory.”

Proposed fix: Reject filenames that are absolute paths, contain path separators, contain parent-directory components, or otherwise fail strict basename validation. Prefer parsing with `Path::new(filename).components()` and only accepting a single `Component::Normal` filename. After constructing the path, verify it remains under `/uploads` before writing.

## Medium Findings

### MEDIUM-1: Malformed multipart input can panic instead of failing gracefully

Citation: `api/handlers/upload.rs:6`

Problem statement: `multipart.next_field().await.unwrap()` panics on multipart parsing errors.

Why it matters: The handler is required to fail gracefully on malformed input. A panic can turn a bad request into a server error and may disrupt request handling.

Source-of-truth reference: Design: “Should fail gracefully on malformed input.”

Proposed fix: Return a `Result<impl IntoResponse, StatusCode>` or equivalent error response type, map multipart parsing errors to `400 Bad Request`, and avoid `unwrap()`.

### MEDIUM-2: Non-file multipart fields panic instead of being skipped

Citation: `api/handlers/upload.rs:7`

Problem statement: `field.file_name().unwrap()` panics when a multipart field has no filename.

Why it matters: The requirement says “For each field with a filename,” which implies fields without filenames should be ignored or handled gracefully, not crash the handler.

Source-of-truth reference: Design: “For each field with a filename, writes the bytes to `/uploads/<filename>`.”

Proposed fix: Use `if let Some(filename) = field.file_name()` and skip fields without filenames.

### MEDIUM-3: Upload read and file write failures panic

Citation: `api/handlers/upload.rs:8` and `api/handlers/upload.rs:14`

Problem statement: `field.bytes().await.unwrap()` and `std::fs::write(&path, data).unwrap()` panic on read or write errors.

Why it matters: Network/client errors, invalid multipart bodies, missing `/uploads`, permission failures, and disk errors should produce controlled error responses rather than panics.

Source-of-truth reference: Design: “Should fail gracefully on malformed input.”

Proposed fix: Propagate these errors through the handler’s return type and map them to appropriate responses, such as `400 Bad Request` for malformed uploads and `500 Internal Server Error` for server-side write failures.

### MEDIUM-4: Blocking filesystem I/O is used inside an async handler

Citation: `api/handlers/upload.rs:14`

Problem statement: `std::fs::write` performs blocking filesystem I/O inside an async Axum handler.

Why it matters: Under load or with large files, blocking the async runtime worker thread can degrade request handling for unrelated requests.

Source-of-truth reference: General async service correctness; acceptance criteria imply a production upload handler.

Proposed fix: Use `tokio::fs::write` or move blocking writes to `tokio::task::spawn_blocking`.

## Low Findings

None.
