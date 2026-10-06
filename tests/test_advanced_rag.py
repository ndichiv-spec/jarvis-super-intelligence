"""
Test Advanced RAG System
=========================
Comprehensive tests for hybrid retrieval, knowledge graph integration,
and multi-hop reasoning.
"""

import json
import sys
import time


def test_entity_extraction():
    """Test entity extraction from text"""
    print("\n" + "=" * 80)
    print("TEST 1: Entity Extraction")
    print("=" * 80)

    from core.advanced_rag import EntityExtractor

    extractor = EntityExtractor()

    # Test text
    text = "Elon Musk founded SpaceX in 2002 and Tesla Motors in 2003. He also owns Twitter."

    print(f"\nInput text: {text}")
    entities = extractor.extract_entities(text)

    print(f"\nExtracted {len(entities)} entities:")
    for entity in entities:
        print(f"  - {entity.entity} ({entity.entity_type}) at position {entity.position}")

    # Extract relationships
    triples = extractor.extract_relationships(text, entities)
    print(f"\nExtracted {len(triples)} relationships:")
    for triple in triples:
        print(f"  - {triple.subject} --[{triple.predicate}]--> {triple.obj}")

    return len(entities) > 0 and len(triples) >= 0


def test_knowledge_base_integration():
    """Test integration with knowledge base"""
    print("\n" + "=" * 80)
    print("TEST 2: Knowledge Base Integration")
    print("=" * 80)

    from core.knowledge_base import get_knowledge_base

    kb = get_knowledge_base()

    # Add test documents
    test_docs = [
        {
            "key": "python_language",
            "value": "Python is a high-level programming language created by Guido van Rossum in 1991.",
            "category": "programming",
            "tags": ["python", "programming", "language"],
        },
        {
            "key": "guido_van_rossum",
            "value": "Guido van Rossum is a Dutch programmer best known as the creator of Python.",
            "category": "biography",
            "tags": ["guido", "python", "creator"],
        },
        {
            "key": "machine_learning",
            "value": "Machine learning is a subset of artificial intelligence that enables systems to learn from data.",
            "category": "ai",
            "tags": ["ml", "ai", "learning"],
        },
    ]

    print("\nAdding test documents to knowledge base...")
    for doc in test_docs:
        kb.add(
            key=doc["key"],
            value=doc["value"],
            category=doc["category"],
            tags=doc["tags"],
        )
        print(f"  ✓ Added: {doc['key']}")

    # Test search
    print("\nSearching for 'Python creator'...")
    results = kb.search("Python creator", top_k=3)
    print(f"Found {len(results)} results:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. [{result.get('score', 0):.2f}] {result.get('value', '')[:80]}...")

    stats = kb.get_stats()
    print(f"\nKnowledge Base Stats:")
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Categories: {list(stats['categories'].keys())}")

    return len(results) > 0


def test_knowledge_graph():
    """Test knowledge graph operations"""
    print("\n" + "=" * 80)
    print("TEST 3: Knowledge Graph Operations")
    print("=" * 80)

    from core.knowledge_graph import get_knowledge_graph

    kg = get_knowledge_graph()

    # Add nodes
    print("\nAdding nodes to knowledge graph...")
    nodes = [
        ("python", "Python", "programming_language"),
        ("guido", "Guido van Rossum", "person"),
        ("tesla", "Tesla", "company"),
        ("spacex", "SpaceX", "company"),
        ("elon", "Elon Musk", "person"),
    ]

    for node_id, label, node_type in nodes:
        kg.add_node(node_id, label, node_type)
        print(f"  ✓ Added node: {label} ({node_type})")

    # Add edges
    print("\nAdding relationships...")
    edges = [
        ("guido", "python", "created"),
        ("elon", "tesla", "founded"),
        ("elon", "spacex", "founded"),
        ("python", "guido", "created_by"),
    ]

    for source, target, relationship in edges:
        kg.add_edge(source, target, relationship)
        print(f"  ✓ {source} --[{relationship}]--> {target}")

    # Query graph
    print("\nQuerying related nodes for 'python'...")
    related = kg.get_related_nodes("python", max_depth=2)
    print(f"Found {related['total']} related nodes:")
    for node in related["related"]:
        print(f"  - {node['label']} ({node['type']})")

    # Find path
    print("\nFinding path from 'elon' to 'python'...")
    path = kg.find_path("elon", "python")
    if path:
        print(f"  Path: {' → '.join(path)}")
    else:
        print("  No path found")

    # Get stats
    stats = kg.get_stats()
    print(f"\nKnowledge Graph Stats:")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Total edges: {stats['total_edges']}")
    print(f"  Clusters: {stats['clusters']}")

    return stats["total_nodes"] > 0 and stats["total_edges"] > 0


