import socket
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .models import TokenUsage, TokenStats

logger = logging.getLogger(__name__)


class TokenDatabase:
    """Token usage Logstash Beats 操作 (企業級 ELK Stack)"""
    
    def __init__(self, logstash_host: str = "elk.54ucl.com", logstash_port: int = 5044):
        self.logstash_host = logstash_host
        self.logstash_port = logstash_port
        self.init_database()
    
    def init_database(self):
        """初始化 Logstash 連接測試"""
        try:
            # 測試 Logstash 連接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.logstash_host, self.logstash_port))
            sock.close()
            
            if result == 0:
                logger.info(f"Logstash connection test successful: {self.logstash_host}:{self.logstash_port}")
            else:
                logger.warning(f"Cannot connect to Logstash: {self.logstash_host}:{self.logstash_port}")
                
        except Exception as e:
            logger.error(f"Failed to test Logstash connection: {e}")
    
    def save_usage(self, usage: TokenUsage) -> bool:
        """發送 token usage 到 Logstash (Beats 協議)"""
        try:
            # 構建 Beats 格式的訊息
            beats_message = {
                "@timestamp": usage.timestamp.isoformat(),
                "@metadata": {
                    "beat": "semantic-kernel",
                    "type": "token-usage",
                    "version": "1.0.0"
                },
                "fields": {
                    "service": "semantic-kernel-api",
                    "environment": "production"
                },
                # Token usage 資料
                "request_id": usage.request_id,
                "model_name": usage.model_name,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "cost_usd": usage.cost_usd,
                "user_id": usage.user_id,
                "endpoint": usage.endpoint,
                "status": usage.status,
                "event_type": "token_usage"
            }
            
            # 發送到 Logstash
            return self._send_to_logstash(beats_message)
            
        except Exception as e:
            logger.error(f"Failed to save usage to Logstash: {e}")
            return False
    
    def _send_to_logstash(self, message: dict) -> bool:
        """透過 TCP 發送 JSON 訊息到 Logstash"""
        try:
            # 轉換為 JSON 並添加換行符 (Logstash JSON codec)
            json_message = json.dumps(message) + "\n"
            
            # 建立 TCP 連接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.logstash_host, self.logstash_port))
            
            # 發送資料
            sock.sendall(json_message.encode('utf-8'))
            sock.close()
            
            logger.debug(f"Sent message to Logstash: {message.get('request_id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to Logstash: {e}")
            return False
    
    def get_usage_by_date_range(self, start_date: datetime, end_date: datetime) -> List[TokenUsage]:
        """根據日期範圍查詢 usage"""
        try:
            query = {
                "query": {
                    "bool": {
                        "filter": [
                            {
                                "range": {
                                    "timestamp": {
                                        "gte": start_date.isoformat(),
                                        "lte": end_date.isoformat()
                                    }
                                }
                            },
                            {
                                "term": {"status": "success"}
                            }
                        ]
                    }
                },
                "sort": [{"timestamp": {"order": "desc"}}],
                "size": 1000
            }
            
            response = self.es_client.search(index=self.index_name, body=query)
            
            usages = []
            for hit in response['hits']['hits']:
                data = hit['_source']
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                usages.append(TokenUsage(**data))
            
            return usages
            
        except Exception as e:
            logger.error(f"Failed to get usage by date range from ES: {e}")
            return []
    
    def get_daily_stats(self, date: datetime) -> Optional[TokenStats]:
        """取得每日統計"""
        try:
            start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 基本統計
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_requests,
                        SUM(total_tokens) as total_tokens,
                        SUM(cost_usd) as total_cost,
                        AVG(total_tokens) as avg_tokens
                    FROM token_usage 
                    WHERE timestamp BETWEEN ? AND ? AND status = 'success'
                ''', (start_date, end_date))
                
                stats = cursor.fetchone()
                
                # 最常用的模型
                cursor.execute('''
                    SELECT model_name, COUNT(*) as count
                    FROM token_usage 
                    WHERE timestamp BETWEEN ? AND ? AND status = 'success'
                    GROUP BY model_name 
                    ORDER BY count DESC 
                    LIMIT 1
                ''', (start_date, end_date))
                
                most_used = cursor.fetchone()
                most_used_model = most_used[0] if most_used else "N/A"
                
                if stats and stats[0] > 0:
                    return TokenStats(
                        total_requests=stats[0],
                        total_tokens=stats[1] or 0,
                        total_cost_usd=stats[2] or 0.0,
                        avg_tokens_per_request=stats[3] or 0.0,
                        most_used_model=most_used_model,
                        time_range=start_date.strftime("%Y-%m-%d")
                    )
                return None
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return None
    
    def get_model_usage_stats(self, days: int = 7) -> Dict[str, Dict]:
        """取得各模型使用統計"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        model_name,
                        COUNT(*) as requests,
                        SUM(total_tokens) as total_tokens,
                        SUM(cost_usd) as total_cost,
                        AVG(total_tokens) as avg_tokens
                    FROM token_usage 
                    WHERE timestamp >= ? AND status = 'success'
                    GROUP BY model_name
                    ORDER BY requests DESC
                ''', (start_date,))
                
                results = {}
                for row in cursor.fetchall():
                    results[row[0]] = {
                        'requests': row[1],
                        'total_tokens': row[2] or 0,
                        'total_cost': row[3] or 0.0,
                        'avg_tokens': row[4] or 0.0
                    }
                return results
        except Exception as e:
            logger.error(f"Failed to get model usage stats: {e}")
            return {}