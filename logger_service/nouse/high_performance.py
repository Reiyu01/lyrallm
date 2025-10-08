"""
企業級高流量 Token Tracking 優化配置
適用於數萬筆資料流量的生產環境
"""

import asyncio
import logging
from typing import List, Dict, Any
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from collections import deque
import threading

logger = logging.getLogger(__name__)

@dataclass
class PerformanceConfig:
    """高性能配置"""
    # Redis 連接池設置
    redis_pool_size: int = 20
    redis_max_connections: int = 50
    redis_connection_timeout: int = 5
    
    # 批次處理設置
    batch_size: int = 100
    batch_timeout: float = 0.5  # 500ms
    max_queue_size: int = 10000
    
    # Consumer 設置
    consumer_workers: int = 8
    consumer_threads: int = 4
    
    # Logstash 設置
    logstash_pool_size: int = 10
    logstash_timeout: int = 3
    logstash_retry_attempts: int = 3
    
    # 監控設置
    metrics_interval: int = 60  # 每分鐘報告一次


class HighPerformanceTokenProducer:
    """高性能 Token Usage Producer - 適用於大流量"""
    
    def __init__(self, redis_client, config: PerformanceConfig):
        self.redis_client = redis_client
        self.config = config
        
        # 內存緩衝區
        self.buffer = deque(maxlen=config.max_queue_size)
        self.buffer_lock = threading.Lock()
        
        # 批次處理
        self.batch_queue = asyncio.Queue(maxsize=config.max_queue_size)
        self.batch_worker_running = False
        
        # 性能監控
        self.metrics = {
            'total_sent': 0,
            'total_failed': 0,
            'batches_processed': 0,
            'last_flush_time': time.time()
        }
    
    async def send_usage_async(self, token_usage) -> bool:
        """異步發送 - 高性能模式"""
        try:
            # 先放入內存緩衝
            with self.buffer_lock:
                self.buffer.append(token_usage)
            
            # 如果緩衝區滿了，觸發批次處理
            if len(self.buffer) >= self.config.batch_size:
                await self._flush_buffer()
            
            return True
            
        except Exception as e:
            logger.error(f"High-performance send failed: {e}")
            self.metrics['total_failed'] += 1
            return False
    
    async def _flush_buffer(self):
        """清空緩衝區並批次發送"""
        try:
            batch = []
            with self.buffer_lock:
                # 取出一批資料
                for _ in range(min(len(self.buffer), self.config.batch_size)):
                    if self.buffer:
                        batch.append(self.buffer.popleft())
            
            if batch:
                await self._send_batch(batch)
                self.metrics['batches_processed'] += 1
                
        except Exception as e:
            logger.error(f"Buffer flush failed: {e}")
    
    async def _send_batch(self, batch: List):
        """批次發送到 Redis"""
        try:
            # 將整批資料序列化
            json_batch = [usage.to_json() for usage in batch]
            
            # 使用 Redis pipeline 提高性能
            pipe = self.redis_client.redis_client.pipeline()
            for json_data in json_batch:
                pipe.lpush("token_usage_queue", json_data)
            
            await asyncio.get_event_loop().run_in_executor(
                None, pipe.execute
            )
            
            self.metrics['total_sent'] += len(batch)
            logger.debug(f"Batch sent: {len(batch)} items")
            
        except Exception as e:
            logger.error(f"Batch send failed: {e}")
            self.metrics['total_failed'] += len(batch)
    
    async def start_background_flusher(self):
        """背景定時清空緩衝區"""
        self.batch_worker_running = True
        
        while self.batch_worker_running:
            try:
                await asyncio.sleep(self.config.batch_timeout)
                
                # 定時清空緩衝區
                if self.buffer:
                    await self._flush_buffer()
                
                # 定時報告性能指標
                await self._report_metrics()
                
            except Exception as e:
                logger.error(f"Background flusher error: {e}")
    
    async def _report_metrics(self):
        """報告性能指標"""
        current_time = time.time()
        time_diff = current_time - self.metrics['last_flush_time']
        
        if time_diff >= self.config.metrics_interval:
            throughput = self.metrics['total_sent'] / time_diff if time_diff > 0 else 0
            
            logger.info(f"Token Tracking Performance:")
            logger.info(f"  - Throughput: {throughput:.2f} items/sec")
            logger.info(f"  - Total sent: {self.metrics['total_sent']}")
            logger.info(f"  - Total failed: {self.metrics['total_failed']}")
            logger.info(f"  - Batches processed: {self.metrics['batches_processed']}")
            logger.info(f"  - Buffer size: {len(self.buffer)}")
            
            # 重置計數器
            self.metrics['total_sent'] = 0
            self.metrics['total_failed'] = 0
            self.metrics['last_flush_time'] = current_time
    
    def stop_background_flusher(self):
        """停止背景處理器"""
        self.batch_worker_running = False


