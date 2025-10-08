import socket
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from loguru import logger as loguru_logger
from .models import TokenUsage, TokenStats

logger = logging.getLogger(__name__)


class LogstashHandler:
    """Token usage Logstash 處理器 - 企業級日誌收集"""
    
    def __init__(self, logstash_host: str = "elk.54ucl.com", logstash_port: int = 5044):
        self.logstash_host = logstash_host
        self.logstash_port = logstash_port
        self.connection_timeout = 5
        self.retry_count = 3
        self.test_connection()
    
    def test_connection(self):
        """測試 Logstash 連接"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connection_timeout)
            result = sock.connect_ex((self.logstash_host, self.logstash_port))
            sock.close()
            
            if result == 0:
                logger.info(f"Logstash connection successful: {self.logstash_host}:{self.logstash_port}")
                return True
            else:
                logger.warning(f"Logstash connection failed: {self.logstash_host}:{self.logstash_port}")
                return False
        except Exception as e:
            logger.error(f"Logstash connection error: {e}")
            return False
    
    def send_to_logstash(self, data: dict) -> bool:
        """發送資料到 Logstash (JSON over TCP)"""
        for attempt in range(self.retry_count):
            try:
                # 準備 JSON 資料
                json_data = json.dumps(data) + '\n'
                
                # 建立 TCP 連接
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.connection_timeout)
                sock.connect((self.logstash_host, self.logstash_port))
                
                # 發送資料
                sock.sendall(json_data.encode('utf-8'))
                sock.close()
                
                logger.info(f"Data sent to Logstash successfully: {data.get('request_id', 'unknown')}")
                return True
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to send to Logstash: {e}")
                if attempt == self.retry_count - 1:
                    logger.error(f"All {self.retry_count} attempts failed for request: {data.get('request_id', 'unknown')}")
                    return False
        
        return False
    
    def save_usage(self, usage: TokenUsage) -> bool:
        """儲存 token usage 記錄到 Logstash"""
        try:
            # 準備符合 ELK 標準的資料格式
            logstash_data = {
                "@timestamp": usage.timestamp.isoformat(),
                "@metadata": {
                    "beat": "semantic-kernel",
                    "version": "1.0.0"
                },
                "service": {
                    "name": "semantic-kernel-api",
                    "type": "ai-gateway"
                },
                "event": {
                    "category": "token_usage",
                    "type": "api_call",
                    "outcome": usage.status
                },
                "request": {
                    "id": usage.request_id,
                    "endpoint": usage.endpoint
                },
                "ai": {
                    "model": {
                        "name": usage.model_name,
                        "provider": "azure_openai"
                    },
                    "tokens": {
                        "prompt": usage.prompt_tokens,
                        "completion": usage.completion_tokens,
                        "total": usage.total_tokens
                    },
                    "cost": {
                        "amount": usage.cost_usd,
                        "currency": "USD"
                    }
                },
                "user": {
                    "id": usage.user_id
                },
                "host": {
                    "name": "semantic-kernel-service"
                },
                "tags": ["token-usage", "ai-api", "cost-tracking"]
            }
            
            return self.send_to_logstash(logstash_data)
            
        except Exception as e:
            logger.error(f"Failed to save usage to Logstash: {e}")
            return False
    
    def batch_save_usage(self, usages: List[TokenUsage]) -> int:
        """批次儲存 token usage 記錄"""
        success_count = 0
        
        try:
            for usage in usages:
                if self.save_usage(usage):
                    success_count += 1
                    
            logger.info(f"Batch save completed: {success_count}/{len(usages)} successful")
            return success_count
            
        except Exception as e:
            logger.error(f"Batch save error: {e}")
            return success_count
    
    def get_connection_status(self) -> dict:
        """取得連接狀態"""
        return {
            "host": self.logstash_host,
            "port": self.logstash_port,
            "connected": self.test_connection(),
            "retry_count": self.retry_count,
            "timeout": self.connection_timeout
        }


# 為了向後相容，保持 TokenDatabase 別名
class TokenDatabase(LogstashHandler):
    """Token Database - 企業級 Logstash 整合"""
    pass