def test_hybrid_retrieval():
    """Test hybrid retrieval combining vector + graph"""
    print("\n" + "=" * 80)
    print("TEST 4: Hybrid Retrieval")
    print("=" * 80)

    from core.advanced_rag import get_rag_engine, HybridRetriever
    from core.knowledge_base import get_knowledge_base
    from core.knowledge_graph import get_knowledge_graph

    kb = get_knowledge_base()
    kg = get_knowledge_graph()

    retriever = HybridRetriever(
        knowledge_base=kb,
        knowledge_graph=kg,
        embedding_model=kb.embedding_model,
    )

    # Test query
    query = "Who created Python?"
    print(f"\nQuery: '{query}'")

    start_time = time.time()
    response = retriever.retrieve(query, top_k=5)
    processing_time = (time.time() - start_time) * 1000

    print(f"\nResults ({response.total_sources} sources, {processing_time:.2f}ms):")
    for i, result in enumerate(response.results, 1):
        print(f"\n  {i}. [{result.source_type.upper()}] Score: {result.relevance_score:.3f}")
        print(f"     Content: {result.content[:100]}...")
        if result.citation:
            print(f"     Citation: {result.citation}")

    print(f"\nReasoning Path:")
    for step in response.reasoning_path:
        print(f"  - {step}")

    print(f"\nConfidence: {response.confidence:.2f}")
    print(f"Related Entities: {response.related_entities}")

    return len(response.results) > 0


def test_full_rag_pipeline():
    """Test complete RAG pipeline"""
    print("\n" + "=" * 80)
    print("TEST 5: Full RAG Pipeline")
    print("=" * 80)

    from core.advanced_rag import get_rag_engine
    from core.knowledge_base import get_knowledge_base
    from core.knowledge_graph import get_knowledge_graph

    kb = get_knowledge_base()
    kg = get_knowledge_graph()

    rag_engine = get_rag_engine(
        knowledge_base=kb,
        knowledge_graph=kg,
    )

    # Add document
    print("\nIngesting document...")
    doc_text = """
    Artificial Intelligence (AI) is transforming industries worldwide. 
    Machine Learning, a subset of AI, uses algorithms to learn from data.
    Deep Learning is a specialized form of ML using neural networks.
    Companies like OpenAI, Google DeepMind, and Anthropic are leading AI research.
    """

    result = rag_engine.add_document(
        document=doc_text,
        metadata={
            "category": "ai",
            "tags": ["ai", "ml", "deep_learning"],
            "source": "test_document",
        },
    )

    print(f"  Document ID: {result['document_id']}")
    print(f"  Triples Extracted: {result['triples_extracted']}")
    print(f"  Processing Time: {result['processing_time_ms']:.2f}ms")

    # Query
    print("\nQuerying RAG engine...")
    queries = [
        "What is machine learning?",
        "Tell me about AI companies",
        "Explain deep learning",
    ]

    for query in queries:
        print(f"\n  Query: '{query}'")
        response = rag_engine.query(query, top_k=3)

        print(f"    Sources: {response.total_sources}")
        print(f"    Confidence: {response.confidence:.2f}")
        print(f"    Processing Time: {response.processing_time_ms:.2f}ms")

        if response.results:
            print(f"    Top Result: {response.results[0].content[:80]}...")

    # Get stats
    stats = rag_engine.get_stats()
    print(f"\nRAG Engine Statistics:")
    print(f"  Total Queries: {stats['total_queries']}")
    print(f"  Cache Hits: {stats['cache_hits']}")
    print(f"  Avg Processing Time: {stats['avg_processing_time_ms']:.2f}ms")
    print(f"  Triples Extracted: {stats['total_triples_extracted']}")

    return stats["total_queries"] > 0


def test_api_endpoints():
    """Test API endpoints (requires running server)"""
    print("\n" + "=" * 80)
    print("TEST 6: API Endpoints (Integration Test)")
    print("=" * 80)

    import requests

    base_url = "http://localhost:8000/api/v1"

    try:
        # Health check
        print("\nChecking RAG health endpoint...")
        response = requests.get(f"{base_url}/rag/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print(f"  Status: {health['status']}")
            print(f"  Components: {list(health['components'].keys())}")
        else:
            print(f"  ✗ Health check failed: {response.status_code}")
            return False

        # Test query
        print("\nTesting RAG query endpoint...")
        payload = {
            "query": "What is Python?",
            "top_k": 3,
            "use_cache": True,
            "enable_multi_hop": True,
        }
        response = requests.post(
            f"{base_url}/rag/query", json=payload, timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            print(f"  Query: {result['query']}")
            print(f"  Results: {result['total_sources']}")
            print(f"  Confidence: {result['confidence']:.2f}")
            print(f"  Citations: {len(result['citations'])}")
        else:
            print(f"  ✗ Query failed: {response.status_code}")
            print(f"  Error: {response.text}")

        # Get stats
        print("\nFetching RAG statistics...")
        response = requests.get(f"{base_url}/rag/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(f"  Total Queries: {stats['total_queries']}")
            print(f"  Cache Size: {stats['cache_size']}")
        else:
            print(f"  ✗ Stats failed: {response.status_code}")

        return True

    except requests.exceptions.ConnectionError:
        print("\n  ⚠ Backend server not running. Skipping API tests.")
        print("  Start server with: python run_backend.py")
        return False
    except Exception as e:
        print(f"\n  ✗ API test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("JARVIS ADVANCED RAG SYSTEM - TEST SUITE")
    print("=" * 80)

    tests = [
        ("Entity Extraction", test_entity_extraction),
        ("Knowledge Base Integration", test_knowledge_base_integration),
        ("Knowledge Graph Operations", test_knowledge_graph),
        ("Hybrid Retrieval", test_hybrid_retrieval),
        ("Full RAG Pipeline", test_full_rag_pipeline),
        ("API Endpoints", test_api_endpoints),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n✗ {test_name} FAILED with exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"  {status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Advanced RAG system is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check output above for details.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
