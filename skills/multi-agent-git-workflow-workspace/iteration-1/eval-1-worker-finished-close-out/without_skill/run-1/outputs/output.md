# Closing Out Your Slice

Nice — gates clean, tests passing, branch ready. Here's a sensible close-out flow.

## 1. Push your branch

Right now your branch is local-only. Push it so others (and CI) can see it:

```bash
git push -u origin feature/proj-42-w2_ci-workflows
```

## 2. Verify CI passes on the remote

Once you push, CI should kick off. Confirm all checks go green there too — local-pass-but-remote-fail is a common gotcha (different env, secrets, etc.).

## 3. Open a pull request into the integration target

Open a PR from `feature/proj-42-w2_ci-workflows` into `integration/proj-42_staging-bringup`.

A solid PR description includes:

- **Summary:** what this slice does (CI workflow YAMLs for the 3-tier flow)
- **Scope:** what's in / what's deliberately out
- **Test plan:** lint clean, typecheck clean, 142/142 unit tests, plus any manual verification
- **Notes for review:** anything the reviewer should pay extra attention to
- **Branch info:** local-only at handoff; head SHA was `7a3f9b1` when you opened the PR

Tag the PR with the parent epic (`proj-42`) and your slice ID (`proj-42-w2`) so it's easy to find.

## 4. Request review

Tag the orchestrator and any other reviewers required by your team's process. Be ready to address feedback and rebase if the integration target moves.

## 5. Merge once approved

Once your PR is approved and any conflicts with the integration branch are resolved, merge it. Squash-merge is usually preferred for feature slices unless your team prefers merge commits — follow the repo's convention.

## 6. Clean up

After merge:

```bash
git branch -d feature/proj-42-w2_ci-workflows         # local
git push origin --delete feature/proj-42-w2_ci-workflows  # remote
```

If you used a worktree, remove it too:

```bash
git worktree remove ../<your-worktree-dir>
```

## 7. Update your task tracker

Mark the slice as done in your tracker (close `proj-42-w2`). Leave a note pointing to the merge commit so the audit trail is clear. Update the parent epic `proj-42` with a brief status if needed.

That's the full close-out. Let me know if you want help drafting the PR description.
