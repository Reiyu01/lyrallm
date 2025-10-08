#!/usr/bin/env python3
"""
測試 Logstash 連接和資料發送
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from logger_service import LogstashHandler, TokenUsage
from datetime import datetime
import uuid

def test_logstash_connection():
    """測試 Logstash 連接"""
    print("🔗 Testing Logstash connection...")
    
    handler = LogstashHandler()
    status = handler.get_connection_status()
    
    print(f"Host: {status['host']}:{status['port']}")
    print(f"Connected: {status['connected']}")
    print(f"Timeout: {status['timeout']}s")
    
    return status['connected']

def test_send_sample_data():
    """測試發送範例資料"""
    print("\n📤 Testing sample data send...")
    
    handler = LogstashHandler()
    
    # 創建測試 TokenUsage
    sample_usage = TokenUsage(
        request_id=f"test_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(),
        model_name="gpt-4o",
        prompt_tokens=50,
        completion_tokens=75,
        total_tokens=125,
        cost_usd=0.0025,
        user_id="test_user",
        endpoint="/v1/chat/completions",
        status="success"
    )
    
    success = handler.save_usage(sample_usage)
    print(f"Send result: {'✅ Success' if success else '❌ Failed'}")
    
    return success

if __name__ == "__main__":
    print("🚀 Semantic Kernel Logstash Integration Test")
    print("=" * 50)
    
    # 測試連接
    connected = test_logstash_connection()
    
    if connected:
        # 測試資料發送
        sent = test_send_sample_data()
        
        if sent:
            print("\n🎉 All tests passed! Ready for production.")
        else:
            print("\n⚠️  Connection OK but data send failed.")
    else:
        print("\n❌ Connection failed. Check Logstash service.")
        print("💡 Make sure elk.54ucl.com:5044 is accessible")
    
    print("\nNext steps:")
    print("1. Integrate with chat.py")
    print("2. Start consumer service") 
    print("3. Monitor in Kibana")