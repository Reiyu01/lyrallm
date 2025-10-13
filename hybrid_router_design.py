#!/usr/bin/env python3
"""
Hybrid Router 實現架構設計
整合 Vector + O3-mini SLM + Rules 的智能路由系統
"""
import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

# 假設的 imports (實際實現時需要調整)
import sys
sys.path.insert(0, '/home/b225nkust/open_web_ui_nkust')

from lyrallm.config.config_manager import config_manager
# from lyrallm.core.semantic_router import SemanticRouter
# from lyrallm.adapters.o3_mini_slm_analyzer import O3MiniSLMAnalyzer  
# from lyrallm.core.rule_engine import RuleEngine

logger = logging.getLogger(__name__)

class ProcessingMode(Enum):
    """處理模式枚舉"""
    PARALLEL = "parallel"      # 並行處理
    PROGRESSIVE = "progressive" # 漸進式處理
    VECTOR_ONLY = "vector_only" # 純向量處理

@dataclass
class IntentAnalysisResult:
    """意圖分析結果"""
    intent: str
    confidence: float
    complexity_score: float
    domain: str
    language: str
    estimated_tokens: int
    processing_time_ms: int
    analyzer_used: str
    consensus: bool = False
    
@dataclass 
class RoutingDecision:
    """路由決策結果"""
    selected_model: str
    confidence: float
    reasoning: str
    fallback_models: List[str]
    estimated_cost: float
    processing_time_ms: int
    decision_path: List[str]

