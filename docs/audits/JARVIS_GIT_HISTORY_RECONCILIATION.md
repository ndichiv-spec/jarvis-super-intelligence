# JARVIS Git history reconciliation plan

## 2026-10-13 verified continuation state

- This mission uses the isolated branch
  `integration/world-workspace-owner-deploy` at recovery-based parent
  `cf18e6eac930974af8fff76587ae456cd6d11eaa`. The expected recovery tip
  `19bd9622dff474e68ab47df46f0f88b78279e89d` remains an ancestor; the four
  recovery commits and later remote recovery merge remain preserved.
- Local remote-tracking state: `origin/recovery/integration-20261012` is
  `0ad896d49b0d22624abf3038655f082c7ea83f09`; `origin/main` is
  `4d69fdc1fdd91596dbd174d6b2a029d78251a640`. `main` was not checked out or
  modified by this work.
- `git merge-base HEAD origin/main` returns no common ancestor. No cherry-pick,
  merge, reset, push, or remote ref update has been performed. This branch is a
  reviewable implementation line based on recovery, not a reconciled history.
- The worktree already contained staged integration implementation changes
  before this continuation; those changes were preserved. The
  `research_engine` package exists inside this branch to remove an import
  dependency on sibling workspace source. No sibling source or `origin/main`
  file was changed.
- This report's earlier starting hashes below describe the prior recovery
  audit and are historical, not the present remote-tracking state.

## Verified starting point

At the mission baseline, the canonical checkout was
`F:\AI\Jarvis-super-intelligence-`, on
`recovery/integration-20261012`, at
`19bd9622dff474e68ab47df46f0f88b78279e89d`. The recovery branch tracks
`origin/recovery/integration-20261012` at that tip. The configured `origin`
is the expected `ndichiv-spec/jarvis-super-intelligence` repository.
`origin/main` was at `74c8dd97c4e9869d9cd22015411e3f0d3244185d`; recovery was
reported 12 commits ahead and 7 behind and `git merge-base` returned no
common ancestor. The checkout was clean before this mission's owner/database
changes. Current mission changes are intentional uncommitted work; inspect
`git status` and the complete diff before staging.

## Preservation invariants

- Preserve recovery tip and all recovery commits (`73b7857`, `5245198`,
  `0fd6b7f`, `19bd962`) and its remote ref.
- Preserve `origin/main` and its independent history.
- Do not reset, force-push, blindly merge unrelated histories, or deploy a
  merge before review.
- Do not include unrelated files from sibling `F:\AI` workspace paths or
  modify them. `research_engine/` is intentionally copied into this isolated
  integration tree and will be reviewed as part of this branch's dependency
  fix.
- Preserve and commit only deliberate, reviewed changes from this mission;
  keep credentials and local environment files out of history.

## Safe reconciliation procedure

1. Fetch refs without modifying either line; record immutable local branch
   names and source SHAs. Confirm configured remotes and upstreams.
2. Create a separate worktree/branch from the intended target (`origin/main`)
   and a recoverable tag/branch for each starting tip. Do not operate in the
   recovery checkout while comparing.
3. Compare full tracked trees, file renames/deletions, schemas, migrations,
   security boundaries, workflow/deployment config and public API behavior.
   Use patch-equivalence only to identify likely duplicates; similar commit
   messages are not proof of equivalent code.
4. Map each recovery change to target files and tests. Resolve conflicts
   manually with the stronger verified behavior, preserving both valuable
   implementations where semantics differ. Never accept remote files wholesale
   over uncommitted/local security fixes.
5. Cherry-pick or manually port only reviewed, dependency-ordered changes onto
   the separate integration branch. Record provenance and adapt tests/config.
6. Run clean-clone collection, offline backend suite, frontend checks,
   changed-file lint, security regressions, schema migration tests, and
   deployment validation on the resulting tree.
7. Review the exact diff and history with the owner, then open a normal PR to
   the chosen target. Keep the recovery branch and remote intact until the
   integration is accepted. Deploy only from a reviewed, tested, immutable
   merge commit with staging and rollback evidence.

## Current disposition

No history reconciliation, merge, deployment, or push was performed as part
of this continuation. The source histories are unrelated and both contain
valuable work; the isolated tree-comparison process above is still the
required next step. The implementation branch is local and reversible; do
not merge it into either history until the semantic comparison, clean-clone
checks, integration review, and release gates in the procedure are complete.
