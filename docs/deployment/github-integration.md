# GitHub integration

JARVIS's repository control-plane connection is distinct from GitHub Actions,
which builds and publishes the application images. Configure a GitHub OAuth
application or GitHub App for the actual deployment and authorize only the
repository and permissions needed.

Use the existing JARVIS Connections/GitHub OAuth flow and server-side
credential storage. Register the callback URL exposed by the currently
configured connector route; confirm its exact path from the live OpenAPI
document before registering it. The base origin must be the real HTTPS domain,
not localhost. Supply OAuth client credentials as server-side secret material;
do not put access tokens in browser storage or ordinary event payloads.

The repository target is `ndichiv-spec/Jarvis-super-intelligence-`, default
branch `main`. The connector currently supports authenticated read/inspection
paths where the authorized installation permits them. Do not assume support
for branch creation, commits, pull requests, webhook ingestion, CI artifact
inspection, or autonomous deployment merely because the repository is
configured. Verify scopes and organization policy through GitHub's actual
authorization result; do not synthesize repository data on access failure.

The self-development approval workflow and complete universal service
connection manager described in the project brief are not delivered by the
deployment stack.
