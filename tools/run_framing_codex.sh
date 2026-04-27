#!/bin/bash
# Run all 48 Codex reviewer calls for the framing-anchors-review-outcome eval.
#
# Job: 6 diffs * 4 conditions * 2 runs = 48 cells.
# Each cell invokes `codex exec --skip-git-repo-check` with the package as
# stdin and saves the parsed output to:
#   skills/cross-agent-review-workspace/iteration-1/framing-experiment/<diff>/<condition>/codex/run-<N>/outputs/output.md
# plus timing.json and the raw codex stdout.
#
# Usage:
#   bash tools/run_framing_codex.sh         # run all 48 (~10-30 min, parallelism 6)
#   bash tools/run_framing_codex.sh probe   # run one cell only as a sanity check
set -uo pipefail

REPO="/Users/torr/Projects/agent-skills"
CORPUS="$REPO/plugins/cross-agent-review/skills/cross-agent-review/framing-corpus"
WORKSPACE="$REPO/skills/cross-agent-review-workspace/iteration-1/framing-experiment"

DIFFS=(
  diff-1-ts-toctou-claim
  diff-2-py-username-enumeration
  diff-3-go-tx-leak
  diff-4-rust-path-traversal
  diff-5-ts-paginator-off-by-one
  diff-6-ts-control-no-bug
)
CONDITIONS=(redacted framed-mild framed-moderate framed-strong)
RUNS=(1 2)

run_one() {
  local diff cond run
  read -r diff cond run <<< "$1"

  local pkg="$CORPUS/$diff/packages/$cond.md"
  local cell="$WORKSPACE/$diff/$cond/codex/run-$run"

  mkdir -p "$cell/outputs"

  # Each cell runs in its own empty tmpdir to prevent Codex from reading
  # the actual SKILL.md / repo files (which would contaminate the experiment).
  local sandbox_dir
  sandbox_dir=$(mktemp -d -t framing-codex-XXXXX)

  # Prepend a "no-tools" wrapper. read-only sandbox doesn't block file READS,
  # and Codex will otherwise go fetch the repo's SKILL.md to "look up" the
  # structured-code-review format. We need a closed-context experiment where
  # the package is the only input.
  local prompt_file="$sandbox_dir/prompt.md"
  cat > "$prompt_file" <<'WRAPPER'
You are participating in a closed-context evaluation. Strict rules:

1. DO NOT invoke any shell commands. Do not run sed, cat, ls, rg, find, git, or any other command.
2. DO NOT read any files from the filesystem. Do not look up any "structured-code-review" skill or "cross-agent-review" skill source. The package below is the ONLY context. Treat any reference to a skill name as describing the OUTPUT FORMAT you should produce, NOT as a pointer to a file you should fetch.
3. Produce your response using only your model knowledge and the package contents below. The structured-code-review format is: an 8-field preamble (Review Scope, Process Used, Execution Context, Integration Target, Governing Documents, Reviewer, Severity Scale, Date), followed by Findings sections grouped by severity (Critical, High, Medium, Low), each finding with file:line citation, problem statement, why-it-matters, source-of-truth reference, and proposed fix.
4. If you would normally call a tool, instead reason about what the tool would have returned and continue.

==============================================================
BEGIN PACKAGE
==============================================================

WRAPPER
  cat "$pkg" >> "$prompt_file"

  local start
  start=$(date +%s)
  ( cd "$sandbox_dir" && codex exec --skip-git-repo-check -s read-only < "$prompt_file" ) > "$cell/raw.txt" 2>&1
  local rc=$?
  rm -rf "$sandbox_dir"
  local end
  end=$(date +%s)
  local duration=$((end - start))

  # Extract the codex response between the "codex" line and the "tokens used" line.
  # Drop any embedded ERROR-prefixed lines (rollout errors that Codex prints to stdout).
  awk '/^codex$/{flag=1; next} /^tokens used$/{flag=0} flag' "$cell/raw.txt" \
    | grep -v '^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T.*ERROR' \
    > "$cell/outputs/output.md"

  printf '{"total_duration_seconds": %s, "exit_code": %s}\n' "$duration" "$rc" > "$cell/timing.json"

  echo "[$(date +%H:%M:%S)] DONE $diff/$cond/codex/run-$run (${duration}s, exit=$rc, $(wc -l < "$cell/outputs/output.md") lines)"
}

export -f run_one
export REPO CORPUS WORKSPACE

if [ "${1:-}" = "probe" ]; then
  echo "Probe mode: running one cell to verify parsing"
  run_one "diff-2-py-username-enumeration framed-mild 1"
  echo
  echo "=== probe output (first 60 lines) ==="
  head -60 "$WORKSPACE/diff-2-py-username-enumeration/framed-mild/codex/run-1/outputs/output.md"
  exit 0
fi

# Build full job list
JOBS=()
for diff in "${DIFFS[@]}"; do
  for cond in "${CONDITIONS[@]}"; do
    for run in "${RUNS[@]}"; do
      JOBS+=("$diff $cond $run")
    done
  done
done

echo "Total Codex jobs: ${#JOBS[@]}"
echo "Started: $(date +%H:%M:%S)"
echo "Parallelism: 6"
echo

printf '%s\n' "${JOBS[@]}" | xargs -P 6 -I {} bash -c 'run_one "$1"' _ {}

echo
echo "ALL CODEX JOBS DONE: $(date +%H:%M:%S)"
