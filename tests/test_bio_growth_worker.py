from __future__ import annotations

import asyncio
import hashlib
import uuid

from jarvis_backend import core
from jarvis_backend.bio_growth_worker import BioGrowthResearchWorker
from jarvis_backend.research import autonomous_research as research


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def test_research_cortex_initializes_portably_and_deduplicates():
    cortex = research.AutonomousResearchCortex()
    cortex.initialize()
    assert cortex.get_due_feeds()

    item = research.DiscoveredItem(
        id=f"test-{uuid.uuid4().hex}",
        source_type=research.SourceType.RSS,
        title="Test research item",
        url="https://example.org/research",
        abstract="Transformer and reasoning research",
        concepts=["transformer"],
        content_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:16],
        provenance="test",
    )
    research._store_discovered_item(item)
    research._store_discovered_item(item)
    research._store_knowledge_node(research.KnowledgeNode(
        id=f"test-node-{uuid.uuid4().hex}",
        name="test-node",
        node_type="concept",
        description="test node",
        source_items=[item.id],
    ))

    assert research._research_item_exists(item.id)


def test_feed_monitor_parses_rss_with_httpx(monkeypatch):
    from jarvis_backend.research.autonomous_research import FeedMonitor

    class FakeResponse:
        content = b"""<rss version="2.0"><channel><item>
        <title>Useful AI research</title>
        <link>https://example.org/paper</link>
        <description>Transformer methods</description>
        <pubDate>Sun, 04 Oct 2026 10:00:00 GMT</pubDate>
        </item></channel></rss>"""

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    items = _run(FeedMonitor.fetch_feed("https://example.org/feed"))

    assert len(items) == 1
    assert items[0].title == "Useful AI research"
    assert items[0].url == "https://example.org/paper"
    assert items[0].published_at.startswith("Sun")


def test_ingestion_persists_digest_and_reloads_graph(monkeypatch):
    async def fetch(_url):
        return [research.DiscoveredItem(
            id="rss-bio-growth-first",
            source_type=research.SourceType.RSS,
            title="Transformer research",
            url="https://example.org/first",
            abstract="A transformer attention method",
            content_hash="bio-growth-first",
        )]

    monkeypatch.setattr(research.FeedMonitor, "fetch_feed", staticmethod(fetch))
    cortex = research.AutonomousResearchCortex()
    cortex.initialize()
    feed_id = next(iter(cortex._feeds))
    first_result = _run(cortex.ingest_feed(feed_id))

    engine = research._get_research_engine()
    with engine.connect() as conn:
        first_item = conn.execute(
            research.select(research._research_items_table).where(
                research._research_items_table.c.id == "rss-bio-growth-first"
            )
        ).first()
    assert first_result["items_new"] == 1
    assert "transformer" in research.json.loads(first_item.concepts_json)
    assert first_item.maturity_score == 0.1

    async def fetch_second(_url):
        return [research.DiscoveredItem(
            id="rss-bio-growth-second",
            source_type=research.SourceType.RSS,
            title="Transformer research continued",
            url="https://example.org/second",
            abstract="Transformer attention and learning",
            content_hash="bio-growth-second",
        )]

    monkeypatch.setattr(research.FeedMonitor, "fetch_feed", staticmethod(fetch_second))
    next_cycle = research.AutonomousResearchCortex()
    next_cycle.initialize()
    second_feed_id = next(iter(next_cycle._feeds))
    second_result = _run(next_cycle.ingest_feed(second_feed_id))

    assert second_result["items_new"] == 1
    node = next_cycle._knowledge_graph["concept-transformer"]
    assert node.source_items == ["rss-bio-growth-first", "rss-bio-growth-second"]
    assert abs(node.maturity_score - 0.15) < 1e-9


def test_worker_runs_only_bundled_feeds_and_persists_results(monkeypatch):
    allowed_feed = research.SEED_FEEDS[0]
    allowed_id = f"feed-{hashlib.sha256(allowed_feed['url'].encode()).hexdigest()[:12]}"
    technology_watch_calls = []

    class FakeCortex:
        def __init__(self):
            self._feeds = {
                allowed_id: {**allowed_feed, "name": allowed_feed["name"]},
                "untrusted-feed": {
                    "url": "http://127.0.0.1/private",
                    "name": "untrusted",
                },
            }

        def initialize(self):
            return None

        def get_due_feeds(self):
            return [allowed_id, "untrusted-feed"]

        async def ingest_feed(self, feed_id):
            return {
                "success": True,
                "items_discovered": 3,
                "items_new": 2,
            }

    async def fake_technology_watch_refresh():
        technology_watch_calls.append(True)
        return {"status": "ok", "new_items": 4, "last_errors": []}

    monkeypatch.setattr(research, "AutonomousResearchCortex", FakeCortex)
    from jarvis_backend.research import technology_watch

    monkeypatch.setattr(technology_watch, "refresh_watch", fake_technology_watch_refresh)
    core.data.clear()
    execution = _run(BioGrowthResearchWorker().run_once())

    assert execution["status"] == "completed"
    assert execution["result"]["feeds_due"] == 1
    assert execution["result"]["items_new"] == 2
    assert execution["result"]["technology_watch"] == {
        "status": "ok",
        "new_items": 4,
        "source_errors": 0,
    }
    assert technology_watch_calls == [True]
    assert core.get_store("executions").load()[-1]["id"] == execution["id"]
    assert core.get_store("misc").load()["bio_growth_worker"]["last_run_id"] == execution["id"]


def test_technology_watch_reports_worker_state(monkeypatch):
    from jarvis_backend.research import technology_watch

    class ActiveWorker:
        running = True

    class EmptyStore:
        def load(self):
            return {}

    monkeypatch.setattr(technology_watch, "get_store", lambda _name: EmptyStore())
    monkeypatch.setattr(
        "jarvis_backend.bio_growth_worker.get_bio_growth_worker",
        lambda: ActiveWorker(),
    )

    assert technology_watch.get_watch_status()["automatic_refresh"] is True


def test_worker_does_not_start_in_test_mode(monkeypatch):
    from jarvis_backend import bio_growth_worker

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.setattr(
        bio_growth_worker,
        "get_bio_growth_worker",
        lambda: (_ for _ in ()).throw(AssertionError("worker must remain stopped")),
    )

    _run(bio_growth_worker.start_bio_growth_worker())