class HybridRouter:
    """
    Hybrid Router - 智能混合路由器
    
    整合三個分析引擎:
    1. Vector Router: 快速向量相似度檢索 (5-20ms)
    2. O3-mini SLM: 智能意圖分析 (200-500ms)  
    3. Rule Engine: 企業級規則決策 (10ms)
    
    支援兩種處理模式:
    - Parallel: Vector + SLM 並行，Rules 後執行
    - Progressive: Vector → SLM (條件觸發) → Rules
    """
    
    def __init__(self):
        """初始化 Hybrid Router"""
        self.config = config_manager.get_routing_config()
        self.intent_config = config_manager.get_intent_analysis_config()
        
        # 初始化三個引擎
        self._init_engines()
        
        # 處理模式配置
        self.processing_mode = ProcessingMode(
            self.intent_config.get('mode', 'parallel')
        )
        
        # 融合策略配置
        self.fusion_config = config_manager.get_fusion_config()
        
        logger.info(f"Hybrid Router 初始化完成，模式: {self.processing_mode.value}")
    
    def _init_engines(self):
        """初始化三個分析引擎"""
        
        # 1. Vector Router (複用現有 SemanticRouter)
        vector_config = config_manager.get_vector_config()
        if vector_config.get('enabled', True):
            # self.vector_router = SemanticRouter()
            self.vector_router = MockVectorRouter()  # 暫時使用模擬
        else:
            self.vector_router = None
            
        # 2. O3-mini SLM Analyzer  
        slm_config = config_manager.get_slm_config()
        if slm_config.get('enabled', True):
            # self.slm_analyzer = O3MiniSLMAnalyzer()
            self.slm_analyzer = MockO3MiniAnalyzer()  # 暫時使用模擬
        else:
            self.slm_analyzer = None
            
        # 3. Rule Engine
        rule_config = self.config.get('rule_engine', {})
        if rule_config.get('enabled', True):
            # self.rule_engine = RuleEngine()
            self.rule_engine = MockRuleEngine()  # 暫時使用模擬
        else:
            self.rule_engine = None
    
    async def route(self, query: str, context: Dict[str, Any] = None) -> RoutingDecision:
        """
        主要路由方法 - Hybrid Router 的核心
        
        Args:
            query: 用戶請求文本
            context: 上下文資訊 (用戶ID、會話資訊等)
            
        Returns:
            RoutingDecision: 路由決策結果
        """
        start_time = time.time()
        context = context or {}
        decision_path = []
        
        try:
            logger.info(f"開始 Hybrid 路由處理: {query[:50]}...")
            
            # 🎯 階段1: 意圖分析 (Vector + SLM)
            intent_result = await self._analyze_intent(query, decision_path)
            
            # 📋 階段2: 規則決策執行
            routing_decision = await self._execute_rules(
                intent_result, query, context, decision_path
            )
            
            # 📊 最終處理
            total_time = int((time.time() - start_time) * 1000)
            routing_decision.processing_time_ms = total_time
            routing_decision.decision_path = decision_path
            
            logger.info(
                f"Hybrid 路由完成: {routing_decision.selected_model} "
                f"(置信度: {routing_decision.confidence:.2f}, "
                f"耗時: {total_time}ms)"
            )
            
            return routing_decision
            
        except Exception as e:
            logger.error(f"Hybrid 路由失敗: {e}")
            return self._fallback_decision(query, context)
    
    async def _analyze_intent(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """
        階段1: 意圖分析 - Vector + SLM 聯合處理
        
        兩種模式:
        - Parallel: Vector 和 SLM 並行執行，然後融合
        - Progressive: Vector 先執行，根據置信度決定是否需要 SLM
        """
        
        if self.processing_mode == ProcessingMode.PARALLEL:
            return await self._parallel_intent_analysis(query, decision_path)
        elif self.processing_mode == ProcessingMode.PROGRESSIVE:
            return await self._progressive_intent_analysis(query, decision_path)
        elif self.processing_mode == ProcessingMode.VECTOR_ONLY:
            return await self._vector_only_analysis(query, decision_path)
        else:
            raise ValueError(f"不支援的處理模式: {self.processing_mode}")
    
    async def _parallel_intent_analysis(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """並行模式: Vector + SLM 同時執行"""
        
        decision_path.append("parallel_intent_analysis")
        
        # 🚀 並行啟動兩個分析器
        tasks = []
        
        if self.vector_router:
            tasks.append(self._safe_vector_analysis(query))
            
        if self.slm_analyzer:  
            tasks.append(self._safe_slm_analysis(query))
        
        # ⚡ 等待所有任務完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 🤝 融合結果
        vector_result = results[0] if len(results) > 0 else None
        slm_result = results[1] if len(results) > 1 else None
        
        return self._merge_intent_results(vector_result, slm_result, decision_path)
    
    async def _progressive_intent_analysis(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """漸進式模式: Vector → SLM (條件觸發)"""
        
        decision_path.append("progressive_intent_analysis")
        
        # 🏃 第1步: Vector 快速分析
        vector_result = None
        if self.vector_router:
            vector_result = await self._safe_vector_analysis(query)
            decision_path.append("vector_analysis_completed")
        
        # 🤔 判斷是否需要 SLM 分析
        need_slm = self._should_trigger_slm(vector_result)
        
        if need_slm and self.slm_analyzer:
            decision_path.append("slm_analysis_triggered")
            slm_result = await self._safe_slm_analysis(query)
            return self._merge_intent_results(vector_result, slm_result, decision_path)
        else:
            decision_path.append("vector_only_sufficient")
            return self._vector_to_intent_result(vector_result, decision_path)
    
    async def _vector_only_analysis(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """純向量模式: 只使用 Vector Router"""
        
        decision_path.append("vector_only_analysis")
        
        if not self.vector_router:
            raise RuntimeError("Vector Router 未啟用但配置為 vector_only 模式")
            
        vector_result = await self._safe_vector_analysis(query)
        return self._vector_to_intent_result(vector_result, decision_path)
    
    def _should_trigger_slm(self, vector_result: Dict) -> bool:
        """判斷是否需要觸發 SLM 分析"""
        
        if not vector_result:
            return True  # Vector 失敗，需要 SLM 作為備用
            
        confidence = vector_result.get('confidence', 0.0)
        threshold = self.fusion_config.get('fast_path_threshold', 0.9)
        
        # 置信度不夠高時觸發 SLM
        return confidence < threshold
    
    async def _safe_vector_analysis(self, query: str) -> Optional[Dict]:
        """安全的 Vector 分析 (處理異常)"""
        try:
            if self.vector_router:
                return await self.vector_router.route(query)
        except Exception as e:
            logger.warning(f"Vector 分析失敗: {e}")
        return None
    
    async def _safe_slm_analysis(self, query: str) -> Optional[Dict]:
        """安全的 SLM 分析 (處理異常)"""  
        try:
            if self.slm_analyzer:
                return await self.slm_analyzer.analyze(query)
        except Exception as e:
            logger.warning(f"SLM 分析失敗: {e}")
        return None
    
    def _merge_intent_results(self, vector_result: Dict, slm_result: Dict, 
                            decision_path: List[str]) -> IntentAnalysisResult:
        """融合 Vector 和 SLM 的分析結果"""
        
        # 獲取融合配置
        vector_weight = self.intent_config.get('vector', {}).get('weight', 0.3)
        slm_weight = self.intent_config.get('small_model', {}).get('weight', 0.7)
        consensus_bonus = self.fusion_config.get('consensus_bonus', 0.2)
        conflict_penalty = self.fusion_config.get('conflict_penalty', 0.1)
        
        # 處理各種情況
        if not vector_result and not slm_result:
            decision_path.append("both_analysis_failed")
            return self._fallback_intent_result()
            
        if not vector_result:
            decision_path.append("vector_failed_slm_only")
            return self._slm_to_intent_result(slm_result)
            
        if not slm_result:
            decision_path.append("slm_failed_vector_only")
            return self._vector_to_intent_result(vector_result, decision_path)
        
        # 🤝 兩者都成功，進行智能融合
        vector_intent = vector_result.get('intent', 'general')
        slm_intent = slm_result.get('intent', 'general')
        vector_confidence = vector_result.get('confidence', 0.5)
        slm_confidence = slm_result.get('confidence', 0.5)
        
        # 檢查意圖一致性
        consensus = (vector_intent == slm_intent)
        decision_path.append(f"consensus_{consensus}")
        
        if consensus:
            # 😊 意圖一致，增強置信度
            final_confidence = (
                vector_confidence * vector_weight + 
                slm_confidence * slm_weight + 
                consensus_bonus
            )
            final_intent = vector_intent
            decision_path.append("intent_consensus_boost")
            
        else:
            # 😕 意圖衝突，選擇置信度更高的
            if slm_confidence > vector_confidence + 0.2:
                final_intent = slm_intent
                final_confidence = slm_confidence - conflict_penalty
                decision_path.append("slm_wins_conflict")
            elif vector_confidence > slm_confidence + 0.2:
                final_intent = vector_intent  
                final_confidence = vector_confidence - conflict_penalty
                decision_path.append("vector_wins_conflict")
            else:
                # 置信度相近，降級到通用意圖
                final_intent = 'general'
                final_confidence = max(vector_confidence, slm_confidence) * 0.8
                decision_path.append("conflict_fallback_to_general")
        
        # 組合其他屬性 (優先使用 SLM 的詳細分析)
        return IntentAnalysisResult(
            intent=final_intent,
            confidence=min(final_confidence, 1.0),  # 確保不超過1.0
            complexity_score=slm_result.get('complexity_score', 5.0),
            domain=slm_result.get('domain', 'general'),
            language=slm_result.get('language', 'zh-TW'),
            estimated_tokens=slm_result.get('estimated_tokens', 100),
            processing_time_ms=max(
                vector_result.get('processing_time_ms', 20),
                slm_result.get('processing_time_ms', 200)
            ),
            analyzer_used='vector+slm_fusion',
            consensus=consensus
        )
    
    def _vector_to_intent_result(self, vector_result: Dict, decision_path: List[str]) -> IntentAnalysisResult:
        """將 Vector 結果轉換為標準意圖結果"""
        if not vector_result:
            return self._fallback_intent_result()
            
        return IntentAnalysisResult(
            intent=vector_result.get('intent', 'general'),
            confidence=vector_result.get('confidence', 0.5),
            complexity_score=5.0,  # Vector 無法判斷複雜度，使用中等值
            domain='general',
            language='zh-TW', 
            estimated_tokens=100,
            processing_time_ms=vector_result.get('processing_time_ms', 20),
            analyzer_used='vector_only',
            consensus=True
        )
    
    def _slm_to_intent_result(self, slm_result: Dict) -> IntentAnalysisResult:
        """將 SLM 結果轉換為標準意圖結果"""
        if not slm_result:
            return self._fallback_intent_result()
            
        return IntentAnalysisResult(
            intent=slm_result.get('intent', 'general'),
            confidence=slm_result.get('confidence', 0.5),
            complexity_score=slm_result.get('complexity_score', 5.0),
            domain=slm_result.get('domain', 'general'),
            language=slm_result.get('language', 'zh-TW'),
            estimated_tokens=slm_result.get('estimated_tokens', 100),
            processing_time_ms=slm_result.get('processing_time_ms', 200),
            analyzer_used='slm_only',
            consensus=True
        )
    
    def _fallback_intent_result(self) -> IntentAnalysisResult:
        """當所有分析器都失敗時的 fallback 結果"""
        return IntentAnalysisResult(
            intent='general',
            confidence=0.3,
            complexity_score=5.0,
            domain='general', 
            language='zh-TW',
            estimated_tokens=100,
            processing_time_ms=10,
            analyzer_used='fallback',
            consensus=False
        )
    
    async def _execute_rules(self, intent_result: IntentAnalysisResult, 
                           query: str, context: Dict[str, Any],
                           decision_path: List[str]) -> RoutingDecision:
        """
        階段2: 規則決策執行
        
        基於意圖分析結果，執行企業級路由規則
        """
        
        decision_path.append("rule_execution_start")
        
        if not self.rule_engine:
            decision_path.append("no_rule_engine_fallback")
            return self._simple_model_selection(intent_result, decision_path)
        
        try:
            # 準備規則引擎輸入
            rule_context = {
                **context,
                'intent': intent_result.intent,
                'confidence': intent_result.confidence,
                'complexity_score': intent_result.complexity_score,
                'domain': intent_result.domain,
                'estimated_tokens': intent_result.estimated_tokens
            }
            
            # 執行規則引擎
            rule_decision = await self.rule_engine.evaluate(rule_context)
            decision_path.append("rule_engine_executed")
            
            return RoutingDecision(
                selected_model=rule_decision['model'],
                confidence=rule_decision['confidence'],
                reasoning=rule_decision['reasoning'],
                fallback_models=rule_decision.get('fallback_models', []),
                estimated_cost=rule_decision.get('estimated_cost', 0.0),
                processing_time_ms=0,  # 將在外層設定
                decision_path=[]  # 將在外層設定
            )
            
        except Exception as e:
            logger.error(f"規則引擎執行失敗: {e}")
            decision_path.append("rule_engine_failed")
            return self._simple_model_selection(intent_result, decision_path)
    
    def _simple_model_selection(self, intent_result: IntentAnalysisResult,
                               decision_path: List[str]) -> RoutingDecision:
        """簡單的模型選擇邏輯 (當規則引擎不可用時)"""
        
        decision_path.append("simple_model_selection")
        
        # 基於意圖的簡單映射
        intent_mapping = config_manager.get_intent_mapping()
        
        if intent_result.intent in intent_mapping:
            mapping = intent_mapping[intent_result.intent]
            preferred_models = mapping.get('preferred_models', ['gpt-3.5-turbo'])
            complexity_threshold = mapping.get('complexity_threshold', 5.0)
            
            # 基於複雜度選擇模型
            if intent_result.complexity_score >= complexity_threshold:
                selected_model = preferred_models[0] if preferred_models else 'gpt-4'
                decision_path.append("high_complexity_model")
            else:
                selected_model = preferred_models[-1] if preferred_models else 'gpt-3.5-turbo'
                decision_path.append("low_complexity_model")
        else:
            selected_model = config_manager.get_default_model()
            decision_path.append("default_model_fallback")
        
        return RoutingDecision(
            selected_model=selected_model,
            confidence=intent_result.confidence * 0.8,  # 降低置信度因為是簡化邏輯
            reasoning=f"基於意圖 {intent_result.intent} 的簡單映射",
            fallback_models=['gpt-3.5-turbo', 'gpt-4o'],
            estimated_cost=0.0,  # 需要計算
            processing_time_ms=0,
            decision_path=[]
        )
    
    def _fallback_decision(self, query: str, context: Dict[str, Any]) -> RoutingDecision:
        """完全失敗時的 fallback 決策"""
        
        return RoutingDecision(
            selected_model=config_manager.get_default_model(),
            confidence=0.2,
            reasoning="所有路由分析器失敗，使用預設模型",
            fallback_models=[],
            estimated_cost=0.0,
            processing_time_ms=10,
            decision_path=["complete_fallback"]
        )


# ========================================
# Mock 類別 (用於測試和演示)
# ========================================

class MockVectorRouter:
    """模擬 Vector Router"""
    async def route(self, query: str) -> Dict:
        await asyncio.sleep(0.02)  # 模擬 20ms 延遲
        
        if '程式' in query or 'code' in query.lower():
            return {
                'intent': 'code_generation',
                'confidence': 0.85,
                'processing_time_ms': 20
            }
        elif '分析' in query or 'analysis' in query.lower():
            return {
                'intent': 'data_analysis', 
                'confidence': 0.78,
                'processing_time_ms': 22
            }
        else:
            return {
                'intent': 'general',
                'confidence': 0.60,
                'processing_time_ms': 18
            }

class MockO3MiniAnalyzer:
    """模擬 O3-mini Analyzer"""
    async def analyze(self, query: str) -> Dict:
        await asyncio.sleep(0.2)  # 模擬 200ms 延遲
        
        if '程式' in query or 'code' in query.lower():
            return {
                'intent': 'code_generation',
                'confidence': 0.92,
                'complexity_score': 7.5,
                'domain': 'programming',
                'language': 'zh-TW',
                'estimated_tokens': 200,
                'processing_time_ms': 200
            }
        elif '分析' in query:
            return {
                'intent': 'data_analysis',
                'confidence': 0.88,
                'complexity_score': 6.0,
                'domain': 'analytics',
                'language': 'zh-TW', 
                'estimated_tokens': 150,
                'processing_time_ms': 210
            }
        else:
            return {
                'intent': 'general',
                'confidence': 0.70,
                'complexity_score': 4.0,
                'domain': 'general',
                'language': 'zh-TW',
                'estimated_tokens': 100,
                'processing_time_ms': 190
            }

class MockRuleEngine:
    """模擬 Rule Engine"""
    async def evaluate(self, context: Dict) -> Dict:
        await asyncio.sleep(0.01)  # 模擬 10ms 延遲
        
        intent = context.get('intent', 'general')
        complexity = context.get('complexity_score', 5.0)
        
        if intent == 'code_generation' and complexity >= 7.0:
            return {
                'model': 'gpt-4',
                'confidence': 0.95,
                'reasoning': '高複雜度程式碼生成，使用 GPT-4',
                'fallback_models': ['claude-3-sonnet', 'gpt-3.5-turbo'],
                'estimated_cost': 0.05
            }
        elif intent == 'data_analysis':
            return {
                'model': 'gpt-4',
                'confidence': 0.90,
                'reasoning': '資料分析需要高推理能力',
                'fallback_models': ['claude-3-sonnet'],
                'estimated_cost': 0.04
            }
        else:
            return {
                'model': 'gpt-3.5-turbo',
                'confidence': 0.80,
                'reasoning': '一般查詢使用經濟模型',
                'fallback_models': ['gpt-4o'],
                'estimated_cost': 0.01
            }


# ========================================  
# 測試程式
# ========================================

async def test_hybrid_router():
    """測試 Hybrid Router"""
    
    print("=" * 70)
    print("🔀 Hybrid Router 測試")
    print("=" * 70)
    
    # 初始化 router
    router = HybridRouter()
    
    test_cases = [
        {
            'query': '請幫我寫一個 Python 排序函數',
            'expected_intent': 'code_generation'
        },
        {
            'query': '分析這份銷售資料的趨勢圖',
            'expected_intent': 'data_analysis'
        },
        {
            'query': '今天天氣如何？',
            'expected_intent': 'general'
        },
        {
            'query': '幫我總結這篇文章',
            'expected_intent': 'text_summary'
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        query = case['query']
        expected = case['expected_intent']
        
        print(f"\n{i}. 測試查詢: '{query}'")
        print(f"   預期意圖: {expected}")
        
        # 執行路由
        start_time = time.time()
        decision = await router.route(query)
        total_time = int((time.time() - start_time) * 1000)
        
        # 顯示結果
        print(f"   ✅ 選擇模型: {decision.selected_model}")
        print(f"   📊 置信度: {decision.confidence:.2f}")
        print(f"   💭 推理: {decision.reasoning}")
        print(f"   ⏱️ 總耗時: {total_time}ms")
        print(f"   🛤️ 決策路徑: {' → '.join(decision.decision_path)}")
        
        if decision.fallback_models:
            print(f"   🔄 備選模型: {', '.join(decision.fallback_models)}")

if __name__ == "__main__":
    asyncio.run(test_hybrid_router())