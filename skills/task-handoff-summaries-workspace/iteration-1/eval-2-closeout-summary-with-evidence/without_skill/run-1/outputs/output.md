# Closeout — proj-42: Add staging branch and 3-tier deploy flow

## Status
Merged to `develop`. Branch cleaned up. Promotion to `uat` and `main` not yet open.

## Process
- **Bead:** proj-42
- **Process:** Full bead process, single-agent.
- **Branch:** `feature/proj-42_staging-branch` (deleted local + remote after merge)
- **Commit:** `9a2b3c4`
- **Pushed:** Yes
- **Integration target reached:** `develop`

## What Shipped
- New branch hierarchy: `main` / `staging` / `develop`.
- Source-ref enforcement on staging-targeted workflows.
- Three new CI workflows: `ci-develop`, `ci-staging`, `ci-main`.
- Pre-commit lint via `simple-git-hooks`.
- Documentation: new staging-branch doc; amendments to branches, commits (UAT Gate section), and testing docs.

## Quality Gates
| Gate | Result |
|---|---|
| Lint | 0 errors |
| Typecheck | 0 errors |
| Unit tests | 142/142 passing |
| Build | Succeeded |
| E2E tests | Deferred — no CI secrets at adoption (see §13 of the policy doc) |
| UAT | Not requested — infrastructure-only change with no user-facing behavior |

## Behavioral Impact
- Developers now work against the new `main` / `staging` / `develop` hierarchy.
- Source-ref enforcement gates which refs can target staging.
- CI runs against three workflows depending on the target branch.
- New pre-commit hook runs lint on staged files for contributors.
- No user-visible product behavior change.

## Risks / Open Items
1. **Branch protection / rulesets are NOT applied.** The current GitHub plan tier doesn't support rulesets on private repos. Until the plan is upgraded, the branch policies are enforced only by review discipline, not by the platform.
2. **E2E and integration test secrets are not provisioned.** Those gates will not pass on day one.
3. **Baseline error counts on `develop` at adoption:** 200 lint errors, 80 typecheck errors, 12 failing unit tests. Promoting these to required gates today would freeze the repo; they're tracked as ratchet-down work.
4. **Promotion stopped at `develop`.** No PR is open from `develop` to `uat`, and none from `uat` to `main`. The work has not yet reached uat or main.

## Files
**New:**
- `docs/development/staging-branch.md`
- `.github/workflows/ci-develop.yml`
- `.github/workflows/ci-staging.yml`
- `.github/workflows/ci-main.yml`
- `.nvmrc`

**Amended:**
- `docs/development/branches.md` (§1, §8)
- `docs/development/commits.md` (UAT Gate section)
- `docs/development/testing.md`
- `package.json` (added `simple-git-hooks`)
