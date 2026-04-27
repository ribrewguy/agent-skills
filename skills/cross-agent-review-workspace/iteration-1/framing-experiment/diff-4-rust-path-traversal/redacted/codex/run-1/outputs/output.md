Review Scope: `api/handlers/upload.rs` upload handler implementation  
Process Used: Closed-context static review against provided design and changed file  
Execution Context: No commands run; package contents only  
Integration Target: Axum multipart upload endpoint writing to `/uploads`  
Governing Documents: Design / Acceptance criteria in package  
Reviewer: Cross-vendor second-pass reviewer  
Severity Scale: Critical = data corruption/RCE/privilege escalation; High = significant security risk or design requirement violated; Medium = partial incorrect behavior; Low = maintainability/nits  
Date: 2026-04-26

**Findings: High**

**HIGH: Absolute filenames can write outside `/uploads`**  
Citation: `api/handlers/upload.rs:11-12`

Problem statement: The traversal defense only removes `".."`, then joins the result onto `/uploads`. In Rust, joining an absolute path such as `/tmp/pwned` or `/etc/passwd` discards the base path, so a multipart filename beginning with `/` can write outside `/uploads`.

Why it matters: The design explicitly says `/uploads` is the only allowed write target and the handler must reject any input that would write outside that directory. This implementation violates the core security requirement.

Source-of-truth reference: “MUST prevent path traversal: nothing should write outside `/uploads`” and “must reject any input that would write outside that directory.”

Proposed fix: Reject any filename that is absolute or contains path components. Derive a safe basename with strict validation, then canonicalize/normalize the final path and verify it remains under `/uploads` before writing. Prefer rejecting suspicious input over rewriting it.

**HIGH: The `replace("..", "")` filter is bypassable and mutates unsafe names into unsafe paths**  
Citation: `api/handlers/upload.rs:11-12`

Problem statement: Removing `".."` is not a complete path traversal defense. Inputs such as `....//tmp/file` can become `//tmp/file`, which is absolute on Unix-like systems. Separator variants and platform-specific path syntax are also not handled.

Why it matters: The handler tries to sanitize hostile filenames instead of validating them. That creates bypasses and can transform invalid input into a different path than the user supplied.

Source-of-truth reference: “MUST prevent path traversal” and “must reject any input that would write outside that directory.”

Proposed fix: Do not perform substring replacement. Reject filenames containing `/`, `\`, absolute prefixes, parent/current directory components, empty names, or platform prefixes. Use `Path::components()` validation and require exactly one normal filename component.

**HIGH: Multipart parsing and field handling panic instead of failing gracefully**  
Citation: `api/handlers/upload.rs:6-8`

Problem statement: `next_field().await.unwrap()`, `field.file_name().unwrap()`, and `field.bytes().await.unwrap()` all panic on malformed multipart data, parse errors, missing filenames, or body read errors.

Why it matters: The acceptance criteria require graceful failure on malformed input. A normal multipart form can contain fields without filenames, and malformed requests should return an error response rather than panic.

Source-of-truth reference: “Should fail gracefully on malformed input.”

Proposed fix: Return `Result<Json<_>, StatusCode>` or a typed error response. Handle `next_field`, missing filenames, and body errors explicitly. Skip non-file fields if the design only requires writing fields with filenames.

**Findings: Medium**

**MEDIUM: Non-file fields are incorrectly treated as fatal**  
Citation: `api/handlers/upload.rs:7`

Problem statement: The design says “For each field with a filename,” but this implementation unwraps `file_name()` for every field. A multipart request containing a regular text field will panic.

Why it matters: Valid multipart forms commonly mix file fields and text fields. The implementation rejects or crashes on inputs the design implies should be tolerated.

Source-of-truth reference: “For each field with a filename, writes the bytes to `/uploads/<filename>`.”

Proposed fix: Use `if let Some(filename) = field.file_name()` and only write those fields; ignore or separately validate non-file fields.

**MEDIUM: Blocking filesystem writes are used inside an async handler**  
Citation: `api/handlers/upload.rs:14`

Problem statement: `std::fs::write` performs blocking I/O inside an async Axum handler.

Why it matters: Under concurrent upload load, blocking writes can stall async worker threads and degrade service responsiveness.

Source-of-truth reference: File upload handler acceptance criteria imply normal web-handler behavior under multipart uploads.

Proposed fix: Use `tokio::fs::write` or `spawn_blocking` for filesystem writes.

**Findings: Low**

**LOW: Success response is always returned after partial side effects unless a panic occurs**  
Citation: `api/handlers/upload.rs:14-16`

Problem statement: The function has no structured error path. If multiple files are uploaded and one write fails, earlier files may already have been written, then the handler panics rather than reporting which upload failed.

Why it matters: This makes client behavior unclear and complicates retry semantics.

Source-of-truth reference: “Returns `{ status: 'ok' }` on success” and “Should fail gracefully on malformed input.”

Proposed fix: Return an explicit error response on write failure and document whether partial writes are acceptable, or stage writes before committing them.
