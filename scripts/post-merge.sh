#!/bin/bash
set -e
pnpm install --frozen-lockfile
pnpm --filter db push

# Re-apply GitHub credential helper so git push origin main works without manual auth.
# The helper script reads $GITHUB_TOKEN from the environment at push time.
git config credential.helper "$(pwd)/scripts/git-credential-github.sh"
