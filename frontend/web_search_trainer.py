"""
JARVIS Search Training & Testing CLI
====================================
Train and test the enhanced search system with multi-engine capabilities.
"""

import asyncio
import os
import sys
import time


def train_web_search():
    """Train JARVIS web search capabilities (legacy - now uses new universal search)"""
    print("=" * 70)
    print("JARVIS ENHANCED SEARCH TRAINING")
    print("=" * 70)
    print("\nNote: The new search system uses:")
    print(
        "  - 7 search engines (Google, Bing, DuckDuckGo, Brave, Yahoo, Yandex, Wikipedia)"
    )
    print("  - Intelligent ranking based on credibility and relevance")
    print("  - Learning from user interactions")
    print("  - Source reputation tracking")
    print()

    print("To use the new search system:")
    print("  1. Start Jarvis API server")
    print("  2. Visit: http://localhost:8000/api/v1/search/docs")
    print("  3. Try: POST /api/v1/search with {'query': 'your search'}")
    print()
    print("To train Jarvis (learn from your searches):")
    print("  1. Use the search system normally")
    print("  2. Rate results as helpful/not helpful")
    print("  3. Jarvis learns your preferences over time")
    print()

    print("Checking search engines...")
    try:
        from core.universal_search_engine import get_universal_search_engine

        engine = get_universal_search_engine()
        status = engine.get_status()

        print(
            f"\n  Available Engines: {status['available_engines']}/{status['total_engines']}"
        )
        for eng_name in status["engine_list"]:
            print(f"    ✓ {eng_name}")

        missing = set(["google", "duckduckgo", "bing", "brave"]) - set(
            status["engine_list"]
        )
        if missing:
            print(f"\n  Note: Some engines may not work due to anti-bot protections")
            print(
                f"  Working: {set(status['engine_list']) & {'duckduckgo', 'wikipedia'}}"
            )

    except ImportError as e:
        print(f"  Import error: {e}")

    print("\n" + "=" * 70)
    print("Training data stored in: data/search_learning.db")
    print("=" * 70)


async def test_search(query: str, num_results: int = 5):
    """Test search with a query"""
    print(f"\n{'=' * 70}")
    print(f"TESTING SEARCH: '{query}'")
    print(f"{'=' * 70}\n")

    try:
        from core.universal_search_engine import get_universal_search_engine
        from core.search_learner import get_search_learner

        engine = get_universal_search_engine()
        learner = get_search_learner()

        print(f"Searching with {len(engine.engines)} engines...")
        start = time.time()
        result = await engine.search(query, num_results=num_results)
        elapsed = (time.time() - start) * 1000

        print(
            f"\nResults ({len(result.results)} of {result.total_results} found in {elapsed:.0f}ms):"
        )
        print(f"Engines used: {', '.join(result.engines_used)}")
        print(f"Domain detected: {result.domain.value}")
        print(f"Confidence: {result.confidence:.0%}")
        print()

        for i, r in enumerate(result.results, 1):
            print(f"{i}. {r.title}")
            print(f"   URL: {r.url}")
            print(f"   Source: {r.source} | Score: {r.combined_score:.2f}")
            print(f"   {r.snippet[:120]}...")
            print()

        if result.facts:
            print("Extracted Facts:")
            for fact in result.facts[:3]:
                print(f"  • {fact}")
            print()

        stats = learner.get_learning_stats()
        print(f"Learning Stats: {stats['total_interactions']} interactions tracked")

    except Exception as e:
        print(f"Search error: {e}")
        import traceback

        traceback.print_exc()


async def test_scraper(url: str):
    """Test web scraper"""
    print(f"\n{'=' * 70}")
    print(f"TESTING SCRAPER: '{url}'")
    print(f"{'=' * 70}\n")

    try:
        from core.web_scraper import get_scraper

        scraper = get_scraper()
        print("Scraping...")
        start = time.time()
        result = await scraper.scrape_url(url)
        elapsed = (time.time() - start) * 1000

        if result.success and result.content:
            c = result.content
            print(f"\n✓ Success ({elapsed:.0f}ms)")
            print(f"Title: {c.title}")
            print(f"Author: {c.author or 'Unknown'}")
            print(f"Date: {c.published_date or 'Unknown'}")
            print(f"Language: {c.language}")
            print(f"Content type: {c.content_type}")
            print(f"Reading time: {c.reading_time_minutes:.1f} min")
            print(f"Word count: {c.metadata.get('word_count', 0)}")
            print(f"Confidence: {c.extraction_confidence:.0%}")
            print()
            print(f"Summary: {c.summary[:200]}...")
            print()
            print(f"Images found: {len(c.images)}")
            print(f"Code snippets: {len(c.code_snippets)}")
            print(f"Tables: {len(c.tables)}")
            print(f"Links: {len(c.links)}")
        else:
            print(f"✗ Failed: {result.error}")

    except Exception as e:
        print(f"Scraper error: {e}")
        import traceback

        traceback.print_exc()


async def run_all_tests():
    """Run comprehensive tests"""
    print("\n" + "=" * 70)
    print("JARVIS SEARCH SYSTEM - COMPREHENSIVE TEST")
    print("=" * 70)

    test_queries = [
        "artificial intelligence news 2024",
        "Python programming tutorial",
        "latest space news",
    ]

    for query in test_queries:
        await test_search(query)
        await asyncio.sleep(1)

    await test_scraper("https://en.wikipedia.org/wiki/Artificial_intelligence")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

    try:
        from core.search_learner import get_search_learner

        learner = get_search_learner()
        stats = learner.get_learning_stats()
        print(f"\nLearning Summary:")
        print(f"  Total interactions: {stats['total_interactions']}")
        print(f"  Sources tracked: {stats['total_sources_tracked']}")
        print(f"  Query patterns: {stats['total_query_patterns']}")
        learner.close()
    except:
        pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS Search Training & Testing")
    parser.add_argument(
        "--train", action="store_true", help="Train search capabilities"
    )
    parser.add_argument("--test", type=str, help="Test search with query")
    parser.add_argument("--scrape", type=str, help="Test scraper with URL")
    parser.add_argument("--run-all", action="store_true", help="Run all tests")
    parser.add_argument("--stats", action="store_true", help="Show learning stats")

    args = parser.parse_args()

    if args.train:
        train_web_search()
    elif args.test:
        asyncio.run(test_search(args.test))
    elif args.scrape:
        asyncio.run(test_scraper(args.scrape))
    elif args.run_all:
        asyncio.run(run_all_tests())
    elif args.stats:
        from core.search_learner import get_search_learner

        learner = get_search_learner()
        stats = learner.get_learning_stats()
        print("JARVIS Search Learning Statistics")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")
        learner.close()
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python web_search_trainer.py --train")
        print("  python web_search_trainer.py --test 'AI news'")
        print("  python web_search_trainer.py --scrape https://example.com")
        print("  python web_search_trainer.py --run-all")
        print("  python web_search_trainer.py --stats")


if __name__ == "__main__":
    main()
