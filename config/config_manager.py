import yaml
import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config.yaml"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """載入並解析 YAML 配置檔案"""
        try:
            if not self.config_path.exists():
                logger.error(f"配置檔案不存在: {self.config_path}")
                return self._get_default_config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if config is None:
                logger.warning("配置檔案是空的，使用預設配置")
                return self._get_default_config()
            
            # 替換環境變數
            config = self._replace_env_vars(config)
            logger.info(f"成功載入配置: {self.config_path}")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"YAML 解析錯誤 {self.config_path}: {e}")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"載入配置檔案失敗 {self.config_path}: {e}")
            return self._get_default_config()
    
    def _replace_env_vars(self, obj):
        """遞迴替換 ${VAR} 為環境變數"""
        if isinstance(obj, dict):
            return {k: self._replace_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
            env_var = obj[2:-1]
            env_value = os.getenv(env_var, '')
            if not env_value:
                logger.warning(f"環境變數 '{env_var}' 未設定或為空")
            return env_value
        return obj
    
    def _get_default_config(self) -> Dict:
        """回傳預設配置"""
        return {
            'server': {
                'host': '0.0.0.0',
                'port': 8081,
                'debug': True
            },
            'models': {
                'default_model': '',
                'available_models': []
            },
            'providers': {},
            'semantic_kernel': {
                'plugins_directory': './plugins',
                'memory_store': 'sqlite',
                'enable_planner': True,
                'enable_functions': True
            },
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'file': 'semantic_kernel.log'
            }
        }
    
    def get_server_config(self) -> Dict:
        """取得伺服器配置"""
        return self.config.get('server', {})
    
    def get_available_models(self) -> List[Dict]:
        """取得啟用的模型列表"""
        models = self.config.get('models', {}).get('available_models', [])
        enabled_models = [model for model in models if model.get('enabled', False)]
        logger.info(f"找到 {len(enabled_models)} 個啟用的模型")
        return enabled_models
    
    def get_all_models(self) -> List[Dict]:
        """取得所有模型列表（包含未啟用的）"""
        return self.config.get('models', {}).get('available_models', [])
    
    def get_default_model(self) -> str:
        """取得預設模型名稱"""
        return self.config.get('models', {}).get('default_model', '')
    
    def get_provider_config(self, provider_name: str) -> Dict:
        """取得特定提供商的配置"""
        return self.config.get('providers', {}).get(provider_name, {})
    
    def get_semantic_kernel_config(self) -> Dict:
        """取得 Semantic Kernel 配置"""
        return self.config.get('semantic_kernel', {})
    
    def get_logging_config(self) -> Dict:
        """取得日誌配置"""
        return self.config.get('logging', {})
    
    def get_model_by_name(self, model_name: str) -> Optional[Dict]:
        """根據名稱取得特定模型配置"""
        models = self.get_all_models()
        for model in models:
            if model.get('name') == model_name:
                return model
        return None
    
    def reload_config(self):
        """重新載入配置"""
        logger.info("重新載入配置...")
        self.config = self._load_config()
    
    def is_model_enabled(self, model_name: str) -> bool:
        """檢查模型是否啟用"""
        model = self.get_model_by_name(model_name)
        return model.get('enabled', False) if model else False

# 全域實例
config_manager = ConfigManager()