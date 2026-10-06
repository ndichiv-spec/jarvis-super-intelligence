"""
JARVIS RESEARCH CORTEX CAPABILITY
==================================

Internet-aware knowledge ingestion: RSS feeds, arXiv, web crawling,
GitHub trending, and semantic analysis. Builds a knowledge DAG of
discovered concepts and their relationships.

Actions:
- 'initialize': Initialize seed feeds and knowledge graph
- 'ingest_feed': Ingest items from a specific RSS/Atom feed
- 'search_arxiv': Search arXiv API for scientific papers
- 'ingest_url': Crawl and digest a web URL
- 'get_knowledge_graph': Retrieve the knowledge graph
- 'discover_new_feeds': Discover new RSS feeds from content
- 'get_status': Get cortex status and metrics
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import (
    Capability, CapabilityStatus, ExecutionContext, ExecutionResult
)
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import AuditLog


class ResearchCortexCapability(Capability):
    """
    Research Cortex capability — JARVIS's internet-aware knowledge ingestion layer.

    Wraps AutonomousResearchCortex to discover, fetch, and digest
    technological knowledge from RSS feeds, arXiv, web crawling,
    and GitHub trending.
    """

    name = "research.cortex"
    version = "1.0.0"
    category = "research"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._cortex = None
        self._initialized = False

    def _get_cortex(self):
        """Lazy-load the research cortex."""
        if self._cortex is None:
            try:
                from jarvis_backend.research.autonomous_research import AutonomousResearchCortex
                self._cortex = AutonomousResearchCortex()
                self._initialized = True
            except ImportError:
                pass
        return self._cortex

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check — verify research infrastructure."""
        cortex_available = False
        feedparser_available = False
        aiohttp_available = False
        feeds_active = 0

        cortex = self._get_cortex()
        if cortex is not None:
            cortex_available = True
            feeds_active = len(cortex._feeds)
            if cortex._initialized:
                feeds_active = len(cortex._feeds)

        # Check optional dependencies
        try:
            import feedparser  # noqa: F401
            feedparser_available = True
        except ImportError:
            pass

        try:
            import aiohttp  # noqa: F401
            aiohttp_available = True
        except ImportError:
            pass

        all_ok = cortex_available
        return {
            'status': CapabilityStatus.READY if all_ok else CapabilityStatus.NOT_CONFIGURED,
            'healthy': all_ok,
            'cortex_available': cortex_available,
            'feedparser_available': feedparser_available,
            'aiohttp_available': aiohttp_available,
            'feeds_active': feeds_active,
            'initialized': self._initialized,
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a research cortex operation."""
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'status')
        start_time = time.time()
        correlation_id = context.correlation_id

        cortex = self._get_cortex()
        if cortex is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Research cortex not available",
                error_type="NOT_AVAILABLE",
                correlation_id=correlation_id,
            )

        try:
            if action == 'initialize':
                cortex.initialize()
                result_data = cortex.get_status()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=result_data,
                    correlation_id=correlation_id,
                    metrics={'feeds': result_data.get('total_feeds', 0)},
                )

            elif action == 'ingest_feed':
                feed_id = request.get('feed_id')
                if not feed_id:
                    # Ingest all feeds
                    tasks = [cortex.ingest_feed(fid) for fid in cortex._feeds]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    total_items = sum(r.get('items_ingested', 0) for r in results if isinstance(r, dict))
                else:
                    r = await cortex.ingest_feed(feed_id)
                    total_items = r.get('items_ingested', 0)
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={'items_ingested': total_items},
                    correlation_id=correlation_id,
                )

            elif action == 'search_arxiv':
                query = request.get('query', '')
                max_results = request.get('max_results', 10)
                items = await cortex.search_arxiv(query, max_results)
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={'query': query, 'results': [i.to_dict() for i in items], 'count': len(items)},
                    correlation_id=correlation_id,
                )

            elif action == 'ingest_url':
                url = request.get('url', '')
                item = await cortex.ingest_url(url)
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=item.to_dict() if item else {'error': 'No content retrieved'},
                    correlation_id=correlation_id,
                )

            elif action == 'get_knowledge_graph':
                graph = cortex.get_knowledge_graph()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=graph,
                    correlation_id=correlation_id,
                )

            elif action == 'discover_new_feeds':
                feeds = await cortex.discover_new_feeds()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={'discovered_feeds': feeds},
                    correlation_id=correlation_id,
                )

            elif action == 'get_status':
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=cortex.get_status(),
                    correlation_id=correlation_id,
                )

            elif action == 'semantic_search':
                query = request.get('query', '')
                limit = request.get('limit', 10)
                source = request.get('source', 'knowledge_graph')
                search_results = cortex.semantic_search(query, limit=limit, source=source)
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={'query': query, 'results': search_results, 'count': len(search_results)},
                    correlation_id=correlation_id,
                )

            elif action == 'ingest_content':
                # Ingest arbitrary content directly
                content = request.get('content', '')
                title = request.get('title', '')
                source = request.get('source', 'manual')
                source_type = request.get('source_type', 'web_crawl')
                item = cortex._create_discovered_item(title, '', source, SourceType(source_type), content)
                if item:
                    cortex._add_discovered_item(item)
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={'item_id': item.id, 'title': title} if item else {'error': 'Content too short'},
                    correlation_id=correlation_id,
                )

            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown action: {action}",
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

        result.latency_ms = (time.time() - start_time) * 1000.0
        self._event_bus.emit(
            event_type=f'research.{action}.completed',
            source='orchestrator',
            capability=self.name,
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed' if result.success else 'failed',
            payload={'action': action, 'success': result.success},
        )

        AuditLog.log(
            event_type=f'research.{action}',
            source=self.name,
            capability=self.name,
            user_id=context.user_id,
            session_id=context.session_id,
            action=action,
            result='success' if result.success else 'error',
        )

        return result

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        if self._cortex:
            self._cortex = None
        self.set_status(CapabilityStatus.OFFLINE)
        return True


# Import for SourceType used in execute
from jarvis_backend.research.autonomous_research import SourceType  # noqa: E402
