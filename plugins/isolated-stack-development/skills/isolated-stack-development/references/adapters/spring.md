# Adapter: spring

How a Spring Boot service in `apps[]` binds to an isolated stack. Java repos
have no `.env` convention, so this adapter differs structurally from the
others — the declaration's `env` field points at a properties/YAML file
instead.

## Config wiring

Spring resolves configuration through a precedence chain (command line >
OS env > profile-specific `application-<profile>.yml` > `application.yml`).
Use a dedicated profile for isolation (e.g. `local-isolated`) and put every
stack-pointing value in that profile's file, gitignored or generated per
worktree:

- `spring.datasource.url` / username / password → the isolated stack's
  database (from `supabase status -o env`; prefer `127.0.0.1` in the JDBC URL).
- `server.port` → the allocated app port.
- Any Supabase URL / key properties the app defines.

Activate with `SPRING_PROFILES_ACTIVE=local-isolated` **scoped to the launch
command**, not exported — an exported profile or an exported
`SPRING_DATASOURCE_URL` shadows every worktree, and OS env outranks the
profile file in Spring's precedence, so a stale export silently wins. That
precedence inversion is this adapter's version of the copied-env audit: check
the *effective* config (`/actuator/env` if enabled, or the boot log's
datasource line), not the file you edited.

## Partial-set refusal

Spring happily boots with a default datasource (or an embedded H2) when
properties are missing, which is exactly the silent fallback the core skill
forbids. Fail fast: make the isolated profile set no defaults, so a missing
property aborts the boot rather than pointing at the wrong database.

## Start and health-check

- Start: the repo's run task (`./gradlew bootRun` / `./mvnw spring-boot:run`)
  with the profile scoped inline, from the worktree, same invocation as the
  `cd`.
- Health: `/actuator/health` on the **allocated** port if actuator is present,
  otherwise the boot log's `Tomcat started on port` line. Resolve the probe
  port from the same profile file the app boots with.
- Identify the process by argv (the main class or the jar path), never by
  port.
