"""
Research Tool - wraps the AutonomousResearchCortex for tool/connector execution.

This tool provides internet-aware knowledge ingestion: RSS/Atom feeds,
arXiv API search, web crawling, and knowledge graph access.
"""
from __future__ import annotations

import sys
import os
from typing import Any, Dict

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


class ResearchTool(ToolBase):
    """Research cortex tool — internet-aware knowledge ingestion."""

    name = "research"
    version = "0.1.0"
    category = "research"
    description = "Research cortex: RSS feeds, arXiv search, web crawling, knowledge graph"

    def __init__(self):
        self._cortex = None

    async def health(self) -> Dict[str, Any]:
        deps = {}
        try:
            import feedparser  # noqa: F401
            deps['feedparser'] = True
        except ImportError:
            deps['feedparser'] = False
        try:
            import aiohttp  # noqa: F401
            deps['aiohttp'] = True
        except ImportError:
            deps['aiohttp'] = False

        cortex = self._get_cortex()
        healthy = cortex is not None
        return {
            'status': 'ok' if healthy else 'unavailable',
            'healthy': healthy,
            'dependencies': deps,
            'feeds': len(cortex._feeds) if cortex else 0,
        }

    def _get_cortex(self):
        if self._cortex is None:
            try:
                from jarvis_backend.research.autonomous_research import AutonomousResearchCortex
                self._cortex = AutonomousResearchCortex()
                self._cortex.initialize()
            except ImportError:
                self._cortex = None
        return self._cortex

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        cortex = self._get_cortex()
        if not cortex:
            return {'success': False, 'error': 'Research cortex not available', 'error_type': 'ENGINE_UNAVAILABLE'}

        import asyncio

        try:
            if action == 'ingest_feed':
                feed_id = params.get('feed_id', '')
                if feed_id:
                    result = await cortex.ingest_feed(feed_id)
                else:
                    tasks = [cortex.ingest_feed(fid) for fid in cortex._feeds]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    total = sum(r.get('items_ingested', 0) for r in results if isinstance(r, dict))
                    result = {'items_ingested': total, 'feeds_processed': len(tasks)}
                return {'success': True, 'data': result}

            elif action == 'search_arxiv':
                query = params.get('query', '')
                max_results = params.get('max_results', 10)
                items = await cortex.search_arxiv(query, max_results)
                return {'success': True, 'data': {
                    'query': query, 'results': [i.to_dict() for i in items], 'count': len(items)
                }}

            elif action == 'ingest_url':
                url = params.get('url', '')
                item = await cortex.ingest_url(url)
                return {'success': True, 'data': item.to_dict() if item else {'error': 'No content'}}

            elif action == 'get_knowledge_graph':
                return {'success': True, 'data': cortex.get_knowledge_graph()}

            elif action == 'discover_new_feeds':
                feeds = await cortex.discover_new_feeds()
                return {'success': True, 'data': {'discovered_feeds': feeds}}

            elif action == 'get_status':
                return {'success': True, 'data': cortex.get_status()}

            elif action == 'ingest_content':
                content = params.get('content', '')
                title = params.get('title', '')
                source = params.get('source', 'manual')
                source_type_str = params.get('source_type', 'web_crawl')
                from jarvis_backend.research.autonomous_research import SourceType
                try:
                    st = SourceType(source_type_str)
                except ValueError:
                    st = SourceType.WEB_CRAWL
                item = cortex._create_discovered_item(title, '', source, st, content)
                if item:
                    cortex._add_discovered_item(item)
                return {'success': True, 'data': {'item_id': item.id, 'title': title} if item else {'error': 'Content too short'}}

            else:
                return {'success': False, 'error': f"Unknown action: {action}", 'error_type': 'INVALID_ACTION'}

        except Exception as e:
            return {'success': False, 'error': str(e), 'error_type': type(e).__name__}

    async def shutdown(self):
        pass


__all__ = ['ResearchTool', 'ToolBase']
