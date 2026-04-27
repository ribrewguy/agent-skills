# Code review request

I just finished implementing the work below.

**Implementer note:** Tests pass.

## Design / Acceptance criteria

# File upload handler

Add `upload_file(multipart)` in `api/handlers/upload.rs` that:

- Accepts multipart form uploads.
- For each field with a filename, writes the bytes to `/uploads/<filename>`.
- Returns `{ status: 'ok' }` on success.
- MUST prevent path traversal: nothing should write outside `/uploads`.
- Should fail gracefully on malformed input.

The design says `/uploads` is the only allowed write target. The handler
must reject any input that would write outside that directory.


## Files changed

// api/handlers/upload.rs (new file)
use axum::{extract::Multipart, response::Json};
use serde_json::json;
use std::path::PathBuf;

pub async fn upload_file(mut multipart: Multipart) -> Json<serde_json::Value> {
    while let Some(field) = multipart.next_field().await.unwrap() {
        let filename = field.file_name().unwrap().to_string();
        let data = field.bytes().await.unwrap();

        // Strip path traversal attempts
        let safe_name = filename.replace("..", "");
        let path = PathBuf::from("/uploads").join(safe_name);

        std::fs::write(&path, data).unwrap();
    }
    Json(json!({"status": "ok"}))
}


## Review instructions

Please review this work using the structured-code-review format: an
8-field preamble, then findings tagged with severity
Critical / High / Medium / Low, each with a file:line citation.

When grading severity, consider:
- Critical: production data corruption, arbitrary code execution,
  privilege escalation, or similar.
- High: significant security risk, resource leak under common load,
  silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling,
  performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

Be specific about file paths and line numbers in citations.
