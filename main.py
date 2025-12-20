"""
Ensure repo root is on sys.path so this file can be executed from inside the `lyrallm/` folder.
This small snippet inserts the repository root (parent of `lyrallm`) into sys.path when necessary.
"""
import os
import sys
_here = os.path.abspath(os.path.dirname(__file__))
# Candidate repo roots: parent of lyrallm (for main.py), or parent of parent (for scripts)
candidates = [
    os.path.abspath(os.path.join(_here, "..")),
    os.path.abspath(os.path.join(_here, "..", "..")),
]
for c in candidates:
    if os.path.isdir(os.path.join(c, "lyrallm")) and c not in sys.path:
        sys.path.insert(0, c)
        break

# 10/8
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import time
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

from lyrallm.config.config_manager import config_manager
from lyrallm.logger_service.event_consumer import start_event_consumer
from lyrallm.core.exceptions import LyraError
from api.models import router as models_router
from api.chat import router as chat_router
from api.table_upload import router as table_router

# 設定日誌
logging_config = config_manager.get_logging_config()
logging.basicConfig(
    level=getattr(logging, logging_config.get('level', 'INFO')),
    format=logging_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
    handlers=[
        logging.FileHandler(logging_config.get('file', 'semantic_kernel.log'), encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # 啟動
    logger.info("🚀 LyraLLM AI Gateway 啟動中...")
    
    # 檢查配置
    enabled_models = config_manager.get_available_models()
    default_model = config_manager.get_default_model()
    
    logger.info(f"📊 載入了 {len(enabled_models)} 個啟用的模型")
    logger.info(f"🎯 預設模型: {default_model}")
    
    for model in enabled_models:
        logger.info(f"  ✅ {model['name']} ({model['provider']})")
    
    # 初始化企業級模型管理器
    try:
        from lyrallm.core.model_manager import get_model_manager
        model_manager = await get_model_manager()
        logger.info("🏥 企業級模型健康監控已啟用")
    except Exception as e:
        logger.warning(f"⚠️ 模型管理器初始化失敗: {e}")
    
    try:
        start_event_consumer()
        logger.info("Token usage event consumer started")
    except Exception as e:
        logger.error(f"Failed to start token usage consumer: {e}")
    

    logger.info("✨ LyraLLM AI Gateway 啟動完成!")
    
    yield
    
    # 關閉
    logger.info("🛑 LyraLLM AI Gateway 正在關閉...")
    
    # 關閉全局 aiohttp session
    try:
        from lyrallm.core.model_executor import close_global_session
        await close_global_session()
        logger.info("🔌 全局連線池已關閉")
    except Exception as e:
        logger.warning(f"⚠️ 全局連線池關閉失敗: {e}")
    
    # 關閉模型管理器
    try:
        from lyrallm.core.model_manager import get_model_manager_sync
        model_manager = get_model_manager_sync()
        if model_manager:
            await model_manager.stop()
            logger.info("🏥 模型管理器已關閉")
    except Exception as e:
        logger.warning(f"⚠️ 模型管理器關閉失敗: {e}")

# 創建 FastAPI 應用
app = FastAPI(
    title="Semantic Kernel API Gateway",
    description="AI 模型請求處理的 Semantic Kernel 框架",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(models_router, tags=["Models"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(table_router, tags=["Table Upload"])

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """記錄所有請求"""
    start_time = time.time()
    
    # 記錄請求
    logger.info(f"請求: {request.method} {request.url}")
    
    # 處理請求
    response = await call_next(request)
    
    # 計算處理時間
    process_time = time.time() - start_time
    logger.info(f"回應: {response.status_code} - 處理時間: {process_time:.4f}秒")
    
    return response
    
    return response

@app.exception_handler(LyraError)
async def lyra_exception_handler(request: Request, exc: LyraError):
    """Lyra 業務異常處理"""
    logger.warning(f"業務異常 {request.url}: {exc.message} (Code: {exc.code})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全域異常處理"""
    logger.error(f"未處理的異常 {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "timestamp": int(time.time())
        }
    )

@app.get("/")
async def root():
    """根端點"""
    return {
        "name": "Semantic Kernel API Gateway",
        "version": "1.0.0",
        "description": "AI 模型請求處理的 Semantic Kernel 框架",
        "status": "running",
        "timestamp": int(time.time()),
        "endpoints": {
            "models": "/api/models (OpenAI 標準格式)",
            "models_detailed": "/api/models/detailed (包含詳細資訊)",
            "model_detail": "/api/models/{model_name}",
            "config": "/api/models/config",
            "reload": "/api/models/reload",
            "status": "/api/models/status",
            "docs": "/docs",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    try:
        # 檢查配置是否正常
        enabled_models = config_manager.get_available_models()
        
        return {
            "status": "healthy",
            "timestamp": int(time.time()),
            "models_count": len(enabled_models),
            "config_loaded": True
        }
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": int(time.time()),
                "error": str(e)
            }
        )

@app.get("/api/info")
async def get_api_info():
    """取得 API 資訊"""
    server_config = config_manager.get_server_config()
    sk_config = config_manager.get_semantic_kernel_config()
    
    # 獲取模型健康狀態
    model_status = {}
    try:
        from lyrallm.core.model_manager import get_model_manager_sync
        model_manager = get_model_manager_sync()
        if model_manager:
            healthy_models = model_manager.get_healthy_models()
            all_metrics = model_manager.get_all_metrics()
            model_status = {
                "healthy_count": len(healthy_models),
                "total_count": len(all_metrics),
                "healthy_models": healthy_models
            }
    except Exception as e:
        logger.warning(f"Failed to get model status: {e}")
    
    return {
        "api_name": "LyraLLM AI Gateway",
        "version": "1.0.0",
        "server_config": {
            "host": server_config.get('host', '0.0.0.0'),
            "port": server_config.get('port', 8081),
            "debug": server_config.get('debug', False)
        },
        "semantic_kernel": {
            "plugins_directory": sk_config.get('plugins_directory', './plugins'),
            "memory_store": sk_config.get('memory_store', 'sqlite'),
            "enable_planner": sk_config.get('enable_planner', True),
            "enable_functions": sk_config.get('enable_functions', True)
        },
        "model_status": model_status,
        "timestamp": int(time.time())
    }

@app.get("/api/models/health")
async def get_models_health():
    """取得模型健康狀態詳細資訊"""
    try:
        from lyrallm.core.model_manager import get_model_manager_sync
        model_manager = get_model_manager_sync()
        
        if not model_manager:
            return {"error": "Model manager not initialized"}
        
        all_metrics = model_manager.get_all_metrics()
        
        health_report = {
            "timestamp": int(time.time()),
            "total_models": len(all_metrics),
            "healthy_models": len(model_manager.get_healthy_models()),
            "models": {}
        }
        
        for name, metrics in all_metrics.items():
            health_report["models"][name] = {
                "status": metrics.status.value,
                "total_requests": metrics.total_requests,
                "success_rate": (1.0 - metrics.error_rate) if metrics.total_requests > 0 else 1.0,
                "avg_latency_ms": metrics.avg_latency_ms,
                "last_success": metrics.last_success.isoformat() if metrics.last_success else None,
                "last_failure": metrics.last_failure.isoformat() if metrics.last_failure else None
            }
        
        return health_report
        
    except Exception as e:
        logger.error(f"Failed to get model health: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # 取得伺服器配置
    server_config = config_manager.get_server_config()
    
    # 啟動服務
    uvicorn.run(
        "main:app",
        host=server_config.get('host', '0.0.0.0'),
        port=server_config.get('port', 8081),
        reload=False,  # 關閉自動重載以避免不斷重啟
        log_level=logging_config.get('level', 'info').lower()
    )

