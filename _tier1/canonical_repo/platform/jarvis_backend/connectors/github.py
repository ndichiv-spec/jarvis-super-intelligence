"""GitHub REST access using user-scoped tokens from the encrypted OAuth vault."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from . import oauth

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubApiError(Exception):
    def __init__(self, status_code: int, detail: Dict[str, Any]) -> None:
        super().__init__(str(detail.get("message") or "GitHub request failed"))
        self.status_code = status_code
        self.detail = detail


class GitHubClient:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    async def request(
        self,
        path: str,
        *,
        params: Optional[Dict[str, str | int]] = None,
    ) -> httpx.Response:
        token = oauth.access_token("github", self.user_id)
        if not token:
            raise GitHubApiError(401, {
                "code": "AUTHORIZATION_REQUIRED",
                "service": "GitHub",
                "resource": path,
                "required_permission": "A valid GitHub OAuth authorization",
                "current_permission": "No usable GitHub access token",
                "remediation": "Authorize or reauthorize GitHub from Connections.",
            })

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    f"{GITHUB_API}{path}",
                    params=params,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {token}",
                        "X-GitHub-Api-Version": GITHUB_API_VERSION,
                        "User-Agent": "JARVIS-Connector",
                    },
                )
        except httpx.HTTPError as exc:
            raise GitHubApiError(503, {
                "code": "SERVICE_UNREACHABLE",
                "service": "GitHub",
                "resource": path,
                "reason": str(exc),
                "remediation": "Retry when GitHub is reachable.",
            }) from exc

        if response.status_code == 401:
            raise GitHubApiError(401, {
                "code": "AUTHENTICATION_FAILED",
                "service": "GitHub",
                "resource": path,
                "required_permission": "A valid GitHub OAuth authorization",
                "current_permission": "GitHub rejected the stored authorization",
                "remediation": "Reauthorize GitHub from Connections.",
            })
        if response.status_code == 403:
            raise GitHubApiError(403, {
                "code": "ACCESS_DENIED",
                "service": "GitHub",
                "resource": path,
                "required_permission": "The repository or account permission required by this operation",
                "current_permission": response.headers.get("X-OAuth-Scopes", "Not disclosed by GitHub"),
                "reason": response.headers.get("X-GitHub-SSO", "GitHub denied this operation."),
                "remediation": "Review granted scopes and organization SSO policy, then reauthorize if needed.",
            })
        if response.status_code == 404:
            raise GitHubApiError(404, {
                "code": "RESOURCE_NOT_FOUND_OR_NOT_AUTHORIZED",
                "service": "GitHub",
                "resource": path,
                "required_permission": "Read access to the requested repository or resource",
                "current_permission": response.headers.get("X-OAuth-Scopes", "Not disclosed by GitHub"),
                "reason": "GitHub returned not found; private resources may be hidden when access is insufficient.",
                "remediation": "Verify the repository name and the authorized account's repository access.",
            })
        if response.status_code >= 400:
            raise GitHubApiError(response.status_code, {
                "code": "GITHUB_REQUEST_FAILED",
                "service": "GitHub",
                "resource": path,
                "reason": f"GitHub returned HTTP {response.status_code}.",
            })
        return response

    async def user(self) -> Dict[str, Any]:
        response = await self.request("/user")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("login"), str):
            raise GitHubApiError(502, {
                "code": "INVALID_PROVIDER_RESPONSE",
                "service": "GitHub",
                "resource": "/user",
                "reason": "GitHub returned an unexpected account response.",
            })
        return {
            "id": payload.get("id"),
            "login": payload["login"],
            "name": payload.get("name"),
            "html_url": payload.get("html_url"),
        }

    async def repositories(self, page: int = 1) -> Dict[str, Any]:
        response = await self.request(
            "/user/repos",
            params={"type": "all", "sort": "updated", "per_page": 100, "page": page},
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubApiError(502, {
                "code": "INVALID_PROVIDER_RESPONSE",
                "service": "GitHub",
                "resource": "/user/repos",
                "reason": "GitHub returned an unexpected repository list.",
            })
        repositories = [
            {
                "id": item.get("id"),
                "full_name": item.get("full_name"),
                "private": item.get("private"),
                "description": item.get("description"),
                "default_branch": item.get("default_branch"),
                "html_url": item.get("html_url"),
                "updated_at": item.get("updated_at"),
                "permissions": item.get("permissions"),
            }
            for item in payload
            if isinstance(item, dict)
        ]
        link = response.headers.get("Link", "")
        return {
            "repositories": repositories,
            "page": page,
            "per_page": 100,
            "has_next_page": 'rel="next"' in link,
        }

    async def repository(self, owner: str, name: str) -> Dict[str, Any]:
        path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        response = await self.request(path)
        data = response.json()
        if not isinstance(data, dict):
            raise GitHubApiError(502, {
                "code": "INVALID_PROVIDER_RESPONSE",
                "service": "GitHub",
                "resource": path,
                "reason": "GitHub returned an unexpected repository response.",
            })
        return {
            "id": data.get("id"),
            "full_name": data.get("full_name"),
            "private": data.get("private"),
            "description": data.get("description"),
            "default_branch": data.get("default_branch"),
            "html_url": data.get("html_url"),
            "updated_at": data.get("updated_at"),
            "permissions": data.get("permissions"),
        }

    async def file(self, owner: str, name: str, path: str) -> Dict[str, Any]:
        repository_path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        encoded_path = quote(path.strip("/"), safe="/")
        response = await self.request(f"{repository_path}/contents/{encoded_path}")
        data = response.json()
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubApiError(422, {
                "code": "UNSUPPORTED_CONTENT_TYPE",
                "service": "GitHub",
                "resource": f"{owner}/{name}/{path}",
                "reason": "The requested GitHub content is not a single file.",
            })
        raw_content = data.get("content")
        decoded_content: Optional[str] = None
        is_binary = False
        if data.get("encoding") == "base64" and isinstance(raw_content, str):
            try:
                decoded_content = base64.b64decode(
                    raw_content.replace("\n", ""),
                    validate=True,
                ).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                is_binary = True
        elif isinstance(raw_content, str):
            decoded_content = raw_content
        return {
            "path": data.get("path"),
            "sha": data.get("sha"),
            "size": data.get("size"),
            "content": decoded_content,
            "binary": is_binary,
            "html_url": data.get("html_url"),
        }
