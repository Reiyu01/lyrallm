#!/usr/bin/env python3
"""
動態 Features 模型生成器
根據 plugin 配置自動生成 Features 類別和參數模型
"""

from pydantic import BaseModel, create_model, Field
from typing import Optional, Dict, Any, Type, List, Union
import logging

logger = logging.getLogger(__name__)

class DynamicFeaturesFactory:
    """動態 Features 工廠類別"""
    
    @staticmethod
    def _create_param_model(plugin_id: str, params_config: Dict[str, Any]) -> Type[BaseModel]:
        """
        根據配置創建參數模型
        
        Args:
            plugin_id: Plugin ID
            params_config: 參數配置字典
            
        Returns:
            動態生成的參數模型類別
        """
        try:
            class_name = params_config.get('class_name', f'{plugin_id.title()}Params')
            description = params_config.get('description', f'{plugin_id} 細項參數')
            fields_config = params_config.get('fields', {})
            
            # 創建動態欄位
            fields = {}
            for field_name, field_config in fields_config.items():
                field_type = field_config.get('type', 'str')
                is_optional = field_config.get('optional', True)
                default_value = field_config.get('default', None)
                field_description = field_config.get('description', '')
                
                # 解析類型字符串
                if field_type == 'str':
                    python_type = str
                elif field_type == 'List[str]':
                    python_type = List[str]
                elif field_type == 'Dict[str, Any]':
                    python_type = Dict[str, Any]
                elif field_type == 'int':
                    python_type = int
                elif field_type == 'float':
                    python_type = float
                elif field_type == 'bool':
                    python_type = bool
                else:
                    python_type = str  # 預設為字符串
                
                # 創建欄位定義
                if is_optional:
                    field_type_annotation = Optional[python_type]
                    fields[field_name] = (field_type_annotation, Field(default=default_value, description=field_description))
                else:
                    field_type_annotation = python_type
                    fields[field_name] = (field_type_annotation, Field(description=field_description))
            
            # 動態創建參數模型
            ParamModel = create_model(
                class_name,
                __base__=BaseModel,
                **fields
            )
            
            # 添加文檔字符串
            ParamModel.__doc__ = description
            
            logger.info(f"✅ 動態生成參數模型: {class_name}，包含欄位: {list(fields.keys())}")
            return ParamModel
            
        except Exception as e:
            logger.error(f"❌ 動態生成參數模型失敗 ({plugin_id}): {e}")
            # 回退到空的基本模型
            FallbackParamModel = create_model(
                f'{plugin_id.title()}Params',
                __base__=BaseModel
            )
            return FallbackParamModel
    
    @staticmethod
    def create_features_model(plugin_manager) -> Type[BaseModel]:
        """
        根據 plugin 配置動態創建 Features 模型
        
        Args:
            plugin_manager: Plugin 管理器實例
            
        Returns:
            動態生成的 Features 模型類別
        """
        try:
            # 取得所有可用的功能
            available_features = plugin_manager.get_available_feature_names()
            plugin_configs = plugin_manager.get_plugin_configs()
            
            # 創建動態欄位
            fields = {}
            param_models = {}
            
            # 基本功能開關
            for feature_name in available_features:
                fields[feature_name] = (Optional[bool], False)
            
            # 創建參數模型
            for plugin_id, plugin_config in plugin_configs.items():
                if 'params_model' in plugin_config:
                    feature_name = plugin_config.get('feature_name', plugin_id)
                    param_model = DynamicFeaturesFactory._create_param_model(plugin_id, plugin_config['params_model'])
                    param_models[feature_name] = param_model
                    
                    # 添加參數欄位到 Features 模型
                    param_field_name = f"{feature_name}_params"
                    fields[param_field_name] = (Optional[param_model], None)
            
            # 動態創建模型
            DynamicFeatures = create_model(
                'Features',
                **fields,
                __config__={'extra': 'allow'}  # 允許額外欄位
            )
            
            # 添加類別方法
            def get_available_features(cls) -> list:
                return available_features
            
            def get_enabled_features(self) -> list:
                model_data = self.model_dump()
                return [name for name, value in model_data.items() if value is True]
            
            def get_param_models(cls) -> Dict[str, Type[BaseModel]]:
                return param_models
            
            DynamicFeatures.get_available_features = classmethod(get_available_features)
            DynamicFeatures.get_enabled_features = get_enabled_features
            DynamicFeatures.get_param_models = classmethod(get_param_models)
            
            logger.info(f"✅ 動態生成 Features 模型，包含功能: {available_features}")
            logger.info(f"✅ 動態生成參數模型: {list(param_models.keys())}")
            return DynamicFeatures
            
        except Exception as e:
            logger.error(f"❌ 動態生成 Features 模型失敗: {e}")
            # 回退到空的基本模型，完全動態
            FallbackFeatures = create_model(
                'Features',
                __config__={'extra': 'allow'}  # 只允許動態欄位
            )
            
            # 為回退模型也添加方法
            def get_available_features(cls) -> list:
                return []  # 空的可用功能列表
            
            def get_enabled_features(self) -> list:
                model_data = self.model_dump()
                return [name for name, value in model_data.items() if value is True]
            
            def get_param_models(cls) -> Dict[str, Type[BaseModel]]:
                return {}
            
            FallbackFeatures.get_available_features = classmethod(get_available_features)
            FallbackFeatures.get_enabled_features = get_enabled_features
            FallbackFeatures.get_param_models = classmethod(get_param_models)
            
            logger.info("✅ 使用回退的空 Features 模型")
            return FallbackFeatures

if __name__ == "__main__":
    # 測試動態 Features 生成
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from semantic_kernel.config.plugin_manager import plugin_manager
    
    print("=== 動態 Features 模型測試 ===")
    
    # 生成動態模型
    FeaturesModel = DynamicFeaturesFactory.create_features_model(plugin_manager)
    
    print(f"可用功能: {FeaturesModel.get_available_features()}")
    
    # 測試實例創建
    features1 = FeaturesModel()
    print(f"預設實例: {features1}")
    
    features2 = FeaturesModel(web_search=True, image_generation=True)
    print(f"啟用功能: {features2.get_enabled_features()}")
    
    # 測試新功能
    features3 = FeaturesModel(web_search=True, custom_feature=True)  # 自定義功能
    print(f"包含自定義功能: {features3}")