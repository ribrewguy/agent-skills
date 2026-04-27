Review Scope: `api/handlers/upload.rs` new upload handler  
Process Used: Static review from provided patch only; no tools or filesystem access used  
Execution Context: Closed-context evaluation package  
Integration Target: Axum multipart upload handler  
Governing Documents: File upload handler acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-27

**High Findings**

**api/handlers/upload.rs:10**  
Problem: Path traversal protection is incomplete. `filename.replace("..", "")` does not guarantee the final path stays under `/uploads`. In Rust, `PathBuf::join` with an absolute child path can discard the `/uploads` prefix, so a filename like `/tmp/evil` or `//tmp/evil` may write outside `/uploads`.

Why it matters: This violates the explicit requirement that `/uploads` is the only allowed write target and creates a significant arbitrary file write risk.

Source-of-truth reference: Acceptance criteria: “MUST prevent path traversal” and “The handler must reject any input that would write outside that directory.”

Proposed fix: Reject filenames containing path separators, absolute paths, parent-directory components, empty names, or platform-specific prefixes. Build the candidate path under `/uploads`, canonicalize or otherwise validate the final parent/target relationship, and reject anything that is not strictly inside `/uploads`.

**Medium Findings**

**api/handlers/upload.rs:7**  
Problem: `multipart.next_field().await.unwrap()` panics on malformed multipart input instead of returning a graceful error response.

Why it matters: The design says malformed input should fail gracefully. A panic turns bad client input into an uncontrolled server error path.

Source-of-truth reference: Acceptance criteria: “Should fail gracefully on malformed input.”

Proposed fix: Change the return type to something like `Result<Json<Value>, StatusCode>` or a custom error response, and map multipart parsing errors to a controlled `400 Bad Request`.

**api/handlers/upload.rs:8**  
Problem: `field.file_name().unwrap()` panics for fields without a filename.

Why it matters: The design says to write bytes “for each field with a filename,” which implies fields without filenames should be skipped or rejected gracefully, not panic.

Source-of-truth reference: Acceptance criteria: “For each field with a filename, writes the bytes…”

Proposed fix: Use `if let Some(filename) = field.file_name()` and skip non-file fields, or return a controlled validation error if non-file fields are not allowed.

**api/handlers/upload.rs:9**  
Problem: `field.bytes().await.unwrap()` panics if reading a multipart field fails.

Why it matters: Malformed uploads, interrupted connections, or oversized payload handling errors can trigger an uncontrolled error instead of a graceful response.

Source-of-truth reference: Acceptance criteria: “Should fail gracefully on malformed input.”

Proposed fix: Propagate the read error into a controlled error response.

**api/handlers/upload.rs:12**  
Problem: `std::fs::write(&path, data).unwrap()` panics on filesystem errors such as missing `/uploads`, permission failure, invalid filename, or disk errors.

Why it matters: Expected operational failures should not panic the handler. The caller should receive a controlled failure response.

Source-of-truth reference: Acceptance criteria: “Returns `{ status: 'ok' }` on success” and “Should fail gracefully on malformed input.”

Proposed fix: Handle write errors explicitly and return an appropriate non-OK response, such as `500` for server-side storage failure or `400` for invalid filename/input.

**Low Findings**

No Low findings.
