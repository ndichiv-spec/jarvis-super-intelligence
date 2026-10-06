"""Autonomous Research Cortex — Internet-Aware Knowledge Ingestion.

CLASSIFIED: Private JARVIS infrastructure.

This module implements JARVIS's autonomous knowledge discovery and ingestion
pipeline. It actively discovers, fetches, and digests technological knowledge
from the internet through multiple channels:

- RSS/Atom feeds (tech blogs, news, journals)
- arXiv API (scientific papers)
- Web crawling (link-following, citation harvesting)
- GitHub trending (emerging software projects)
- Semantic digestions (concept extraction, relationship mapping)

The cortex builds a knowledge DAG (directed acyclic graph) of discovered
concepts, entities, and their relationships. Growth starts from seed feeds
(Phase 0) and expands organically through citation analysis and link discovery.

All ingestion happens within the JARVIS sandbox for safety.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger("jarvis.research.cortex")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    RSS = "rss"
    ARXIV = "arxiv"
    WEB_CRAWL = "web_crawl"
    GITHUB_TRENDING = "github_trending"
    ACADEMIC = "academic"


@dataclass
class DiscoveredItem:
    """A piece of discovered knowledge — a paper, article, or web page."""
    id: str
    source_type: SourceType
    title: str
    url: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    content: str = ""
    published_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    provenance: str = ""
    content_hash: str = ""
    maturity_score: float = 0.0  # 0.0 = raw, 1.0 = digested

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type.value,
            "title": self.title,
            "url": self.url,
            "authors": self.authors,
            "abstract": self.abstract,
            "content": self.content[:5000],  # Truncate for storage
            "published_at": self.published_at,
            "tags": self.tags,
            "citations": self.citations,
            "concepts": self.concepts,
            "provenance": self.provenance,
            "content_hash": self.content_hash,
            "maturity_score": self.maturity_score,
        }


@dataclass
class KnowledgeNode:
    """A node in the knowledge DAG."""
    id: str
    name: str
    node_type: str  # "concept", "entity", "domain", "method", "tool"
    description: str = ""
    related_concepts: List[str] = field(default_factory=list)
    source_items: List[str] = field(default_factory=list)  # IDs of source items
    first_seen: str = ""
    maturity_score: float = 0.0  # How deeply understood this concept is
    growth_rate: float = 0.0  # How rapidly new sources mention this concept

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type,
            "description": self.description,
            "related_concepts": self.related_concepts,
            "source_items": self.source_items,
            "first_seen": self.first_seen,
            "maturity_score": self.maturity_score,
            "growth_rate": self.growth_rate,
        }


# ---------------------------------------------------------------------------
# Seed feeds — Phase 0 (birth stage)
# ---------------------------------------------------------------------------

SEED_FEEDS: List[Dict[str, Any]] = [
    {
        "name": "arXiv cs.AI",
        "url": "https://export.arxiv.org/rss/cs.AI",
        "source_type": SourceType.RSS,
        "category": "artificial_intelligence",
        "poll_interval": 3600,  # 1 hour
    },
    {
        "name": "arXiv cs.LG",
        "url": "https://export.arxiv.org/rss/cs.LG",
        "source_type": SourceType.RSS,
        "category": "machine_learning",
        "poll_interval": 3600,
    },
    {
        "name": "arXiv math.AG",
        "url": "https://export.arxiv.org/rss/math.AG",
        "source_type": SourceType.RSS,
        "category": "algebraic_geometry",
        "poll_interval": 7200,
    },
    {
        "name": "arXiv stat.ML",
        "url": "https://export.arxiv.org/rss/stat.ML",
        "source_type": SourceType.RSS,
        "category": "machine_learning_stats",
        "poll_interval": 3600,
    },
    {
        "name": "arXiv cs.CL",
        "url": "https://export.arxiv.org/rss/cs.CL",
        "source_type": SourceType.RSS,
        "category": "computation_and_language",
        "poll_interval": 3600,
    },
    {
        "name": "Hacker News",
        "url": "https://hnrss.org/newest",
        "source_type": SourceType.RSS,
        "category": "technology",
        "poll_interval": 600,
    },
    {
        "name": "GitHub Trending Python",
        "url": "https://github.com/trending/python?since=daily",
        "source_type": SourceType.GITHUB_TRENDING,
        "category": "software",
        "poll_interval": 86400,
    },
    {
        "name": "MIT Technology Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "source_type": SourceType.RSS,
        "category": "ai_news",
        "poll_interval": 3600,
    },
]

# Concept extraction patterns (domain-specific keyword sets)
TECH_CONCEPT_PATTERNS = {
    "transformer": r"transformer|attention mechanism|self-attention",
    "llm": r"large language model|LLM|GPT|BERT|language model",
    "diffusion": r"diffusion model|diffusion probabilistic",
    "reinforcement_learning": r"reinforcement learning|Q-learning|policy gradient|actor-critic",
    "graph_neural_network": r"graph neural network|GNN|graph convolution",
    "symbolic_ai": r"symbolic.*AI|knowledge representation|ontologies|logical reasoning",
    "neuro_symbolic": r"neuro-symbolic|neuro-symbolic",
    "quantum_computing": r"quantum computing|qubit|quantum gate|quantum algorithm",
    "edge_computing": r"edge computing|fog computing|edge AI",
    "federated_learning": r"federated learning|distributed training",
    "continual_learning": r"continual learning|lifelong learning|catastrophic forgetting",
    "few_shot": r"few-shot|zero-shot|prompt engineering",
    "alignment": r"AI alignment|value alignment|RLHF|constitutional",
    "emergence": r"emergent behavior|emergence|scaling laws",
}


def _extract_content_hash(text: str) -> str:
    """Generate a short content hash for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _content_to_markdown(html: str) -> str:
    """Convert HTML to markdown text, stripping boilerplate."""
    try:
        from markdownify import markdownify as md
        return md(html, strip=["script", "style", "nav", "header", "footer"])
    except ImportError:
        # Fallback: basic HTML tag stripping
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return text.strip()


