"""
Browser Tool - uses the real browser_engine infrastructure.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
import os
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class ToolBase:
    """Base class for all tools."""
    name: str = "base"
    version: str = "1.0.0"
    category: str = "tool"

    async def health(self) -> Dict[str, Any]:
        return {'status': 'unknown', 'healthy': False}

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        raise NotImplementedError


class BrowserTool(ToolBase):
    """Browser automation tool - uses the real HttpBrowserEngine."""

    name = "browser"
    version = "1.0.0"
    category = "browser"
    description = "Browse the web, fetch pages, extract content, search"

    def __init__(self):
        self._engine = None

    async def health(self) -> Dict[str, Any]:
        try:
            from jarvis_backend.browser_engine import get_engine
            engine = get_engine()
            self._engine = engine
            probe = await asyncio.to_thread(
                engine.fetch,
                "https://html.duckduckgo.com/html/?q=jarvis-runtime-health",
                {"timeout": 8},
            )
            page_error = self._failed_page_result(probe)
            if page_error:
                return {
                    "status": "unavailable",
                    "healthy": False,
                    "engine": engine.__class__.__name__,
                    "error": page_error["error"],
                }
            return {
                'status': 'ok',
                'healthy': True,
                'engine': engine.__class__.__name__,
                'endpoint': "https://html.duckduckgo.com",
            }
        except Exception as e:
            return {'status': 'error', 'healthy': False, 'error': str(e)}

    def _get_engine(self):
        if self._engine is None:
            try:
                from jarvis_backend.browser_engine import get_engine
                self._engine = get_engine()
            except Exception:
                self._engine = None
        return self._engine

    @staticmethod
    def _failed_page_result(result: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict):
            return {"success": False, "error": "Browser engine returned an invalid response", "error_type": "INVALID_RESPONSE"}
        status = result.get("status")
        if result.get("error") or (isinstance(status, int) and not 200 <= status < 400):
            return {
                "success": False,
                "error": str(result.get("error") or f"Page request returned HTTP {status}")[:300],
                "error_type": "PAGE_REQUEST_FAILED",
            }
        return None

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute a browser tool action."""
        engine = self._get_engine()
        if not engine:
            return {
                'success': False,
                'error': 'Browser engine not available',
                'error_type': 'ENGINE_UNAVAILABLE',
            }

        if action == 'fetch':
            url = params.get('url', '')
            if not url:
                return {'success': False, 'error': 'URL required', 'error_type': 'INVALID_INPUT'}

            try:
                result = engine.fetch(url, {'timeout': params.get('timeout', 30)})
                page_error = self._failed_page_result(result)
                if page_error:
                    return page_error
                if result:
                    content = result.get('html', '') if isinstance(result, dict) else str(result)
                    return {
                        'success': True,
                        'data': {
                            'url': url,
                            'content': content[:10000],
                            'content_length': len(content),
                            'status_code': result.get('status', 200) if isinstance(result, dict) else 200,
                            'headers': result.get('headers', {}) if isinstance(result, dict) else {},
                        },
                    }
                else:
                    return {'success': False, 'error': 'No content returned', 'error_type': 'EMPTY_RESPONSE'}
            except Exception as e:
                return {'success': False, 'error': str(e), 'error_type': type(e).__name__}

        elif action == 'search':
            query = str(params.get('query', '')).strip()
            if not query:
                return {'success': False, 'error': 'Query required', 'error_type': 'INVALID_INPUT'}

            try:
                raw_results = engine.search(query, max_results=10, timeout=15)
                if not isinstance(raw_results, list):
                    return {
                        'success': False,
                        'error': 'Search provider returned an invalid result list',
                        'error_type': 'INVALID_RESPONSE',
                    }

                results = []
                for rank, item in enumerate(raw_results[:10], start=1):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get('url') or '').strip()
                    parsed = urlsplit(url)
                    if (
                        parsed.scheme.lower() not in {'http', 'https'}
                        or not parsed.hostname
                        or parsed.username is not None
                        or parsed.password is not None
                    ):
                        continue
                    results.append({
                        'title': str(item.get('title') or '')[:500],
                        'url': url,
                        'snippet': str(item.get('snippet') or '')[:2000],
                        'provider': str(item.get('provider') or item.get('source') or 'unknown'),
                        'rank': int(item.get('rank') or rank),
                    })

                if raw_results and not results:
                    return {
                        'success': False,
                        'error': 'Search provider returned no links with a safe HTTP(S) destination',
                        'error_type': 'INVALID_RESPONSE',
                    }

                providers = sorted({result['provider'] for result in results})

                return {
                    'success': True,
                    'data': {
                        'query': query,
                        'results': results,
                        'result_count': len(results),
                        'provenance': {
                            'capability': 'HttpBrowserEngine.search',
                            'providers': providers,
                            'result_urls_validated': len(results),
                            'page_content_fetched': False,
                        },
                    },
                }
            except Exception as e:
                return {'success': False, 'error': str(e), 'error_type': type(e).__name__}

        elif action == 'extract_links':
            url = params.get('url', '')
            if not url:
                return {'success': False, 'error': 'URL required', 'error_type': 'INVALID_INPUT'}

            try:
                result = engine.fetch(url, {'timeout': 30})
                page_error = self._failed_page_result(result)
                if page_error:
                    return page_error
                content = result.get('html', '') if isinstance(result, dict) else str(result)

                links = []
                for match in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL):
                    links.append({
                        'href': match.group(1),
                        'text': re.sub(r'<[^>]+>', '', match.group(2)).strip()[:200],
                    })

                return {
                    'success': True,
                    'data': {
                        'url': url,
                        'links': links[:100],
                        'link_count': len(links),
                    },
                }
            except Exception as e:
                return {'success': False, 'error': str(e), 'error_type': type(e).__name__}

        elif action == 'extract_text':
            url = params.get('url', '')
            if not url:
                return {'success': False, 'error': 'URL required', 'error_type': 'INVALID_INPUT'}

            try:
                result = engine.fetch(url, {'timeout': 30})
                page_error = self._failed_page_result(result)
                if page_error:
                    return page_error
                content = result.get('html', '') if isinstance(result, dict) else str(result)

                # Strip HTML
                text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()

                return {
                    'success': True,
                    'data': {
                        'url': url,
                        'text': text[:10000],
                        'text_length': len(text),
                    },
                }
            except Exception as e:
                return {'success': False, 'error': str(e), 'error_type': type(e).__name__}

        return {
            'success': False,
            'error': f"Unknown browser action: {action}",
            'error_type': 'INVALID_ACTION',
        }

    async def shutdown(self):
        pass


__all__ = ['BrowserTool', 'ToolBase']
