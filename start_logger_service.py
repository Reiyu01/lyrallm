#!/usr/bin/env python3
"""
啟動企業級 Token Usage Logger Service
獨立於 SK API，專職處理高性能數據追蹤
"""

import asyncio
import logging
import signal
import sys
from logger_service import RedisClient, LogstashHandler

# 有條件地匯入 high_performance；若不存在則使用簡單 consumer 作為 fallback
try:
    from logger_service.high_performance import (
        HighPerformanceTokenProducer,
        HighPerformanceConsumerPool,
        PerformanceConfig,
    )
    HIGH_PERF_AVAILABLE = True
except Exception:
    HIGH_PERF_AVAILABLE = False
    # 簡單 consumer 在 consumer.py
    from logger_service.consumer import TokenUsageConsumer

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TokenLoggerService:
    """企業級 Token Usage Logger 服務"""
    
    def __init__(self):
        # 若 high-performance 模組可用，使用其 config；否則建立一個最小化的 config
        if HIGH_PERF_AVAILABLE:
            self.config = PerformanceConfig()
        else:
            class SimpleConfig:
                consumer_workers = 1
                batch_size = 10
            self.config = SimpleConfig()

        self.redis_client = RedisClient()
        self.logstash_handler = LogstashHandler()
        self.consumer_pool = None
        self.running = False
    
    async def start_service(self):
        """啟動 Logger 服務"""
        logger.info("🚀 Starting Enterprise Token Logger Service")
        logger.info(f"Configuration: {self.config.consumer_workers} workers, batch size {self.config.batch_size}")
        
        try:
            # 測試連接
            if not self.redis_client.test_connection():
                raise Exception("Redis connection failed")
            
            if not self.logstash_handler.test_connection():
                raise Exception("Logstash connection failed")
            
            # 啟動高性能消費者池（如果可用），否則啟動簡單 consumer
            if HIGH_PERF_AVAILABLE:
                self.consumer_pool = HighPerformanceConsumerPool(
                    self.redis_client,
                    self.logstash_handler,
                    self.config,
                )

                self.running = True
                logger.info("✅ Token Logger Service (high-perf) started successfully")
                logger.info(f"📊 Configuration: {self.config.consumer_workers} workers, batch size {self.config.batch_size}")
                # 啟動消費者池（阻塞直到停止）
                await self.consumer_pool.start_consumer_pool()
            else:
                logger.info("⚠️ High-performance components not available; starting simple consumer")
                consumer = TokenUsageConsumer(self.redis_client, self.logstash_handler)
                self.running = True
                logger.info("✅ Token Logger Service (simple consumer) started successfully")
                logger.info(f"📊 Configuration: workers=1, batch size={self.config.batch_size}")
                await consumer.start_consuming(batch_size=self.config.batch_size)
            
        except Exception as e:
            logger.error(f"❌ Failed to start Token Logger Service: {e}")
            sys.exit(1)
    
    async def stop_service(self):
        """停止 Logger 服務"""
        logger.info("🛑 Stopping Token Logger Service...")
        self.running = False
        
        if self.consumer_pool:
            self.consumer_pool.stop_consumer_pool()
        
        logger.info("✅ Token Logger Service stopped")
    
    def setup_signal_handlers(self):
        """設置信號處理器"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            asyncio.create_task(self.stop_service())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """主函數"""
    logger_service = TokenLoggerService()
    logger_service.setup_signal_handlers()
    
    try:
        await logger_service.start_service()
    except KeyboardInterrupt:
        await logger_service.stop_service()
    except Exception as e:
        logger.error(f"Service error: {e}")
        await logger_service.stop_service()

if __name__ == "__main__":
    print("=" * 60)
    print("🏢 Enterprise Token Usage Logger Service")
    print("📈 High-Performance Redis → Logstash → Elasticsearch")
    print("=" * 60)
    
    # 運行服務
    asyncio.run(main())