def _extract_concepts(text: str) -> List[str]:
    """Extract technology and science concepts from text using keyword patterns."""
    concepts = []
    text_lower = text.lower()
    for concept, pattern in TECH_CONCEPT_PATTERNS.items():
        if re.search(pattern, text_lower):
            concepts.append(concept)
    return concepts


def _extract_tags(title: str, content: str) -> List[str]:
    """Generate tags from title and content keywords."""
    tags = []
    combined = (title + " " + content[:2000]).lower()

    # Domain tags
    domain_keywords = {
        "ai": ["neural", "deep learning", "transformer", "llm", "gpt", "bert"],
        "math": ["theorem", "proof", "equation", "calculus", "algebra", "geometry", "sympy"],
        "physics": ["quantum", "relativity", "particle", "entropy", "thermodynamics"],
        "biology": ["genome", "protein", "cell", "dna", "evolution", "neural"],
        "computer_science": ["algorithm", "complexity", "distributed", "blockchain"],
        "engineering": ["optimization", "control", "signal", "robotics"],
    }

    for tag, keywords in domain_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(tag)

    return tags[:5]


# ---------------------------------------------------------------------------
# Persistence (uses existing JARVIS database)
# ---------------------------------------------------------------------------

from sqlalchemy import (
    MetaData, Table, Column, String, Text, Float, Integer, insert, select, update, text
)

_RESEARCH_METADATA = MetaData()

_research_items_table = Table(
    "jarvis_research_items", _RESEARCH_METADATA,
    Column("id", String(64), primary_key=True),
    Column("source_type", String(50), nullable=False),
    Column("title", String(1000), nullable=False),
    Column("url", String(2000)),
    Column("authors_json", Text),
    Column("abstract", Text),
    Column("content", Text),
    Column("published_at", String(64)),
    Column("tags_json", Text),
    Column("citations_json", Text),
    Column("concepts_json", Text),
    Column("provenance", Text),
    Column("content_hash", String(64)),
    Column("maturity_score", Float, default=0.0),
    Column("discovered_at", String(64), nullable=False),
    Column("embedding_json", Text),  # pgvector-style semantic embedding
)

_knowledge_graph_table = Table(
    "jarvis_knowledge_graph", _RESEARCH_METADATA,
    Column("id", String(64), primary_key=True),
    Column("name", String(500), nullable=False),
    Column("node_type", String(50), nullable=False),
    Column("description", Text),
    Column("related_concepts_json", Text),
    Column("source_items_json", Text),
    Column("first_seen", String(64)),
    Column("maturity_score", Float, default=0.0),
    Column("growth_rate", Float, default=0.0),
    Column("embedding_json", Text),  # pgvector-style semantic embedding
)

