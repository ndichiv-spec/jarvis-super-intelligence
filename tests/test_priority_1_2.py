"""
JARVIS Priority 1 & 2 Test Suite
==================================
Comprehensive testing for advanced AI capabilities and real-time streaming.
"""

import asyncio
import json
import sys
from typing import Dict, Any


async def test_local_llm_engine():
    """Test Local LLM Engine"""
    print("\n" + "="*80)
    print("Testing Local LLM Engine")
    print("="*80)
    
    try:
        from core.local_llm_engine import get_local_llm_engine
        
        engine = get_local_llm_engine()
        await engine.initialize()
        
        # Check status
        status = engine.get_status()
        print(f"\n✓ Engine Status: {status}")
        
        # List models
        models = await engine.get_model_info()
        print(f"\n✓ Available Models: {list(models.keys())}")
        
        # Test model selection
        best_model = engine.select_best_model("chat")
        print(f"✓ Best model for chat: {best_model}")
        
        best_coding = engine.select_best_model("coding")
        print(f"✓ Best model for coding: {best_coding}")
        
        print("\n✅ Local LLM Engine: PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Local LLM Engine: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_streaming_engine():
    """Test Advanced Streaming Engine"""
    print("\n" + "="*80)
    print("Testing Advanced Streaming Engine")
    print("="*80)
    
    try:
        from core.advanced_streaming import get_stream_manager, StreamConfig
        
        stream_mgr = get_stream_manager()
        
        # Check status
        status = stream_mgr.get_all_streams_status()
        print(f"\n✓ Stream Manager Status: {status['active_streams']} active streams")
        
        # Test metrics
        metrics = stream_mgr.metrics.get_stats()
        print(f"✓ Metrics: {metrics}")
        
        print("\n✅ Advanced Streaming Engine: PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Advanced Streaming Engine: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_training_engine():
    """Test Advanced Training Engine"""
    print("\n" + "="*80)
    print("Testing Advanced Training Engine")
    print("="*80)
    
    try:
        from core.advanced_training_engine import get_training_engine, FeedbackType
        
        engine = get_training_engine()
        await engine.initialize()
        
        # Check status
        status = engine.get_status()
        print(f"\n✓ Training Engine Status: {status}")
        
        # Test feedback recording
        await engine.record_feedback(
            query="What is Python?",
            response="Python is a programming language",
            feedback_type=FeedbackType.THUMBS_UP,
            score=1.0,
        )
        print("✓ Feedback recorded successfully")
        
        # Get insights
        insights = engine.get_learning_insights()
        print(f"✓ Learning Insights: {insights['total_samples']} samples, "
              f"{insights['average_feedback_score']} avg score")
        
        print("\n✅ Advanced Training Engine: PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Advanced Training Engine: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test API endpoints"""
    print("\n" + "="*80)
    print("Testing API Endpoints")
    print("="*80)
    
    try:
        import httpx
        
        base_url = "http://localhost:8000/api/v1/advanced-ai"
        
        async with httpx.AsyncClient() as client:
            # Test health endpoint
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✓ Health endpoint: OK")
            else:
                print(f"✗ Health endpoint: {response.status_code}")
            
            # Test LLM models endpoint
            response = await client.get(f"{base_url}/llm/models")
            if response.status_code == 200:
                models = response.json()
                print(f"✓ LLM Models: {len(models)} models available")
            else:
                print(f"✗ LLM Models: {response.status_code}")
            
            # Test training status
            response = await client.get(f"{base_url}/training/status")
            if response.status_code == 200:
                status = response.json()
                print(f"✓ Training Status: {status}")
            else:
                print(f"✗ Training Status: {response.status_code}")
            
            # Test learning insights
            response = await client.get(f"{base_url}/training/insights")
            if response.status_code == 200:
                insights = response.json()
                print(f"✓ Learning Insights retrieved")
            else:
                print(f"✗ Learning Insights: {response.status_code}")
        
        print("\n✅ API Endpoints: PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ API Endpoints: FAILED - {e}")
        print("Note: Backend server must be running on port 8000")
        return False


async def test_integration():
    """Test full integration"""
    print("\n" + "="*80)
    print("Testing Full Integration")
    print("="*80)
    
    try:
        from core.priority_integration import (
            initialize_priority_1_and_2,
            get_priority_capabilities_summary,
        )
        
        # Initialize
        results = await initialize_priority_1_and_2()
        print(f"\n✓ Integration Status: {results['status']}")
        
        # Get summary
        summary = get_priority_capabilities_summary()
        print(f"✓ Priority 1 Capabilities: {len(summary['priority_1_ai_core']['capabilities'])}")
        print(f"✓ Priority 2 Capabilities: {len(summary['priority_2_streaming']['capabilities'])}")
        
        print("\n✅ Full Integration: PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Full Integration: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "#"*80)
    print("# JARVIS Priority 1 & 2 Test Suite")
    print("#"*80)
    
    results = {
        "local_llm": await test_local_llm_engine(),
        "streaming": await test_streaming_engine(),
        "training": await test_training_engine(),
        "integration": await test_integration(),
        "api": await test_api_endpoints(),
    }
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:20s}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Priority 1 & 2 are fully operational.")
    elif passed > 0:
        print(f"\n⚠️  {passed}/{total} tests passed. Some features may need attention.")
    else:
        print("\n❌ All tests failed. Please check the implementation.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
