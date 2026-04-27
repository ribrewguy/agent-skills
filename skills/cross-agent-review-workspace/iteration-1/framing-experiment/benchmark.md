# Framing-anchors-review-outcome experiment

**Cells:** 96/96 (0 missing)

## Headline: catch rate × severity × nit count by condition × reviewer

| Condition | Reviewer | n | Catch rate | Severity dist | Median nits | Mean total findings |
|---|---|---|---|---|---|---|
| framed-mild | claude | 10 | 100% | Critical:6, High:4 | 3.5 | 9.7 |
| framed-mild | codex | 10 | 80% | High:8, NotFlagged:2 | 1.0 | 2.6 |
| framed-moderate | claude | 10 | 100% | Critical:7, High:3 | 4.5 | 12 |
| framed-moderate | codex | 10 | 70% | High:6, Medium:1, NotFlagged:3 | 0.0 | 2.4 |
| framed-strong | claude | 10 | 100% | Critical:7, High:3 | 3.5 | 11.2 |
| framed-strong | codex | 10 | 100% | High:10 | 1.5 | 4 |
| redacted | claude | 10 | 100% | Critical:9, High:1 | 4.5 | 13 |
| redacted | codex | 10 | 70% | High:7, NotFlagged:3 | 1.0 | 9.4 |

## Within-reviewer redacted vs framed (per-condition deltas)

- **claude** redacted vs framed-mild: catch Δ = +0%; median nits Δ = +1.0
- **claude** redacted vs framed-moderate: catch Δ = +0%; median nits Δ = +0.0
- **claude** redacted vs framed-strong: catch Δ = +0%; median nits Δ = +1.0
- **codex** redacted vs framed-mild: catch Δ = -10%; median nits Δ = +0.0
- **codex** redacted vs framed-moderate: catch Δ = +0%; median nits Δ = +1.0
- **codex** redacted vs framed-strong: catch Δ = -30%; median nits Δ = -0.5

## Control diff (no planted bug): false-positive proxy

| Condition | Reviewer | Mean control findings |
|---|---|---|
| framed-mild | claude | 11.5 |
| framed-mild | codex | 5.5 |
| framed-moderate | claude | 9.5 |
| framed-moderate | codex | 5 |
| framed-strong | claude | 6 |
| framed-strong | codex | 1 |
| redacted | claude | 12.5 |
| redacted | codex | 2 |