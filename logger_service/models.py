from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import json


class TokenUsage(BaseModel):
    """Token 使用量記錄模型"""
    request_id: str
    timestamp: datetime
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    endpoint: str = "/v1/chat/completions"
    status: str = "success"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def to_json(self) -> str:
        """轉換為 JSON 字符串用於 Redis"""
        return self.model_dump_json()
    
    @classmethod
    def from_json(cls, json_str: str) -> "TokenUsage":
        """從 JSON 字符串創建對象"""
        data = json.loads(json_str)
        if isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class TokenStats(BaseModel):
    """Token 統計資料"""
    total_requests: int
    total_tokens: int
    total_cost_usd: float
    avg_tokens_per_request: float
    most_used_model: str
    time_range: str