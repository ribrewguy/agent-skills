**Review Scope:** `api/handlers/upload.rs` new upload handler  
**Process Used:** Structured code review from supplied package only  
**Execution Context:** Closed-context review; no commands or file reads performed  
**Integration Target:** Axum multipart upload handler  
**Governing Documents:** File upload handler design / acceptance criteria  
**Reviewer:** Codex  
**Severity Scale:** Critical / High / Medium / Low as defined in request  
**Date:** 2026-04-26

**Findings - Critical**

**api/handlers/upload.rs:11**  
Problem statement: Path safety is not actually enforced. `filename.replace("..", "")` does not prevent absolute paths; in Rust, joining an absolute child path can discard the `/uploads` base, so a filename like `/etc/passwd` can target `/etc/passwd` instead of `/uploads/...`.

Why it matters: This violates the core requirement that nothing write outside `/uploads` and can become arbitrary file overwrite wherever the process has permissions.

Source of truth: Acceptance criteria: “MUST prevent path traversal: nothing should write outside `/uploads`” and “`/uploads` is the only allowed write target.”

Proposed fix: Reject filenames containing path separators or absolute paths, derive a basename-only filename, join it under `/uploads`, then verify the resolved target remains under `/uploads`. Prefer safe creation semantics that avoid symlink traversal if `/uploads` may contain attacker-controlled entries.

**Findings - High**

**api/handlers/upload.rs:14**  
Problem statement: `std::fs::write(&path, data)` follows symlinks. If `/uploads/safe_name` is a symlink to a path outside `/uploads`, the handler can write outside the allowed directory even if the filename itself looks safe.

Why it matters: The design prohibits any write outside `/uploads`, not only syntactic `../` traversal.

Source of truth: Acceptance criteria: “The handler must reject any input that would write outside that directory.”

Proposed fix: Use filesystem APIs that prevent following final-path symlinks where available, or create files via a directory handle rooted at `/uploads` with no-follow/openat-style constraints. Also reject existing symlink targets before writing.

**Findings - Medium**

**api/handlers/upload.rs:6**  
Problem statement: `multipart.next_field().await.unwrap()` panics on malformed multipart input.

Why it matters: The handler should fail gracefully on malformed input; a panic can produce a 500 and may disrupt request handling depending on runtime configuration.

Source of truth: Acceptance criteria: “Should fail gracefully on malformed input.”

Proposed fix: Return a `Result` response type and map multipart errors to an appropriate client error, such as `400 Bad Request`.

**api/handlers/upload.rs:7**  
Problem statement: `field.file_name().unwrap()` panics for fields without filenames, but the design says to write “for each field with a filename,” implying fields without filenames should be skipped.

Why it matters: Valid multipart forms often contain regular text fields. This implementation turns those inputs into panics instead of ignoring non-file fields.

Source of truth: Acceptance criteria: “For each field with a filename, writes the bytes…”

Proposed fix: Use `if let Some(filename) = field.file_name()` and continue when absent.

**api/handlers/upload.rs:8**  
Problem statement: `field.bytes().await.unwrap()` panics if reading the uploaded field fails.

Why it matters: Upload read failures are malformed or interrupted input cases and should be handled gracefully.

Source of truth: Acceptance criteria: “Should fail gracefully on malformed input.”

Proposed fix: Propagate the error into a structured failure response instead of unwrapping.

**api/handlers/upload.rs:14**  
Problem statement: `std::fs::write(&path, data).unwrap()` panics on normal filesystem errors such as missing `/uploads`, permission denied, filename too long, directory target, or disk full.

Why it matters: These are expected operational failures; the handler should return an error response instead of panicking.

Source of truth: Acceptance criteria: “Returns `{ status: 'ok' }` on success” and “Should fail gracefully…”

Proposed fix: Return `Result<Json<_>, StatusCode>` or a custom error response and map write failures to appropriate server/client errors.