_research_feeds_table = Table(
    "jarvis_research_feeds", _RESEARCH_METADATA,
    Column("id", String(64), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("url", String(2000), nullable=False),
    Column("source_type", String(50)),
    Column("category", String(100)),
    Column("poll_interval", Integer, default=3600),
    Column("last_polled", String(64)),
    Column("active", Integer, default=1),
)

def _get_research_engine():
    """Get the database engine for research data."""
    from jarvis_backend.db import get_engine, ensure_schema
    ensure_schema()
    return get_engine()


def _init_research_tables():
    """Create tables for research data if they don't exist."""
    engine = _get_research_engine()
    _RESEARCH_METADATA.create_all(engine)


def _store_discovered_item(item: DiscoveredItem) -> None:
    """Store a discovered item in the database."""
    _init_research_tables()
    engine = _get_research_engine()
    # Generate semantic embedding (pgvector-style, stored as JSON)
    embedding = _generate_embedding(item.title + " " + item.abstract + " " + item.content)
    values = dict(
            id=item.id,
            source_type=item.source_type.value,
            title=item.title,
            url=item.url,
            authors_json=json.dumps(item.authors),
            abstract=item.abstract,
            content=item.content,
            published_at=item.published_at,
            tags_json=json.dumps(item.tags),
            citations_json=json.dumps(item.citations),
            concepts_json=json.dumps(item.concepts),
            provenance=item.provenance,
            content_hash=item.content_hash,
            maturity_score=item.maturity_score,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            embedding_json=embedding,
        )
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        elif engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            if not _research_item_exists(item.id):
                conn.execute(insert(_research_items_table).values(**values))
            conn.commit()
            return
        stmt = dialect_insert(_research_items_table).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        conn.execute(stmt)
        conn.commit()


def _generate_embedding(text: str) -> Optional[str]:
    """Generate a semantic embedding for text, stored as JSON string.
    Uses the jarvis_backend.embeddings module if available; falls back to None.
    """
    try:
        from jarvis_backend.embeddings import embed_text
        vec = embed_text(text, dimension=384)
        return json.dumps(vec)
    except Exception:
        return None


def _store_knowledge_node(node: KnowledgeNode) -> None:
    """Store a knowledge graph node (upsert)."""
    _init_research_tables()
    engine = _get_research_engine()
    embedding = _generate_embedding(node.name + " " + node.description)
    with engine.connect() as conn:
        values = dict(
            id=node.id,
            name=node.name,
            node_type=node.node_type,
            description=node.description,
            related_concepts_json=json.dumps(node.related_concepts),
            source_items_json=json.dumps(node.source_items),
            first_seen=node.first_seen,
            maturity_score=node.maturity_score,
            growth_rate=node.growth_rate,
            embedding_json=embedding,
        )
        existing = conn.execute(
            select(_knowledge_graph_table.c.id).where(
                _knowledge_graph_table.c.id == node.id
            )
        ).first()
        if existing:
            conn.execute(
                update(_knowledge_graph_table)
                .where(_knowledge_graph_table.c.id == node.id)
                .values(**{
                    key: value
                    for key, value in values.items()
                    if key != "id"
                })
            )
        else:
            conn.execute(insert(_knowledge_graph_table).values(**values))
        conn.commit()


# ---------------------------------------------------------------------------
# Hybrid semantic / lexical search
# ---------------------------------------------------------------------------
_RESEARCH_SEARCH_TABLES = {
    "jarvis_knowledge_graph": ("name", "description"),
    "jarvis_research_items": ("title", "abstract"),
}
_SEARCH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "of", "on", "or", "the", "to", "what", "when", "where",
    "which", "with",
}


def _search_terms(text: str) -> Set[str]:
    return {
        term for term in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text.lower())
        if term not in _SEARCH_STOP_WORDS
    }


def _rank_research_rows(
    rows: List[Any],
    query: str,
    query_vec: Optional[List[float]],
    cosine_similarity: Any,
    limit: int,
) -> List[Dict[str, Any]]:
    """Rank stored rows by reciprocal-rank fusion of vectors and term overlap."""
    query_terms = _search_terms(query)
    semantic_ranked: List[Tuple[str, float]] = []
    lexical_ranked: List[Tuple[str, float]] = []
    row_by_id: Dict[str, Any] = {}

    for row in rows:
        row_id = str(row[0])
        title = str(row[1] or "")
        abstract = str(row[2] or "")
        row_by_id[row_id] = row
        if query_terms:
            document_terms = _search_terms(f"{title} {abstract}")
            title_hits = len(query_terms & _search_terms(title))
            all_hits = len(query_terms & document_terms)
            if all_hits:
                # Prefer exact title matches while retaining abstract recall.
                score = 0.8 * all_hits / len(query_terms) + 0.2 * title_hits / len(query_terms)
                lexical_ranked.append((row_id, score))

        if query_vec is None:
            continue
        try:
            stored_vec = json.loads(row[3])
        except (json.JSONDecodeError, TypeError, IndexError):
            continue
        if (
            not isinstance(stored_vec, list)
            or len(stored_vec) != len(query_vec)
            or not stored_vec
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in stored_vec
            )
        ):
            continue
        score = cosine_similarity(query_vec, stored_vec)
        if math.isfinite(score) and score > 0.05:
            semantic_ranked.append((row_id, score))

    semantic_ranked.sort(key=lambda entry: entry[1], reverse=True)
    lexical_ranked.sort(key=lambda entry: entry[1], reverse=True)

    # Reciprocal-rank fusion combines rankings without treating unrelated
    # vector-cosine and keyword-overlap scales as if they were equivalent.
    rrf_constant = 60
    fused_scores: Dict[str, float] = {}
    ranks: Dict[str, Set[str]] = {}
    for mode, ranked in (("semantic", semantic_ranked), ("keyword", lexical_ranked)):
        for position, (row_id, _score) in enumerate(ranked, start=1):
            fused_scores[row_id] = fused_scores.get(row_id, 0.0) + 1.0 / (rrf_constant + position)
            ranks.setdefault(row_id, set()).add(mode)

    semantic_scores = dict(semantic_ranked)
    lexical_scores = dict(lexical_ranked)
    ordered_ids = sorted(fused_scores, key=lambda row_id: fused_scores[row_id], reverse=True)
    results = []
    for row_id in ordered_ids[:limit]:
        row = row_by_id[row_id]
        matched_by = ranks[row_id]
        results.append({
            "id": row_id,
            "title": row[1],
            "abstract": row[2],
            "similarity_score": round(
                semantic_scores.get(row_id, lexical_scores.get(row_id, 0.0)), 4
            ),
            "match_type": "hybrid" if len(matched_by) == 2 else next(iter(matched_by)),
            "combined_score": round(fused_scores[row_id], 6),
        })
    return results


