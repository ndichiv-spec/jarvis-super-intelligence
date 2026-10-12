# JARVIS Git history reconciliation plan

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
- Do not include unrelated files from sibling `F:\AI` workspace paths,
  including the external `research_engine` package.
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
of this audit. The source histories are unrelated and both contain valuable
work; the isolated tree-comparison process above is the required next step.
