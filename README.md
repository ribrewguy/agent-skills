# agent-skills

Claude Code skills authored and maintained by [@ribrewguy](https://github.com/ribrewguy). Each skill is designed, evaluated, and iterated with the [skill-creator](https://github.com/anthropics/skills) workflow, and ships with a reproducible eval set so the skill's expected output is documented in verifiable terms — not just prose.

## Skills in this repo

| Skill | Purpose |
|---|---|
| [`rest-api-design`](skills/rest-api-design/SKILL.md) | Design and review HTTP REST APIs. Covers resource-oriented URLs, HTTP method semantics (PATCH for state transitions — not sub-resource verbs), status codes, domain-expressive error codes that don't echo HTTP status, flat error envelopes, cursor/offset/page pagination, idempotency keys on side-effectful POSTs, content-type negotiation (NDJSON / SSE / vendor media types), patch format selection (plain JSON / `merge-patch+json` / `json-patch+json`), typed contracts across TypeScript / Python / Go / Rust, and reviewer-grade output conventions with severity tagging. |

## Install

### Option A — as a Claude Code plugin (recommended)

From inside Claude Code:

```bash
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
```

The first command registers this repo as a plugin marketplace. The second installs the `rest-api-design` plugin from it. After installation the skill is invokable as `/rest-api-design` and triggers automatically when a task matches its description.

To get updates when the repo changes:

```bash
/plugin marketplace update ribrewguy-skills
```

Auto-update on session start is opt-in per-marketplace — toggle it via the `/plugin` UI if you want it.

### Option B — manual symlink (no plugin manifest needed)

If you manage skills yourself (e.g., you have a central `~/.agents/skills/` that multiple AI tools symlink into), you can skip the plugin layer and point `~/.claude/skills/` directly at the repo:

```bash
git clone git@github.com:ribrewguy/agent-skills.git ~/Projects/agent-skills
ln -s ~/Projects/agent-skills/skills/rest-api-design ~/.claude/skills/rest-api-design
```

Or, if you keep a canonical skills home outside `~/.claude/`:

```bash
ln -s ~/Projects/agent-skills/skills/rest-api-design ~/.agents/skills/rest-api-design
ln -s ../../.agents/skills/rest-api-design ~/.claude/skills/rest-api-design
```

Claude Code watches `~/.claude/skills/` for changes during a session, so the skill becomes available without a restart (first-time creation of `~/.claude/skills/` does need a new session).

## Verify the install

In a new Claude Code session, run `/help` and look under Skills — `rest-api-design` should appear. Or just drop a prompt that should trigger it:

> "Audit this endpoint: `POST /api/createOrder` returning `200 { order_id: '...' }`. What's wrong?"

If the skill is active, the output will catch the verb-in-URL, the wrong success status, the missing `Location` header, and the snake_case response key — each tagged with severity.

## Using the skill

Typical prompts that invoke it:

- *"Design the HTTP contract for a `<resource>` API — list with search/filter/sort, create, update, delete. Include typed request/response."*
- *"Review this PR against our REST conventions. List every violation with severity, and propose the corrected alternative."*
- *"Is `POST /api/payments` ready to ship? Here's the draft."*
- *"Should this endpoint use PATCH or a sub-resource action?"*

The skill produces reviewer-grade output: violations are tagged `Critical` / `High` / `Medium` / `Low`, issues outside the REST surface (crypto, auth internals, file layout) are explicitly flagged as out-of-lane and deferred to the appropriate neighbor skill, and the reasoning is argued directly rather than cited from the skill's own rulebook.

## Development

### Editing the skill

The skill lives at [`skills/rest-api-design/SKILL.md`](skills/rest-api-design/SKILL.md). If you installed via Option B (symlink), edits in the repo flow through to Claude Code immediately — `git pull` is the update path. If you installed via Option A (plugin), run `/plugin marketplace update ribrewguy-skills` after pulling to pick up changes.

### Running the evals

Eval definitions live at [`skills/rest-api-design/evals/evals.json`](skills/rest-api-design/evals/evals.json) — four test cases with per-assertion pass/fail criteria. Each case is designed to be adversarial or to probe a specific skill rule:

| Eval | Probes |
|---|---|
| `design-task-api-from-scratch` | Whether the skill produces the canonical envelope shapes (pagination, errors), picks PATCH over sub-resource verbs for state transitions, and uses domain-expressive error codes. |
| `pr-audit-multiple-violations` | Whether the skill catches a realistic cluster of REST violations and tags each with severity, without drifting into adjacent concerns (password hashing, file layout). |
| `payments-post-idempotency-trap` | Whether the skill identifies the missing `Idempotency-Key` on a money-moving POST and reshapes the proposed error envelope to the flat / domain-expressive form. |
| `bounded-notifications-not-a-list` | Whether the skill resists the urge to paginate a bounded-by-policy resource and avoids inventing extra top-level envelope fields. |

To run the evals yourself, use the skill-creator workflow: spawn one subagent per eval with the skill loaded, one baseline subagent per eval without it (or with a different version of the skill), grade each output against the assertions, and aggregate into a benchmark. The [skill-creator](https://github.com/anthropics/skills) plugin automates this.

### Contributing a new skill

To add a new skill to this repo:

1. Create `skills/<skill-name>/SKILL.md` with the [Claude Code skill format](https://code.claude.com/docs/en/skills.md) (YAML frontmatter with `name`, `description`; Markdown body).
2. Add an entry to [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) under `plugins` so it's installable from the marketplace.
3. (Optional but encouraged) Add `skills/<skill-name>/evals/evals.json` with test cases and per-case assertions so the skill's expected output is verifiable.
4. Open a PR — include the iteration-1 benchmark if you ran evals.

If the repo grows to more than one or two skills, it's worth restructuring to the canonical multi-plugin layout:

```
.claude-plugin/marketplace.json
plugins/
  rest-api-design/
    .claude-plugin/plugin.json
    skills/rest-api-design/SKILL.md
  other-skill/
    .claude-plugin/plugin.json
    skills/other-skill/SKILL.md
```

with each plugin's `marketplace.json` entry pointing at `./plugins/<name>` instead of `.`.

## License

TBD — to be added before wider distribution. Until then, consider this code available for personal use and review only.
