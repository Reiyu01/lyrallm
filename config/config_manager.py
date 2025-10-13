import yaml
import os
import json
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
        self.config_dir = self.config_path.parent
        self.config = self._load_config()
        
        # 載入路由規則和價格資訊
        self.routing_rules = None
        self.pricing_data = None
        self._load_extended_configs()
    
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
    
    def _load_extended_configs(self):
        """載入擴展配置檔案"""
        try:
            # 載入路由規則
            routing_config = self.config.get('models', {}).get('routing', {})
            if routing_config.get('enabled', False):
                rules_file = routing_config.get('config_file', 'routing_rules.yaml')
                self._load_routing_rules(rules_file)
            
            # 載入價格資訊
            self._load_pricing_data()
            
        except Exception as e:
            logger.error(f"載入擴展配置失敗: {e}")

    def _load_routing_rules(self, rules_file: str):
        """載入路由規則配置"""
        try:
            # 首先嘗試在 config 目錄中查找
            rules_path = self.config_dir / "config" / rules_file
            if not rules_path.exists():
                # 如果不在 config 子目錄，嘗試在同級目錄
                rules_path = self.config_dir / rules_file
            
            if rules_path.exists():
                with open(rules_path, 'r', encoding='utf-8') as f:
                    self.routing_rules = yaml.safe_load(f)
                logger.info(f"成功載入路由規則: {rules_path}")
            else:
                logger.warning(f"路由規則檔案不存在: {rules_path}")
        except Exception as e:
            logger.error(f"載入路由規則失敗: {e}")

    def _load_pricing_data(self):
        """載入價格資訊"""
        try:
            # 首先嘗試在 config 目錄中查找
            pricing_path = self.config_dir / "config" / "model_prices_and_context_window.json"
            if not pricing_path.exists():
                # 如果不在 config 子目錄，嘗試在同級目錄
                pricing_path = self.config_dir / "model_prices_and_context_window.json"
            
            if pricing_path.exists():
                with open(pricing_path, 'r', encoding='utf-8') as f:
                    self.pricing_data = json.load(f)
                logger.info(f"成功載入價格資訊: {pricing_path}")
            else:
                logger.warning(f"價格資訊檔案不存在: {pricing_path}")
        except Exception as e:
            logger.error(f"載入價格資訊失敗: {e}")

    # 路由相關方法
    def get_routing_config(self) -> Dict:
        """取得路由配置"""
        return self.config.get('models', {}).get('routing', {})

    def is_routing_enabled(self) -> bool:
        """檢查路由功能是否啟用"""
        return self.get_routing_config().get('enabled', False)

    def get_routing_strategy(self) -> str:
        """取得路由策略"""
        return self.get_routing_config().get('strategy', 'vector_only')

    def get_intent_analysis_config(self) -> Dict:
        """取得意圖分析配置"""
        return self.get_routing_config().get('intent_analysis', {})

    def is_intent_analysis_enabled(self) -> bool:
        """檢查意圖分析是否啟用"""
        return self.get_intent_analysis_config().get('enabled', False)

    def get_intent_analysis_mode(self) -> str:
        """取得意圖分析模式"""
        return self.get_intent_analysis_config().get('mode', 'parallel')

    def get_vector_config(self) -> Dict:
        """取得向量分析器配置"""
        return self.get_intent_analysis_config().get('vector', {})

    def get_slm_config(self) -> Dict:
        """取得小模型分析器配置"""
        return self.get_intent_analysis_config().get('small_model', {})

    def get_fusion_config(self) -> Dict:
        """取得融合策略配置"""
        return self.get_intent_analysis_config().get('fusion', {})

    def get_intent_mapping(self) -> Dict:
        """取得意圖映射配置"""
        if not self.routing_rules:
            return {}
        return self.routing_rules.get('intent_mapping', {})

    def get_slm_analysis_config(self) -> Dict:
        """取得 SLM 分析器配置 (prompt 等)"""
        if not self.routing_rules:
            return {}
        return self.routing_rules.get('slm_analysis', {})

    def get_slm_system_prompt(self) -> str:
        """取得 SLM 系統 Prompt"""
        slm_config = self.get_slm_analysis_config()
        return slm_config.get('system_prompt', '')

    def get_slm_user_prompt_template(self) -> str:
        """取得 SLM 用戶 Prompt 模板"""
        slm_config = self.get_slm_analysis_config()
        return slm_config.get('user_prompt_template', 'Analyze: {user_query}')

    def get_routing_rules(self) -> Optional[Dict]:
        """取得路由規則"""
        return self.routing_rules

    def get_applicable_rules(self, context: Dict) -> List[Dict]:
        """根據上下文取得適用的路由規則"""
        if not self.routing_rules:
            return []
        
        rules = self.routing_rules.get('routing_rules', [])
        applicable_rules = []
        
        for rule in rules:
            if rule.get('enabled', True):
                applicable_rules.append(rule)
        
        # 按優先級排序 (高優先級在前)
        applicable_rules.sort(key=lambda r: r.get('priority', 0), reverse=True)
        return applicable_rules

    def get_user_tier_config(self, tier: str) -> Dict:
        """取得用戶分層配置"""
        if not self.routing_rules:
            return {}
        return self.routing_rules.get('user_tiers', {}).get(tier, {})

    def get_cost_management_config(self) -> Dict:
        """取得成本管理配置"""
        if not self.routing_rules:
            return {}
        return self.routing_rules.get('global', {}).get('cost_management', {})

    def get_model_pricing(self, model_name: str) -> Optional[Dict]:
        """取得模型價格資訊"""
        if not self.pricing_data:
            return None
        return self.pricing_data.get(model_name)

    def calculate_estimated_cost(self, model_name: str, input_tokens: int, output_tokens: int = 0) -> float:
        """計算預估成本"""
        pricing = self.get_model_pricing(model_name)
        if not pricing:
            return 0.0
        
        input_cost = pricing.get('input_cost_per_token', 0) * input_tokens
        output_cost = pricing.get('output_cost_per_token', 0) * output_tokens
        
        return input_cost + output_cost

    def reload_config(self):
        """重新載入配置"""
        logger.info("重新載入配置...")
        self.config = self._load_config()
        self._load_extended_configs()

    def reload_routing_rules(self):
        """熱更新路由規則"""
        logger.info("熱更新路由規則...")
        routing_config = self.config.get('models', {}).get('routing', {})
        if routing_config.get('enabled', False):
            rules_file = routing_config.get('config_file', 'routing_rules.yaml')
            self._load_routing_rules(rules_file)
    
    def is_model_enabled(self, model_name: str) -> bool:
        """檢查模型是否啟用"""
        model = self.get_model_by_name(model_name)
        return model.get('enabled', False) if model else False

# 全域實例
config_manager = ConfigManager()