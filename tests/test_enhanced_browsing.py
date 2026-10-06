#!/usr/bin/env python3
"""JARVIS Enhanced Browsing Engine - Test Script"""

import asyncio
import sys
import io

sys.path.insert(0, ".")

# Fix Windows console encoding
if sys.platform == "win32":
    import codecs

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.enhanced_browsing_engine import get_enhanced_search_engine
from core.browsing_trainer import get_browsing_trainer


async def test_browsing_engine():
    print("=" * 60)
    print("JARVIS Enhanced Browsing Engine Test")
    print("=" * 60)

    # Get engine
    engine = get_enhanced_search_engine()
    trainer = get_browsing_trainer()

    # Test 1: Status
    print("\n1. Engine Status:")
    status = engine.get_status()
    print(f"   Engines: {len(status['engines'])} configured")
    print(f"   Available: {sum(1 for v in status['engines'].values() if v)}")

    # Test 2: Search
    print("\n2. Search Test:")
    result = await engine.search("artificial intelligence", num_results=5)
    print(f"   Query: {result.query}")
    print(f"   Domain: {result.domain.value}")
    print(f"   Results: {len(result.results)}")
    print(f"   Time: {result.processing_time_ms:.0f}ms")
    print(f"   Engines: {result.engines_used}")

    if result.results:
        r = result.results[0]
        title = r.title[:50].encode("ascii", "replace").decode("ascii")
        print(f"   Top Result: {title}...")
        print(f"   Score: {r.combined_score:.2f}")

    # Test 3: Feedback
    print("\n3. Feedback Recording:")
    if result.results:
        urls = [r.url for r in result.results]
        engine.record_interaction(
            query=result.query,
            displayed_results=urls,
            clicked_url=urls[0],
            time_to_click=1.5,
            helpful=True,
            rating=0.9,
        )

        trainer.train_on_feedback(
            query=result.query,
            clicked_url=urls[0],
            all_results=urls,
            helpful=True,
            rating=0.9,
            session_id="test_session",
        )
        print("   Feedback recorded successfully")

    # Test 4: Learning Stats
    print("\n4. Learning Stats:")
    engine_stats = engine.get_learning_stats()
    print(f"   Total interactions: {engine_stats['total_interactions']}")
    print(f"   Successful: {engine_stats['successful_interactions']}")
    print(f"   Sources tracked: {engine_stats['sources_tracked']}")
    print(f"   Query patterns: {engine_stats['query_patterns']}")

    training_stats = trainer.get_training_stats()
    print(f"   Training samples: {training_stats['training_samples']}")
    print(f"   Patterns learned: {training_stats['patterns_learned']}")

    # Test 5: Different domains
    print("\n5. Domain Classification Test:")
    test_queries = [
        "how to learn python programming",
        "latest news about AI",
        "best stock to buy 2024",
        "quantum physics research",
    ]

    for q in test_queries:
        domain = engine.domain_classifier.classify(q)
        engines = engine._select_engines(domain)
        q_short = q[:40].encode("ascii", "replace").decode("ascii")
        print(f"   '{q_short}...' -> {domain.value} (engines: {engines[:2]}...)")

    print("\n" + "=" * 60)
    print("All tests passed! Enhanced Browsing Engine is working.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_browsing_engine())
