"""
簡單的速率限制器
用於控制 API 調用頻率，避免 429 錯誤
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SimpleRateLimiter:
    """簡單的速率限制器"""
    
    def __init__(self, calls_per_minute: int = 30, delay_between_calls: float = 1.0):
        """
        初始化速率限制器
        
        Args:
            calls_per_minute: 每分鐘允許的調用次數
            delay_between_calls: 調用之間的固定延遲（秒）
        """
        self.calls_per_minute = calls_per_minute
        self.delay_between_calls = delay_between_calls
        self.call_times = []
        self.last_call_time = 0
        
        logger.info(f"🚦 速率限制器初始化: {calls_per_minute} 次/分鐘, {delay_between_calls}秒延遲")
    
    async def acquire(self):
        """獲取調用許可（會自動等待必要的時間）"""
        current_time = time.time()
        
        # 清理過期的調用記錄（超過1分鐘）
        cutoff_time = current_time - 60
        self.call_times = [t for t in self.call_times if t > cutoff_time]
        
        # 檢查是否需要等待（基於每分鐘調用次數）
        if len(self.call_times) >= self.calls_per_minute:
            wait_time = 60 - (current_time - self.call_times[0])
            if wait_time > 0:
                logger.info(f"⏳ 速率限制：等待 {wait_time:.2f} 秒")
                await asyncio.sleep(wait_time)
                current_time = time.time()
        
        # 檢查是否需要等待（基於固定延遲）
        time_since_last = current_time - self.last_call_time
        if time_since_last < self.delay_between_calls:
            wait_time = self.delay_between_calls - time_since_last
            logger.debug(f"⏱️ 固定延遲：等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)
            current_time = time.time()
        
        # 記錄這次調用
        self.call_times.append(current_time)
        self.last_call_time = current_time
    
    async def safe_api_call(self, api_func, *args, **kwargs):
        """
        安全的 API 調用包裝器
        
        Args:
            api_func: 要調用的 API 函數
            *args, **kwargs: API 函數的參數
            
        Returns:
            API 調用結果
        """
        await self.acquire()
        try:
            return await api_func(*args, **kwargs)
        except Exception as e:
            # 如果是 429 錯誤，額外等待
            if "429" in str(e) or "Too Many Requests" in str(e):
                logger.warning(f"⚠️ 收到 429 錯誤，額外等待 30 秒")
                await asyncio.sleep(30)
            raise

# 全域速率限制器實例
_global_rate_limiter: Optional[SimpleRateLimiter] = None

def get_rate_limiter() -> SimpleRateLimiter:
    """獲取全域速率限制器實例"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = SimpleRateLimiter(
            calls_per_minute=15,  # 更保守的設置：15次/分鐘
            delay_between_calls=3.0  # 3秒延遲
        )
    return _global_rate_limiter

async def safe_chat_completion(chat_service, chat_history, settings):
    """
    安全的聊天完成 API 調用
    
    Args:
        chat_service: 聊天服務實例
        chat_history: 聊天歷史
        settings: 設置參數
        
    Returns:
        API 調用結果
    """
    rate_limiter = get_rate_limiter()
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            return await rate_limiter.safe_api_call(
                chat_service.get_chat_message_contents,
                chat_history=chat_history,
                settings=settings
            )
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Too Many Requests" in error_str:
                wait_time = 60 + (retry * 30)  # 60, 90, 120 秒
                logger.warning(f"⚠️ 收到 429 錯誤，重試 {retry + 1}/{max_retries}，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                if retry == max_retries - 1:
                    raise Exception(f"達到最大重試次數，最後錯誤: {error_str}")
            else:
                raise