# Should this PR be merged?

**No.** Don't merge `develop -> main` directly. The demo is real, but it's not a reason to skip a tier.

## Why not

The flow is `develop -> uat -> main` for a reason. `uat` exists so that what reaches `main` has been seen and accepted in a stakeholder-facing environment. If you merge `develop` straight to `main`:

- You skip stakeholder acceptance entirely. `main` is supposed to mean "passed UAT," not "whatever happened to be on develop at 4pm yesterday."
- You skip the gate set that's specific to the `uat` boundary (integration, e2e, UAT environment smoke). `develop` doesn't run those. Whatever lands in production has only had develop's lighter gates run on it.
- You set a precedent. The next "urgent" thing — and there's always a next one — comes with the same argument.

The source-ref check on `main` is also configured to require source = `uat`. The PR as written should fail that check on its own; if it doesn't, the check is misconfigured and that's a separate bug to fix. **Do not disable branch protection or bypass the source-ref check to push this through.** Those rules are the only thing standing between this incident and the next one.

## What to do instead

Run the work through the correct path:

1. **Promote `develop` to `uat`.** Open a PR `develop -> uat`. Run the uat gate set (lint, typecheck, unit, build, integration, e2e, source-ref check). On merge, `uat` deploys to the UAT environment.
2. **Stakeholder acceptance in UAT.** This is the literal point of the tier. UAT environment smoke tests run; the demo person (or PM) can validate the feature actually works in a prod-like environment.
3. **Promote `uat` to `main`.** Open a PR `uat -> main` once acceptance is done. Source-ref check passes (source = uat), gates run, two approvers sign off, merge, prod deploy.

### Realistic time estimate

- If your gate matrix is tight (fast unit/integration suites, e2e under ~15 minutes, smoke tests automated): the entire `develop -> uat -> main` cycle can be done in **30-60 minutes of wall-clock time**, most of which is CI runtime.
- If e2e is slow (an hour or more) or stakeholder acceptance involves a human looking at a UI: **2-4 hours**, possibly more.
- 9am Pacific tomorrow gives roughly 17 hours from now if you start tonight. That is plenty of time for the correct path even at the pessimistic end.

If the team is genuinely concerned about cutting it close, start the `develop -> uat` PR right now. The time pressure argues for *more* discipline, not less, because rushing through `main` directly is exactly when null-deploy disasters happen.

## A workaround if main-deployment timing is the only blocker

The demo is at 9am tomorrow. **Does the demo have to be from production?**

If the answer is no — and for client demos, "no" is usually fine — the UAT environment is already deployed and stakeholders use it for acceptance every day. Run the demo against `uat`:

- Promote `develop -> uat` tonight (gates + smoke).
- Demo against the UAT URL tomorrow morning.
- Promote `uat -> main` after the demo, on the normal cadence.

This gets the feature in front of the client on time, gets stakeholder acceptance in the loop the right way, and avoids a rushed prod push under demo pressure.

If the demo *must* be on the production URL (e.g., domain branding requirement, or the client is going to test purchase flows that only work against prod payment processing), then you still run the full `develop -> uat -> main` path — just start it now, not at 8:45am tomorrow. There's enough time.

## What NOT to do

- Don't merge `develop` directly to `main`.
- Don't disable branch protection on `main` "just for this merge."
- Don't push directly to `main` to bypass the PR.
- Don't bypass or temporarily delete the source-ref check.
- Don't have an admin force-merge over failing checks.

Each of those is the kind of decision that becomes a postmortem bullet point next week.

## Recommended response on the PR

Close the PR with a comment along the lines of:

> Closing — `main` only accepts PRs sourced from `uat`. To get this in front of the client by 9am Pacific tomorrow, I'm opening `develop -> uat` now and we can promote `uat -> main` after acceptance. If demoing from the UAT environment works for the client, we can also do that and skip the prod push until our normal release window. I'll start the `develop -> uat` PR in the next 10 minutes.
