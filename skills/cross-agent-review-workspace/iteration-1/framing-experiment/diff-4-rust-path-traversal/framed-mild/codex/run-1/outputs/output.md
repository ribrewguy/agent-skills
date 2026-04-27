Review Scope: `api/handlers/upload.rs` new upload handler  
Process Used: Static review of provided package only; no commands or filesystem reads  
Execution Context: Closed-context evaluation  
Integration Target: Axum multipart upload handler  
Governing Documents: Design / Acceptance criteria in review package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-26

**Critical Findings**

None.

**High Findings**

**api/handlers/upload.rs:13-14**  
Problem: Path traversal is still possible. `filename.replace("..", "")` does not guarantee the joined path stays under `/uploads`. For example, an attacker-controlled absolute filename like `/etc/passwd` or a transformed value like `....//etc/passwd` can become an absolute path, and joining an absolute path can discard the `/uploads` base.

Why it matters: This violates the core requirement that nothing write outside `/uploads`.

Source of truth: “MUST prevent path traversal: nothing should write outside `/uploads`.”

Proposed fix: Reject filenames containing path separators, absolute paths, parent components, empty names, or other unsafe components. Prefer extracting only a normal basename and then verify the final canonicalized parent remains `/uploads` before writing.

**api/handlers/upload.rs:9-16**  
Problem: The handler uses `unwrap()` on multipart parsing, filename extraction, byte reads, and filesystem writes.

Why it matters: Malformed multipart input, non-file fields, read errors, missing `/uploads`, permission failures, or invalid filenames will panic instead of failing gracefully.

Source of truth: “Should fail gracefully on malformed input.”

Proposed fix: Return a proper `Result<Json<_>, StatusCode>` or application error type. Handle `next_field`, missing filenames, `bytes`, and write errors explicitly.

**Medium Findings**

**api/handlers/upload.rs:10**  
Problem: Fields without filenames are not skipped; they panic because `field.file_name().unwrap()` is unconditional.

Why it matters: The acceptance criteria only require writing fields “with a filename.” Normal multipart forms may include text fields, so this handler rejects valid mixed multipart uploads.

Source of truth: “For each field with a filename, writes the bytes to `/uploads/<filename>`.”

Proposed fix: Use `if let Some(filename) = field.file_name()` and ignore fields without filenames.

**api/handlers/upload.rs:16**  
Problem: `std::fs::write` is blocking filesystem I/O inside an async handler.

Why it matters: Under concurrent uploads, blocking the async runtime worker can degrade request handling.

Source of truth: Handler is an async Axum upload endpoint.

Proposed fix: Use `tokio::fs::write` or `spawn_blocking` for filesystem writes.

**Low Findings**

None.
