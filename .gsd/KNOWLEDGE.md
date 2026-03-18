# Knowledge Base

## Worktree symlinks must be converted to real files

**Context:** When restoring `src/` from a commit in a git worktree, the `trading/` and `shared/db.py` files are tracked as symlinks pointing to absolute paths in the main repo (`/Users/igol/Documents/repo/polyedge/src/...`). These symlinks work if the main repo has matching files, but they break worktree isolation.

**Rule:** After `git checkout <commit> -- src/`, always run `find src -type l` and convert symlinks to real copies with `cp`. The pattern: `for f in $(find src -type l); do target=$(readlink "$f"); rm "$f" && cp "$target" "$f"; done`.

**Why it matters:** Downstream tasks that modify files in the worktree would silently modify the main repo's files through the symlinks, causing cross-branch contamination.
