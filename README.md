# agent-skills

A small, growing collection of skills I've built for AI coding tools. They're just markdown with a bit of YAML frontmatter — the `SKILL.md` format that [Claude Code](https://claude.com/code), [Gemini CLI](https://geminicli.com), [OpenAI Codex](https://developers.openai.com/codex), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), and [Cline](https://docs.cline.bot) all read natively. Other tools (Cursor, Aider) don't have a native skills system, but you can point their rule files at these.

Each skill gets shaped the same way: write a draft, run it against its own test prompts, read the outputs next to a baseline, revise, repeat. The test prompts and per-case assertions ship with the skill in `evals/evals.json`, so "the skill works" means something you can actually measure instead of vibes.

## What's in here

### `rest-api-design`

For designing or reviewing HTTP REST APIs. Covers the usual suspects — URLs, methods, status codes, pagination, idempotency — plus a few opinions that tend to surface in code review:

- **State transitions are `PATCH`**, not a `/complete` or `/cancel` sub-resource verb. Side effects (emails, audit rows) belong to the state change in the service layer, not to a URL invention. Inventing verbs fragments the URL space and doesn't compose with generic update clients.
- **Error codes name the domain reason**, not the HTTP status. `TaskNotFound` or `CardDeclined`, not `NOT_FOUND` or `BAD_REQUEST`. The HTTP status classifies at the protocol layer; the code explains *why* within the domain. Echoing the status wastes the field.
- **Flat error envelopes.** If your type is `APIError`, wrapping its contents in `{ error: { ... } }` is a layer of indirection that HTTP status already provides. Drop the wrapper.
- **Typed contracts are language-agnostic.** Examples in TypeScript, Python, Go, and Rust — because "REST" isn't a TypeScript-ism.
- **Reviewer-grade output with severity tags.** When you ask it to audit a PR, every finding comes back tagged `Critical` / `High` / `Medium` / `Low`, so the author knows what blocks merge and what's polish. The skill also stays strictly in its lane — crypto, auth internals, file layout, etc. get flagged and handed off to neighbor skills rather than absorbed into one über-review.

Full skill at [`plugins/rest-api-design/skills/rest-api-design/SKILL.md`](plugins/rest-api-design/skills/rest-api-design/SKILL.md).

## Install

Pick the section that matches your tool. If you use multiple tools, the "canonical home" pattern at the end of the Claude Code section sets you up to share one copy of the skill across all of them.

### Claude Code

Easiest path — install via the plugin marketplace:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
```

Run `/plugin marketplace update ribrewguy-skills` to pull updates. Auto-update on session start is off by default for third-party marketplaces; flip it on in the `/plugin` UI if you want it.

Once installed, the skill fires automatically when a task matches its description — or you can invoke it explicitly with `/rest-api-design`.

**Prefer a symlink?** Clone the repo and point Claude Code at the skill directly:

```bash
git clone git@github.com:ribrewguy/agent-skills.git ~/Projects/agent-skills
ln -s ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design \
      ~/.claude/skills/rest-api-design
```

`git pull` in the repo updates what Claude Code sees — no `/plugin update` dance.

**The canonical-home pattern** (if you use more than one AI tool): keep a single `~/.agents/skills/` directory and let every tool symlink into it. Copilot CLI reads `~/.agents/skills/` natively, and the others can be pointed at it. Set it up once:

```bash
ln -s ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design \
      ~/.agents/skills/rest-api-design
ln -s ../../.agents/skills/rest-api-design ~/.claude/skills/rest-api-design
```

Then one `git pull` updates every tool.

### Gemini CLI

Gemini has a native skills system at `~/.gemini/skills/` (user-level) and `.gemini/skills/` or `.agents/skills/` (workspace-level):

```bash
ln -s ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design \
      ~/.gemini/skills/rest-api-design
```

Or if you're using the canonical-home pattern, point Gemini at the same shared home:

```bash
ln -s ../../.agents/skills/rest-api-design ~/.gemini/skills/rest-api-design
```

Gemini loads skill metadata at session start and activates the body on demand via its `activate_skill` tool. Docs: [Agent Skills | Gemini CLI](https://geminicli.com/docs/cli/skills/).

### OpenAI Codex CLI

Codex looks for `SKILL.md` files under `~/.codex/skills/` (configurable in `~/.codex/config.toml`):

```bash
ln -s ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design \
      ~/.codex/skills/rest-api-design
```

Same thing via the canonical home:

```bash
ln -s ../../.agents/skills/rest-api-design ~/.codex/skills/rest-api-design
```

Docs: [Agent Skills – Codex](https://developers.openai.com/codex/skills).

### GitHub Copilot CLI

Copilot CLI reads a handful of directories natively — including `~/.agents/skills/` and `~/.claude/skills/` — so if you're using either of those, you're already covered. If you want an explicit Copilot-specific home:

```bash
ln -s ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design \
      ~/.copilot/skills/rest-api-design
```

As of April 2026 there's also a registry-style `gh skill` subcommand for install/publish — check the [Copilot CLI skills docs](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) for the latest.

### Cline

Cline reads `~/.cline/skills/` (user) and `.cline/skills/` (workspace):

```bash
ln -s ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design \
      ~/.cline/skills/rest-api-design
```

Cline keeps skills under 5k tokens in the context window and lazy-loads anything under a `docs/` subdirectory — same progressive-disclosure pattern as Claude Code. Docs: [Skills | Cline](https://docs.cline.bot/customization/skills).

### Cursor

Cursor doesn't have a native skills system — it uses `.cursor/rules/` with `.mdc` files for project-level rules. To use a skill here, reference it from a rule file:

```markdown
<!-- .cursor/rules/rest-api.mdc -->
# REST API conventions
When designing or reviewing HTTP REST APIs, apply the guidance in
~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design/SKILL.md.

Key rules: state transitions use PATCH, error codes name the domain
reason (not HTTP status), flat error envelopes, pagination uses
cursor with default limit 20 and max 100. Full details in the file
above.
```

Or paste the relevant sections of `SKILL.md` directly into the rule file. Docs: [Cursor Rules](https://docs.cursor.com/context/rules-for-ai).

### Aider

Aider uses `CONVENTIONS.md` loaded via `--read` or a project-level `.aider.conf.yml`. Easiest path:

```bash
# in the project where you want the skill active:
echo "read: ~/Projects/agent-skills/plugins/rest-api-design/skills/rest-api-design/SKILL.md" \
  >> .aider.conf.yml
```

Aider then includes the skill content as read-only context on every prompt. Docs: [Aider configuration](https://aider.chat/docs/config.html).

## Check that it's working

Drop this prompt in a fresh session:

> Review this endpoint — `POST /api/createOrder` returning `200 { order_id: '...' }`. What's wrong?

If the skill is loaded, you'll get back at least: verb in the URL (`/createOrder` should be `POST /api/orders`), wrong status (`200` should be `201 Created`), missing `Location` header, `snake_case` response key (`order_id` should be `id`), and each finding tagged with severity. Without the skill, you'll get a looser answer that misses some of these or treats them all with equal weight.

## Editing or adding skills

Each skill lives at `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`, with eval definitions next to it at `evals/evals.json`. To add a new one:

1. **Plugin manifest** — `plugins/<your-plugin>/.claude-plugin/plugin.json` with `name`, `description`, `version`.
2. **Skill file** — `plugins/<your-plugin>/skills/<your-skill>/SKILL.md`, standard YAML frontmatter + Markdown body. See [Claude Code's skill docs](https://code.claude.com/docs/en/skills.md) for the exact schema.
3. **Marketplace entry** — add to `.claude-plugin/marketplace.json` under `plugins`, with `source: ./plugins/<your-plugin>`.
4. **Evals** (optional but the whole point) — `plugins/<your-plugin>/skills/<your-skill>/evals/evals.json` with test cases and per-assertion pass/fail criteria. This is what makes "the skill works" a measurable claim.

Open a PR. If you ran evals, drop the benchmark in the PR description.

## Repo layout

```
.claude-plugin/
  └── marketplace.json                    # lists all plugins in this repo
plugins/
  └── rest-api-design/
      ├── .claude-plugin/plugin.json      # this plugin's manifest
      └── skills/rest-api-design/
          ├── SKILL.md                    # the skill
          └── evals/evals.json            # test cases + assertions
LICENSE
README.md
```

## License

[MIT](LICENSE). Use it, fork it, break it, whatever.
