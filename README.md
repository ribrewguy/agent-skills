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

Pick the section that matches your tool. The plugin marketplace path (Claude Code) needs no setup. The symlink-based installs share a one-time setup so they can compose cleanly.

### Claude Code — plugin marketplace (easiest)

Inside a Claude Code session:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
```

Run `/plugin marketplace update ribrewguy-skills` to pull updates. Auto-update on session start is off by default for third-party marketplaces; flip it on in the `/plugin` UI if you want it.

Once installed, the skill fires automatically when a task matches its description — or you can invoke it explicitly with `/rest-api-design`.

### Symlink-based install (everything else)

The remaining tools want a directory or file to point at. Clone the repo wherever you keep dev tooling, then export `REPO` so the snippets below resolve. (Add the export to your shell rc if you want it persistent.)

```bash
# wherever you keep cloned repos — adjust to taste
git clone git@github.com:ribrewguy/agent-skills.git
export REPO="$(pwd)/agent-skills"
```

After that, every install command in this section uses `"$REPO/..."` and you can paste it as-is.

> [!TIP]
> If you use more than one AI tool, set up the canonical-home pattern first (right below). The per-tool sections after it are one-click expandable — open the one you need.

<details>
<summary><b>Canonical-home pattern (recommended for multi-tool setups)</b></summary>

Keep a single `~/.agents/skills/` directory and let every tool symlink into it. GitHub Copilot CLI reads `~/.agents/skills/` natively, and the others get pointed at it with one line each. Set the canonical entry up once:

```bash
mkdir -p ~/.agents/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.agents/skills/rest-api-design
```

Now `git pull` in `$REPO` updates every tool that reaches into `~/.agents/skills/` — directly or via symlink. The per-tool sections below show both options: point at `~/.agents/skills/` (preferred when you use multiple tools), or point straight at the repo.

</details>

<details>
<summary><b>Claude Code</b> (symlink alternative to the marketplace)</summary>

```bash
mkdir -p ~/.claude/skills
ln -s ../../.agents/skills/rest-api-design ~/.claude/skills/rest-api-design
# or, skipping the canonical home:
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.claude/skills/rest-api-design
```

</details>

<details>
<summary><b>Gemini CLI</b></summary>

Gemini has a native skills system at `~/.gemini/skills/` (user-level), plus workspace-level `.gemini/skills/` and `.agents/skills/`:

```bash
mkdir -p ~/.gemini/skills
ln -s ../../.agents/skills/rest-api-design ~/.gemini/skills/rest-api-design
# or directly:
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.gemini/skills/rest-api-design
```

Gemini loads skill metadata at session start and activates the body on demand via its `activate_skill` tool. Docs: [Agent Skills | Gemini CLI](https://geminicli.com/docs/cli/skills/).

</details>

<details>
<summary><b>OpenAI Codex CLI</b></summary>

Codex looks for `SKILL.md` files under `~/.codex/skills/` (configurable in `~/.codex/config.toml`):

```bash
mkdir -p ~/.codex/skills
ln -s ../../.agents/skills/rest-api-design ~/.codex/skills/rest-api-design
# or directly:
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.codex/skills/rest-api-design
```

Docs: [Agent Skills – Codex](https://developers.openai.com/codex/skills).

</details>

<details>
<summary><b>GitHub Copilot CLI</b></summary>

Copilot CLI reads `~/.agents/skills/` and `~/.claude/skills/` natively — so if you set up either of those above, you're already done. If you want an explicit Copilot-specific home:

```bash
mkdir -p ~/.copilot/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.copilot/skills/rest-api-design
```

As of April 2026 there's also a registry-style `gh skill` subcommand for install/publish — check the [Copilot CLI skills docs](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) for the latest.

</details>

<details>
<summary><b>Cline</b></summary>

Cline reads `~/.cline/skills/` (user) and `.cline/skills/` (workspace):

```bash
mkdir -p ~/.cline/skills
ln -s ../../.agents/skills/rest-api-design ~/.cline/skills/rest-api-design
# or directly:
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.cline/skills/rest-api-design
```

Cline keeps skills under 5k tokens in context and lazy-loads anything under a `docs/` subdirectory — same progressive-disclosure pattern as Claude Code. Docs: [Skills | Cline](https://docs.cline.bot/customization/skills).

</details>

<details>
<summary><b>Cursor</b> — rule-file reference (no native skills system)</summary>

Cursor uses `.cursor/rules/` with `.mdc` files for project-level rules. Reference the skill from a rule file (replace `<path-to-cloned-repo>` with your actual clone path — rule files don't get shell variable expansion):

```markdown
<!-- .cursor/rules/rest-api.mdc -->
# REST API conventions
When designing or reviewing HTTP REST APIs, apply the guidance in
<path-to-cloned-repo>/plugins/rest-api-design/skills/rest-api-design/SKILL.md.

Key rules: state transitions use PATCH, error codes name the domain
reason (not HTTP status), flat error envelopes, pagination uses
cursor with default limit 20 and max 100. Full details in the file
above.
```

Or paste the relevant sections of `SKILL.md` directly into the rule file. Docs: [Cursor Rules](https://docs.cursor.com/context/rules-for-ai).

</details>

<details>
<summary><b>Aider</b></summary>

Aider uses `CONVENTIONS.md` loaded via `--read` or a project-level `.aider.conf.yml`. Easiest path:

```bash
# in the project where you want the skill active:
echo "read: $REPO/plugins/rest-api-design/skills/rest-api-design/SKILL.md" \
  >> .aider.conf.yml
```

(`$REPO` gets expanded by the shell here, so the value baked into `.aider.conf.yml` will be the absolute path to the skill — no further substitution needed when Aider reads the config.)

Aider then includes the skill content as read-only context on every prompt. Docs: [Aider configuration](https://aider.chat/docs/config.html).

</details>

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