def _semantic_search(table: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search research rows with vector ranking and a keyword recall path.

    Invalid or unavailable stored embeddings are skipped; lexical ranking still
    returns matching records and identifies them as keyword matches.
    """
    if table not in _RESEARCH_SEARCH_TABLES:
        raise ValueError(f"Unsupported research search table: {table}")
    if not query or not query.strip():
        return []
    limit = min(max(int(limit), 1), 100)

    try:
        from jarvis_backend.embeddings import embed_text, cosine_similarity
    except ImportError:
        embed_text = None
        cosine_similarity = None

    _init_research_tables()
    engine = _get_research_engine()
    title_column, abstract_column = _RESEARCH_SEARCH_TABLES[table]

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT id, {title_column}, {abstract_column}, embedding_json "
                f"FROM {table}"
            )
        ).fetchall()

    query_vec = embed_text(query, dimension=384) if embed_text is not None else None
    return _rank_research_rows(
        rows, query, query_vec, cosine_similarity, limit
    )


def _store_feed(feed_id: str, name: str, url: str, source_type: str,
                category: str, poll_interval: int) -> None:
    """Store a research feed definition (upsert)."""
    _init_research_tables()
    engine = _get_research_engine()
    with engine.connect() as conn:
        values = dict(
            id=feed_id,
            name=name,
            url=url,
            source_type=source_type,
            category=category,
            poll_interval=poll_interval,
            last_polled=None,
            active=1,
        )
        if engine.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        elif engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            exists = conn.execute(
                select(_research_feeds_table.c.id).where(
                    _research_feeds_table.c.id == feed_id
                )
            ).first()
            if exists is None:
                conn.execute(insert(_research_feeds_table).values(**values))
            conn.commit()
            return
        stmt = dialect_insert(_research_feeds_table).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        conn.execute(stmt)
        conn.commit()


def _research_item_exists(item_id: str) -> bool:
    """Check persisted identity so feed re-polls remain idempotent after restart."""
    _init_research_tables()
    engine = _get_research_engine()
    with engine.connect() as conn:
        return conn.execute(
            select(_research_items_table.c.id).where(
                _research_items_table.c.id == item_id
            )
        ).first() is not None


# ---------------------------------------------------------------------------
# Ingestion engines
# ---------------------------------------------------------------------------

class FeedMonitor:
    """Monitors RSS/Atom feeds for new content."""

    @staticmethod
    async def fetch_feed(feed_url: str, timeout: int = 15) -> List[DiscoveredItem]:
        """Fetch and parse an RSS/Atom feed."""
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx is required for feed monitoring")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=False,
                headers={"User-Agent": "JARVIS-Research/1.0"},
            ) as client:
                response = await client.get(feed_url)
                response.raise_for_status()
        except httpx.HTTPError:
            raise

        atom_ns = "{http://www.w3.org/2005/Atom}"
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid RSS/Atom XML from {feed_url}") from exc
        entries = root.findall("./channel/item")
        if not entries:
            entries = root.findall(f"{atom_ns}entry")

        items = []
        for entry in entries:
            title = (
                entry.findtext("title")
                or entry.findtext(f"{atom_ns}title")
                or "Untitled"
            ).strip()
            content = (
                entry.findtext("description")
                or entry.findtext("summary")
                or entry.findtext(f"{atom_ns}summary")
                or entry.findtext(f"{atom_ns}content")
                or ""
            )
            url = (entry.findtext("link") or "").strip()
            if not url:
                atom_link = entry.find(f"{atom_ns}link")
                url = atom_link.get("href", "").strip() if atom_link is not None else ""
            published_at = (
                entry.findtext("pubDate")
                or entry.findtext("published")
                or entry.findtext("updated")
                or entry.findtext(f"{atom_ns}published")
                or entry.findtext(f"{atom_ns}updated")
            )

            item = DiscoveredItem(
                id=f"rss-{hashlib.sha256((url + title).encode()).hexdigest()[:12]}",
                source_type=SourceType.RSS,
                title=title,
                url=url,
                abstract=_content_to_markdown(content)[:2000],
                published_at=published_at,
                tags=["rss", "feed"],
                concepts=_extract_concepts(title + " " + content),
                provenance=f"feed:{feed_url}",
                content_hash=hashlib.sha256((title + url).encode()).hexdigest()[:16],
            )
            items.append(item)

        log.info("Feed %s: discovered %d items", feed_url, len(items))
        return items[:20]  # Limit per feed


class ArXivHarvester:
    """Harvests papers from the arXiv API."""

    ARXIV_API = "http://export.arxiv.org/api/query"

    @staticmethod
    async def search(query: str, max_results: int = 10) -> List[DiscoveredItem]:
        """Search arXiv for papers matching the query."""
        import urllib.parse
        params = {
            "search_query": f"all:{query}",
            "max_results": max_results,
            "sortBy": "relevance",
        }
        url = ArXivHarvester.ARXIV_API + "?" + urllib.parse.urlencode(params)

        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.get(url) as resp:
                    xml_text = await resp.text()
        except Exception as e:
            log.warning("arXiv fetch failed for '%s': %s", query, e)
            return []

        # Parse arXiv Atom XML
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            log.warning("arXiv XML parse error for '%s'", query)
            return []

        namespace = "{http://www.w3.org/2005/Atom}"
        items = []

        for entry in root.findall(f"{namespace}entry"):
            title = entry.findtext(f"{namespace}title", "").strip()
            summary = entry.findtext(f"{namespace}summary", "").strip()
            url = entry.findtext(f"{namespace}id", "").strip()
            published = entry.findtext(f"{namespace}published", "")

            # Extract authors
            authors = []
            for author in entry.findall(f"{namespace}author"):
                name = author.findtext(f"{namespace}name", "")
                if name:
                    authors.append(name)

            # Extract links to related papers (citations/references)
            citations = []
            for link in entry.findall(f"{namespace}link"):
                rel = link.get("rel", "")
                href = link.get("href", "")
                if rel == "related" and href:
                    citations.append(href)

            content_hash = hashlib.sha256((title + summary[:100]).encode()).hexdigest()[:16]
            item = DiscoveredItem(
                id=f"arxiv-{content_hash}",
                source_type=SourceType.ARXIV,
                title=title,
                url=url,
                authors=authors,
                abstract=summary[:3000],
                published_at=published,
                tags=["arxiv", "paper", query.lower().replace(" ", "_")],
                citations=citations,
                concepts=_extract_concepts(title + " " + summary),
                provenance=f"arxiv:{query}",
                content_hash=content_hash,
            )
            items.append(item)

        log.info("arXiv search '%s': %d papers found", query, len(items))
        return items


class SemanticDigester:
    """Extracts concepts, relationships, and meaning from ingested content."""

    @staticmethod
    def digest(item: DiscoveredItem) -> Tuple[List[str], List[str]]:
        """Process an item and extract concepts and related concepts.

        Returns:
            (own_concepts, related_concepts)
        """
        text = (item.title + " " + item.abstract + " " + item.content[:5000]).lower()

        # Extract own concepts
        own_concepts = _extract_concepts(text)

        # Extract related concepts (co-occurrence analysis)
        related = set()
        for concept in TECH_CONCEPT_PATTERNS:
            pattern = TECH_CONCEPT_PATTERNS[concept]
            if re.search(pattern, text):
                # Find co-occurring concepts
                for other_concept in TECH_CONCEPT_PATTERNS:
                    if other_concept != concept:
                        other_pattern = TECH_CONCEPT_PATTERNS[other_concept]
                        if re.search(other_pattern, text):
                            related.add(other_concept)

        # Basic keyword co-occurrence for concept relationships
        word_pairs = re.findall(
            r"(\w+(?:\s+\w+)*)\s+(?:and|with|via|using)\s+(\w+(?:\s+\w+)*)",
            text,
        )
        for w1, w2 in word_pairs[:10]:
            if w1.strip() and w2.strip():
                related.add(w1.strip())
                related.add(w2.strip())

        return own_concepts, list(related)[:15]

    @staticmethod
    def build_knowledge_node(item: DiscoveredItem, concepts: List[str]) -> KnowledgeNode:
        """Create or update a knowledge graph node from a discovered item."""
        node_id = f"concept-{concepts[0]}" if concepts else f"node-{hashlib.sha256(item.url.encode()).hexdigest()[:12]}"

        now = datetime.now(timezone.utc).isoformat()

        return KnowledgeNode(
            id=node_id,
            name=concepts[0] if concepts else item.title[:100],
            node_type="concept",
            description=item.title,
            related_concepts=[],
            source_items=[item.id],
            first_seen=now,
            maturity_score=0.1,  # Just discovered
            growth_rate=0.0,
        )


class TrendWatcher:
    """Monitors GitHub trending and tech news for emerging trends."""

    @staticmethod
    async def fetch_github_trending(language: str = "python") -> List[DiscoveredItem]:
        """Fetch GitHub trending repositories."""
        url = f"https://github.com/trending/{language}?since=daily"
        try:
            from jarvis_backend.capabilities.browser import BrowserCapability
            from jarvis_backend.capability import ExecutionContext

            browser = BrowserCapability()
            ctx = ExecutionContext(user_id="system", session_id="trend-watcher")
            result = await browser._navigate({"url": url}, ctx)

            if result.success:
                content = result.data.get("content", "")
                items = []

                # Parse trending repo entries
                # GitHub trending HTML has article elements with repo info
                pattern = r'<a[^>]*href="/([^"]+)"[^>]*class=".*s-link-dark.*"'
                repos = re.findall(r'href="(/[^/]+/[^/]+)"[^>]*>([^<]+)</a>', content)

                for repo_path, repo_name in repos[:10]:
                    repo_url = f"https://github.com{repo_path}"
                    item = DiscoveredItem(
                        id=f"gh-{hashlib.sha256(repo_path.encode()).hexdigest()[:12]}",
                        source_type=SourceType.GITHUB_TRENDING,
                        title=f"{repo_name.strip()} — Trending on GitHub",
                        url=repo_url,
                        abstract=f"Trending {repo_path} on GitHub",
                        tags=["github", "trending", language],
                        concepts=["software", "repository"],
                        provenance="github_trending",
                        content_hash=hashlib.sha256(repo_path.encode()).hexdigest()[:16],
                    )
                    items.append(item)

                return items
        except Exception as e:
            log.warning("GitHub trending fetch failed: %s", e)
        return []

    @staticmethod
    async def fetch_hackernews() -> List[DiscoveredItem]:
        """Fetch Hacker News front page stories."""
        url = "https://news.ycombinator.com/"
        try:
            from jarvis_backend.capabilities.browser import BrowserCapability
            from jarvis_backend.capability import ExecutionContext

            browser = BrowserCapability()
            ctx = ExecutionContext(user_id="system", session_id="trend-watcher-hn")
            result = await browser._navigate({"url": url}, ctx)

            if result.success:
                content = result.data.get("content", "")
                items = []

                # Parse HN story links
                story_pattern = r'<a[^>]*class="storylink"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
                matches = re.findall(story_pattern, content, re.DOTALL | re.IGNORECASE)

                for url, title in matches[:15]:
                    clean_title = re.sub(r"<[^>]+>", "", title).strip()
                    if clean_title:
                        item = DiscoveredItem(
                            id=f"hn-{hashlib.sha256(url.encode()).hexdigest()[:12]}",
                            source_type=SourceType.RSS,
                            title=clean_title,
                            url=url,
                            abstract="",
                            tags=["hackernews", "news"],
                            concepts=_extract_concepts(clean_title + " " + url),
                            provenance="hackernews",
                            content_hash=hashlib.sha256(url.encode()).hexdigest()[:16],
                        )
                        items.append(item)

                return items
        except Exception as e:
            log.warning("Hacker News fetch failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Main cortex class
# ---------------------------------------------------------------------------

class AutonomousResearchCortex:
    """
    Autonomous Research Cortex — the internet-aware ingestion layer.

    Growth stages:
    - Birth (Phase 0): Seeded feeds from SEED_FEEDS
    - Growth: Expanded feeds discovered through link/citation analysis
    - Mastery: Predictive ingestion (knowing what to look for before looking)
    - Infinity: Self-expanding discovery loops
    """

    name = "research.cortex"
    version = "0.1.0"
    category = "research"

    def __init__(self):
        self._initialized = False
        self._feeds: Dict[str, Dict[str, Any]] = {}
        self._discovered_items: Dict[str, DiscoveredItem] = {}
        self._knowledge_graph: Dict[str, KnowledgeNode] = {}
        self._growth_stage = "birth"  # birth → growth → mastery → infinity
        self._total_ingested = 0
        self._total_concepts = 0

    def initialize(self) -> None:
        """Initialize the cortex — create tables, seed feeds."""
        _init_research_tables()
        engine = _get_research_engine()

        # Register seed feeds (Phase 0 — birth)
        for feed in SEED_FEEDS:
            feed_id = f"feed-{hashlib.sha256(feed['url'].encode()).hexdigest()[:12]}"
            self._feeds[feed_id] = {
                "id": feed_id,
                "name": feed["name"],
                "url": feed["url"],
                "source_type": feed["source_type"].value,
                "category": feed["category"],
                "poll_interval": feed["poll_interval"],
                "last_polled": None,
                "active": 1,
            }
            _store_feed(feed_id, feed["name"], feed["url"],
                        feed["source_type"].value, feed["category"],
                        feed["poll_interval"])

        # Load feeds from DB
        with engine.connect() as conn:
            rows = conn.execute(
                select(_research_feeds_table).where(_research_feeds_table.c.active == 1)
            ).fetchall()
            for row in rows:
                row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(zip(row._fields, row))
                self._feeds[row_dict["id"]] = row_dict
            nodes = conn.execute(select(_knowledge_graph_table)).fetchall()
            for row in nodes:
                node = row._mapping
                try:
                    related = json.loads(node["related_concepts_json"] or "[]")
                    sources = json.loads(node["source_items_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    related, sources = [], []
                self._knowledge_graph[node["id"]] = KnowledgeNode(
                    id=node["id"],
                    name=node["name"],
                    node_type=node["node_type"],
                    description=node["description"] or "",
                    related_concepts=related if isinstance(related, list) else [],
                    source_items=sources if isinstance(sources, list) else [],
                    first_seen=node["first_seen"] or "",
                    maturity_score=node["maturity_score"] or 0.0,
                    growth_rate=node["growth_rate"] or 0.0,
                )

        self._initialized = True
        log.info("Research Cortex initialized: %d seed feeds, stage=%s",
                 len(self._feeds), self._growth_stage)

    def get_due_feeds(self, now: Optional[datetime] = None) -> List[str]:
        """List active feeds whose configured polling interval has elapsed."""
        current = now or datetime.now(timezone.utc)
        due = []
        for feed_id, feed in self._feeds.items():
            if not feed.get("active", 1):
                continue
            last_polled = feed.get("last_polled")
            if not last_polled:
                due.append(feed_id)
                continue
            try:
                polled_at = datetime.fromisoformat(str(last_polled).replace("Z", "+00:00"))
            except ValueError:
                due.append(feed_id)
                continue
            if polled_at.tzinfo is None:
                polled_at = polled_at.replace(tzinfo=timezone.utc)
            interval = max(60, int(feed.get("poll_interval") or 3600))
            if (current - polled_at).total_seconds() >= interval:
                due.append(feed_id)
        return due

    async def ingest_feed(self, feed_id: str) -> Dict[str, Any]:
        """Ingest items from a specific feed."""
        if feed_id not in self._feeds:
            return {"error": f"Feed {feed_id} not found", "success": False}

        feed = self._feeds[feed_id]
        source_type = SourceType(feed["source_type"])

        if source_type == SourceType.RSS:
            items = await FeedMonitor.fetch_feed(feed["url"])
        elif source_type == SourceType.GITHUB_TRENDING:
            items = await TrendWatcher.fetch_github_trending(feed.get("category", "python"))
        else:
            items = []

        new_count = 0
        for item in items:
            content_hash = item.content_hash
            if (
                content_hash not in [i.content_hash for i in self._discovered_items.values()]
                and not _research_item_exists(item.id)
            ):
                # Digest and update knowledge graph
                own_concepts, related_concepts = SemanticDigester.digest(item)
                item.concepts = own_concepts
                item.maturity_score = 0.1
                self._discovered_items[content_hash] = item
                _store_discovered_item(item)

                for concept_name in own_concepts:
                    node_id = f"concept-{concept_name}"
                    if node_id not in self._knowledge_graph:
                        node = KnowledgeNode(
                            id=node_id,
                            name=concept_name,
                            node_type="concept",
                            description="",
                            related_concepts=related_concepts,
                            source_items=[item.id],
                            first_seen=datetime.now(timezone.utc).isoformat(),
                            maturity_score=0.1,
                            growth_rate=0.0,
                        )
                    else:
                        node = self._knowledge_graph[node_id]
                        node.source_items.append(item.id)
                        node.maturity_score = min(1.0, node.maturity_score + 0.05)
                        for rel in related_concepts:
                            if rel not in node.related_concepts:
                                node.related_concepts.append(rel)

                    node.growth_rate = (
                        len(node.source_items) / max(1, _days_since(node.first_seen))
                        if node.first_seen else 0.0
                    )
                    self._knowledge_graph[node_id] = node
                    _store_knowledge_node(node)

                new_count += 1

        self._total_ingested += new_count
        self._total_concepts = len(self._knowledge_graph)

        # Update feed's last_polled
        engine = _get_research_engine()
        polled_at = datetime.now(timezone.utc).isoformat()
        with engine.connect() as conn:
            conn.execute(
                update(_research_feeds_table).where(_research_feeds_table.c.id == feed_id).values(
                    last_polled=polled_at,
                )
            )
            conn.commit()
        feed["last_polled"] = polled_at

        # Evolve growth stage
        if self._total_ingested > 100 and self._growth_stage == "birth":
            self._growth_stage = "growth"
            log.info("Research Cortex evolved: birth → growth (total_ingested=%d)",
                     self._total_ingested)

        return {
            "success": True,
            "feed_id": feed_id,
            "feed_name": feed["name"],
            "items_discovered": len(items),
            "items_new": new_count,
            "total_ingested": self._total_ingested,
            "growth_stage": self._growth_stage,
        }

    async def search_arxiv(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search arXiv for papers and ingest them."""
        items = await ArXivHarvester.search(query, max_results)

        new_count = 0
        for item in items:
            existing_hashes = [i.content_hash for i in self._discovered_items.values()]
            if item.content_hash not in existing_hashes:
                self._discovered_items[item.content_hash] = item
                _store_discovered_item(item)

                own_concepts, related_concepts = SemanticDigester.digest(item)
                item.concepts = own_concepts

                for concept_name in own_concepts:
                    node_id = f"concept-{concept_name}"
                    if node_id not in self._knowledge_graph:
                        node = KnowledgeNode(
                            id=node_id,
                            name=concept_name,
                            node_type="concept",
                            description="",
                            related_concepts=related_concepts,
                            source_items=[item.id],
                            first_seen=datetime.now(timezone.utc).isoformat(),
                            maturity_score=0.1,
                        )
                    else:
                        node = self._knowledge_graph[node_id]
                        node.source_items.append(item.id)
                        node.maturity_score = min(1.0, node.maturity_score + 0.03)

                    self._knowledge_graph[node_id] = node
                    _store_knowledge_node(node)

                new_count += 1

        self._total_ingested += new_count
        self._total_concepts = len(self._knowledge_graph)

        return {
            "success": True,
            "query": query,
            "papers_found": len(items),
            "papers_new": new_count,
            "total_ingested": self._total_ingested,
        }

    async def ingest_url(self, url: str) -> Dict[str, Any]:
        """Ingest content from an arbitrary URL."""
        try:
            from jarvis_backend.capabilities.browser import BrowserCapability
            from jarvis_backend.capability import ExecutionContext

            browser = BrowserCapability()
            ctx = ExecutionContext(user_id="system", session_id="cortex-ingest")
            result = await browser._navigate({"url": url}, ctx)

            if result.success:
                content = result.data.get("content", "")
                title = result.data.get("title", "")

                item = DiscoveredItem(
                    id=f"url-{hashlib.sha256(url.encode()).hexdigest()[:12]}",
                    source_type=SourceType.WEB_CRAWL,
                    title=title or url,
                    url=url,
                    content=content[:10000],
                    tags=["web_crawl"],
                    concepts=_extract_concepts(title + " " + content),
                    provenance="manual_ingest",
                    content_hash=hashlib.sha256((title + content[:500]).encode()).hexdigest()[:16],
                )

                existing_hashes = [i.content_hash for i in self._discovered_items.values()]
                if item.content_hash not in existing_hashes:
                    self._discovered_items[item.content_hash] = item
                    _store_discovered_item(item)

                    own_concepts, related_concepts = SemanticDigester.digest(item)
                    item.concepts = own_concepts

                    for concept_name in own_concepts:
                        node_id = f"concept-{concept_name}"
                        if node_id not in self._knowledge_graph:
                            node = KnowledgeNode(
                                id=node_id,
                                name=concept_name,
                                node_type="concept",
                                related_concepts=related_concepts,
                                source_items=[item.id],
                                first_seen=datetime.now(timezone.utc).isoformat(),
                                maturity_score=0.1,
                            )
                        else:
                            node = self._knowledge_graph[node_id]
                            node.source_items.append(item.id)

                        self._knowledge_graph[node_id] = node
                        _store_knowledge_node(node)

                    self._total_ingested += 1
                    self._total_concepts = len(self._knowledge_graph)

                    return {
                        "success": True,
                        "item_id": item.id,
                        "title": item.title,
                        "concepts": item.concepts,
                        "content_length": len(content),
                        "total_ingested": self._total_ingested,
                    }

                return {"success": False, "error": "Content already ingested (duplicate)"}
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    def get_knowledge_graph(self, limit: int = 100) -> Dict[str, Any]:
        """Return the knowledge graph state."""
        nodes = list(self._knowledge_graph.values())[:limit]
        edges = []
        for node in nodes:
            for related in node.related_concepts:
                edges.append({"from": node.id, "to": f"concept-{related}"})

        # Augment with semantic search results from persistence layer
        semantic_results = _semantic_search("jarvis_knowledge_graph", "transformer AI", limit=5)

        return {
            "nodes": [n.to_dict() for n in nodes],
            "edges": edges,
            "total_nodes": len(self._knowledge_graph),
            "total_edges": len(edges),
            "growth_stage": self._growth_stage,
            "total_ingested": self._total_ingested,
            "semantic_search_sample": semantic_results,
        }

    def semantic_search(self, query: str, limit: int = 10, source: str = "knowledge_graph") -> List[Dict[str, Any]]:
        """Search ingested knowledge by semantic similarity (vector search).

        Uses the jarvis_backend.embeddings module for cosine similarity.
        Searches either the knowledge graph or research items table.
        """
        table = "jarvis_knowledge_graph" if source == "knowledge_graph" else "jarvis_research_items"
        return _semantic_search(table, query, limit=limit)

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the research cortex."""
        return {
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "initialized": self._initialized,
            "growth_stage": self._growth_stage,
            "total_feeds": len(self._feeds),
            "total_ingested": self._total_ingested,
            "total_concepts": self._total_concepts,
            "knowledge_graph_nodes": len(self._knowledge_graph),
        }

    def discover_new_feeds(self) -> List[Dict[str, Any]]:
        """Phase 2 (growth): Discover new feeds from link analysis.

        Looks at ingested content for links to other feeds/resources
        and adds them as candidate sources.
        """
        new_feeds = []

        for item in list(self._discovered_items.values())[:200]:
            # Look for RSS/Atom feed URLs in content
            feed_urls = re.findall(
                r'(?:href|src)\s*=\s*["\']?([^"\'>\s]*(?:feed|rss|atom)[^"\'>\s]*)',
                item.content,
                re.IGNORECASE,
            )
            for url in feed_urls[:3]:
                feed_id = f"discovered-{hashlib.sha256(url.encode()).hexdigest()[:12]}"
                if feed_id not in self._feeds:
                    new_feeds.append({
                        "id": feed_id,
                        "name": f"Discovered: {url[:80]}",
                        "url": url,
                        "source_type": SourceType.RSS.value,
                        "category": "discovered",
                        "poll_interval": 7200,
                    })

        # Deduplicate and add new feeds
        seen_ids = set()
        unique_feeds = []
        for f in new_feeds:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                self._feeds[f["id"]] = f
                unique_feeds.append(f)

        return unique_feeds


def _days_since(iso_timestamp: Optional[str]) -> float:
    """Calculate days since an ISO timestamp."""
    if not iso_timestamp:
        return 1.0
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return max(1.0, delta.total_seconds() / 86400.0)
    except Exception:
        return 1.0
