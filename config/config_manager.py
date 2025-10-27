import yaml

import os

import json

import logging

from typing import Any, Dict, List, Optional

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

        self.roles_config: Dict[str, Dict[str, Any]] = {}

        self.auth_default_role: Optional[str] = None

        self._load_roles_config()

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

        self._load_roles_config()

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



    # -----------------------------

    # Capability / IQ → percentile → level (1-10)

    # -----------------------------

    def _compute_capability_cache(self):

        if hasattr(self, '_capability_cache') and self._capability_cache:

            return

        models = [m for m in self.get_all_models() if m.get('iq_score') is not None]

        if not models:

            self._capability_cache = {}

            return

        # Rank-based percentile

        scored = sorted(models, key=lambda m: m.get('iq_score'))

        n = len(scored)

        percentiles = {}

        for idx, m in enumerate(scored, start=1):

            pr = 100.0 * (idx - 0.5) / n

            percentiles[m['name']] = pr

        # Map PR -> capability level (1..10) using optional gamma

        gamma = 1.0  # could make configurable later

        capability = {}

        for m in models:

            pr = percentiles[m['name']]

            level = 1 + 9 * ((pr / 100.0) ** gamma)

            capability[m['name']] = {

                'iq': m.get('iq_score'),

                'pr': pr,

                'base_level': round(level, 2)

            }

        self._capability_cache = capability



    def get_model_capability(self, model_name: str, intent: str = None) -> dict:

        """Return capability info for model (intent now ignored for level adjustment)."""

        self._compute_capability_cache()

        base = self._capability_cache.get(model_name)

        if not base:

            return {'level': None, 'pr': None, 'iq': None}

        level = base['base_level']

        return {

            'level': level,

            'pr': base['pr'],

            'iq': base['iq']

        }



    def get_all_capabilities(self) -> dict:

        self._compute_capability_cache()

        return self._capability_cache.copy()



# 全域實例


    def _load_roles_config(self):
        """Load RBAC role definitions from config.yaml."""
        auth_config = self.config.get('auth', {})
        roles_raw = auth_config.get('roles', [])

        parsed: Dict[str, Dict[str, Any]] = {}
        if isinstance(roles_raw, list):
            for item in roles_raw:
                if not isinstance(item, dict):
                    logger.warning("Skipping invalid role entry (expected dict): %s", item)
                    continue

                name = str(item.get('name', '')).strip()
                if not name:
                    logger.warning("Skipping role entry without a name: %s", item)
                    continue

                def _as_str_list(values: Any) -> List[str]:
                    if not values:
                        return []
                    if isinstance(values, (list, tuple, set)):
                        cleaned: List[str] = []
                        for value in values:
                            if value is None:
                                continue
                            text_value = str(value).strip()
                            if not text_value or text_value in cleaned:
                                continue
                            cleaned.append(text_value)
                        return cleaned
                    text_value = str(values).strip()
                    return [text_value] if text_value else []

                routing_policies = item.get('routing_policies')
                if routing_policies is None:
                    routing_policies = {}
                elif not isinstance(routing_policies, dict):
                    logger.warning(
                        "Role '%s' has invalid routing_policies; expected dict but got %s",
                        name,
                        type(routing_policies).__name__,
                    )
                    routing_policies = {}

                role_entry: Dict[str, Any] = {
                    'name': name,
                    'description': item.get('description', ''),
                    'inherits': _as_str_list(item.get('inherits')),
                    'permissions': _as_str_list(item.get('permissions')),
                    'feature_flags': _as_str_list(item.get('feature_flags')),
                    'routing_policies': routing_policies,
                    'metadata': item.get('metadata') or {},
                }

                allowed_models = _as_str_list(item.get('allowed_models'))
                if allowed_models:
                    role_entry['allowed_models'] = allowed_models

                parsed[name] = role_entry
        else:
            logger.warning("auth.roles should be a list - got %s", type(roles_raw).__name__)

        self.roles_config = parsed

        default_role = auth_config.get('default_role')
        if isinstance(default_role, str) and default_role in parsed:
            self.auth_default_role = default_role
        elif parsed:
            fallback = sorted(parsed.keys())[0]
            if default_role and default_role not in parsed:
                logger.warning(
                    "Configured default_role '%s' not found; using '%s' instead",
                    default_role,
                    fallback,
                )
            self.auth_default_role = fallback
        else:
            self.auth_default_role = None
            if default_role:
                logger.warning("Configured default_role '%s' but no roles were loaded", default_role)

    def get_auth_config(self) -> Dict[str, Any]:
        """Return the raw auth configuration."""
        return self.config.get('auth', {})

    def get_roles_config(self) -> Dict[str, Dict[str, Any]]:
        """Return parsed role definitions keyed by role name."""
        return self.roles_config

    def get_role_config(self, role_name: str) -> Optional[Dict[str, Any]]:
        """Return configuration for a specific role."""
        return self.roles_config.get(role_name)

    def get_default_role_name(self) -> Optional[str]:
        """Return the default role name resolved from configuration."""
        return self.auth_default_role

config_manager = ConfigManager()

