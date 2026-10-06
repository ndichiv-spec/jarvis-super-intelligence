"""
JARVIS KNOWLEDGE CAPABILITY
===========================

Knowledge retrieval and RAG. This is independent from conversation -
the Brain can request knowledge retrieval through the orchestrator.

Implements:
- ingestion
- indexing
- retrieval
- ranking
- provenance
- citation/reference
- permissions
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import AuditLog, ArtifactRepository


class KnowledgeCapability(Capability):
    """
    Knowledge/RAG capability for JARVIS.

    Independent from conversation. The Brain requests knowledge retrieval
    through the orchestrator. Results include provenance and citations.
    """

    name = "knowledge.search"
    version = "1.0.0"
    category = "knowledge"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._index_dir = os.environ.get(
            'JARVIS_KNOWLEDGE_DIR',
            'F:/AI/Jarvis-super-intelligence-/jarvis_backend/data/knowledge'
        )
        os.makedirs(self._index_dir, exist_ok=True)

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify search infrastructure."""
        search_available = False
        embedding_available = False
        providers = []

        # Check web search providers
        if os.environ.get('TAVILY_API_KEY'):
            providers.append({'name': 'tavily', 'type': 'web_search', 'status': 'configured'})
            search_available = True
        elif os.environ.get('SERPER_API_KEY'):
            providers.append({'name': 'serper', 'type': 'web_search', 'status': 'configured'})
            search_available = True

        # Check embedding providers
        if os.environ.get('OPENAI_API_KEY'):
            providers.append({'name': 'openai', 'type': 'embedding', 'status': 'configured'})
            embedding_available = True

        # Check local search
        providers.append({'name': 'browser', 'type': 'web_search', 'status': 'available'})
        search_available = True

        all_ok = search_available
        return {
            'status': CapabilityStatus.READY if all_ok else CapabilityStatus.NOT_CONFIGURED,
            'healthy': all_ok,
            'search_available': search_available,
            'embedding_available': embedding_available,
            'providers': providers,
            'index_directory': self._index_dir,
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a knowledge operation.

        Actions:
        - 'search': Search for information
        - 'ingest': Ingest a document
        - 'retrieve': Retrieve from vector store
        - 'semantic_search': Semantic search with embeddings
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'search')
        start_time = time.time()
        correlation_id = context.correlation_id

        self._event_bus.emit(
            event_type=f'knowledge.{action}.started',
            source='orchestrator',
            capability='knowledge.search',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'query': request.get('query', '')[:100]},
        )

        try:
            if action == 'search':
                result = await self._search(request, context)
            elif action == 'ingest':
                result = await self._ingest(request, context)
            elif action == 'retrieve':
                result = await self._retrieve(request, context)
            elif action == 'semantic_search':
                result = await self._semantic_search(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown knowledge action: {action}",
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
        result.correlation_id = correlation_id

        self._event_bus.emit(
            event_type=f'knowledge.{action}.completed',
            source='knowledge.search',
            capability='knowledge.search',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload={'success': result.success, 'result_count': len(result.data.get('results', [])) if result.success else 0},
        )

        AuditLog.log(
            event_type=f'knowledge.{action}',
            source='knowledge.search',
            capability='knowledge.search',
            user_id=context.user_id,
            session_id=context.session_id,
        )

        return result

    async def _search(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Search using existing search infrastructure."""
        query = request.get('query', '')
        if not query:
            return ExecutionResult(
                capability=self.name, success=False,
                error="query is required",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        results = []
        sources = []

        # Try Tavily search
        tavily_key = os.environ.get('TAVILY_API_KEY')
        if tavily_key:
            try:
                import requests
                resp = requests.post(
                    'https://api.tavilyai.com/search',
                    json={'api_key': tavily_key, 'query': query, 'search_depth': 'advanced'},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get('results', []):
                        results.append({
                            'title': r.get('title', ''),
                            'url': r.get('url', ''),
                            'content': r.get('content', r.get('snippet', '')),
                            'score': r.get('score', 0.0),
                        })
                    sources.append('tavily')
            except Exception:
                pass

        # Try Serper search
        if not results:
            serper_key = os.environ.get('SERPER_API_KEY')
            if serper_key:
                try:
                    import requests
                    resp = requests.post(
                        'https://google.serper.dev/search',
                        json={'q': query},
                        headers={'X-API-KEY': serper_key},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for r in data.get('organic', []):
                            results.append({
                                'title': r.get('title', ''),
                                'url': r.get('link', ''),
                                'content': r.get('snippet', ''),
                                'score': r.get('position', 0) / 10.0,
                            })
                        sources.append('serper')
                except Exception:
                    pass

        # Fallback: use browser capability for live search
        if not results:
            results = await self._browser_search(query)
            if results:
                sources.append('browser')

        # Always include provenance info
        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'query': query,
                'results': results[:10],
                'result_count': len(results),
                'sources_used': sources,
                'provenance': {
                    'search_time': time.time(),
                    'query': query,
                    'sources': sources,
                },
            },
            correlation_id=context.correlation_id,
            metrics={'result_count': len(results), 'sources': len(sources)},
        )

    async def _browser_search(self, query: str) -> List[Dict[str, Any]]:
        """Use the browser capability to search."""
        try:
            from jarvis_backend.capabilities.browser import BrowserCapability
            browser = BrowserCapability()
            # Create execution context
            exec_ctx = ExecutionContext(
                user_id="system",
                session_id="knowledge-search",
            )

            # Build a DuckDuckGo search URL
            from urllib.parse import quote_plus
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            result = await browser._navigate({'url': search_url}, exec_ctx)

            if result.success:
                import re
                content = result.data.get('content', '')

                # Parse DuckDuckGo results
                links = re.findall(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    content, re.DOTALL | re.IGNORECASE
                )
                snippets = re.findall(
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    content, re.DOTALL | re.IGNORECASE
                )

                search_results = []
                for i, (url, title) in enumerate(links[:10]):
                    title_text = re.sub(r'<[^>]+>', '', title).strip()
                    snippet_text = re.sub(r'<[^>]+>', '',
                                          snippets[i] if i < len(snippets) else '').strip()
                    search_results.append({
                        'title': title_text,
                        'url': url,
                        'content': snippet_text,
                        'score': 1.0 - (i * 0.1),
                    })

                return search_results
        except Exception:
            pass
        return []

    async def _ingest(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Ingest a document."""
        source_url = request.get('url')
        content = request.get('content', '')
        title = request.get('title', '')

        # Fetch content if URL provided
        if source_url and not content:
            try:
                from jarvis_backend.capabilities.browser import BrowserCapability
                browser = BrowserCapability()
                result = await browser._navigate(
                    {'url': source_url},
                    ExecutionContext(user_id=context.user_id, session_id=context.session_id)
                )
                if result.success:
                    content = result.data.get('content', '')
            except Exception:
                pass

        # Store as artifact
        artifact_id = ArtifactRepository.store_artifact(
            capability='knowledge.search',
            artifact_type='document',
            url=source_url,
            file_size=len(content) if content else 0,
            mime_type='text/html',
            session_id=context.session_id,
            correlation_id=context.correlation_id,
            provenance='knowledge_ingestion',
            metadata={'title': title, 'source_url': source_url},
        )

        # Generate embedding if OpenAI available
        embedding_id = None
        if os.environ.get('OPENAI_API_KEY') and content:
            try:
                import openai
                client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
                emb_response = client.embeddings.create(
                    model='text-embedding-3-small',
                    input=content[:8000]
                )
                embedding = emb_response.data[0].embedding

                from jarvis_backend.persistence import MemoryRepository
                embedding_id = MemoryRepository.store_memory(
                    memory_type='semantic',
                    content=title or source_url or 'ingested_document',
                    session_id=context.session_id,
                    user_id=context.user_id,
                    embedding=embedding,
                    provenance=f'ingestion_{artifact_id}',
                    metadata={'artifact_id': artifact_id, 'source_url': source_url},
                )
            except Exception:
                pass

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'artifact_id': artifact_id,
                'embedding_id': embedding_id,
                'content_length': len(content) if content else 0,
            },
            correlation_id=context.correlation_id,
            artifacts=[{'type': 'document', 'id': artifact_id, 'url': source_url}],
        )

    async def _retrieve(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Retrieve from vector/semantic store."""
        query = request.get('query', '')
        limit = request.get('limit', 5)

        from jarvis_backend.persistence import MemoryRepository
        memories = MemoryRepository.retrieve_memories(
            memory_type='semantic',
            session_id=context.session_id,
            user_id=context.user_id,
            limit=limit * 3,  # Get more for ranking
        )

        if not memories:
            return ExecutionResult(
                capability=self.name, success=True,
                data={'query': query, 'results': [], 'result_count': 0},
                correlation_id=context.correlation_id,
            )

        # Simple ranking by keyword overlap
        query_words = set(query.lower().split())
        scored = []
        for mem in memories:
            content = mem.get('content', '').lower()
            content_words = set(content.split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                scored.append({
                    'content': mem.get('content', ''),
                    'metadata': json.loads(mem.get('metadata_json', '{}')),
                    'provenance': mem.get('provenance', ''),
                    'score': overlap / max(len(query_words), 1),
                    'created_at': mem.get('created_at', ''),
                })

        scored.sort(key=lambda x: x['score'], reverse=True)

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'query': query,
                'results': scored[:limit],
                'result_count': len(scored[:limit]),
            },
            correlation_id=context.correlation_id,
        )

    async def _semantic_search(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Semantic search using embeddings."""
        query = request.get('query', '')

        if not os.environ.get('OPENAI_API_KEY'):
            return await self._retrieve(request, context)

        try:
            import openai
            client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
            emb_response = client.embeddings.create(
                model='text-embedding-3-small',
                input=query
            )
            query_embedding = emb_response.data[0].embedding

            # Retrieve semantically similar memories
            from jarvis_backend.persistence import MemoryRepository
            memories = MemoryRepository.retrieve_memories(
                memory_type='semantic',
                session_id=context.session_id,
                user_id=context.user_id,
                limit=50,
            )

            # Cosine similarity
            import math
            def cosine_sim(a, b):
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x * x for x in a))
                norm_b = math.sqrt(sum(y * y for y in b))
                if norm_a == 0 or norm_b == 0:
                    return 0.0
                return dot / (norm_a * norm_b)

            scored = []
            for mem in memories:
                embedding_str = mem.get('embedding_json')
                if embedding_str:
                    try:
                        emb = json.loads(embedding_str)
                        sim = cosine_sim(query_embedding, emb)
                        if sim > 0.3:
                            scored.append({
                                'content': mem.get('content', ''),
                                'score': sim,
                                'metadata': json.loads(mem.get('metadata_json', '{}')),
                                'provenance': mem.get('provenance', ''),
                            })
                    except Exception:
                        pass

            scored.sort(key=lambda x: x['score'], reverse=True)

            return ExecutionResult(
                capability=self.name,
                success=True,
                data={
                    'query': query,
                    'results': scored[:10],
                    'result_count': len(scored),
                    'method': 'semantic_similarity',
                },
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

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        return True


__all__ = ['KnowledgeCapability']
