"""
智能參數管理器
根據不同模型類型自動選擇合適的參數
"""

import logging
from typing import Dict, Any, Optional
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase

logger = logging.getLogger(__name__)

class SmartParameterManager:
    """智能參數管理器，根據模型類型自動調整參數"""
    
    # 模型特殊參數配置
    MODEL_CONFIGS = {
        'o3-mini': {
            'supports_temperature': False,
            'supports_max_tokens': False,
            'supports_max_completion_tokens': True,
            'supports_top_p': False,
            'default_max_completion_tokens': 2000
        },
        'o1': {
            'supports_temperature': False,
            'supports_max_tokens': False,
            'supports_max_completion_tokens': True,
            'supports_top_p': False,
            'default_max_completion_tokens': 4000
        },
        'gpt-4o': {
            'supports_temperature': True,
            'supports_max_tokens': True,
            'supports_max_completion_tokens': True,
            'supports_top_p': True,
            'default_temperature': 0.7,
            'default_max_completion_tokens': 4000
        },
        'default': {
            'supports_temperature': True,
            'supports_max_tokens': True,
            'supports_max_completion_tokens': True,
            'supports_top_p': True,
            'default_temperature': 0.7,
            'default_max_completion_tokens': 2000
        }
    }
    
    @classmethod
    def get_model_name_from_service(cls, chat_service: ChatCompletionClientBase) -> str:
        """從聊天服務中提取模型名稱"""
        try:
            # 嘗試從 service_id 提取
            service_id = getattr(chat_service, 'service_id', '')
            
            # 檢查是否包含已知模型名稱
            for model_name in cls.MODEL_CONFIGS.keys():
                if model_name in service_id.lower():
                    return model_name
            
            # 嘗試從 ai_model_id 提取
            ai_model_id = getattr(chat_service, 'ai_model_id', '')
            for model_name in cls.MODEL_CONFIGS.keys():
                if model_name in ai_model_id.lower():
                    return model_name
            
            # 嘗試從 deployment_name 提取
            deployment_name = getattr(chat_service, 'deployment_name', '')
            for model_name in cls.MODEL_CONFIGS.keys():
                if model_name in deployment_name.lower():
                    return model_name
            
            logger.warning(f"未能識別模型類型，使用預設配置。service_id: {service_id}")
            return 'default'
            
        except Exception as e:
            logger.warning(f"模型名稱提取失敗: {e}，使用預設配置")
            return 'default'
    
    @classmethod
    def get_smart_settings(
        cls, 
        chat_service: ChatCompletionClientBase,
        max_completion_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        根據模型類型智能生成參數設置
        
        Args:
            chat_service: 聊天服務實例
            max_completion_tokens: 期望的最大完成tokens
            temperature: 期望的溫度設置
            top_p: 期望的top_p設置
            
        Returns:
            適合該模型的參數字典
        """
        model_name = cls.get_model_name_from_service(chat_service)
        config = cls.MODEL_CONFIGS.get(model_name, cls.MODEL_CONFIGS['default'])
        
        settings = {}
        
        # 設置 max_completion_tokens
        if config['supports_max_completion_tokens']:
            tokens = max_completion_tokens or config.get('default_max_completion_tokens', 2000)
            settings['max_completion_tokens'] = tokens
        elif config['supports_max_tokens']:
            tokens = max_completion_tokens or config.get('default_max_completion_tokens', 2000)
            settings['max_tokens'] = tokens
        
        # 設置 temperature
        if config['supports_temperature'] and temperature is not None:
            settings['temperature'] = temperature
        elif config['supports_temperature']:
            default_temp = config.get('default_temperature')
            if default_temp is not None:
                settings['temperature'] = default_temp
        
        # 設置 top_p
        if config['supports_top_p'] and top_p is not None:
            settings['top_p'] = top_p
        
        logger.info(f"為模型 {model_name} 生成智能參數: {settings}")
        return settings
    
    @classmethod
    def create_prompt_execution_settings(
        cls,
        chat_service: ChatCompletionClientBase,
        max_completion_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ):
        """
        創建適合該模型的 PromptExecutionSettings
        
        Args:
            chat_service: 聊天服務實例
            max_completion_tokens: 期望的最大完成tokens
            temperature: 期望的溫度設置
            top_p: 期望的top_p設置
            
        Returns:
            配置好的 PromptExecutionSettings 實例
        """
        settings_dict = cls.get_smart_settings(
            chat_service, max_completion_tokens, temperature, top_p
        )
        
        # 創建設置類實例
        settings_class = chat_service.get_prompt_execution_settings_class()
        return settings_class(**settings_dict)

# 便捷函數
def smart_settings(
    chat_service: ChatCompletionClientBase,
    max_completion_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None
):
    """
    便捷函數：創建智能參數設置
    
    使用方法:
    settings = smart_settings(chat_service, max_completion_tokens=1000, temperature=0.7)
    response = await chat_service.get_chat_message_contents(chat_history, settings=settings)
    """
    return SmartParameterManager.create_prompt_execution_settings(
        chat_service, max_completion_tokens, temperature, top_p
    )