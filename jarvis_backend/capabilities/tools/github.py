"""
GitHub Connector Tool
======================

Demonstrates a genuinely useful connector end-to-end using existing infrastructure.

Flow:
    Brain
    |- Tool request
    |- Authorization
    |- GitHub connector
    |- Secure credential access (via vault)
    |- External system (GitHub API)
    |- Sanitized result
    |- Brain
    |- Conversation

Credentials are accessed through the existing vault/secrets manager,
never passed from the Brain or conversation.
"""
from __future__ import annotations

import json
import os
import sys
import base64
import re
from typing import Any, Dict, Optional
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class GitHubTool:
    """
    GitHub API connector tool.

    Demonstrates the full connector pattern:
    1. Brain requests a GitHub operation
    2. Authorization is checked
    3. The connector accesses credentials through the vault
    4. GitHub API is called
    5. Results are sanitized
    """

    name = "github"
    version = "1.0.0"
    category = "connector"
    description = "GitHub API integration for repos, issues, PRs, commits"

    def __init__(self):
        self._token = None
        self._token_source = None

    async def health(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Real health check - verify GitHub API connectivity."""
        token = self._get_token(user_id)
        if not token:
            return {
                'status': 'not_configured',
                'healthy': False,
                'error': 'No GitHub token configured. Set GITHUB_TOKEN or configure via vault.',
            }

        try:
            import requests
            headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
            resp = requests.get('https://api.github.com/user', headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    'status': 'ok',
                    'healthy': True,
                    'user': data.get('login', 'unknown'),
                    'name': data.get('name', ''),
                    'rate_limit_remaining': resp.headers.get('X-RateLimit-Remaining', 'unknown'),
                }
            else:
                return {
                    'status': 'error',
                    'healthy': False,
                    'error': f'GitHub API returned {resp.status_code}',
                }
        except Exception as e:
            return {
                'status': 'error',
                'healthy': False,
                'error': f'GitHub API connection failed: {str(e)[:200]}',
            }

    def _get_token(self, user_id: Optional[str] = None) -> Optional[str]:
        """Get GitHub token from vault or environment.
        
        Credentials are NEVER passed from the Brain or conversation.
        They come from the secret boundary only.
        """
        if user_id and user_id != "anonymous":
            from jarvis_backend.connectors.oauth import access_token

            token = access_token("github", user_id)
            if token:
                self._token = token
                self._token_source = "oauth"
                return token

        if os.environ.get("JARVIS_ENV", "").strip().lower() in {"production", "prod"}:
            return None

        # Try vault first
        try:
            from infrastructure.vault.manager import get_secrets_manager
            token = get_secrets_manager().get_or_none('github_token')
            if token:
                self._token = token
                self._token_source = 'vault'
                return token
        except Exception:
            pass

        # Try environment
        token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
        if token:
            self._token = token
            self._token_source = 'environment'
            return token

        return None

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute a GitHub API operation."""
        import requests

        token = self._get_token(getattr(context, "user_id", None))
        if not token:
            return {
                'success': False,
                'error': 'GitHub token not configured. Set GITHUB_TOKEN env var or configure via vault.',
                'error_type': 'NOT_CONFIGURED',
            }

        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
        base_url = 'https://api.github.com'

        try:
            if action == 'get_repo':
                owner = params.get('owner', '')
                repo = params.get('repo', '')
                if not owner or not repo:
                    return {'success': False, 'error': 'owner and repo are required', 'error_type': 'INVALID_INPUT'}

                resp = requests.get(f'{base_url}/repos/{owner}/{repo}', headers=headers, timeout=15)

                if resp.status_code == 200:
                    data = resp.json()
                    # Sanitize: only return safe fields
                    return {
                        'success': True,
                        'data': {
                            'name': data.get('name', ''),
                            'full_name': data.get('full_name', ''),
                            'description': data.get('description', ''),
                            'default_branch': data.get('default_branch', ''),
                            'private': data.get('private', False),
                            'stargazers_count': data.get('stargazers_count', 0),
                            'forks_count': data.get('forks_count', 0),
                            'open_issues_count': data.get('open_issues_count', 0),
                            'created_at': data.get('created_at', ''),
                            'updated_at': data.get('updated_at', ''),
                            'language': data.get('language', ''),
                            'html_url': data.get('html_url', ''),
                        },
                    }
                else:
                    return self._handle_error(resp, 'get_repo')

            elif action == 'list_repos':
                org = params.get('org', '')
                if org:
                    resp = requests.get(f'{base_url}/orgs/{org}/repos', headers=headers, timeout=15,
                                        params={'per_page': 100})
                else:
                    resp = requests.get(f'{base_url}/user/repos', headers=headers, timeout=15,
                                        params={'per_page': 100})

                if resp.status_code == 200:
                    data = resp.json()
                    repos = [{
                        'name': r.get('name', ''),
                        'full_name': r.get('full_name', ''),
                        'description': r.get('description', ''),
                        'private': r.get('private', False),
                        'stargazers_count': r.get('stargazers_count', 0),
                        'language': r.get('language', ''),
                    } for r in data]
                    return {
                        'success': True,
                        'data': {'repos': repos, 'count': len(repos)},
                    }
                else:
                    return self._handle_error(resp, 'list_repos')

            elif action == 'list_issues':
                owner = params.get('owner', '')
                repo = params.get('repo', '')
                state = params.get('state', 'open')
                if not owner or not repo:
                    return {'success': False, 'error': 'owner and repo required', 'error_type': 'INVALID_INPUT'}

                resp = requests.get(
                    f'{base_url}/repos/{owner}/{repo}/issues',
                    headers=headers, timeout=15,
                    params={'state': state, 'per_page': 50}
                )

                if resp.status_code == 200:
                    data = resp.json()
                    issues = [{
                        'number': i.get('number', 0),
                        'title': i.get('title', ''),
                        'state': i.get('state', ''),
                        'created_at': i.get('created_at', ''),
                        'updated_at': i.get('updated_at', ''),
                        'labels': [l.get('name', '') for l in i.get('labels', [])],
                        'author': i.get('user', {}).get('login', ''),
                        'url': i.get('html_url', ''),
                    } for i in data if 'pull_request' not in i]
                    return {
                        'success': True,
                        'data': {'issues': issues, 'count': len(issues), 'repo': f'{owner}/{repo}'},
                    }
                else:
                    return self._handle_error(resp, 'list_issues')

            elif action == 'list_commits':
                owner = params.get('owner', '')
                repo = params.get('repo', '')
                per_page = params.get('per_page', 10)
                if not owner or not repo:
                    return {'success': False, 'error': 'owner and repo required', 'error_type': 'INVALID_INPUT'}

                resp = requests.get(
                    f'{base_url}/repos/{owner}/{repo}/commits',
                    headers=headers, timeout=15,
                    params={'per_page': per_page}
                )

                if resp.status_code == 200:
                    data = resp.json()
                    commits = [{
                        'sha': c.get('sha', '')[:12],
                        'message': c.get('commit', {}).get('message', '')[:200],
                        'author': c.get('commit', {}).get('author', {}).get('name', ''),
                        'date': c.get('commit', {}).get('author', {}).get('date', ''),
                        'url': c.get('html_url', ''),
                    } for c in data]
                    return {
                        'success': True,
                        'data': {'commits': commits, 'count': len(commits), 'repo': f'{owner}/{repo}'},
                    }
                else:
                    return self._handle_error(resp, 'list_commits')

            elif action == 'create_issue':
                owner = params.get('owner', '')
                repo = params.get('repo', '')
                title = params.get('title', '')
                body = params.get('body', '')

                if not owner or not repo or not title:
                    return {'success': False, 'error': 'owner, repo, and title required', 'error_type': 'INVALID_INPUT'}

                resp = requests.post(
                    f'{base_url}/repos/{owner}/{repo}/issues',
                    headers=headers, timeout=15,
                    json={'title': title, 'body': body}
                )

                if resp.status_code == 201:
                    data = resp.json()
                    return {
                        'success': True,
                        'data': {
                            'number': data.get('number', 0),
                            'title': data.get('title', ''),
                            'url': data.get('html_url', ''),
                            'state': data.get('state', ''),
                        },
                    }
                else:
                    return self._handle_error(resp, 'create_issue')

            elif action == 'update_file':
                owner = params.get('owner', '')
                repo = params.get('repo', '')
                path = params.get('path', '')
                content = params.get('content')
                message = params.get('message', '')
                if (
                    not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', owner)
                    or not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo)
                ):
                    return {'success': False, 'error': 'A valid owner and repository name are required', 'error_type': 'INVALID_INPUT'}
                if (
                    not isinstance(path, str) or not path or path.startswith('/')
                    or '\\' in path or any(part in {'', '.', '..'} for part in path.split('/'))
                ):
                    return {'success': False, 'error': 'path must be a repository-relative file path', 'error_type': 'INVALID_INPUT'}
                if not isinstance(content, str) or not isinstance(message, str) or not message.strip():
                    return {'success': False, 'error': 'content and a commit message are required', 'error_type': 'INVALID_INPUT'}
                branch = params.get('branch')
                if (
                    not isinstance(branch, str)
                    or not re.fullmatch(r'jarvis/[A-Za-z0-9][A-Za-z0-9._/-]*', branch)
                    or any(part in {'', '.', '..'} for part in branch.split('/'))
                ):
                    return {
                        'success': False,
                        'error': 'File writes require an explicit development branch under jarvis/',
                        'error_type': 'INVALID_INPUT',
                    }
                encoded_content = content.encode('utf-8')
                if len(encoded_content) > 1_000_000:
                    return {'success': False, 'error': 'content exceeds the 1 MB limit', 'error_type': 'INVALID_INPUT'}

                file_url = (
                    f'{base_url}/repos/{quote(owner, safe="")}/{quote(repo, safe="")}'
                    f'/contents/{quote(path, safe="/")}'
                )
                repo_resp = requests.get(
                    f'{base_url}/repos/{quote(owner, safe="")}/{quote(repo, safe="")}',
                    headers=headers,
                    timeout=15,
                )
                if repo_resp.status_code != 200:
                    return self._handle_error(repo_resp, 'update_file')
                if branch == repo_resp.json().get('default_branch'):
                    return {
                        'success': False,
                        'error': 'Direct writes to the repository default branch are not allowed',
                        'error_type': 'PROTECTED_BRANCH',
                    }
                sha = params.get('sha')
                if sha is None:
                    current = requests.get(
                        file_url,
                        headers=headers,
                        params={'ref': branch},
                        timeout=15,
                    )
                    if current.status_code == 200:
                        sha = current.json().get('sha')
                        if not sha:
                            return {'success': False, 'error': 'GitHub did not return the current file revision', 'error_type': 'API_ERROR'}
                    elif current.status_code != 404:
                        return self._handle_error(current, 'update_file')

                payload = {
                    'message': message.strip(),
                    'content': base64.b64encode(encoded_content).decode('ascii'),
                    'branch': branch,
                }
                if sha:
                    payload['sha'] = sha
                resp = requests.put(file_url, headers=headers, json=payload, timeout=20)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    commit = data.get('commit') or {}
                    file_data = data.get('content') or {}
                    return {
                        'success': True,
                        'data': {
                            'path': file_data.get('path', path),
                            'sha': file_data.get('sha'),
                            'commit_sha': commit.get('sha'),
                            'commit_url': commit.get('html_url'),
                            'html_url': file_data.get('html_url'),
                        },
                    }
                return self._handle_error(resp, 'update_file')

            else:
                return {
                    'success': False,
                    'error': f"Unknown GitHub action: {action}. "
                             "Available: get_repo, list_repos, list_issues, list_commits, create_issue, "
                             "update_file (jarvis/* branches only)",
                    'error_type': 'INVALID_ACTION',
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'GitHub API error: {str(e)[:200]}',
                'error_type': type(e).__name__,
            }

    def _handle_error(self, resp, action: str) -> Dict[str, Any]:
        """Handle API errors with sanitized messages."""
        import json as _json
        try:
            error_data = resp.json()
            error_msg = error_data.get('message', 'Unknown API error')
        except Exception:
            error_msg = f'HTTP {resp.status_code}'

        return {
            'success': False,
            'error': f'GitHub API error ({action}): {error_msg}',
            'error_type': 'API_ERROR',
            'status_code': resp.status_code,
        }

    async def shutdown(self):
        self._token = None
        self._token_source = None


__all__ = ['GitHubTool']
