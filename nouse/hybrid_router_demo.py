#!/usr/bin/env python3
"""
Hybrid Router 實現演示 - 核心架構說明
"""
import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
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

# Mock配置
MOCK_CONFIG = {
    'routing': {
        'enabled': True,
        'default_model': 'gpt-3.5-turbo'
    },
    'intent_analysis': {
        'mode': 'parallel',
        'vector': {'weight': 0.3, 'enabled': True},
        'small_model': {'weight': 0.7, 'enabled': True}
    },
    'fusion': {
        'consensus_bonus': 0.2,
        'conflict_penalty': 0.1,
        'fast_path_threshold': 0.9
    },
    'intent_mapping': {
        'code_generation': {
            'preferred_models': ['gpt-4', 'claude-3-sonnet', 'gpt-3.5-turbo'],
            'complexity_threshold': 6.0
        },
        'data_analysis': {
            'preferred_models': ['gpt-4', 'claude-3-sonnet'],
            'complexity_threshold': 5.0
        },
        'general': {
            'preferred_models': ['gpt-3.5-turbo', 'gpt-4o'],
            'complexity_threshold': 4.0
        }
    }
}

class HybridRouter:
    """
    🔀 Hybrid Router - 智能混合路由器
    
    ✨ 核心設計理念:
    ┌─────────────────────────────────────────────────┐
    │  Hybrid Router 不是一個「路由器」               │
    │  而是一個「指揮官」(Coordinator)                │
    │                                                 │
    │  🎯 指揮三個專業分析師:                         │
    │  • Vector Router: 快速相似度專家 (5-20ms)      │
    │  • O3-mini SLM: 智能意圖分析師 (200-500ms)     │  
    │  • Rule Engine: 企業規則執行者 (5-10ms)        │
    └─────────────────────────────────────────────────┘
    
    🚀 兩階段處理流程:
    
    階段1️⃣ 意圖分析 (Intent Analysis)
    ┌─ Vector + SLM 聯合分析 ─┐
    │                        │
    │ 🔄 Parallel Mode:       │ ⚡ 並行執行，智能融合
    │   Vector ┐             │
    │          ├─► Fusion    │
    │   SLM   ┘              │
    │                        │
    │ 📈 Progressive Mode:    │ 🎯 漸進式優化
    │   Vector → (條件) SLM  │
    └────────────────────────┘
    
    階段2️⃣ 規則決策 (Rule Execution)  
    ┌─ 企業級智能決策 ─┐
    │ • 用戶權限檢查   │
    │ • 成本控制      │
    │ • 負載平衡      │  
    │ • 模型可用性    │
    │ • 業務規則      │
    └─────────────────┘
    """
    
    def __init__(self):
        """初始化 Hybrid Router"""
        self.config = MOCK_CONFIG
        
        # 處理模式配置
        self.processing_mode = ProcessingMode(
            self.config['intent_analysis']['mode']
        )
        
        # 初始化分析引擎
        self.vector_router = MockVectorRouter()
        self.slm_analyzer = MockO3MiniAnalyzer() 
        self.rule_engine = MockRuleEngine()
        
        logger.info(f"🚀 Hybrid Router 初始化完成 (模式: {self.processing_mode.value})")
    
    async def route(self, query: str, context: Dict[str, Any] = None) -> RoutingDecision:
        """
        🎯 主要路由方法 - 兩階段智能路由
        
        Flow:
        用戶請求 → 意圖分析 → 規則決策 → 模型選擇
        """
        start_time = time.time()
        context = context or {}
        decision_path = []
        
        logger.info(f"📥 開始 Hybrid 路由: '{query[:30]}...'")
        
        try:
            # 🧠 階段1: 意圖分析 (Vector + SLM)
            print(f"\n🧠 階段1: 意圖分析 ({self.processing_mode.value})")
            intent_result = await self._analyze_intent(query, decision_path)
            
            print(f"   📊 意圖: {intent_result.intent} (置信度: {intent_result.confidence:.2f})")
            print(f"   🔬 複雜度: {intent_result.complexity_score:.1f}")
            print(f"   🏷️ 領域: {intent_result.domain}")
            print(f"   ⚡ 分析器: {intent_result.analyzer_used}")
            print(f"   🤝 共識: {'是' if intent_result.consensus else '否'}")
            
            # 📋 階段2: 規則決策執行  
            print(f"\n📋 階段2: 規則決策執行")
            routing_decision = await self._execute_rules(
                intent_result, query, context, decision_path
            )
            
            # 📊 最終處理
            total_time = int((time.time() - start_time) * 1000)
            routing_decision.processing_time_ms = total_time
            routing_decision.decision_path = decision_path
            
            print(f"   🎯 選擇模型: {routing_decision.selected_model}")
            print(f"   📈 決策置信度: {routing_decision.confidence:.2f}")
            print(f"   💭 推理過程: {routing_decision.reasoning}")
            print(f"   💰 預估成本: ${routing_decision.estimated_cost:.4f}")
            
            logger.info(
                f"✅ Hybrid 路由完成: {routing_decision.selected_model} "
                f"(總耗時: {total_time}ms)"
            )
            
            return routing_decision
            
        except Exception as e:
            logger.error(f"❌ Hybrid 路由失敗: {e}")
            return self._fallback_decision(query, context)
    
    async def _analyze_intent(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """🧠 階段1: 意圖分析 - Vector + SLM 聯合處理"""
        
        if self.processing_mode == ProcessingMode.PARALLEL:
            return await self._parallel_analysis(query, decision_path)
        elif self.processing_mode == ProcessingMode.PROGRESSIVE:
            return await self._progressive_analysis(query, decision_path)
        else:
            return await self._vector_only_analysis(query, decision_path)
    
    async def _parallel_analysis(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """⚡ 並行模式: Vector + SLM 同時執行"""
        
        decision_path.append("parallel_mode")
        print("   ⚡ 啟動 Vector + SLM 並行分析...")
        
        # 🚀 並行啟動
        vector_task = asyncio.create_task(self._safe_vector_analysis(query))
        slm_task = asyncio.create_task(self._safe_slm_analysis(query))
        
        # ⏱️ 等待完成
        vector_result, slm_result = await asyncio.gather(vector_task, slm_task)
        
        print(f"   📊 Vector: {vector_result['intent'] if vector_result else 'Failed'} "
              f"({vector_result['confidence']:.2f})" if vector_result else "")
        print(f"   🤖 SLM: {slm_result['intent'] if slm_result else 'Failed'} "
              f"({slm_result['confidence']:.2f})" if slm_result else "")
        
        # 🤝 智能融合
        return self._merge_results(vector_result, slm_result, decision_path)
    
    async def _progressive_analysis(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """📈 漸進式模式: Vector → SLM (條件觸發)"""
        
        decision_path.append("progressive_mode")
        print("   📈 啟動漸進式分析...")
        
        # 🏃 第1步: Vector 快速分析
        print("     🔍 Vector 快速分析...")
        vector_result = await self._safe_vector_analysis(query)
        
        if vector_result:
            confidence = vector_result['confidence']
            threshold = self.config['fusion']['fast_path_threshold']
            
            print(f"     📊 Vector 置信度: {confidence:.2f} (閾值: {threshold})")
            
            # 🤔 判斷是否需要 SLM
            if confidence >= threshold:
                print("     ✅ 置信度足夠，跳過 SLM 分析")
                decision_path.append("fast_path_sufficient")
                return self._vector_to_intent_result(vector_result, decision_path)
        
        # 📚 第2步: SLM 深度分析
        print("     🤖 觸發 SLM 深度分析...")
        decision_path.append("slm_triggered")
        slm_result = await self._safe_slm_analysis(query)
        
        return self._merge_results(vector_result, slm_result, decision_path)
    
    async def _vector_only_analysis(self, query: str, decision_path: List[str]) -> IntentAnalysisResult:
        """🔍 純向量模式"""
        decision_path.append("vector_only")
        vector_result = await self._safe_vector_analysis(query)
        return self._vector_to_intent_result(vector_result, decision_path)
    
    def _merge_results(self, vector_result: Dict, slm_result: Dict, 
                      decision_path: List[str]) -> IntentAnalysisResult:
        """🤝 智能融合 Vector 和 SLM 結果"""
        
        # 處理失敗情況
        if not vector_result and not slm_result:
            decision_path.append("both_failed")
            return self._fallback_intent_result()
            
        if not slm_result:
            decision_path.append("slm_failed_vector_only")
            return self._vector_to_intent_result(vector_result, decision_path)
            
        if not vector_result:
            decision_path.append("vector_failed_slm_only") 
            return self._slm_to_intent_result(slm_result)
        
        # 🎯 智能融合邏輯
        vector_intent = vector_result['intent']
        slm_intent = slm_result['intent'] 
        vector_conf = vector_result['confidence']
        slm_conf = slm_result['confidence']
        
        # 檢查共識
        consensus = (vector_intent == slm_intent)
        print(f"   🤝 意圖共識: {consensus} ({vector_intent} vs {slm_intent})")
        
        # 權重配置
        vector_weight = self.config['intent_analysis']['vector']['weight']
        slm_weight = self.config['intent_analysis']['small_model']['weight']
        consensus_bonus = self.config['fusion']['consensus_bonus']
        conflict_penalty = self.config['fusion']['conflict_penalty']
        
        if consensus:
            # 😊 意圖一致，獎勵
            final_confidence = (
                vector_conf * vector_weight + 
                slm_conf * slm_weight + 
                consensus_bonus
            )
            final_intent = vector_intent
            decision_path.append("consensus_boost")
            print(f"   ✅ 共識獎勵: +{consensus_bonus}")
            
        else:
            # 😕 意圖衝突，選擇更強的
            if slm_conf > vector_conf + 0.2:
                final_intent = slm_intent
                final_confidence = slm_conf - conflict_penalty
                decision_path.append("slm_wins")
                print(f"   🤖 SLM 勝出，衝突懲罰: -{conflict_penalty}")
            else:
                final_intent = vector_intent
                final_confidence = vector_conf - conflict_penalty
                decision_path.append("vector_wins")
                print(f"   🔍 Vector 勝出，衝突懲罰: -{conflict_penalty}")
        
        return IntentAnalysisResult(
            intent=final_intent,
            confidence=min(final_confidence, 1.0),
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
    
    async def _execute_rules(self, intent_result: IntentAnalysisResult, 
                           query: str, context: Dict[str, Any],
                           decision_path: List[str]) -> RoutingDecision:
        """📋 階段2: 企業級規則決策執行"""
        
        decision_path.append("rule_execution")
        print("   📋 執行企業規則引擎...")
        
        # 準備規則上下文
        rule_context = {
            **context,
            'intent': intent_result.intent,
            'confidence': intent_result.confidence,
            'complexity_score': intent_result.complexity_score,
            'domain': intent_result.domain,
            'estimated_tokens': intent_result.estimated_tokens
        }
        
        print(f"   📊 規則輸入: 意圖={intent_result.intent}, "
              f"複雜度={intent_result.complexity_score:.1f}")
        
        # 執行規則引擎
        rule_decision = await self.rule_engine.evaluate(rule_context)
        decision_path.append("rule_evaluated")
        
        return RoutingDecision(
            selected_model=rule_decision['model'],
            confidence=rule_decision['confidence'],
            reasoning=rule_decision['reasoning'],
            fallback_models=rule_decision.get('fallback_models', []),
            estimated_cost=rule_decision.get('estimated_cost', 0.0),
            processing_time_ms=0,
            decision_path=[]
        )
    
    def _vector_to_intent_result(self, vector_result: Dict, decision_path: List[str]) -> IntentAnalysisResult:
        """將 Vector 結果轉為標準格式"""
        if not vector_result:
            return self._fallback_intent_result()
            
        return IntentAnalysisResult(
            intent=vector_result['intent'],
            confidence=vector_result['confidence'],
            complexity_score=5.0,  # Vector 無法判斷，預設中等
            domain='general',
            language='zh-TW',
            estimated_tokens=100,
            processing_time_ms=vector_result['processing_time_ms'],
            analyzer_used='vector_only',
            consensus=True
        )
    
    def _slm_to_intent_result(self, slm_result: Dict) -> IntentAnalysisResult:
        """將 SLM 結果轉為標準格式"""
        return IntentAnalysisResult(
            intent=slm_result['intent'],
            confidence=slm_result['confidence'],
            complexity_score=slm_result['complexity_score'],
            domain=slm_result['domain'],
            language=slm_result['language'],
            estimated_tokens=slm_result['estimated_tokens'],
            processing_time_ms=slm_result['processing_time_ms'],
            analyzer_used='slm_only',
            consensus=True
        )
    
    def _fallback_intent_result(self) -> IntentAnalysisResult:
        """完全失敗的 fallback"""
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
    
    def _fallback_decision(self, query: str, context: Dict) -> RoutingDecision:
        """完全失敗的決策 fallback"""
        return RoutingDecision(
            selected_model=self.config['routing']['default_model'],
            confidence=0.2,
            reasoning="所有路由分析器失敗，使用預設模型",
            fallback_models=[],
            estimated_cost=0.0,
            processing_time_ms=10,
            decision_path=["complete_fallback"]
        )
    
    async def _safe_vector_analysis(self, query: str) -> Optional[Dict]:
        """安全的 Vector 分析"""
        try:
            return await self.vector_router.route(query)
        except Exception as e:
            logger.warning(f"Vector 分析失敗: {e}")
            return None
    
    async def _safe_slm_analysis(self, query: str) -> Optional[Dict]:
        """安全的 SLM 分析"""
        try:
            return await self.slm_analyzer.analyze(query)
        except Exception as e:
            logger.warning(f"SLM 分析失敗: {e}")
            return None

# ========================================
# Mock 分析器實現  
# ========================================

class MockVectorRouter:
    """🔍 模擬 Vector Router - 快速向量相似度檢索"""
    
    async def route(self, query: str) -> Dict:
        # 模擬向量檢索延遲
        await asyncio.sleep(0.02)  # 20ms
        
        if any(keyword in query for keyword in ['程式', 'code', '函數', '演算法']):
            return {
                'intent': 'code_generation',
                'confidence': 0.85,
                'processing_time_ms': 20
            }
        elif any(keyword in query for keyword in ['分析', '資料', '圖表', 'analysis']):
            return {
                'intent': 'data_analysis',
                'confidence': 0.78,
                'processing_time_ms': 22
            }
        elif any(keyword in query for keyword in ['總結', '摘要', 'summary']):
            return {
                'intent': 'text_summary',
                'confidence': 0.75,
                'processing_time_ms': 18
            }
        else:
            return {
                'intent': 'general',
                'confidence': 0.60,
                'processing_time_ms': 18
            }

class MockO3MiniAnalyzer:
    """🤖 模擬 O3-mini SLM Analyzer - 深度意圖分析"""
    
    async def analyze(self, query: str) -> Dict:
        # 模擬 O3-mini API 調用延遲
        await asyncio.sleep(0.2)  # 200ms
        
        if any(keyword in query for keyword in ['程式', 'code', '函數', '演算法']):
            complexity = 8.0 if '複雜' in query or 'complex' in query else 6.5
            return {
                'intent': 'code_generation',
                'confidence': 0.92,
                'complexity_score': complexity,
                'domain': 'programming',
                'language': 'zh-TW',
                'estimated_tokens': 250,
                'processing_time_ms': 200
            }
        elif any(keyword in query for keyword in ['分析', '資料', '圖表']):
            return {
                'intent': 'data_analysis',
                'confidence': 0.88,
                'complexity_score': 7.0,
                'domain': 'analytics',
                'language': 'zh-TW',
                'estimated_tokens': 180,
                'processing_time_ms': 210
            }
        elif any(keyword in query for keyword in ['總結', '摘要']):
            return {
                'intent': 'text_summary',
                'confidence': 0.82,
                'complexity_score': 4.0,
                'domain': 'text_processing',
                'language': 'zh-TW',
                'estimated_tokens': 120,
                'processing_time_ms': 190
            }
        else:
            return {
                'intent': 'general',
                'confidence': 0.70,
                'complexity_score': 3.5,
                'domain': 'general',
                'language': 'zh-TW',
                'estimated_tokens': 80,
                'processing_time_ms': 190
            }

class MockRuleEngine:
    """📋 模擬企業規則引擎 - 智能決策執行"""
    
    async def evaluate(self, context: Dict) -> Dict:
        # 模擬規則評估延遲
        await asyncio.sleep(0.01)  # 10ms
        
        intent = context.get('intent', 'general')
        complexity = context.get('complexity_score', 5.0)
        confidence = context.get('confidence', 0.5)
        
        # 📋 企業級決策邏輯
        if intent == 'code_generation':
            if complexity >= 7.0:
                return {
                    'model': 'gpt-4',
                    'confidence': 0.95,
                    'reasoning': f'高複雜度程式碼生成 (複雜度: {complexity:.1f})，使用 GPT-4',
                    'fallback_models': ['claude-3-sonnet', 'gpt-3.5-turbo'],
                    'estimated_cost': 0.06
                }
            else:
                return {
                    'model': 'claude-3-sonnet',
                    'confidence': 0.88,
                    'reasoning': f'中等程式碼生成 (複雜度: {complexity:.1f})，使用 Claude',
                    'fallback_models': ['gpt-4', 'gpt-3.5-turbo'],
                    'estimated_cost': 0.04
                }
                
        elif intent == 'data_analysis':
            return {
                'model': 'gpt-4',
                'confidence': 0.92,
                'reasoning': '資料分析需要強推理能力，使用 GPT-4',
                'fallback_models': ['claude-3-sonnet'],
                'estimated_cost': 0.05
            }
            
        elif intent == 'text_summary':
            return {
                'model': 'gpt-3.5-turbo',
                'confidence': 0.85,
                'reasoning': '文本摘要任務，使用經濟模型',
                'fallback_models': ['gpt-4o'],
                'estimated_cost': 0.02
            }
        else:
            return {
                'model': 'gpt-3.5-turbo',
                'confidence': 0.75,
                'reasoning': f'一般查詢 (置信度: {confidence:.2f})，使用經濟模型',
                'fallback_models': ['gpt-4o'],
                'estimated_cost': 0.01
            }

# ========================================
# 測試與演示
# ========================================

async def demo_hybrid_router():
    """🚀 Hybrid Router 完整演示"""
    
    print("🔀" + "="*68)
    print("🔀 LyraLLM Hybrid Router 智能路由演示")
    print("🔀" + "="*68)
    print()
    
    # 初始化 router
    router = HybridRouter()
    
    test_cases = [
        {
            'query': '請幫我寫一個複雜的 Python 排序演算法',
            'desc': '高複雜度程式碼生成'
        },
        {
            'query': '分析這份銷售資料的趋勢並生成圖表',
            'desc': '資料分析任務'
        },
        {
            'query': '總結這篇文章的重點',
            'desc': '文本摘要任務'
        },
        {
            'query': '今天天氣如何？',
            'desc': '一般查詢'
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        query = case['query']
        desc = case['desc']
        
        print(f"📝 測試案例 {i}: {desc}")
        print(f"🔤 查詢: \"{query}\"")
        print("─" * 70)
        
        # 執行路由
        decision = await router.route(query)
        
        print(f"\n🎯 最終決策:")
        print(f"   📱 選擇模型: {decision.selected_model}")
        print(f"   📊 決策置信度: {decision.confidence:.2f}")
        print(f"   💭 推理依據: {decision.reasoning}")
        print(f"   💰 預估成本: ${decision.estimated_cost:.4f}")
        print(f"   ⏱️ 總處理時間: {decision.processing_time_ms}ms")
        
        if decision.fallback_models:
            print(f"   🔄 備選模型: {', '.join(decision.fallback_models[:2])}")
        
        print(f"   🛤️ 決策路徑: {' → '.join(decision.decision_path)}")
        
        print("\n" + "="*70 + "\n")

async def test_processing_modes():
    """測試不同處理模式"""
    
    print("⚡ 處理模式對比測試")
    print("="*50)
    
    query = "請幫我寫一個 Python 機器學習模型"
    
    modes = ['parallel', 'progressive']
    
    for mode in modes:
        print(f"\n🔄 測試模式: {mode}")
        print("-" * 30)
        
        # 創建對應模式的 router
        MOCK_CONFIG['intent_analysis']['mode'] = mode
        router = HybridRouter()
        
        start_time = time.time()
        decision = await router.route(query)
        total_time = int((time.time() - start_time) * 1000)
        
        print(f"✅ 模型: {decision.selected_model}")
        print(f"📊 置信度: {decision.confidence:.2f}")
        print(f"⏱️ 總耗時: {total_time}ms")
        print(f"🛤️ 路徑: {' → '.join(decision.decision_path[-3:])}")

if __name__ == "__main__":
    # 執行完整演示
    asyncio.run(demo_hybrid_router())
    
    # 執行模式對比
    asyncio.run(test_processing_modes())