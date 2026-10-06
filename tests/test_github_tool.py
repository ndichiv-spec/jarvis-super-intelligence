from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from jarvis_backend.capability import ExecutionContext
from jarvis_backend.capabilities.tools.github import GitHubTool


@pytest.mark.asyncio
async def test_github_tool_uses_the_authenticated_users_oauth_grant(monkeypatch):
    from jarvis_backend.connectors import oauth

    requested = []
    monkeypatch.setattr(
        oauth,
        "access_token",
        lambda provider, user_id: requested.append((provider, user_id)) or "account-scoped-token",
    )
    tool = GitHubTool()
    token = tool._get_token("workspace-user")

    assert token == "account-scoped-token"
    assert tool._token_source == "oauth"
    assert requested == [("github", "workspace-user")]


def test_production_github_connector_does_not_fall_back_to_shared_credentials(monkeypatch):
    from jarvis_backend.connectors import oauth

    monkeypatch.setenv("JARVIS_ENV", "production")
    monkeypatch.setenv("GITHUB_TOKEN", "shared-environment-token")
    monkeypatch.setattr(oauth, "access_token", lambda _provider, _user_id: None)

    tool = GitHubTool()
    assert tool._get_token("workspace-user") is None


@pytest.mark.asyncio
async def test_github_update_file_encodes_content_and_uses_current_revision(monkeypatch):
    import requests

    calls = []

    class Response:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def get(url, **kwargs):
        calls.append(("get", url, kwargs))
        if url.endswith("/repos/acme/project"):
            return Response({"default_branch": "main"})
        return Response({"sha": "existing-sha"})

    def put(url, **kwargs):
        calls.append(("put", url, kwargs))
        return Response({
            "content": {
                "path": "docs/guide.md",
                "sha": "updated-sha",
                "html_url": "https://github.com/acme/project/blob/main/docs/guide.md",
            },
            "commit": {
                "sha": "commit-sha",
                "html_url": "https://github.com/acme/project/commit/commit-sha",
            },
        })

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    tool = GitHubTool()
    monkeypatch.setattr(tool, "_get_token", lambda user_id=None: "authorized-token")

    result = await tool.execute(
        "update_file",
        {
            "owner": "acme",
            "repo": "project",
            "path": "docs/guide.md",
            "content": "Updated guide\n",
            "message": "Update guide",
            "branch": "jarvis/docs-guide",
        },
        ExecutionContext(user_id="workspace-user", session_id="test"),
    )

    assert result["success"] is True
    assert result["data"]["commit_sha"] == "commit-sha"
    assert [call[0] for call in calls] == ["get", "get", "put"]
    assert calls[1][2]["params"] == {"ref": "jarvis/docs-guide"}
    payload = calls[2][2]["json"]
    assert payload["sha"] == "existing-sha"
    assert payload["branch"] == "jarvis/docs-guide"
    assert base64.b64decode(payload["content"]).decode() == "Updated guide\n"


@pytest.mark.asyncio
async def test_github_update_file_rejects_path_traversal_before_request(monkeypatch):
    import requests

    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid paths must not reach the GitHub API")

    monkeypatch.setattr(requests, "get", fail_if_called)
    monkeypatch.setattr(requests, "put", fail_if_called)
    tool = GitHubTool()
    monkeypatch.setattr(tool, "_get_token", lambda user_id=None: "authorized-token")

    result = await tool.execute(
        "update_file",
        {
            "owner": "acme",
            "repo": "project",
            "path": "../secrets.txt",
            "content": "no",
            "message": "invalid",
        },
        SimpleNamespace(user_id="workspace-user"),
    )

    assert result["success"] is False
    assert result["error_type"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_github_update_file_refuses_default_branch_writes(monkeypatch):
    import requests

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"default_branch": "jarvis/main"}

    calls = []
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
    )
    monkeypatch.setattr(
        requests,
        "put",
        lambda *args, **kwargs: pytest.fail("default-branch writes must be blocked"),
    )
    tool = GitHubTool()
    monkeypatch.setattr(tool, "_get_token", lambda user_id=None: "authorized-token")

    result = await tool.execute(
        "update_file",
        {
            "owner": "acme",
            "repo": "project",
            "path": "README.md",
            "content": "not on default",
            "message": "attempt default-branch update",
            "branch": "jarvis/main",
        },
        SimpleNamespace(user_id="workspace-user"),
    )

    assert result["success"] is False
    assert result["error_type"] == "PROTECTED_BRANCH"
    assert len(calls) == 1
