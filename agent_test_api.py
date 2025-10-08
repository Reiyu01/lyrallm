#!/usr/bin/env python3
"""
簡化的 Agent 系統測試 API
專門用於測試多 Agent 協作功能
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging

# 本地匯入
from config.config_manager import config_manager
from agents.practical_agent_orchestrator import create_practical_agent_orchestrator

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Semantic Kernel Agent API",
    description="多 Agent 協作系統測試 API",
    version="1.0.0"
)

class AgentRequest(BaseModel):
    """Agent 請求模型"""
    message: str
    features: Optional[Dict[str, Any]] = {}

class AgentResponse(BaseModel):
    """Agent 回應模型"""
    response: str
    conversation_log: List[Dict[str, Any]]
    available_features: List[str]
    success: bool

@app.get("/")
async def root():
    """根路徑"""
    return {
        "message": "Semantic Kernel Agent API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    """健康檢查"""
    try:
        # 檢查配置
        models = config_manager.get_available_models()
        
        return {
            "status": "healthy",
            "available_models": len(models),
            "message": "Agent API 運行正常"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/agent/capabilities")
async def get_capabilities():
    """獲取 Agent 系統能力"""
    try:
        orchestrator = await create_practical_agent_orchestrator()
        
        if not orchestrator:
            raise HTTPException(status_code=500, detail="無法初始化 Agent 協調器")
        
        features = orchestrator.get_available_features()
        
        return {
            "available_features": features,
            "description": {
                "web_search": "網路搜尋和分析能力"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取能力失敗: {str(e)}")

@app.post("/agent/chat", response_model=AgentResponse)
async def agent_chat(request: AgentRequest):
    """Agent 聊天端點"""
    try:
        logger.info(f"收到 Agent 請求: {request.message[:50]}...")
        logger.info(f"請求功能: {request.features}")
        
        # 創建 Agent 協調器
        orchestrator = await create_practical_agent_orchestrator()
        
        if not orchestrator:
            raise HTTPException(status_code=500, detail="無法初始化 Agent 協調器")
        
        # 處理請求
        result = await orchestrator.process_request(request.message, request.features)
        
        # 獲取對話記錄和可用功能
        conversation_log = orchestrator.get_conversation_log()
        available_features = orchestrator.get_available_features()
        
        logger.info(f"Agent 回應完成，長度: {len(result)}")
        
        return AgentResponse(
            response=result,
            conversation_log=conversation_log,
            available_features=available_features,
            success=True
        )
        
    except Exception as e:
        logger.error(f"Agent 處理失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Agent 處理失敗: {str(e)}")

@app.get("/models")
async def get_models():
    """獲取可用模型"""
    try:
        models = config_manager.get_available_models()
        
        return {
            "models": [
                {
                    "name": model.get("name"),
                    "provider": model.get("provider"),
                    "enabled": model.get("enabled", False),
                    "description": model.get("description", "")
                }
                for model in models
            ],
            "total": len(models)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取模型失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 啟動 Semantic Kernel Agent 測試 API")
    
    uvicorn.run(
        "agent_test_api:app",
        host="0.0.0.0",
        port=8082,
        reload=True,
        log_level="info"
    )