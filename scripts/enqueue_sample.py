# scripts/enqueue_sample.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from logger_service import RedisClient, TokenUsageProducer, TokenUsage
from datetime import datetime
import uuid
import time

rc = RedisClient()
producer = TokenUsageProducer(rc)

for i in range(20):
    usage = TokenUsage(
        request_id=f"smoke_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(),
        model_name="gpt-test",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0005,
        user_id="smoke_test",
        endpoint="/v1/test",
        status="success"
    )
    ok = producer.send_usage(usage)
    print(f"Pushed {usage.request_id}: {ok}")
    time.sleep(0.05)

print("Done pushing sample events.")
