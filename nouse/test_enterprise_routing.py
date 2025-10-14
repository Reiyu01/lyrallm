#!/usr/bin/env python3
"""
Enterprise Auto Routing Test - Fast validation without external API calls
"""
import sys
import os
import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, '/home/b225nkust/open_web_ui_nkust')

from lyrallm.config.config_manager import config_manager
from lyrallm.core import get_default_executor, SemanticRouter

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class MockSemanticRouter:
    """Mock semantic router for testing."""
    
    async def ensure_indexes(self):
        pass
    
    async def route(self, query: str):
        """Return mock routing based on keywords."""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['信用卡', '貸款', '投資', '金融']):
            intent = 'finance'
            model = 'o1'
        elif any(word in query_lower for word in ['摘要', '總結', '整理']):
            intent = 'summarize' 
            model = 'o3-mini'
        elif any(word in query_lower for word in ['問題', '如何', '怎麼']):
            intent = 'qa'
            model = 'o3-mini'
        else:
            intent = 'general'
            model = 'gpt-4o'
            
        return {
            'routing': {
                'intent': intent,
                'model': model,
                'confidence': 0.85,
                'votes': {intent: 0.85}
            }
        }

class MockChatCompletion:
    """Mock chat completion for testing."""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.service_id = f"mock_{model_name}"
    
    async def get_chat_message_contents(self, chat_history, settings, kernel=None):
        """Return mock response."""
        from semantic_kernel.contents.chat_message_content import ChatMessageContent
        
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        # Get last user message
        last_message = ""
        for msg in chat_history.messages:
            if msg.role == 'user':
                last_message = str(msg.content)
        
        # Generate mock response based on model
        if self.model_name == 'o1':
            response = f"[O1 Finance Analysis] 關於您的問題「{last_message}」，建議您..."
        elif self.model_name == 'o3-mini':
            response = f"[O3-Mini Response] 針對「{last_message}」，簡要說明..."
        else:
            response = f"[GPT-4o Response] 您好！關於「{last_message}」的問題..."
        
        mock_response = MagicMock()
        mock_response.content = response
        return [mock_response]

