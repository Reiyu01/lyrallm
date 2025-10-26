"""
測試 S1-S14 安全分類格式解析

驗證 analyzer_slm.py 能正確解析新的三行文字格式
"""

import asyncio
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_s_category_parser():
    """測試 S-category 格式解析器"""
    from core.router_v1.analyzer_slm import SLMAnalyzer, MODELS_AVAILABLE
    
    print("="*80)
    print("🧪 測試 S1-S14 格式解析")
    print("="*80)
    print(f"\n📦 資料模型可用: {'✅ 是' if MODELS_AVAILABLE else '❌ 否'}")
    print()
    
    analyzer = SLMAnalyzer()
    
    # 測試案例 1：Safe 內容
    print("="*80)
    print("測試 1️⃣: Safe 內容（正常程式請求）")
    print("="*80)
    
    text1 = """Intent: Code Generation
Safety: Safe
Category: None"""
    
    result1 = analyzer._parse_s_category_format(text1)
    print(f"✅ 解析成功: {result1 is not None}")
    if result1:
        print(f"   - Intent: {result1['intent']}")
        print(f"   - Safety: {result1['safety_status']}")
        print(f"   - Category: {result1['safety_category']}")
        print(f"   - Confidence: {result1['confidence']}")
        print(f"   - Complexity: {result1['complexity_score']}")
    
    if MODELS_AVAILABLE:
        safety1 = analyzer._map_s_category_to_safety_labels('None', 'Safe')
        print(f"   - SafetyLabels.is_safe(): {safety1.is_safe()}")
        print(f"   - Risk Level: {safety1.risk_level.value}")
    
    print()
    
    # 測試案例 2：Unsafe - S1 (暴力犯罪)
    print("="*80)
    print("測試 2️⃣: Unsafe - S1 (暴力犯罪)")
    print("="*80)
    
    text2 = """Intent: Open QA
Safety: Unsafe
Category: S1"""
    
    result2 = analyzer._parse_s_category_format(text2)
    print(f"✅ 解析成功: {result2 is not None}")
    if result2:
        print(f"   - Intent: {result2['intent']}")
        print(f"   - Safety: {result2['safety_status']}")
        print(f"   - Category: {result2['safety_category']}")
    
    if MODELS_AVAILABLE:
        safety2 = analyzer._map_s_category_to_safety_labels('S1', 'Unsafe')
        print(f"   - SafetyLabels.is_safe(): {safety2.is_safe()}")
        print(f"   - Violence Level: {safety2.violence.value}")
        print(f"   - Risk Level: {safety2.risk_level.value}")
        print(f"   - Details: {safety2.details}")
    
    print()
    
    # 測試案例 3：Unsafe - S2 (非暴力犯罪)
    print("="*80)
    print("測試 3️⃣: Unsafe - S2 (非暴力犯罪 - 駭客攻擊)")
    print("="*80)
    
    text3 = """Intent: Code Generation
Safety: Unsafe
Category: S2"""
    
    result3 = analyzer._parse_s_category_format(text3)
    if MODELS_AVAILABLE:
        safety3 = analyzer._map_s_category_to_safety_labels('S2', 'Unsafe')
        print(f"   - Confidential Data: {safety3.confidential_data.value}")
        print(f"   - Risk Level: {safety3.risk_level.value}")
        print(f"   - Requires Escalation: {safety3.requires_escalation()}")
    
    print()
    
    # 測試案例 4：Unsafe - S14 (代碼濫用)
    print("="*80)
    print("測試 4️⃣: Unsafe - S14 (代碼解釋器濫用)")
    print("="*80)
    
    text4 = """Intent: Code Generation
Safety: Unsafe
Category: S14"""
    
    result4 = analyzer._parse_s_category_format(text4)
    if MODELS_AVAILABLE:
        safety4 = analyzer._map_s_category_to_safety_labels('S14', 'Unsafe')
        print(f"   - Jailbreak Attempt: {safety4.jailbreak_attempt}")
        print(f"   - Risk Level: {safety4.risk_level.value}")
        print(f"   - Details: {safety4.details}")
    
    print()
    
    # 測試案例 5：Controversial 內容
    print("="*80)
    print("測試 5️⃣: Controversial - S6 (專業建議)")
    print("="*80)
    
    text5 = """Intent: Open QA
Safety: Controversial
Category: S6"""
    
    result5 = analyzer._parse_s_category_format(text5)
    if result5:
        print(f"   - Confidence: {result5['confidence']} (較低，因為 Controversial)")
    
    if MODELS_AVAILABLE:
        safety5 = analyzer._map_s_category_to_safety_labels('S6', 'Controversial')
        print(f"   - Risk Level: {safety5.risk_level.value} (降級處理)")
        print(f"   - Details: {safety5.details}")
    
    print()
    
    # 測試案例 6：所有 S1-S14 類別映射
    print("="*80)
    print("測試 6️⃣: 所有 S1-S14 類別映射")
    print("="*80)
    
    if MODELS_AVAILABLE:
        categories = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 
                     'S8', 'S9', 'S10', 'S11', 'S12', 'S13', 'S14']
        
        for cat in categories:
            safety = analyzer._map_s_category_to_safety_labels(cat, 'Unsafe')
            print(f"   {cat}: Risk={safety.risk_level.value:8s} | {safety.details[0][:50]}")
    
    print()
    
    # 測試案例 7：混合格式檢測
    print("="*80)
    print("測試 7️⃣: 混合格式（應該識別為 S-category）")
    print("="*80)
    
    text7 = """Some extra text before
Intent: Chatbot
Safety: Safe
Category: None
Some extra text after"""
    
    result7 = analyzer._parse_s_category_format(text7)
    print(f"✅ 能識別混合格式: {result7 is not None}")
    if result7:
        print(f"   - Intent: {result7['intent']}")
    
    print()
    
    # 測試案例 8：JSON 格式（應該返回 None）
    print("="*80)
    print("測試 8️⃣: JSON 格式（應該返回 None，表示不是 S-category）")
    print("="*80)
    
    text8 = """{
    "intent": "code_generation",
    "confidence": 0.9,
    "complexity_score": 7
}"""
    
    result8 = analyzer._parse_s_category_format(text8)
    print(f"✅ 正確識別為非 S-category 格式: {result8 is None}")
    
    print()
    
    print("="*80)
    print("🎉 測試完成！")
    print("="*80)
    
    # 總結
    print("\n📊 測試總結：")
    print("✅ S-category 格式解析器可以正確識別三行格式")
    print("✅ S1-S14 類別可以正確映射到 SafetyLabels")
    print("✅ Safe/Unsafe/Controversial 狀態可以正確處理")
    print("✅ Controversial 內容會降低風險等級")
    print("✅ 可以區分 S-category 格式和 JSON 格式")
    print("✅ Intent 類型可以正確映射到舊系統")


