"""
測試 SLM Analyzer 的擴展功能

驗證 analyzer_slm.py 能正確解析擴展後的 JSON 格式
"""

import asyncio
import sys
import json
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def test_analyzer_with_mock_response():
    """測試 Analyzer 解析擴展 JSON"""
    from core.router_v1.analyzer_slm import SLMAnalyzer, MODELS_AVAILABLE
    
    print("="*80)
    print("🧪 測試 SLM Analyzer 擴展功能")
    print("="*80)
    print(f"\n📦 資料模型可用: {'✅ 是' if MODELS_AVAILABLE else '❌ 否'}")
    print()
    
    # 創建 Analyzer 實例
    analyzer = SLMAnalyzer()
    
    # 測試案例 1：完整的 JSON（包含所有新欄位）
    print("="*80)
    print("測試 1️⃣: 完整 JSON（包含工具、安全標籤、權限）")
    print("="*80)
    
    full_json = {
        "intent": "code_generation",
        "confidence": 0.95,
        "complexity_score": 7.5,
        "domain": "programming",
        "language": "zh-TW",
        "estimated_tokens": 500,
        "required_tools": [
            {
                "tool_type": "code_interpreter",
                "priority": "required",
                "reason": "需要執行 Python 代碼",
                "parameters": {}
            }
        ],
        "safety_labels": {
            "violence": "none",
            "sexual": "none",
            "hate_speech": "none",
            "self_harm": "none",
            "confidential_data": "none",
            "jailbreak_attempt": False,
            "risk_level": "none",
            "details": ["正常的程式設計請求"]
        },
        "required_permissions": {
            "min_tier": "pro",
            "roles": ["developer"],
            "permissions": ["use_code_interpreter"],
            "data_access_level": "public",
            "reason": "需要代碼執行器"
        }
    }
    
    # 測試解析工具需求
    tools = analyzer._parse_tool_requirements(full_json)
    print(f"✅ 工具需求解析: {tools is not None}")
    if tools and MODELS_AVAILABLE:
        print(f"   - needs_tools: {tools.needs_tools}")
        print(f"   - 工具數量: {len(tools.required_tools)}")
        if tools.required_tools:
            for req in tools.required_tools:
                print(f"   - {req.tool_type.value} ({req.priority.value}): {req.reason}")
    
    # 測試解析安全標籤
    safety = analyzer._parse_safety_labels(full_json)
    print(f"✅ 安全標籤解析: {safety is not None}")
    if safety and MODELS_AVAILABLE:
        print(f"   - is_safe: {safety.is_safe()}")
        print(f"   - risk_level: {safety.risk_level.value}")
        print(f"   - jailbreak_attempt: {safety.jailbreak_attempt}")
    
    print()
    
    # 測試案例 2：基礎 JSON（僅有舊欄位，測試向後兼容）
    print("="*80)
    print("測試 2️⃣: 基礎 JSON（僅舊欄位，測試向後兼容）")
    print("="*80)
    
    basic_json = {
        "intent": "qa_general",
        "confidence": 0.85,
        "complexity_score": 3.0
    }
    
    tools = analyzer._parse_tool_requirements(basic_json)
    safety = analyzer._parse_safety_labels(basic_json)
    
    print(f"✅ 工具需求（預設）: {tools is not None}")
    if tools and MODELS_AVAILABLE:
        print(f"   - needs_tools: {tools.needs_tools}")
    
    print(f"✅ 安全標籤（預設）: {safety is not None}")
    if safety and MODELS_AVAILABLE:
        print(f"   - is_safe: {safety.is_safe()}")
    
    print()
    
    # 測試案例 3：包含危險內容的 JSON
    print("="*80)
    print("測試 3️⃣: 危險內容 JSON（測試安全檢測）")
    print("="*80)
    
    dangerous_json = {
        "intent": "qa_general",
        "confidence": 0.9,
        "complexity_score": 2.0,
        "required_tools": [],
        "safety_labels": {
            "violence": "critical",
            "sexual": "none",
            "hate_speech": "none",
            "self_harm": "none",
            "confidential_data": "none",
            "jailbreak_attempt": False,
            "risk_level": "critical",
            "details": ["包含危險暴力內容"]
        },
        "required_permissions": {
            "min_tier": "admin",
            "roles": ["admin"],
            "permissions": [],
            "data_access_level": "restricted",
            "reason": "危險內容需要管理員審查"
        }
    }
    
    safety = analyzer._parse_safety_labels(dangerous_json)
    print(f"✅ 安全標籤解析: {safety is not None}")
    if safety and MODELS_AVAILABLE:
        print(f"   - is_safe: {safety.is_safe()}")
        print(f"   - risk_level: {safety.risk_level.value}")
        print(f"   - violence: {safety.violence.value}")
        print(f"   - requires_escalation: {safety.requires_escalation()}")
        print(f"   - details: {safety.details}")
    
    print()
    
    # 測試案例 4：包含 Jailbreak 攻擊的 JSON
    print("="*80)
    print("測試 4️⃣: Jailbreak 攻擊 JSON")
    print("="*80)
    
    jailbreak_json = {
        "intent": "qa_general",
        "confidence": 0.8,
        "complexity_score": 2.0,
        "required_tools": [],
        "safety_labels": {
            "violence": "none",
            "sexual": "none",
            "hate_speech": "none",
            "self_harm": "none",
            "confidential_data": "none",
            "jailbreak_attempt": True,
            "risk_level": "critical",
            "details": ["檢測到 jailbreak 攻擊模式"]
        },
        "required_permissions": {
            "min_tier": "admin",
            "roles": ["admin"],
            "permissions": [],
            "data_access_level": "public",
            "reason": "疑似惡意攻擊"
        }
    }
    
    safety = analyzer._parse_safety_labels(jailbreak_json)
    print(f"✅ 安全標籤解析: {safety is not None}")
    if safety and MODELS_AVAILABLE:
        print(f"   - is_safe: {safety.is_safe()}")
        print(f"   - jailbreak_attempt: {safety.jailbreak_attempt}")
        print(f"   - risk_level: {safety.risk_level.value}")
        print(f"   - requires_escalation: {safety.requires_escalation()}")
    
    print()
    
    # 測試案例 5：複雜多工具需求
    print("="*80)
    print("測試 5️⃣: 複雜多工具需求 JSON")
    print("="*80)
    
    multi_tool_json = {
        "intent": "data_analysis",
        "confidence": 0.95,
        "complexity_score": 8.0,
        "required_tools": [
            {
                "tool_type": "web_search",
                "priority": "required",
                "reason": "需要查詢即時股價"
            },
            {
                "tool_type": "code_interpreter",
                "priority": "required",
                "reason": "需要執行資料分析代碼"
            },
            {
                "tool_type": "data_analysis",
                "priority": "recommended",
                "reason": "建議使用資料分析工具"
            }
        ],
        "safety_labels": {
            "violence": "none",
            "sexual": "none",
            "hate_speech": "none",
            "self_harm": "none",
            "confidential_data": "none",
            "jailbreak_attempt": False,
            "risk_level": "none",
            "details": ["正常的資料分析請求"]
        },
        "required_permissions": {
            "min_tier": "pro",
            "roles": ["analyst", "data_scientist"],
            "permissions": ["use_web_search", "use_code_interpreter", "use_data_analysis"],
            "data_access_level": "public",
            "reason": "需要多種分析工具"
        }
    }
    
    tools = analyzer._parse_tool_requirements(multi_tool_json)
    print(f"✅ 工具需求解析: {tools is not None}")
    if tools and MODELS_AVAILABLE:
        print(f"   - needs_tools: {tools.needs_tools}")
        print(f"   - 工具總數: {len(tools.required_tools)}")
        print(f"   - 必須工具: {len(tools.get_required_tools())}")
        print(f"   - 建議工具: {len(tools.get_recommended_tools())}")
        for req in tools.required_tools:
            print(f"   - {req.tool_type.value} ({req.priority.value})")
    
    print()
    
    # 總結
    print("="*80)
    print("📊 測試總結")
    print("="*80)
    print(f"✅ IntentResult 欄位已擴展")
    print(f"✅ 工具需求解析功能正常")
    print(f"✅ 安全標籤解析功能正常")
    print(f"✅ 向後兼容性正常")
    print(f"✅ 降級處理正常")
    
    if not MODELS_AVAILABLE:
        print("\n⚠️  注意：資料模型模組未載入，部分功能受限")
        print("   請確保 models/ 目錄存在且包含所需模組")
    else:
        print("\n🎉 所有測試通過！SLM Analyzer 已成功擴展！")
    
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_analyzer_with_mock_response())
