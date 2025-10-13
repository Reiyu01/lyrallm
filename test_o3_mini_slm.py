#!/usr/bin/env python3
"""
O3-mini SLM 分析器理論實現示例
演示如何使用 O3-mini 進行意圖分析
"""
import json
import asyncio
import sys
import os
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, '/home/b225nkust/open_web_ui_nkust')

from lyrallm.config.config_manager import config_manager

class O3MiniSLMAnalyzer:
    """使用 O3-mini 的意圖分析器"""
    
    def __init__(self):
        self.slm_config = config_manager.get_slm_config()
        self.system_prompt = config_manager.get_slm_system_prompt()
        self.user_prompt_template = config_manager.get_slm_user_prompt_template()
        
    async def analyze(self, user_query: str) -> Dict[str, Any]:
        """分析用戶請求意圖"""
        
        # 構建 prompt
        user_prompt = self.user_prompt_template.format(user_query=user_query)
        
        # 模擬 O3-mini API 調用 (實際會調用 Azure OpenAI)
        mock_response = await self._call_o3_mini(user_prompt)
        
        # 解析 JSON 回應
        try:
            result = json.loads(mock_response)
            
            # 標準化輸出格式
            return {
                'intent': result.get('intent', 'general'),
                'confidence': float(result.get('confidence', 0.5)),
                'complexity_score': float(result.get('complexity_score', 5.0)),
                'domain': result.get('domain', 'general'),
                'language': result.get('language', 'zh-TW'),
                'estimated_tokens': int(result.get('estimated_tokens', 100)),
                'processing_time_ms': 200,  # O3-mini 典型響應時間
                'analyzer': 'o3-mini-slm'
            }
            
        except json.JSONDecodeError:
            # JSON 解析失敗的 fallback
            return self._fallback_analysis(user_query)
    
    async def _call_o3_mini(self, prompt: str) -> str:
        """模擬 O3-mini API 調用"""
        
        # 實際實現會是：
        # return await azure_openai_client.chat.completions.create(
        #     model=self.slm_config['deployment_name'],
        #     messages=[
        #         {"role": "system", "content": self.system_prompt},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=self.slm_config.get('temperature', 0.1),
        #     max_tokens=self.slm_config.get('max_tokens', 150)
        # )
        
        # 這裡返回模擬回應
        return '''
        {
            "intent": "code_generation",
            "confidence": 0.92,
            "complexity_score": 7.5,
            "domain": "programming",
            "language": "zh-TW",
            "estimated_tokens": 200
        }
        '''
    
    def _fallback_analysis(self, user_query: str) -> Dict[str, Any]:
        """當 O3-mini 回應格式錯誤時的 fallback"""
        
        # 簡單的關鍵字匹配 fallback
        query_lower = user_query.lower()
        
        if any(word in query_lower for word in ['程式', '代碼', '函數', 'code', 'function']):
            intent = 'code_generation'
            complexity = 7.0
        elif any(word in query_lower for word in ['分析', '資料', '數據', 'analysis', 'data']):
            intent = 'data_analysis'  
            complexity = 6.0
        elif any(word in query_lower for word in ['摘要', '總結', 'summary']):
            intent = 'text_summary'
            complexity = 4.0
        else:
            intent = 'qa_general'
            complexity = 3.0
            
        return {
            'intent': intent,
            'confidence': 0.6,  # 較低置信度表示是 fallback
            'complexity_score': complexity,
            'domain': 'general',
            'language': 'zh-TW',
            'estimated_tokens': 100,
            'processing_time_ms': 50,
            'analyzer': 'o3-mini-fallback'
        }

# 測試 O3-mini SLM 分析器
async def test_o3_mini_analyzer():
    """測試 O3-mini 分析器"""
    
    print("=" * 60)
    print("O3-mini SLM 分析器測試")
    print("=" * 60)
    
    analyzer = O3MiniSLMAnalyzer()
    
    # 測試不同類型的請求
    test_queries = [
        "請幫我寫一個 Python 排序函數",
        "分析這份銷售資料的趨勢", 
        "幫我總結這篇文章",
        "什麼是機器學習？",
        "翻譯這段英文"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. 測試查詢: '{query}'")
        result = await analyzer.analyze(query)
        
        print(f"   意圖: {result['intent']}")
        print(f"   置信度: {result['confidence']:.2f}")
        print(f"   複雜度: {result['complexity_score']}/10")
        print(f"   領域: {result['domain']}")
        print(f"   預估處理時間: {result['processing_time_ms']}ms")
        print(f"   分析器: {result['analyzer']}")

if __name__ == "__main__":
    asyncio.run(test_o3_mini_analyzer())