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
            query = params.get('query', '')
            if not query:
                return {'success': False, 'error': 'Query required', 'error_type': 'INVALID_INPUT'}

            from urllib.parse import quote_plus
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            try:
                result = engine.fetch(search_url, {'timeout': 30})
                page_error = self._failed_page_result(result)
                if page_error:
                    return page_error
                content = result.get('html', '') if isinstance(result, dict) else str(result)

                # Parse DuckDuckGo results
                links = re.findall(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    content, re.DOTALL | re.IGNORECASE
                )
                snippets = re.findall(
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    content, re.DOTALL | re.IGNORECASE
                )

                results = []
                for i, (url, title) in enumerate(links[:10]):
                    title_text = re.sub(r'<[^>]+>', '', title).strip()
                    snippet_text = re.sub(r'<[^>]+>', '',
                                          snippets[i] if i < len(snippets) else '').strip()
                    results.append({
                        'title': title_text,
                        'url': url,
                        'snippet': snippet_text,
                    })

                return {
                    'success': True,
                    'data': {
                        'query': query,
                        'results': results,
                        'result_count': len(results),
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
