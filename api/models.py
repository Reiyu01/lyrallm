from fastapi import APIRouter, HTTPException
from typing import List, Dict
import time
import logging
from config.config_manager import config_manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/models")
async def get_models():
    """
    取得可用的模型列表
    完全相容於 OpenAI API 格式
    """
    try:
        available_models = config_manager.get_available_models()
        
        # OpenAI API 標準格式
        models_response = {
            "object": "list",
            "data": []
        }
        
        for model in available_models:
            # 完全符合 OpenAI API 的模型格式
            model_data = {
                "id": model["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": f"semantic-kernel",
                "permission": [
                    {
                        "id": f"modelperm-{model['name']}",
                        "object": "model_permission",
                        "created": int(time.time()),
                        "allow_create_engine": False,
                        "allow_sampling": True,
                        "allow_logprobs": True,
                        "allow_search_indices": False,
                        "allow_view": True,
                        "allow_fine_tuning": False,
                        "organization": "*",
                        "group": None,
                        "is_blocking": False
                    }
                ],
                "root": model["name"],
                "parent": None
            }
            models_response["data"].append(model_data)
        
        logger.info(f"返回 OpenAI 格式的 {len(models_response['data'])} 個模型")
        return models_response
        
    except Exception as e:
        logger.error(f"取得模型列表失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")

@router.get("/api/models/{model_name}")
async def get_model_detail(model_name: str):
    """
    取得特定模型的詳細資訊
    """
    try:
        model = config_manager.get_model_by_name(model_name)
        
        if not model:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
        
        model_detail = {
            "id": model["name"],
            "object": "model",
            "created": int(time.time()),
            "owned_by": f"semantic-kernel-{model.get('provider', 'unknown')}",
            "permission": [],
            "root": model["name"],
            "parent": None,
            "details": {
                "name": model["name"],
                "provider": model.get("provider", ""),
                "endpoint": model.get("endpoint", ""),
                "description": model.get("description", ""),
                "max_tokens": model.get("max_tokens", 4096),
                "temperature": model.get("temperature", 0.7),
                "deployment_name": model.get("deployment_name", ""),
                "api_version": model.get("api_version", ""),
                "enabled": model.get("enabled", False)
            }
        }
        
        logger.info(f"返回模型詳情: {model_name}")
        return model_detail
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取得模型詳情失敗 {model_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get model detail: {str(e)}")

@router.get("/api/models/detailed")
async def get_models_detailed():
    """
    取得詳細的模型列表（包含額外資訊）
    此端點供內部管理使用，非 OpenAI 標準格式
    """
    try:
        available_models = config_manager.get_available_models()
        
        models_response = {
            "object": "list",
            "data": []
        }
        
        for model in available_models:
            model_data = {
                "id": model["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": f"semantic-kernel-{model.get('provider', 'unknown')}",
                "permission": [],
                "root": model["name"],
                "parent": None,
                # 額外的詳細資訊
                "details": {
                    "description": model.get("description", ""),
                    "provider": model.get("provider", ""),
                    "endpoint": model.get("endpoint", ""),
                    "max_tokens": model.get("max_tokens", 4096),
                    "temperature": model.get("temperature", 0.7),
                    "deployment_name": model.get("deployment_name", ""),
                    "api_version": model.get("api_version", ""),
                    "enabled": model.get("enabled", False)
                }
            }
            models_response["data"].append(model_data)
        
        logger.info(f"返回詳細的 {len(models_response['data'])} 個模型資訊")
        return models_response
        
    except Exception as e:
        logger.error(f"取得詳細模型列表失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get detailed models: {str(e)}")

@router.get("/api/models/config")
async def get_models_config():
    """
    取得原始模型配置（包含未啟用的模型）
    """
    try:
        all_models = config_manager.get_all_models()
        default_model = config_manager.get_default_model()
        
        config_response = {
            "default_model": default_model,
            "total_models": len(all_models),
            "enabled_models": len(config_manager.get_available_models()),
            "models": all_models,
            "providers": {
                "azure_openai": config_manager.get_provider_config("azure_openai"),
                "openai": config_manager.get_provider_config("openai"),
                "ollama": config_manager.get_provider_config("ollama")
            }
        }
        
        logger.info(f"返回完整模型配置")
        return config_response
        
    except Exception as e:
        logger.error(f"取得模型配置失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models config: {str(e)}")

@router.post("/api/models/reload")
async def reload_models_config():
    """
    重新載入模型配置
    """
    try:
        config_manager.reload_config()
        available_models = config_manager.get_available_models()
        
        return {
            "status": "success",
            "message": "Configuration reloaded successfully",
            "enabled_models": len(available_models),
            "timestamp": int(time.time())
        }
        
    except Exception as e:
        logger.error(f"重新載入配置失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload config: {str(e)}")

@router.get("/api/models/status")
async def get_models_status():
    """
    取得模型狀態統計
    """
    try:
        all_models = config_manager.get_all_models()
        enabled_models = config_manager.get_available_models()
        
        status_by_provider = {}
        for model in all_models:
            provider = model.get('provider', 'unknown')
            if provider not in status_by_provider:
                status_by_provider[provider] = {"total": 0, "enabled": 0}
            status_by_provider[provider]["total"] += 1
            if model.get('enabled', False):
                status_by_provider[provider]["enabled"] += 1
        
        return {
            "total_models": len(all_models),
            "enabled_models": len(enabled_models),
            "disabled_models": len(all_models) - len(enabled_models),
            "default_model": config_manager.get_default_model(),
            "providers": status_by_provider,
            "timestamp": int(time.time())
        }
        
    except Exception as e:
        logger.error(f"取得模型狀態失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models status: {str(e)}")