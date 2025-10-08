import redis
import json
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from .models import TokenUsage

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis 客戶端用於 token usage 佇列操作"""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis_client = redis.Redis(
            host=host, 
            port=port, 
            db=db, 
            decode_responses=True
        )
        self.queue_name = "token_usage_queue"
        self.dlq_name = "token_usage_dlq"
        self.stats_key_prefix = "token_stats"
        
    def test_connection(self) -> bool:
        """測試 Redis 連接"""
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return False
    
    def enqueue_usage(self, usage: TokenUsage) -> bool:
        """將 token usage 加入佇列"""
        try:
            self.redis_client.lpush(self.queue_name, usage.to_json())
            logger.info(f"Enqueued token usage: {usage.request_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue usage: {e}")
            return False
    
    def dequeue_usage(self) -> Optional[TokenUsage]:
        """從佇列中取出 token usage"""
        try:
            json_str = self.redis_client.brpop(self.queue_name, timeout=1)
            if json_str:
                return TokenUsage.from_json(json_str[1])
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue usage: {e}")
            return None
    
    def get_queue_length(self) -> int:
        """取得佇列長度"""
        try:
            return self.redis_client.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    def enqueue_to_dlq(self, json_str: str) -> bool:
        """將失敗的事件放到 DLQ 以便人工或重試處理"""
        try:
            self.redis_client.lpush(self.dlq_name, json_str)
            logger.warning("Enqueued event to DLQ")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue to DLQ: {e}")
            return False

    def get_dlq_length(self) -> int:
        """取得 DLQ 的長度"""
        try:
            return self.redis_client.llen(self.dlq_name)
        except Exception as e:
            logger.error(f"Failed to get DLQ length: {e}")
            return 0
    
    def store_daily_stats(self, date: str, stats: dict) -> bool:
        """儲存每日統計資料"""
        try:
            key = f"{self.stats_key_prefix}:daily:{date}"
            self.redis_client.hset(key, mapping=stats)
            # 設定過期時間為 90 天
            self.redis_client.expire(key, 90 * 24 * 3600)
            return True
        except Exception as e:
            logger.error(f"Failed to store daily stats: {e}")
            return False
    
    def get_daily_stats(self, date: str) -> Optional[dict]:
        """取得每日統計資料"""
        try:
            key = f"{self.stats_key_prefix}:daily:{date}"
            return self.redis_client.hgetall(key)
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return None
    
    def increment_counter(self, key: str, amount: int = 1) -> int:
        """增加計數器"""
        try:
            return self.redis_client.incr(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment counter {key}: {e}")
            return 0