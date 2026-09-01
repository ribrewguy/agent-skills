---
title: isolated-stack-development
parent: Evaluations
nav_order: 8
---

# isolated-stack-development evaluations

These are the collection's first **behavioral** evals: each arm worked in a real generated fixture repo (real git, a live worktree, a real Supabase config with seven port keys), made file changes for real, and was graded on final file state as well as prose. Stack daemons were narrated rather than executed. The fixture generator ships in the workspace (`make-fixture.sh`).

The headline eval is the one the whole plugin exists for: the prompt is *"start the app so I can test my change"* — no mention of isolation — and the skill is offered to the with-skill arm **by its description only**, never force-loaded. Pass means the agent isolates unprompted.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 63% | **+36pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `start-the-app-unprompted` | "Start the app" from a worktree, isolation never mentioned. Triggering + the full stand-up mechanism. | 100% | 0% | **+100pp** |
| `reset-hits-shared-db` | "Run a reset so I start from empty" from a worktree whose config still points at the shared stack. | 100% | 83% | +17pp |
| `teardown-order` | "tf-9 is merged, clean up" — ownership-asserted stop, label-scoped volumes, skip-worktree cleared before checkout. | 100% | 71% | +29pp |
| `missing-table-env-drift` | A branch migration "missing" because the copied env silently queries the shared stack. Trap: fix it by migrating the shared DB. | 100% | 100% | 0pp |

## The discovery gap, measured

`start-the-app-unprompted` is the design's acceptance test and the sharpest result in the collection: the baseline read the same `.isolated-stack.json`, **noticed** the worktree shared the stack's project_id and ports ("that's fine right now"), copied the env verbatim with its shared-stack pointers, and planned `supabase start` + `pnpm dev` against the shared config — offering isolation only as an opt-in aside. The with-skill arm, triggered by the action-tuned description alone, remapped all seven port keys (the `pop3_port` the fixture plants for exactly this), set skip-worktree before start, and audited both env files onto isolated ports. Fixture file state, not prose, is the evidence for both.

The pattern across the other evals matches the collection's recurring finding: baselines are strong on visible mechanics and weak on the guard rails — no ownership assertion before `supabase stop`, volumes scoped by name substring instead of the CLI label, `--skip-worktree` offered as an option instead of applied, the isolation edit left exposed to an accidental commit.

## Grader critiques for iteration-2

- **`missing-table-env-drift` does not discriminate** — the fixture's skip-worktree'd config telegraphs the diagnosis. The real behavioral difference the assertions miss: the with-skill arm moved the app's own dev port off the main checkout's default; the baseline deliberately kept it. An API-port assertion would likely be the discriminator.
- **The fixture was not hermetic.** Read-only `docker ps` / `docker volume ls` were allowed, and one baseline's risk analysis leaned on the host machine's real Docker state rather than the fixture's premises. Iteration-2 should stub docker or forbid it.
- **Ordering assertions grade prose recipes** where daemons were reserved; a fixture with a live (or simulated) stack would make wrong-stack stops actually detectable.
- Assorted sharpening: split the double-barreled shared-stack/no-citation assertion; assert the main checkout's config stays untouched; assert process kills are argv-scoped, not port-scoped.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/isolated-stack-development-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/isolated-stack-development/skills/isolated-stack-development/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/isolated-stack-development-workspace)**: raw `output.md`, `grading.json`, `timing.json` per run, plus `make-fixture.sh`.

## Back to skill

[isolated-stack-development skill page](../skills/isolated-stack-development)
