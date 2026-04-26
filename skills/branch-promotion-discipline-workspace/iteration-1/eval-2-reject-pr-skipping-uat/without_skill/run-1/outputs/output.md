# Should this PR be merged?

Short answer: **no, not in its current form**. Don't merge `develop` directly to `main`.

## Why not

Your team chose a 3-tier flow specifically so that `uat` sits between integration and production. Skipping `uat` for a demo defeats the purpose of having the tier:

- `uat` is your acceptance environment. Code that hasn't passed through it hasn't been validated by stakeholders or against the closer-to-prod test suite.
- "Urgent for client demo" is one of the most common reasons people cite for shortcuts, and shortcuts under deadline pressure are when bad bugs reach production. The features most people want to demo are also the ones most likely to surface integration issues that only show up in a prod-like environment.
- Once you make the exception once, it becomes the precedent for the next "urgent" thing. The flow's value is in being non-negotiable.

## What should happen instead

Run it through the proper sequence:

1. Open a PR `develop -> uat`. Make sure the develop->uat CI gates pass.
2. Merge to `uat`. Wait for the UAT deploy to complete. Run smoke tests against the UAT environment.
3. Have whoever owns acceptance (PM, tech lead, or whoever is doing the demo) sanity-check the feature in UAT.
4. Open a PR `uat -> main`. Get the required reviews. Merge once green.
5. Prod deploys.

### Realistic timing

How long this takes depends on your CI:

- If your suites are fast (lint + unit + integration in 5-10 min, e2e in 10-20 min, smoke tests a few minutes), the whole develop -> uat -> main path can be done in **roughly 45-90 minutes of wall-clock time**, including the human acceptance step.
- If e2e is slow (an hour or more) or acceptance requires manual review by someone who's offline, you might be looking at **3-5 hours** end-to-end.

The demo is at 9am Pacific tomorrow. Even on the pessimistic end, you have most of a workday plus an evening before then. The proper flow fits, easily.

## What I'd actually suggest

A couple of practical options that get the demo done without breaking the flow:

**Option A: Promote tonight.** Start the `develop -> uat` PR immediately. CI runs while people finish other work. UAT deploys, somebody validates. Open `uat -> main` before EOD or first thing in the morning. Hits 9am with margin.

**Option B: Demo from UAT, not prod.** If the demo doesn't strictly need to be on the production URL/data, do the demo against the UAT environment. UAT is already deployed and the stakeholders have presumably seen it before. You can promote to main on the normal cadence afterward. This is the cleanest answer if the demo is just showing functionality, not transacting against prod systems.

**Option C: Push `develop` to `uat` now and accept that production lags by a day.** The client demo can be on UAT; the prod push happens after the demo is over. No deadline pressure on the main push at all.

Option B is usually best if the demo is feature-walkthrough rather than "watch real users do real things in prod."

## Things to NOT do

- Don't disable branch protection on `main` to push the PR through.
- Don't have an admin override the source-branch check.
- Don't manually merge by deleting and re-creating the PR with a different base.
- Don't push directly to `main`.

All of these defeat exactly the controls that the team set up to prevent this scenario. If the rules can be bypassed when there's deadline pressure, they don't work — deadline pressure is when you most need them to hold.

## Suggested PR comment

Something like:

> Closing this — `main` shouldn't take a PR from `develop` directly; we go through `uat` for stakeholder acceptance. I'll open `develop -> uat` now so the change is deployed to UAT well before tomorrow's demo. If the demo can run against UAT, that's the cleanest path; otherwise we promote `uat -> main` after acceptance tonight or first thing in the morning. Either way, 9am is comfortably in reach.
