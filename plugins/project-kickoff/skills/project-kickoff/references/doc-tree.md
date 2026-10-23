# The documentation tree

Back to [SKILL.md](../SKILL.md#fresh-kickoff). `project-kickoff write` creates these seven documents where they are missing. Each has real headers and honest placeholder lines; none has a date in its name. The exact text is the set of templates under this skill's `assets/templates/` directory, which the tool renders with the project name, title and purpose; read those files when you need the wording, so this reference never drifts from what the tool writes.

```
README.md
docs/prds/<name>.md                               business rules only
docs/architecture/overview.md                     vendor- and library-neutral
docs/policies/development/README.md               index of policies
docs/policies/development/technical-decisions.md  the register
docs/design/features/README.md                    index of feature designs
docs/research/README.md                           index of research
```

## What goes where

- **PRD** (`docs/prds/`): outcomes, roles, permitted behaviour, business constraints. Never a language, library, vendor, framework, protocol, storage choice, process or task status.
- **Development policies** (`docs/policies/development/`): every concrete technical choice, each with a status. The register is the index of decisions; longer policies get their own file and a row in the directory `README.md`.
- **Architecture** (`docs/architecture/`): responsibilities, boundaries, relationships, flow, invariants. Names capabilities, not products.
- **Feature designs** (`docs/design/features/`): one stable file per feature.
- **Research** (`docs/research/`): evidence. It informs a register row; it never decides one.

## Register status vocabulary

Exactly four words. `required` is a binding capability or constraint. `selected` is an adopted implementation direction. `proposed` is a candidate without adoption. `unresolved` is a choice still to make. `seed` turns every `unresolved` row into a `Decide: <concern>` task under the open-decisions epic; when the row changes status, close the task.

## Adding a feature design

1. Create `docs/design/features/<stable-name>.md`. The checker requires a `Business authority:` line and a `Status:` line near the top, and the file must end with `## Open decisions` containing `Tracking: ` followed by the Beads issue id in backticks.
2. Add the file to `docs/design/features/README.md`; the checker fails an unindexed document.
3. Create the open-decisions child in Beads before writing prose about what is undecided.
