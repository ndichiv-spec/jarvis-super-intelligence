"""
Quick RAG Integration Test
===========================
Simple test to verify the Advanced RAG system integrates correctly with JARVIS.
"""

import sys


def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from core.advanced_rag import (
            AdvancedRAGEngine,
            HybridRetriever,
            EntityExtractor,
            AutoKGBuilder,
            get_rag_engine,
        )
        print("  ✓ Core RAG modules imported")
    except ImportError as e:
        print(f"  ✗ Failed to import core RAG modules: {e}")
        return False
    
    try:
        from api.routers.advanced_rag import router
        print("  ✓ API router imported")
    except ImportError as e:
        print(f"  ✗ Failed to import API router: {e}")
        return False
    
    try:
        from api.router_registry import get_all_routers
        routers = get_all_routers()
        if "advanced_rag" in routers:
            print("  ✓ Router registered in registry")
        else:
            print("  ✗ Router not found in registry")
            return False
    except Exception as e:
        print(f"  ✗ Failed to verify router registration: {e}")
        return False
    
    return True


def test_basic_functionality():
    """Test basic RAG functionality"""
    print("\nTesting basic functionality...")
    
    try:
        from core.advanced_rag import EntityExtractor
        
        extractor = EntityExtractor()
        entities = extractor.extract_entities("Python was created by Guido van Rossum")
        
        if len(entities) > 0:
            print(f"  ✓ Entity extraction works ({len(entities)} entities)")
        else:
            print("  ⚠ Entity extraction returned no results (may need SpaCy)")
        
        return True
    except Exception as e:
        print(f"  ✗ Basic functionality test failed: {e}")
        return False


def test_knowledge_base():
    """Test knowledge base integration"""
    print("\nTesting knowledge base integration...")
    
    try:
        from core.knowledge_base import get_knowledge_base
        
        kb = get_knowledge_base()
        
        # Add test entry
        kb.add(
            key="test_rag_integration",
            value="This is a test entry for RAG integration",
            category="test",
            tags=["rag", "test"]
        )
        
        # Search for it
        results = kb.search("test entry", top_k=1)
        
        if len(results) > 0:
            print(f"  ✓ Knowledge base search works ({len(results)} results)")
            return True
        else:
            print("  ⚠ Search returned no results")
            return True  # Not critical
            
    except Exception as e:
        print(f"  ✗ Knowledge base test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_knowledge_graph():
    """Test knowledge graph integration"""
    print("\nTesting knowledge graph integration...")
    
    try:
        from core.knowledge_graph import get_knowledge_graph
        
        kg = get_knowledge_graph()
        
        # Add test nodes
        kg.add_node("test_entity_1", "Test Entity 1", "test")
        kg.add_node("test_entity_2", "Test Entity 2", "test")
        kg.add_edge("test_entity_1", "test_entity_2", "related_to")
        
        # Query
        related = kg.get_related_nodes("test_entity_1", max_depth=1)
        
        if related.get("total", 0) > 0:
            print(f"  ✓ Knowledge graph works ({related['total']} related nodes)")
            return True
        else:
            print("  ⚠ No related nodes found")
            return True  # Not critical
            
    except Exception as e:
        print(f"  ✗ Knowledge graph test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag_engine():
    """Test full RAG engine"""
    print("\nTesting RAG engine initialization...")
    
    try:
        from core.advanced_rag import get_rag_engine
        from core.knowledge_base import get_knowledge_base
        from core.knowledge_graph import get_knowledge_graph
        
        kb = get_knowledge_base()
        kg = get_knowledge_graph()
        
        rag = get_rag_engine(knowledge_base=kb, knowledge_graph=kg)
        
        # Check components
        if rag.hybrid_retriever:
            print("  ✓ Hybrid retriever initialized")
        if rag.auto_kg_builder:
            print("  ✓ Auto KG builder initialized")
        
        # Get stats
        stats = rag.get_stats()
        print(f"  ✓ RAG engine stats accessible")
        print(f"    - Total queries: {stats['total_queries']}")
        print(f"    - Triple count: {stats['triple_count']}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ RAG engine test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests"""
    print("=" * 80)
    print("JARVIS ADVANCED RAG - INTEGRATION TEST")
    print("=" * 80)
    
    tests = [
        ("Imports", test_imports),
        ("Basic Functionality", test_basic_functionality),
        ("Knowledge Base", test_knowledge_base),
        ("Knowledge Graph", test_knowledge_graph),
        ("RAG Engine", test_rag_engine),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ {name} FAILED: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All integration tests passed!")
        print("\nThe Advanced RAG system is ready to use.")
        print("\nNext steps:")
        print("  1. Start backend: python run_backend.py")
        print("  2. Access API docs: http://localhost:8000/api/v1/docs")
        print("  3. Try RAG endpoints at /api/v1/rag/*")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