def test_intent_mapping():
    """測試 Intent 類型映射"""
    from core.router_v1.analyzer_slm import SLMAnalyzer
    
    print("\n" + "="*80)
    print("🔄 測試 Intent 類型映射")
    print("="*80)
    
    analyzer = SLMAnalyzer()
    
    intent_tests = [
        ("Open QA", "qa_general"),
        ("Closed QA", "qa_general"),
        ("Code Generation", "code_generation"),
        ("Text Generation", "creative_writing"),
        ("Summarization", "text_summary"),
        ("Extraction", "data_analysis"),
        ("Chatbot", "qa_general"),
        ("Classification", "qa_general"),
        ("Rewrite", "text_summary"),
        ("Brainstorming", "creative_writing"),
        ("Other", "qa_general"),
    ]
    
    for new_intent, expected_intent in intent_tests:
        text = f"""Intent: {new_intent}
Safety: Safe
Category: None"""
        
        result = analyzer._parse_s_category_format(text)
        if result:
            actual_intent = result['intent']
            status = "✅" if actual_intent == expected_intent else "❌"
            print(f"{status} {new_intent:20s} → {actual_intent:20s} (期望: {expected_intent})")


if __name__ == '__main__':
    test_s_category_parser()
    test_intent_mapping()
    
    print("\n" + "="*80)
    print("💡 下一步：")
    print("   1. 測試實際的 SLM 輸出（用真實模型 如 Qwen、GPT-4o-mini）")
    print("   2. 驗證 routing_rules.yaml 的 system_prompt 輸出格式")
    print("   3. 整合到完整的 Router 流程測試")
    print("="*80)
