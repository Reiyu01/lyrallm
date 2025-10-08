#!/usr/bin/env python3
"""
Plugin 管理器 - 基於配置文件動態載入 plugins
"""

import yaml
import logging
import importlib
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class PluginManager:
    """Plugin 管理器 - 負責根據配置文件動態載入 plugins"""
    
    def __init__(self, config_path: str = None):
        """
        初始化 Plugin 管理器
        
        Args:
            config_path: plugin 配置文件路徑，默認為 config/plugin_config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent / "plugin_config.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
        self.available_plugins = self._parse_plugin_configs()
        
        logger.info(f"🔌 Plugin Manager initialized with {len(self.available_plugins)} plugin definitions")
    
    def _load_config(self) -> Dict[str, Any]:
        """載入 plugin 配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"✅ Loaded plugin config from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"❌ Failed to load plugin config from {self.config_path}: {e}")
            return {"plugins": {}, "settings": {}}
    
    def _parse_plugin_configs(self) -> Dict[str, Dict[str, Any]]:
        """解析 plugin 配置"""
        plugins = {}
        for plugin_id, plugin_config in self.config.get('plugins', {}).items():
            # 檢查是否啟用
            if not plugin_config.get('enabled', True):
                logger.info(f"🔌 Plugin '{plugin_id}' is disabled in config")
                continue
                
            plugins[plugin_id] = plugin_config
            logger.debug(f"🔌 Registered plugin config: {plugin_id}")
        
        return plugins
    
    def get_plugins_for_features(self, features) -> List[Dict[str, Any]]:
        """
        根據前端 features 參數，返回需要載入的 plugins 列表
        
        Args:
            features: Features 物件，包含前端啟用的功能
            
        Returns:
            List[Dict]: 需要載入的 plugin 配置列表
        """
        if not features:
            return []
        
        plugins_to_load = []
        
        for plugin_id, plugin_config in self.available_plugins.items():
            feature_name = plugin_config.get('feature_name')
            
            # 檢查前端是否啟用了對應的 feature
            if hasattr(features, feature_name) and getattr(features, feature_name):
                plugins_to_load.append({
                    'id': plugin_id,
                    'config': plugin_config
                })
                logger.info(f"🎯 Plugin '{plugin_id}' selected for feature '{feature_name}'")
        
        return plugins_to_load
    
    def load_plugin_instance(self, plugin_config: Dict[str, Any]):
        """
        載入單個 plugin 實例
        
        Args:
            plugin_config: plugin 配置字典
            
        Returns:
            plugin 實例或 None
        """
        try:
            # 動態導入 plugin 類別
            plugin_class_path = plugin_config['plugin_class']
            module_path, class_name = plugin_class_path.rsplit('.', 1)
            
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            
            # 檢查配置（如果需要）
            if plugin_config.get('require_config', False):
                config_module_path = plugin_config.get('config_module')
                config_check_method = plugin_config.get('config_check_method', 'is_configured')
                
                if config_module_path:
                    config_module = importlib.import_module(config_module_path)
                    config_checker = getattr(config_module, config_check_method)
                    
                    if not config_checker():
                        logger.warning(f"⚠️  Plugin config check failed for {plugin_config['plugin_class']}")
                        return None
            
            # 創建 plugin 實例
            plugin_instance = plugin_class()
            logger.info(f"✅ Loaded plugin: {plugin_config['plugin_class']}")
            return plugin_instance
            
        except Exception as e:
            logger.error(f"❌ Failed to load plugin {plugin_config.get('plugin_class', 'unknown')}: {e}")
            if self.config.get('settings', {}).get('continue_on_error', True):
                return None
            else:
                raise
    
    async def load_plugins_to_kernel(self, kernel, model_name: str, features) -> int:
        """
        根據 features 動態載入 plugins 到 kernel
        
        Args:
            kernel: Semantic Kernel 實例
            model_name: 模型名稱（用於 logging）
            features: Features 物件
            
        Returns:
            int: 成功載入的 plugin 數量
        """
        if not features:
            logger.info(f"🔌 [{model_name}] No features specified, basic chat mode only")
            return 0
        
        plugins_to_load = self.get_plugins_for_features(features)
        plugins_loaded = 0
        
        for plugin_info in plugins_to_load:
            plugin_id = plugin_info['id']
            plugin_config = plugin_info['config']
            
            try:
                # 載入 plugin 實例
                plugin_instance = self.load_plugin_instance(plugin_config)
                
                if plugin_instance:
                    # 取得 plugin 細項參數
                    plugin_params = self._get_plugin_params(features, plugin_id)
                    
                    # 如果 plugin 有參數，嘗試設定
                    if plugin_params and hasattr(plugin_instance, 'set_params'):
                        try:
                            plugin_instance.set_params(plugin_params)
                            logger.info(f"🔧 [{model_name}] Set parameters for plugin '{plugin_id}': {plugin_params}")
                        except Exception as e:
                            logger.warning(f"⚠️  [{model_name}] Failed to set parameters for plugin '{plugin_id}': {e}")
                    
                    # 添加到 kernel
                    kernel_name = plugin_config.get('kernel_name', plugin_id)
                    kernel.add_plugin(plugin_instance, plugin_name=kernel_name)
                    plugins_loaded += 1
                    
                    logger.info(f"✅ [{model_name}] Loaded plugin '{plugin_id}' as '{kernel_name}' (frontend enabled)")
                else:
                    logger.warning(f"⚠️  [{model_name}] Plugin '{plugin_id}' not loaded - config check failed")
                    
            except Exception as e:
                logger.error(f"❌ [{model_name}] Failed to load plugin '{plugin_id}': {e}")
                if not self.config.get('settings', {}).get('continue_on_error', True):
                    raise
        
        return plugins_loaded
    
    def _get_plugin_params(self, features, plugin_id: str) -> dict:
        """取得特定 plugin 的細項參數 - 動態處理所有參數"""
        try:
            if not features:
                return {}
            
            # 動態查找對應的參數欄位
            plugin_config = self.config.get('plugins', {}).get(plugin_id, {})
            feature_name = plugin_config.get('feature_name', plugin_id)
            param_field_name = f"{feature_name}_params"
            
            # 檢查是否有對應的參數欄位
            if hasattr(features, param_field_name):
                param_obj = getattr(features, param_field_name)
                if param_obj is not None:
                    return param_obj.model_dump(exclude_none=True)
            
            return {}
        except Exception as e:
            logger.warning(f"無法取得 plugin '{plugin_id}' 的參數: {e}")
            return {}
    
    def get_available_feature_names(self) -> List[str]:
        """取得所有可用的功能名稱列表"""
        feature_names = []
        for plugin_config in self.available_plugins.values():
            feature_name = plugin_config.get('feature_name')
            if feature_name and feature_name not in feature_names:
                feature_names.append(feature_name)
        return feature_names
    
    def get_plugin_configs(self) -> Dict[str, Dict[str, Any]]:
        """取得所有 plugin 配置"""
        return self.config.get('plugins', {})
    
    def get_plugin_info(self) -> Dict[str, Any]:
        """返回 plugin 配置資訊，用於狀態查詢"""
        return {
            'total_plugins': len(self.config.get('plugins', {})),
            'available_plugins': len(self.available_plugins),
            'plugin_list': [
                {
                    'id': pid,
                    'feature_name': pconfig.get('feature_name'),
                    'description': pconfig.get('description'),
                    'enabled': pconfig.get('enabled', True),
                    'require_config': pconfig.get('require_config', False)
                }
                for pid, pconfig in self.config.get('plugins', {}).items()
            ],
            'settings': self.config.get('settings', {})
        }
    
    def reload_config(self):
        """重新載入配置文件（熱更新）"""
        logger.info("🔄 Reloading plugin configuration...")
        self.config = self._load_config()
        self.available_plugins = self._parse_plugin_configs()
        logger.info(f"✅ Plugin configuration reloaded with {len(self.available_plugins)} available plugins")

