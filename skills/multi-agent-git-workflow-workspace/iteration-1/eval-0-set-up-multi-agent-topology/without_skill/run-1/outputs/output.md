# Multi-Agent Topology for proj-42

Here's a setup for splitting proj-42 across 3 implementation agents.

## Branches

I'd recommend a branch-per-slice approach:

- `proj-42/main` — the parent epic branch off of `main` or `develop`
- `proj-42/policy-docs` — slice 1 (worker A)
- `proj-42/ci-workflows` — slice 2 (worker B)
- `proj-42/source-ref-enforcement` — slice 3 (worker C)

The parent `proj-42/main` branch is where all three slices integrate before the final merge to your target branch (likely `main` or `develop`).

## Worktrees

Each agent should work in a separate directory to avoid stepping on each other:

```bash
git worktree add ../proj-42-policy-docs proj-42/policy-docs
git worktree add ../proj-42-ci-workflows proj-42/ci-workflows
git worktree add ../proj-42-source-ref proj-42/source-ref-enforcement
```

This way each agent has its own checkout and they can work fully in parallel.

## Tasks / Beads

- Parent task: `proj-42` — Add staging branch and 3-tier deploy flow
- Subtask A: `proj-42a` — policy doc updates
- Subtask B: `proj-42b` — CI workflow YAMLs
- Subtask C: `proj-42c` — source-ref enforcement + pre-commit

## Worker A — Policy doc updates and renames

**Responsibilities:**
- Update existing policy documentation to reflect the staging branch and 3-tier flow
- Rename anything that references the old 2-tier model
- Make sure the docs are consistent across the repo

**MUST NOT:**
- Touch the CI workflow YAMLs (that's Worker B)
- Touch the source-ref enforcement workflow (that's Worker C)
- Push directly to main

## Worker B — CI workflow YAMLs

**Responsibilities:**
- Create `ci-develop.yml`, `ci-staging.yml`, and `ci-main.yml`
- Make sure each pipeline runs the right gates for that environment
- Test the workflows locally with `act` or similar before opening a PR

**MUST NOT:**
- Modify policy docs (Worker A's lane)
- Modify pre-commit hook config (Worker C's lane)

## Worker C — Source-ref enforcement + pre-commit hook

**Responsibilities:**
- Build the source-ref enforcement workflow that validates branch sources
- Set up the pre-commit hook configuration
- Make sure both work locally and in CI

**MUST NOT:**
- Modify CI workflow YAMLs beyond what's needed to wire in source-ref enforcement
- Edit policy docs

## You (Orchestrator)

**Responsibilities:**
- Track progress across all three workers
- Resolve merge conflicts when integrating their branches into `proj-42/main`
- Run integration tests after each merge
- Open the final PR from `proj-42/main` to your target branch
- Communicate status to stakeholders

**MUST NOT:**
- Get bogged down implementing slices yourself — delegate to the workers
- Merge a worker's branch without reviewing it first
- Skip integration testing between merges

## Suggested workflow

1. Workers complete their slices on their branches.
2. Each worker opens a PR into `proj-42/main`.
3. You review and merge each PR, resolving any conflicts.
4. After all three are merged, run the full integration test suite.
5. Open the final PR from `proj-42/main` to your target branch.

Let me know if you want help drafting the bead/task descriptions or the initial PR templates.