class HighPerformanceConsumerPool:
    """高性能 Consumer 池 - 多進程處理"""
    
    def __init__(self, redis_client, logstash_handler, config: PerformanceConfig):
        self.redis_client = redis_client
        self.logstash_handler = logstash_handler
        self.config = config
        self.workers = []
        self.running = False
        
        # 線程池
        self.executor = ThreadPoolExecutor(max_workers=config.consumer_threads)
    
    async def start_consumer_pool(self):
        """啟動消費者池"""
        self.running = True
        logger.info(f"Starting {self.config.consumer_workers} consumer workers")
        
        # 創建多個 worker
        tasks = []
        for worker_id in range(self.config.consumer_workers):
            task = asyncio.create_task(self._consumer_worker(worker_id))
            tasks.append(task)
        
        # 等待所有 worker
        await asyncio.gather(*tasks)
    
    async def _consumer_worker(self, worker_id: int):
        """消費者工作器"""
        logger.info(f"Consumer worker {worker_id} started")
        
        while self.running:
            try:
                # 批次取出資料
                batch = await self._fetch_batch(worker_id)
                
                if batch:
                    # 並行處理批次資料
                    await self._process_batch_parallel(worker_id, batch)
                else:
                    # 沒有資料時短暫休息
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Consumer worker {worker_id} error: {e}")
                await asyncio.sleep(1)
    
    async def _fetch_batch(self, worker_id: int) -> List:
        """批次取出資料"""
        batch = []
        
        try:
            for _ in range(self.config.batch_size):
                usage = self.redis_client.dequeue_usage()
                if usage:
                    batch.append(usage)
                else:
                    break
            
            if batch:
                logger.debug(f"Worker {worker_id} fetched batch: {len(batch)} items")
            
            return batch
            
        except Exception as e:
            logger.error(f"Worker {worker_id} fetch failed: {e}")
            return []
    
    async def _process_batch_parallel(self, worker_id: int, batch: List):
        """並行處理批次資料"""
        try:
            # 使用線程池並行發送到 Logstash
            loop = asyncio.get_event_loop()
            
            # 分割批次為更小的子批次
            sub_batch_size = max(1, len(batch) // self.config.consumer_threads)
            sub_batches = [
                batch[i:i + sub_batch_size] 
                for i in range(0, len(batch), sub_batch_size)
            ]
            
            # 並行處理子批次
            tasks = []
            for sub_batch in sub_batches:
                task = loop.run_in_executor(
                    self.executor,
                    self._send_to_logstash_sync,
                    sub_batch
                )
                tasks.append(task)
            
            # 等待所有子批次完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            success_count = sum(1 for r in results if isinstance(r, int) and r > 0)
            logger.info(f"Worker {worker_id} processed {success_count}/{len(sub_batches)} sub-batches")
            
        except Exception as e:
            logger.error(f"Worker {worker_id} parallel processing failed: {e}")
    
    def _send_to_logstash_sync(self, batch: List) -> int:
        """同步發送到 Logstash（在線程池中執行）"""
        try:
            return self.logstash_handler.batch_save_usage(batch)
        except Exception as e:
            logger.error(f"Logstash sync send failed: {e}")
            return 0
    
    def stop_consumer_pool(self):
        """停止消費者池"""
        self.running = False
        self.executor.shutdown(wait=True)
        logger.info("Consumer pool stopped")


# 全域高性能配置
HIGH_PERFORMANCE_CONFIG = PerformanceConfig(
    redis_pool_size=20,
    batch_size=200,  # 更大的批次
    batch_timeout=0.3,  # 更快的批次處理
    consumer_workers=12,  # 更多 worker
    consumer_threads=6,
    max_queue_size=50000  # 更大的佇列
)