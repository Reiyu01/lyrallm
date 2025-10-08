import asyncio
import logging
from datetime import datetime
from typing import List
from .redis_client import RedisClient
from .logstash_handler import LogstashHandler
from .models import TokenUsage

logger = logging.getLogger(__name__)


class TokenUsageConsumer:
    """Token usage 消費者 - 處理 Redis 佇列中的資料並發送到 Logstash"""
    
    def __init__(self, redis_client: RedisClient, logstash_handler: LogstashHandler):
        self.redis_client = redis_client
        self.logstash_handler = logstash_handler
        self.running = False
        
    async def start_consuming(self, batch_size: int = 10):
        """開始消費佇列中的資料"""
        self.running = True
        logger.info("Token usage consumer started")
        
        try:
            while self.running:
                # 批次處理提高效率
                batch = []
                
                for _ in range(batch_size):
                    usage = self.redis_client.dequeue_usage()
                    if usage:
                        batch.append(usage)
                    else:
                        break
                
                if batch:
                    await self.process_batch(batch)
                else:
                    # 沒有資料時稍作休息
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            logger.info("Token usage consumer stopped")
    
    async def process_batch(self, batch: list[TokenUsage]):
        """處理一批 usage 資料並發送到 Logstash，對單筆做重試並將持續失敗的事件放入 DLQ"""
        try:
            successful = []
            failed = []

            for usage in batch:
                ok = await self._process_single_usage_with_retry(usage)
                if ok:
                    successful.append(usage)
                else:
                    failed.append(usage)

            logger.info(f"Processed batch: {len(successful)}/{len(batch)} successful, {len(failed)} failed")

            # 只根據成功的項目更新統計
            if successful:
                await self.update_redis_stats(successful)

        except Exception as e:
            logger.error(f"Failed to process batch: {e}")

    async def _process_single_usage_with_retry(self, usage: TokenUsage, max_attempts: int = 3, base_delay: float = 0.5) -> bool:
        """對單筆 usage 嘗試發送到 Logstash，失敗時進行指數退避，最終放入 DLQ"""
        attempt = 0
        json_payload = usage.to_json()

        while attempt < max_attempts:
            try:
                # 同步呼叫 logstash handler (它本身有 retry)，這裡做額外保護
                sent = self.logstash_handler.save_usage(usage)
                if sent:
                    return True
                else:
                    attempt += 1
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(f"Send failed for {usage.request_id}, attempt {attempt}/{max_attempts}, retrying in {delay}s")
                    await asyncio.sleep(delay)

            except Exception as e:
                attempt += 1
                delay = base_delay * (2 ** (attempt - 1))
                logger.error(f"Error sending usage {usage.request_id}: {e}. attempt {attempt}/{max_attempts}")
                await asyncio.sleep(delay)

        # 如果到這裡仍失敗，把原始 JSON 放入 DLQ
        try:
            self.redis_client.enqueue_to_dlq(json_payload)
            logger.error(f"Usage {usage.request_id} moved to DLQ after {max_attempts} attempts")
        except Exception as e:
            logger.error(f"Failed to move usage {usage.request_id} to DLQ: {e}")

        return False
    
    async def update_redis_stats(self, batch: List[TokenUsage]):
        """更新 Redis 統計快取"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 累計統計
            total_requests = len(batch)
            total_tokens = sum(usage.total_tokens for usage in batch)
            total_cost = sum(usage.cost_usd for usage in batch)
            
            # 更新 Redis 計數器
            self.redis_client.increment_counter(f"stats:{today}:requests", total_requests)
            self.redis_client.increment_counter(f"stats:{today}:tokens", total_tokens)
            
            # 儲存詳細統計
            stats_data = {
                'date': today,
                'requests': str(total_requests),
                'tokens': str(total_tokens),
                'cost_usd': str(total_cost),
                'updated_at': datetime.now().isoformat()
            }
            
            self.redis_client.store_daily_stats(today, stats_data)
            logger.info(f"Updated Redis stats for {today}: {total_requests} requests, {total_tokens} tokens")
            
        except Exception as e:
            logger.error(f"Failed to update Redis stats: {e}")
    
    def stop_consuming(self):
        """停止消費"""
        self.running = False
        logger.info("Consumer stop requested")


class TokenUsageProducer:
    """Token usage 生產者 - 發送資料到 Redis 佇列"""
    
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client
    
    def send_usage(self, usage: TokenUsage) -> bool:
        """發送 usage 到佇列"""
        try:
            return self.redis_client.enqueue_usage(usage)
        except Exception as e:
            logger.error(f"Failed to send usage to queue: {e}")
            return False
    
    def get_queue_status(self) -> dict:
        """取得佇列狀態"""
        try:
            return {
                'queue_length': self.redis_client.get_queue_length(),
                'redis_connected': self.redis_client.test_connection()
            }
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            return {'queue_length': -1, 'redis_connected': False}