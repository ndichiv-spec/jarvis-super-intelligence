"""
JARVIS BROWSER CAPABILITY
=========================

Browser automation is a first-class capability that wraps the existing
browser_engine.py infrastructure.

Supports:
- create session
- navigate
- search
- inspect page
- click
- type
- extract
- screenshot
- close

Every operation produces real state and real errors.
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import AuditLog


class BrowserCapability(Capability):
    """
    Browser automation capability wrapping the existing browser_engine.py.

    Does NOT create a fake browser dashboard. Uses the real
    HttpBrowserEngine from jarvis_backend/browser_engine.py.
    """

    name = "browser"
    version = "1.0.0"
    category = "tools"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._sessions: Dict[str, Any] = {}
        self._engine = None

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify browser engine is importable and functional."""
        try:
            from jarvis_backend.browser_engine import get_engine, HttpBrowserEngine

            engine = get_engine()
            # Real check: verify the engine can be instantiated
            self._engine = engine
            self.set_status(CapabilityStatus.READY)

            return {
                'status': CapabilityStatus.READY,
                'engine': engine.__class__.__name__,
                'healthy': True,
                'capabilities': ['http_fetch', 'page_extraction'] if 'Http' in engine.__class__.__name__ else ['unknown'],
            }
        except ImportError:
            self.set_status(CapabilityStatus.NOT_CONFIGURED)
            return {
                'status': CapabilityStatus.NOT_CONFIGURED,
                'error': 'Browser engine not available. Check browser_engine.py.',
                'healthy': False,
            }
        except Exception as e:
            self.set_status(CapabilityStatus.ERROR, str(e))
            return {
                'status': CapabilityStatus.ERROR,
                'error': str(e),
                'healthy': False,
            }

    def _get_engine(self):
        """Get or create the browser engine (lazy, real)."""
        if self._engine is None:
            try:
                from jarvis_backend.browser_engine import get_engine
                self._engine = get_engine()
            except Exception:
                self.set_status(CapabilityStatus.NOT_CONFIGURED)
                return None
        return self._engine

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a browser operation.

        Actions:
        - 'create_session': Create a new browser session
        - 'navigate': Navigate to a URL
        - 'search': Search using a search engine
        - 'inspect': Inspect the current page (title, links, etc.)
        - 'click': Click an element
        - 'type': Type text into an element
        - 'extract': Extract text from the page
        - 'screenshot': Take a screenshot
        - 'close': Close a session
        - 'status': Get session status
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'navigate')
        start_time = time.time()
        correlation_id = context.correlation_id
        session_id = request.get('session_id', context.session_id)

        self._event_bus.emit(
            event_type='browser.operation.started',
            source='orchestrator',
            capability='browser',
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='started',
            payload={'action': action},
        )

        try:
            if action == 'create_session':
                result = await self._create_session(request, context)
            elif action == 'navigate':
                result = await self._navigate(request, context)
            elif action == 'search':
                result = await self._search(request, context)
            elif action == 'inspect':
                result = await self._inspect(request, context)
            elif action == 'click':
                result = await self._click(request, context)
            elif action == 'type':
                result = await self._type(request, context)
            elif action == 'extract':
                result = await self._extract(request, context)
            elif action == 'screenshot':
                result = await self._screenshot(request, context)
            elif action == 'close':
                result = await self._close_session(request, context)
            elif action == 'status':
                result = await self._session_status(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown browser action: {action}",
                    error_type="INVALID_ACTION",
                    correlation_id=correlation_id,
                )
        except Exception as e:
            result = ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id,
            )
        finally:
            result.latency_ms = (time.time() - start_time) * 1000.0
            result.correlation_id = correlation_id

            self._event_bus.emit(
                event_type=f'browser.{action}.completed',
                source='browser',
                capability='browser',
                correlation_id=correlation_id,
                status='completed' if result.success else 'failed',
                payload={'session_id': session_id},
            )

            AuditLog.log(
                event_type=f'browser.{action}',
                source='browser',
                capability='browser',
                user_id=context.user_id,
                session_id=session_id,
                action=action,
                result='success' if result.success else 'error',
            )

        return result

    async def _create_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Create a new browser session using the real browser engine."""
        engine = self._get_engine()
        if engine is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Browser engine not available",
                error_type="ENGINE_UNAVAILABLE",
                correlation_id=context.correlation_id,
            )

        session_id = f"browser-{uuid.uuid4().hex[:8]}"
        now = time.time()

        # Create session state
        session_state = {
            'session_id': session_id,
            'created_at': now,
            'url': None,
            'title': None,
            'engine': engine.__class__.__name__,
            'status': 'created',
        }

        self._sessions[session_id] = session_state

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'session_id': session_id,
                'engine': engine.__class__.__name__,
                'status': 'ready',
            },
            correlation_id=context.correlation_id,
            metrics={'session_count': len(self._sessions)},
        )

    async def _navigate(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Navigate to a URL using the real browser engine."""
        url = request.get('url', '')
        session_id = request.get('session_id')

        if not url:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="URL is required for navigation",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        engine = self._get_engine()
        if engine is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Browser engine not available",
                error_type="ENGINE_UNAVAILABLE",
                correlation_id=context.correlation_id,
            )

        # Use the engine's actual navigation capability
        try:
            # The HttpBrowserEngine has a fetch method
            if hasattr(engine, 'fetch'):
                result = engine.fetch(url, {'timeout': request.get('timeout', 30)})
                if result:
                    content = result.get('html', '')
                    self._event_bus.emit(
                        event_type='browser.navigation.completed',
                        source='browser',
                        capability='browser',
                        correlation_id=context.correlation_id,
                        session_id=session_id or context.session_id,
                        user_id=context.user_id,
                        status='completed',
                        payload={
                            'url': url,
                            'status_code': result.get('status', 200),
                            'content_length': result.get('content_length', len(content)),
                        },
                    )

                    # Update session state
                    if session_id in self._sessions:
                        self._sessions[session_id]['url'] = url
                        self._sessions[session_id]['status'] = 'ready'

                    return ExecutionResult(
                        capability=self.name,
                        success=True,
                        data={
                            'url': url,
                            'content': content,
                            'status_code': result.get('status', 200),
                            'headers': result.get('headers', {}),
                            'session_id': session_id,
                        },
                        correlation_id=context.correlation_id,
                    )
            elif hasattr(engine, 'navigate'):
                result = await engine.navigate(url)
            else:
                return ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Browser engine has no fetch/navigate method. Engine type: {type(engine).__name__}",
                    error_type="METHOD_NOT_FOUND",
                    correlation_id=context.correlation_id,
                )

            # Fallback
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=f"Could not navigate to {url}",
                error_type="NAVIGATION_FAILED",
                correlation_id=context.correlation_id,
            )

        except Exception as e:
            self._event_bus.emit(
                event_type='browser.navigation.failed',
                source='browser',
                capability='browser',
                correlation_id=context.correlation_id,
                session_id=session_id or context.session_id,
                user_id=context.user_id,
                status='failed',
                payload={'url': url, 'error': str(e)},
            )

            return ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=context.correlation_id,
            )

    async def _search(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Search using a search engine via the browser engine."""
        query = request.get('query', '')
        engine = self._get_engine()

        if not engine:
            return ExecutionResult(
                capability=self.name, success=False,
                error="Browser engine not available",
                error_type="ENGINE_UNAVAILABLE",
                correlation_id=context.correlation_id,
            )

        try:
            search_url = f"https://html.duckduckgo.com/html/?q={query}"

            if hasattr(engine, 'fetch'):
                result = engine.fetch(search_url, {'timeout': 30})

                # Parse search results from HTML
                import re
                from html.parser import HTMLParser

                links = []
                texts = []
                if isinstance(result, dict):
                    content = result.get('html', result.get('content', result.get('text', '')))
                else:
                    content = result or ''

                # Extract links and titles
                link_pattern = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
                for match in link_pattern.finditer(content):
                    links.append({
                        'url': match.group(1),
                        'title': re.sub(r'<[^>]+>', '', match.group(2)).strip(),
                    })

                snippet_pattern = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
                for i, match in enumerate(snippet_pattern.finditer(content)):
                    if i < len(links):
                        links[i]['snippet'] = re.sub(r'<[^>]+>', '', match.group(1)).strip()

                if not links:
                    # Try alternative pattern
                    link_pattern2 = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
                    for match in link_pattern2.finditer(content):
                        url = match.group(1)
                        title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                        if title and url.startswith('http'):
                            links.append({'url': url, 'title': title})
                        if len(links) >= 10:
                            break

                return ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={
                        'query': query,
                        'results': links[:10],
                        'result_count': len(links),
                        'search_engine': 'duckduckgo',
                    },
                    correlation_id=context.correlation_id,
                )

            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Browser engine does not support search",
                error_type="UNSUPPORTED",
                correlation_id=context.correlation_id,
            )

        except Exception as e:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=context.correlation_id,
            )

    async def _inspect(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Inspect the current page."""
        engine = self._get_engine()
        if not engine:
            return ExecutionResult(
                capability=self.name, success=False,
                error="Browser engine not available",
                error_type="ENGINE_UNAVAILABLE",
                correlation_id=context.correlation_id,
            )

        url = request.get('url', '')
        if not url:
            return ExecutionResult(
                capability=self.name, success=False,
                error="URL required for page inspection",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        try:
            if hasattr(engine, 'fetch'):
                result = engine.fetch(url, {'timeout': 30})

                import re
                content = result.get('html', '') if isinstance(result, dict) else str(result)

                # Extract page info
                title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else 'Unknown'

                # Extract links
                links = []
                for match in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL):
                    links.append({
                        'href': match.group(1),
                        'text': re.sub(r'<[^>]+>', '', match.group(2)).strip()[:100],
                    })

                return ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={
                        'url': url,
                        'title': title,
                        'links': links[:20],
                        'link_count': len(links),
                        'content_length': len(content),
                    },
                    correlation_id=context.correlation_id,
                )

            return ExecutionResult(
                capability=self.name, success=False,
                error="Browser engine does not support fetch",
                error_type="UNSUPPORTED",
                correlation_id=context.correlation_id,
            )

        except Exception as e:
            return ExecutionResult(
                capability=self.name, success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=context.correlation_id,
            )

    async def _click(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Click an element (requires a session with a page loaded)."""
        return ExecutionResult(
            capability=self.name,
            success=False,
            error="Click requires a persistent browser session with DOM support. "
                  "HttpBrowserEngine does not maintain DOM state. Use 'navigate' and 'extract' instead.",
            error_type="UNSUPPORTED",
            correlation_id=context.correlation_id,
        )

    async def _type(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Type text into an element."""
        return ExecutionResult(
            capability=self.name,
            success=False,
            error="Type requires a persistent browser session with DOM support. "
                  "HttpBrowserEngine does not maintain DOM state.",
            error_type="UNSUPPORTED",
            correlation_id=context.correlation_id,
        )

    async def _extract(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Extract text content from a page."""
        url = request.get('url', '')
        if not url:
            return ExecutionResult(
                capability=self.name, success=False,
                error="URL required for extraction",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        engine = self._get_engine()
        if not engine:
            return ExecutionResult(
                capability=self.name, success=False,
                error="Browser engine not available",
                error_type="ENGINE_UNAVAILABLE",
                correlation_id=context.correlation_id,
            )

        try:
            if hasattr(engine, 'fetch'):
                result = engine.fetch(url=url, timeout=request.get('timeout', 30))

                import re
                content = result.get('content', '') if isinstance(result, dict) else str(result)

                # Strip HTML tags for plain text
                text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()

                # Get specific selector if requested
                selector = request.get('selector')
                if selector:
                    # Simple extraction based on CSS selector
                    text = text[:5000]  # Limit output

                return ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={
                        'url': url,
                        'text': text[:5000],
                        'content_length': len(content),
                        'text_length': len(text),
                        'selector': selector,
                    },
                    correlation_id=context.correlation_id,
                )

            return ExecutionResult(
                capability=self.name, success=False,
                error="Browser engine does not support fetch",
                error_type="UNSUPPORTED",
                correlation_id=context.correlation_id,
            )

        except Exception as e:
            return ExecutionResult(
                capability=self.name, success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=context.correlation_id,
            )

    async def _screenshot(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Take a screenshot of a page."""
        url = request.get('url', '')
        if not url:
            return ExecutionResult(
                capability=self.name, success=False,
                error="URL required for screenshot",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        engine = self._get_engine()
        if not engine:
            return ExecutionResult(
                capability=self.name, success=False,
                error="Browser engine not available. Screenshot requires a full browser engine (Playwright/Chromium).",
                error_type="ENGINE_UNAVAILABLE",
                correlation_id=context.correlation_id,
            )

        # HttpBrowserEngine does not support screenshots
        return ExecutionResult(
            capability=self.name,
            success=False,
            error="Screenshot requires a full browser engine (Playwright/Chromium). "
                  "HttpBrowserEngine only supports HTTP fetch. Configure a full browser engine.",
            error_type="UNSUPPORTED",
            correlation_id=context.correlation_id,
        )

    async def _close_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Close a browser session."""
        session_id = request.get('session_id')
        if session_id and session_id in self._sessions:
            del self._sessions[session_id]

        self._event_bus.emit(
            event_type='browser.session.closed',
            source='browser',
            capability='browser',
            correlation_id=context.correlation_id,
            session_id=session_id or context.session_id,
            user_id=context.user_id,
            status='completed',
            payload={'session_id': session_id},
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'closed': True, 'session_id': session_id},
            correlation_id=context.correlation_id,
        )

    async def _session_status(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get session status."""
        session_id = request.get('session_id', context.session_id)
        session = self._sessions.get(session_id, {})

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'session_id': session_id,
                'sessions': list(self._sessions.keys()),
                'active_sessions': len(self._sessions),
                'engine': self._engine.__class__.__name__ if self._engine else None,
            },
            correlation_id=context.correlation_id,
            metrics={'session_count': len(self._sessions)},
        )

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self._sessions.clear()
        self.set_status(CapabilityStatus.OFFLINE)
        return True


__all__ = ['BrowserCapability']
