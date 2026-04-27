**Review Scope:** `api/handlers/upload.rs` new upload handler  
**Process Used:** Closed-context structured code review; no tools or filesystem access used  
**Execution Context:** Axum async multipart upload handler  
**Integration Target:** `/uploads`-only file write endpoint  
**Governing Documents:** Provided design / acceptance criteria  
**Reviewer:** Codex  
**Severity Scale:** Critical, High, Medium, Low as defined in request  
**Date:** 2026-04-26

**High Findings**

**H1: Path traversal prevention is incomplete**  
Citation: `api/handlers/upload.rs:11-12`

Problem statement: The code attempts to make filenames safe with `filename.replace("..", "")`, then joins the result onto `/uploads`. This does not guarantee the final path remains under `/uploads`. Absolute filenames such as `/etc/passwd` are not changed by removing `..`, and path joining with an absolute path can escape the intended base directory.

Why it matters: The acceptance criteria explicitly require that nothing writes outside `/uploads`, and that inputs which would write outside that directory are rejected. This implementation can still write outside the allowed directory.

Source-of-truth reference: Design: “MUST prevent path traversal: nothing should write outside `/uploads`.” Also: “The handler must reject any input that would write outside that directory.”

Proposed fix: Reject unsafe filenames instead of sanitizing by substring replacement. Treat the filename as a single basename only: reject absolute paths, path separators, prefixes, parent components, empty names, and other non-normal components. Build the candidate path, canonicalize or otherwise validate its normalized parent relationship, and ensure it remains inside `/uploads` before writing.

**Medium Findings**

**M1: Malformed input and I/O errors panic instead of failing gracefully**  
Citation: `api/handlers/upload.rs:6-8`, `api/handlers/upload.rs:14`

Problem statement: The handler calls `unwrap()` on multipart parsing, filename extraction, byte reading, and file writing. Malformed multipart input, fields without filenames, read errors, missing `/uploads`, permission errors, or disk errors will panic the request handler.

Why it matters: The design says the handler should fail gracefully on malformed input. Panics are not graceful failures and may become denial-of-service behavior depending on runtime configuration.

Source-of-truth reference: Acceptance criteria: “Should fail gracefully on malformed input.”

Proposed fix: Return a `Result` from the handler with appropriate HTTP errors, for example `Result<Json<Value>, StatusCode>` or a project-specific error type. Use `?` on fallible operations, skip fields without filenames if intended, and return `400 Bad Request` for malformed multipart or unsafe filenames.

**M2: Fields without filenames are handled incorrectly**  
Citation: `api/handlers/upload.rs:7`

Problem statement: The acceptance criteria say “For each field with a filename,” but the implementation unwraps `field.file_name()`. Multipart fields without filenames will panic rather than being ignored or handled as non-file form fields.

Why it matters: Ordinary multipart forms often contain text fields alongside file fields. This makes valid mixed multipart input fail unexpectedly.

Source-of-truth reference: Acceptance criteria: “For each field with a filename, writes the bytes to `/uploads/<filename>`.”

Proposed fix: Use `if let Some(filename) = field.file_name()` and only write file fields. Continue past fields without filenames unless the API contract requires rejecting them.

**M3: Blocking filesystem write is used inside an async handler**  
Citation: `api/handlers/upload.rs:14`

Problem statement: `std::fs::write` performs blocking filesystem I/O inside an async Axum handler.

Why it matters: Under load or with slow storage, this can block async runtime worker threads and degrade unrelated requests.

Source-of-truth reference: Execution context: Axum async request handler.

Proposed fix: Use `tokio::fs::write` or offload blocking file I/O with `spawn_blocking`, depending on the project’s filesystem policy.

**Low Findings**

No Low-severity findings.
