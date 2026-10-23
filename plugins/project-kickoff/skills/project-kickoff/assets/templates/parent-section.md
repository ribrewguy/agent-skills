
## Parent instructions

Read and apply the parent `{{parent_file}}` before working here. Parent guidance is not inherited by copying it into this file.

- The parent is `../{{parent_file}}` from the owning repository root. From a linked worktree under `.worktrees/<name>` it is `../../../{{parent_file}}`. Resolve through the owning repository, not the worktree's immediate parent, and never treat a worktree's copy of this file as the parent.
- If the checkout is relocated, locate and read its actual enclosing parent instructions, and report an expected parent that is missing instead of silently skipping it.
- A standalone clone with no parent applies these local rules alone.
