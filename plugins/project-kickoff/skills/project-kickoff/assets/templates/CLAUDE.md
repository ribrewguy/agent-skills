# {{title}} agent instructions
{{parent}}
## Hard rules

1. Keep this file and `AGENTS.md` identical. Only {{title}}-specific rules live here; shared workflow and development guidance belongs to the parent instructions and the installed skills.
2. The PRD in `docs/prds/` holds **business rules only**: outcomes, roles, permitted behaviour and business constraints. It must not prescribe languages, libraries, vendors, frameworks, protocols, storage, development process or task status.
3. Technical choices and development requirements live in `docs/policies/development/`. Record each with a status of exactly `required`, `selected`, `proposed` or `unresolved`. A recommendation never silently becomes a decision.
4. `docs/architecture/` describes responsibilities, boundaries, relationships, data and control flow and invariants. Keep it vendor- and library-neutral; refer to the development policies for concrete choices.
5. Each feature has a discrete design document in `docs/design/features/`, linked to its governing business rules, architecture and policies. Research in `docs/research/` is evidence, not authority to implement.
6. **No project file may have a date in its filename.** Use stable descriptive names; dates belong in document content. This applies to generated files too, so choose tools and configuration compatible with it.
7. Track every open decision in Beads as a child of the open-decisions epic (`<open-decisions-epic>`), not only in prose. When a decision is made, record it with its status in the register or owning document and remove it from the open list.
8. Review records (code, design or documentation reviews) are not kept in source control. Record review outcomes in the Beads task under review.

### Project-specific rules

None yet. Add rules here as the project earns them, and keep them specific to {{title}}.

## Document conventions

- Each feature design begins with `Business authority:` and `Status:` lines and ends with `## Open decisions`, which names the Beads issue tracking them (`Tracking: \`<id>\``).
- Register every design, policy and research document in its directory's `README.md` index.
- Fold new content into the existing structure of a document rather than appending a dated or topical section to its end.

## Canonical documents

- [Business rules](docs/prds/{{name}}.md)
- [Development policies](docs/policies/development/README.md)
- [Architecture](docs/architecture/overview.md)
- [Feature designs](docs/design/features/README.md)
- [Research index](docs/research/README.md)

## Local tooling

Beads is initialised with prefix `{{name}}`; run `bd prime` for tracker context and `bd ready` for available work. Open decisions are children of `<open-decisions-epic>`. Procedural memory lives in `.cass/`; run `cm context "<task>"` before non-trivial work.

Run `python3 scripts/check_docs.py` to check instruction parity, portable local links, date-bearing filenames, index coverage and feature-design structure; `python3 -m unittest discover -s scripts -p 'test_*.py'` runs its regression tests. The Beads pre-commit hook runs the same check against the staged snapshot; fix failures rather than bypassing them.

Build and test commands: none yet. Add them here with the first executable slice.