# 全域 Plugin 管理器實例
plugin_manager = PluginManager()

if __name__ == "__main__":
    # 測試 Plugin 管理器
    print("=== Plugin Manager 測試 ===")
    
    # 模擬 Features 物件
    class MockFeatures:
        def __init__(self, web_search=False, image_generation=False, code_interpreter=False):
            self.web_search = web_search
            self.image_generation = image_generation
            self.code_interpreter = code_interpreter
    
    # 測試不同的 features 組合
    test_cases = [
        ("無 features", None),
        ("只啟用 web_search", MockFeatures(web_search=True)),
        ("啟用多個 features", MockFeatures(web_search=True, image_generation=True)),
    ]
    
    for test_name, features in test_cases:
        print(f"\n--- {test_name} ---")
        plugins = plugin_manager.get_plugins_for_features(features)
        print(f"需要載入的 plugins: {[p['id'] for p in plugins]}")
    
    # 顯示 plugin 資訊
    print(f"\n--- Plugin 配置資訊 ---")
    info = plugin_manager.get_plugin_info()
    for key, value in info.items():
        if key != 'plugin_list':
            print(f"{key}: {value}")
    
    print(f"\n--- 可用 Plugins ---")
    for plugin in info['plugin_list']:
        status = "✅" if plugin['enabled'] else "❌"
        print(f"{status} {plugin['id']}: {plugin['description']}")