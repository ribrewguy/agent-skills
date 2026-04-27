Review Scope: `api/handlers/upload.rs` new upload handler  
Process Used: Closed-context manual review of supplied package only  
Execution Context: No commands, filesystem reads, or external lookup used  
Integration Target: File upload handler acceptance criteria  
Governing Documents: Design / Acceptance criteria in package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as provided  
Date: 2026-04-26  

**High Findings**

**H1: Path traversal protection is bypassable via absolute paths**  
Citation: `api/handlers/upload.rs:11` and `api/handlers/upload.rs:12`  

Problem statement: The handler only removes `".."` from the submitted filename before joining it with `/uploads`. In Rust, joining an absolute RHS path can discard the base path. For example, a filename like `../tmp/pwned` becomes `/tmp/pwned` after the replace, and `PathBuf::from("/uploads").join("/tmp/pwned")` targets `/tmp/pwned`, outside `/uploads`.

Why it matters: The design explicitly requires that nothing write outside `/uploads`. This implementation allows writes outside the allowed directory, which is a significant security risk and violates a MUST requirement.

Source-of-truth reference: “MUST prevent path traversal: nothing should write outside `/uploads`” and “The handler must reject any input that would write outside that directory.”

Proposed fix: Reject unsafe filenames instead of mutating them. Accept only a plain file name component, reject absolute paths, parent components, separators, empty names, and other non-normal filename components. Build the candidate path under `/uploads`, then verify the final normalized/canonical parent remains `/uploads` before writing.

**Medium Findings**

**M1: Malformed multipart input and non-file fields panic instead of failing gracefully**  
Citation: `api/handlers/upload.rs:6`, `api/handlers/upload.rs:7`, `api/handlers/upload.rs:8`, and `api/handlers/upload.rs:14`  

Problem statement: The handler uses `unwrap()` on multipart parsing, filename extraction, byte extraction, and filesystem writes. A malformed multipart body, a normal form field without a filename, a read error, or a write failure will panic.

Why it matters: The acceptance criteria require graceful failure on malformed input. Also, the design says to write “for each field with a filename,” which implies fields without filenames should be skipped or handled without crashing.

Source-of-truth reference: “For each field with a filename, writes the bytes…” and “Should fail gracefully on malformed input.”

Proposed fix: Change the handler to return a `Result<Json<_>, StatusCode>` or structured error response. Handle `next_field().await` and `field.bytes().await` errors explicitly, skip fields where `file_name()` is `None`, reject unsafe filenames with a client error, and return a server error for write failures.

**Low Findings**

No Low findings.
