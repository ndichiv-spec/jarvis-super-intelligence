"""
JARVIS Search System Test
========================
Quick test to verify the enhanced search system is working.
"""

import asyncio
import sys


async def test_system():
    print("=" * 70)
    print("JARVIS ENHANCED SEARCH SYSTEM - TEST")
    print("=" * 70)

    errors = []

    print("\n[1/5] Testing imports...")
    try:
        from core.universal_search_engine import get_universal_search_engine

        print("  ✓ Universal Search Engine")
    except Exception as e:
        errors.append(f"Universal Search: {e}")
        print(f"  ✗ Universal Search: {e}")

    try:
        from core.search_learner import get_search_learner

        print("  ✓ Search Learner")
    except Exception as e:
        errors.append(f"Search Learner: {e}")
        print(f"  ✗ Search Learner: {e}")

    try:
        from core.web_scraper import get_scraper

        print("  ✓ Web Scraper")
    except Exception as e:
        errors.append(f"Web Scraper: {e}")
        print(f"  ✗ Web Scraper: {e}")

    print("\n[2/5] Testing search engine initialization...")
    try:
        from core.universal_search_engine import get_universal_search_engine

        engine = get_universal_search_engine()
        status = engine.get_status()
        print(f"  Engines: {status['available_engines']}/{status['total_engines']}")
        print(f"  List: {', '.join(status['engine_list'])}")
    except Exception as e:
        errors.append(f"Engine init: {e}")
        print(f"  ✗ {e}")

    print("\n[3/5] Testing search...")
    try:
        from core.universal_search_engine import get_universal_search_engine

        engine = get_universal_search_engine()
        result = await engine.search("test query", num_results=3)
        print(f"  Found {len(result.results)} results")
        print(f"  Engines: {', '.join(result.engines_used)}")
        if result.results:
            print(f"  Top result: {result.results[0].title[:50]}...")
    except Exception as e:
        errors.append(f"Search: {e}")
        print(f"  ✗ {e}")

    print("\n[4/5] Testing scraper...")
    try:
        from core.web_scraper import get_scraper

        scraper = get_scraper()
        result = await scraper.scrape_url("https://example.com")
        if result.success:
            print(f"  ✓ Scraped: {result.content.title}")
        else:
            print(f"  ✗ {result.error}")
    except Exception as e:
        errors.append(f"Scraper: {e}")
        print(f"  ✗ {e}")

    print("\n[5/5] Testing learner...")
    try:
        from core.search_learner import get_search_learner

        learner = get_search_learner()
        stats = learner.get_learning_stats()
        print(f"  Interactions: {stats['total_interactions']}")
        print(f"  Sources: {stats['total_sources_tracked']}")
        learner.close()
    except Exception as e:
        errors.append(f"Learner: {e}")
        print(f"  ✗ {e}")

    print("\n" + "=" * 70)
    if errors:
        print(f"FAILED - {len(errors)} error(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    else:
        print("SUCCESS - All tests passed!")
        print("\nTo use the search system:")
        print("  1. Run: python -m uvicorn api.main:app --reload")
        print("  2. Visit: http://localhost:8000/api/v1/search/docs")
        print("  3. API: POST /api/v1/search with {'query': 'your search'}")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_system())
    sys.exit(exit_code)
