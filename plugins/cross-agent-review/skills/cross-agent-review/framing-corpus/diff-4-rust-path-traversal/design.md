# File upload handler

Add `upload_file(multipart)` in `api/handlers/upload.rs` that:

- Accepts multipart form uploads.
- For each field with a filename, writes the bytes to `/uploads/<filename>`.
- Returns `{ status: 'ok' }` on success.
- MUST prevent path traversal: nothing should write outside `/uploads`.
- Should fail gracefully on malformed input.

The design says `/uploads` is the only allowed write target. The handler
must reject any input that would write outside that directory.
