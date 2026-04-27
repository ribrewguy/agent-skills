**Review Scope:** `api/handlers/upload.rs` upload handler implementation  
**Process Used:** Closed-context second-pass review against supplied design and acceptance criteria  
**Execution Context:** No commands run; no filesystem reads; review based only on provided package  
**Integration Target:** Axum multipart upload endpoint  
**Governing Documents:** Design / Acceptance criteria: File upload handler  
**Reviewer:** Codex cross-vendor reviewer  
**Severity Scale:** Critical, High, Medium, Low as defined in request  
**Date:** 2026-04-26

## Findings

### Critical

None.

### High

**H-1: Absolute filenames can escape `/uploads`**  
**Citation:** `api/handlers/upload.rs:12`  
**Problem:** `PathBuf::from("/uploads").join(safe_name)` does not guarantee the result stays under `/uploads`. In Rust, joining an absolute path replaces the base path. A filename like `/tmp/owned` or `/etc/passwd` would produce an absolute path outside `/uploads`.  
**Why it matters:** This directly violates the design requirement: “MUST prevent path traversal” and “`/uploads` is the only allowed write target.”  
**Source of truth:** Design / Acceptance criteria: handler must reject any input that would write outside `/uploads`.  
**Proposed fix:** Reject absolute paths and path components before writing. Parse with `Path::new(filename)`, require exactly one normal filename component, reject prefixes/root dirs/parent dirs, and verify the final path starts with canonical `/uploads`.

**H-2: Path traversal filtering is incomplete and unsafe**  
**Citation:** `api/handlers/upload.rs:11`  
**Problem:** `filename.replace("..", "")` is not a valid traversal defense. It mutates attacker input instead of rejecting it and does not validate path structure. Inputs containing separators, absolute paths, platform-specific separators, encoded traversal forms, or crafted names can still produce unintended paths or surprising writes.  
**Why it matters:** The design requires rejection of unsafe input, not best-effort sanitization. Silent mutation can also cause filename collisions, e.g. distinct attacker-controlled names collapsing to the same output name.  
**Source of truth:** Design / Acceptance criteria: “must reject any input that would write outside that directory.”  
**Proposed fix:** Do not transform traversal strings. Reject any filename whose parsed components are not a single safe basename. Consider allowing only `Component::Normal` with no `/`, `\`, root, prefix, or parent components.

**H-3: Symlink writes can target files outside `/uploads`**  
**Citation:** `api/handlers/upload.rs:14`  
**Problem:** The code writes directly to `/uploads/<safe_name>` without protecting against symlinks. If `/uploads/name` is a symlink to a path outside `/uploads`, `std::fs::write` follows it.  
**Why it matters:** The acceptance criteria say `/uploads` is the only allowed write target. Following symlinks can violate that even when the lexical path appears to start with `/uploads`.  
**Source of truth:** Design / Acceptance criteria: `/uploads` is the only allowed write target.  
**Proposed fix:** Open files with options that prevent symlink following where supported, write into a controlled upload directory with strict ownership/permissions, and validate canonical parent paths. Prefer creating new files safely rather than overwriting arbitrary existing paths.

### Medium

**M-1: Malformed multipart input panics instead of failing gracefully**  
**Citation:** `api/handlers/upload.rs:6`  
**Problem:** `multipart.next_field().await.unwrap()` panics on multipart parsing errors.  
**Why it matters:** The design says malformed input should fail gracefully. A panic can become a 500 response, terminate request handling, or expose unstable behavior under malformed uploads.  
**Source of truth:** Design / Acceptance criteria: “Should fail gracefully on malformed input.”  
**Proposed fix:** Return `Result<Json<_>, StatusCode>` or a structured error response and map multipart parsing errors to a graceful `400 Bad Request`.

**M-2: Fields without filenames panic, but the design says to process only fields with filenames**  
**Citation:** `api/handlers/upload.rs:7`  
**Problem:** `field.file_name().unwrap()` panics for normal multipart form fields that do not have a filename.  
**Why it matters:** The design says “For each field with a filename,” which implies fields without filenames should be skipped, not treated as fatal malformed input.  
**Source of truth:** Design / Acceptance criteria: process each field with a filename.  
**Proposed fix:** Use `if let Some(filename) = field.file_name()` and skip non-file fields.

**M-3: Body read and filesystem errors panic instead of returning controlled failures**  
**Citation:** `api/handlers/upload.rs:8`, `api/handlers/upload.rs:14`  
**Problem:** `field.bytes().await.unwrap()` and `std::fs::write(&path, data).unwrap()` panic on read errors, permission errors, missing `/uploads`, disk-full errors, and invalid filenames.  
**Why it matters:** These are expected operational failure modes for uploads. Panics violate graceful failure behavior and make the handler brittle under common error conditions.  
**Source of truth:** Design / Acceptance criteria: return ok on success and fail gracefully on malformed input.  
**Proposed fix:** Propagate errors explicitly and return appropriate HTTP status codes, such as `400` for bad input and `500` or `507` for storage failures.

**M-4: Blocking filesystem write inside async handler can stall the runtime**  
**Citation:** `api/handlers/upload.rs:14`  
**Problem:** `std::fs::write` performs blocking disk I/O inside an async Axum handler.  
**Why it matters:** Under concurrent upload load, blocking writes can occupy async runtime worker threads and degrade unrelated requests.  
**Source of truth:** Design / Acceptance criteria: upload handler for an async Axum API.  
**Proposed fix:** Use `tokio::fs::write`, stream to a file asynchronously, or move blocking file work to `spawn_blocking`.

### Low

None.
