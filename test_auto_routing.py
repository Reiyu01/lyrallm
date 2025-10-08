#!/usr/bin/env python3
"""
Test script for LyraLLM auto routing functionality
"""
import sys
import os
import asyncio
import logging

# Add project root to path
sys.path.insert(0, '/home/b225nkust/open_web_ui_nkust')

from lyrallm.config.config_manager import config_manager
from lyrallm.model_executor import get_default_executor

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_model_executor():
    """Test the ModelExecutor with various scenarios."""
    
    print("=" * 60)
    print("LyraLLM Auto Routing Test")
    print("=" * 60)
    
    # Test 1: Configuration loading
    print("\n1. Testing Configuration Loading:")
    models = config_manager.get_available_models()
    print(f"   Available models: {len(models)}")
    for model in models:
        print(f"   - {model['name']} ({model['provider']}) - enabled: {model.get('enabled')}")
    print(f"   Default model: {config_manager.get_default_model()}")
    
    # Test 2: ModelExecutor initialization
    print("\n2. Testing ModelExecutor:")
    executor = get_default_executor()
    print(f"   Executor initialized: {executor is not None}")
    print(f"   Cached models: {executor.get_cached_models()}")
    
    # Test 3: Fake model generation (should work without external dependencies)
    print("\n3. Testing Fake Model Generation:")
    fake_messages = [{'role': 'user', 'content': 'Hello, world!'}]
    
    try:
        result = await executor.generate('fake', fake_messages)
        print(f"   Fake model result: {result['choices'][0]['message']['content'][:50]}...")
        print(f"   Latency: {result['meta']['latency_ms']}ms")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 4: Auto routing (with fallback)
    print("\n4. Testing Auto Routing (may use fallback if no semantic data):")
    test_messages = [
        {'role': 'user', 'content': '如何申請信用卡？'},  # Finance intent
        {'role': 'user', 'content': '今天天氣如何？'},    # General intent
        {'role': 'user', 'content': '請摘要這篇文章'},    # Summarize intent
    ]
    
    for i, msg in enumerate(test_messages):
        try:
            print(f"   Test {i+1}: '{msg['content'][:30]}...'")
            result = await executor.generate('auto', [msg], temperature=0.1)
            actual_model = result.get('model', 'unknown')
            routing_info = result.get('meta', {}).get('routing_info', {})
            print(f"     → Routed to: {actual_model}")
            if routing_info:
                print(f"     → Intent: {routing_info.get('intent', 'unknown')}")
                print(f"     → Confidence: {routing_info.get('confidence', 0):.3f}")
        except Exception as e:
            print(f"     → Error: {e}")
    
    # Test 5: Model health check
    print("\n5. Testing Model Manager Integration:")
    try:
        from lyrallm.core.model_manager import get_model_manager_sync
        model_manager = get_model_manager_sync()
        if model_manager:
            healthy = model_manager.get_healthy_models()
            print(f"   Model manager active: Yes")
            print(f"   Healthy models: {healthy}")
        else:
            print("   Model manager active: No (not started)")
    except Exception as e:
        print(f"   Model manager error: {e}")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_model_executor())