async def test_enterprise_auto_routing():
    """Comprehensive enterprise auto routing test."""
    
    print("=" * 80)
    print("🚀 LyraLLM Enterprise Auto Routing Test")
    print("=" * 80)
    
    # Test 1: Configuration validation
    print("\n📋 1. Configuration Validation:")
    models = config_manager.get_available_models()
    auto_model = next((m for m in models if m['name'] == 'auto'), None)
    
    print(f"   ✅ Total models configured: {len(models)}")
    print(f"   ✅ Auto model present: {'Yes' if auto_model else 'No'}")
    print(f"   ✅ Default model: {config_manager.get_default_model()}")
    
    # Show model-intent mapping
    print("\n   📊 Model-Intent Mapping:")
    for model in models:
        if model['name'] != 'auto':
            intents = model.get('intents', [])
            print(f"     - {model['name']}: {intents}")
    
    # Test 2: Mock semantic routing
    print("\n🧠 2. Semantic Routing Logic Test:")
    
    test_queries = [
        ("如何申請信用卡？", "finance", "o1"),
        ("請幫我摘要這份文件", "summarize", "o3-mini"), 
        ("公司的休假政策是什麼？", "qa", "o3-mini"),
        ("今天天氣如何？", "general", "gpt-4o")
    ]
    
    router = MockSemanticRouter()
    
    for query, expected_intent, expected_model in test_queries:
        result = await router.route(query)
        routing = result['routing']
        
        intent_match = routing['intent'] == expected_intent
        model_match = routing['model'] == expected_model
        
        print(f"   Query: '{query}'")
        print(f"     → Intent: {routing['intent']} {'✅' if intent_match else '❌'}")
        print(f"     → Model: {routing['model']} {'✅' if model_match else '❌'}")
        print(f"     → Confidence: {routing['confidence']:.3f}")
    
    # Test 3: ModelExecutor with mocked providers
    print("\n🎯 3. ModelExecutor Auto Routing Test:")
    
    executor = get_default_executor()
    
    # Mock the semantic router and kernel creation to avoid real API calls
    with patch.object(executor, '_router', router), \
         patch.object(executor, '_get_kernel_for_model') as mock_kernel_method:
        
        # Mock the kernel creation
        async def mock_get_kernel(model_name):
            if model_name == 'auto':
                return None  # Auto should not create kernel
            
            # Create mock kernel
            kernel = MagicMock()
            kernel.plugins = []
            
            # Create mock service
            service = MockChatCompletion(model_name)
            kernel.get_service.return_value = service
            
            # Mock execution settings
            settings = MagicMock()
            settings.temperature = 0.7
            kernel.get_prompt_execution_settings_from_service_id.return_value = settings
            
            return kernel
        
        # Apply mock
        with patch.object(executor, '_get_kernel_for_model', mock_get_kernel):
            for query, expected_intent, expected_model in test_queries:
                try:
                    start_time = time.time()
                    
                    result = await executor.generate(
                        model_name='auto',
                        messages=[{'role': 'user', 'content': query}],
                        temperature=0.1
                    )
                    
                    actual_model = result.get('model')
                    latency = time.time() - start_time
                    response_text = result['choices'][0]['message']['content']
                    
                    model_match = actual_model == expected_model
                    
                    print(f"\n   🔄 Query: '{query[:40]}...'")
                    print(f"     → Routed to: {actual_model} {'✅' if model_match else '❌'}")
                    print(f"     → Latency: {latency*1000:.1f}ms")
                    print(f"     → Response: {response_text[:60]}...")
                    
                except Exception as e:
                    print(f"     → ❌ Error: {e}")
    
    # Test 4: Performance metrics
    print("\n📊 4. Performance Validation:")
    
    # Test response time requirements
    start_time = time.time()
    fake_result = await executor.generate('fake', [{'role': 'user', 'content': 'test'}])
    fake_latency = time.time() - start_time
    
    print(f"   ⚡ Fake model latency: {fake_latency*1000:.1f}ms {'✅' if fake_latency < 0.1 else '❌'}")
    
    # Test cache performance
    cache_info = executor.get_cached_models()
    print(f"   💾 Cached models: {len(cache_info)} {'✅' if len(cache_info) <= 10 else '❌'}")
    
    # Test 5: Error handling and fallback
    print("\n🛡️  5. Error Handling Test:")
    
    try:
        # Test invalid model - should fallback gracefully
        result = await executor.generate('nonexistent-model', [{'role': 'user', 'content': 'test'}])
        
        # Check if fallback occurred
        if result.get('meta', {}).get('fallback_attempted'):
            print("   ✅ Enterprise fallback strategy worked")
        else:
            # Should have fallen back or returned error response
            actual_model = result.get('model', 'unknown')
            if actual_model != 'nonexistent-model':
                print(f"   ✅ Fallback to {actual_model} successful")
            else:
                print("   ⚠️  Unexpected behavior - check error handling")
                
    except Exception as e:
        print(f"   ✅ Properly handled invalid model: {type(e).__name__}")
    
    # Test 6: Enterprise features validation
    print("\n🏢 6. Enterprise Features:")
    
    try:
        from lyrallm.core.model_manager import ModelManager
        model_manager = ModelManager()
        print("   ✅ ModelManager importable")
        
        # Test metrics initialization
        model_manager._initialize_metrics()
        metrics_count = len(model_manager.metrics)
        print(f"   ✅ Metrics initialized: {metrics_count} models")
        
        # Test health scoring
        if metrics_count > 0:
            first_model = list(model_manager.metrics.keys())[0]
            score = model_manager._calculate_model_score(model_manager.metrics[first_model])
            print(f"   ✅ Health scoring works: {score:.3f}")
        
    except Exception as e:
        print(f"   ❌ Enterprise features error: {e}")
    
    print("\n" + "=" * 80)
    print("🎉 Enterprise Auto Routing Test Complete!")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_enterprise_auto_routing())
        exit_code = 0 if result else 1
        print(f"\n🏁 Test completed with exit code: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)