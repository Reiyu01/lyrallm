"""
Ollama Web Search Plugin 配置管理
"""

import os
from typing import Optional
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

class OllamaConfig:
    """Ollama Web Search 配置管理"""
    
    def __init__(self):
        # Web Search API 配置
        self.api_key = self._get_api_key()
        self.base_url = os.getenv("OLLAMA_WEB_SEARCH_BASE_URL", "https://ollama.com/api")
        self.timeout = int(os.getenv("OLLAMA_WEB_SEARCH_TIMEOUT", "30"))
        self.max_results_limit = int(os.getenv("OLLAMA_WEB_SEARCH_MAX_RESULTS", "10"))
        self.enabled = self._get_enabled_status()
        
        # 本地 Ollama 服務配置 (用於模型服務)
        self.local_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    def _get_api_key(self) -> Optional[str]:
        """從環境變數或配置檔案獲取 API Key"""
        # 優先從環境變數獲取
        api_key = os.getenv("OLLAMA_API_KEY") or os.getenv("OLLAMA_WEB_SEARCH_API_KEY")
        
        if not api_key:
            # 嘗試從配置檔案讀取（但先檢查方法是否存在）
            try:
                from lyrallm.config.config_manager import config_manager
                # config_manager 沒有 get_service_config 方法，暫時跳過
                # ollama_config = config_manager.get_service_config("ollama_web_search")
                # if ollama_config:
                #     api_key = ollama_config.get("api_key")
                pass
            except (ImportError, AttributeError):
                pass
        
        return api_key
    
    def _get_enabled_status(self) -> bool:
        """檢查 Web Search 是否啟用"""
        enabled_env = os.getenv("OLLAMA_WEB_SEARCH_ENABLED", "true").lower()
        return enabled_env in ("true", "1", "yes", "on")
    
    def is_configured(self) -> bool:
        """檢查是否已正確配置"""
        return bool(self.api_key and self.enabled)
    
    def get_config_dict(self) -> dict:
        """獲取配置字典"""
        return {
            # Web Search 配置
            "web_search": {
                "api_key": "***" if self.api_key else None,
                "base_url": self.base_url,
                "timeout": self.timeout,
                "max_results_limit": self.max_results_limit,
                "enabled": self.enabled,
                "configured": self.is_configured()
            },
            # 本地服務配置
            "local_service": {
                "base_url": self.local_base_url
            }
        }
    
    def get_web_search_config(self) -> dict:
        """獲取 Web Search 專用配置"""
        if not self.is_configured():
            raise ValueError(
                "Ollama Web Search not configured. Please set OLLAMA_API_KEY environment variable "
                "and ensure OLLAMA_WEB_SEARCH_ENABLED=true"
            )
        
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_results": self.max_results_limit
        }

# 全域配置實例
ollama_config = OllamaConfig()