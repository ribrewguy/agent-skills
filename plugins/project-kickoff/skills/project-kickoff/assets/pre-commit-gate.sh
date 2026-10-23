
# --- BEGIN PROJECT KICKOFF DOCUMENTATION GATE ---
# Kept outside the beads-managed markers, which bd preserves across hook installs
# and upgrades. Checks exactly the snapshot being committed; fix findings rather
# than bypassing the hook.
_kickoff_root=$(git rev-parse --show-toplevel)
if [ -f "$_kickoff_root/scripts/check_docs.py" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo >&2 "check_docs: python3 is required for scripts/check_docs.py --staged"
    exit 1
  fi
  python3 "$_kickoff_root/scripts/check_docs.py" --staged || exit 1
fi
# --- END PROJECT KICKOFF DOCUMENTATION GATE ---
