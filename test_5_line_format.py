"""
測試新的 5 行格式（Confidence 和 Complexity 由 SLM 提供）
"""

from lyrallm.core.router_v1.analyzer_slm import SLMAnalyzer

def test_parse_5_line_format():
    """測試解析 5 行格式"""
    analyzer = SLMAnalyzer()  # 不傳參數
    
    # 測試案例 1: 完整的 5 行格式
    text1 = """
Intent: Code Generation
Confidence: 0.92
Complexity: 8.5
Safety: Safe
Category: None
"""
    
    result1 = analyzer._parse_s_category_format(text1)
    print(f"Test 1 - 完整 5 行格式:")
    print(f"  Intent: {result1['intent']}")
    print(f"  Confidence: {result1['confidence']}")
    print(f"  Complexity: {result1['complexity_score']}")
    print(f"  Safety: {result1['safety_status']}")
    print(f"  Category: {result1['safety_category']}")
    assert result1['intent'] == 'code_generation'
    assert result1['confidence'] == 0.92
    assert result1['complexity_score'] == 8.5
    assert result1['safety_status'] == 'Safe'
    print("  ✅ 通過\n")
    
    # 測試案例 2: 簡單請求
    text2 = """
Intent: Open QA
Confidence: 0.98
Complexity: 1.5
Safety: Safe
Category: None
"""
    
    result2 = analyzer._parse_s_category_format(text2)
    print(f"Test 2 - 簡單問答:")
    print(f"  Intent: {result2['intent']}")
    print(f"  Confidence: {result2['confidence']}")
    print(f"  Complexity: {result2['complexity_score']}")
    assert result2['intent'] == 'qa_general'
    assert result2['confidence'] == 0.98
    assert result2['complexity_score'] == 1.5
    print("  ✅ 通過\n")
    
    # 測試案例 3: Unsafe 內容（S1）
    text3 = """
Intent: Open QA
Confidence: 0.88
Complexity: 6.0
Safety: Unsafe
Category: S1
"""
    
    result3 = analyzer._parse_s_category_format(text3)
    print(f"Test 3 - Unsafe S1:")
    print(f"  Intent: {result3['intent']}")
    print(f"  Confidence: {result3['confidence']}")
    print(f"  Complexity: {result3['complexity_score']}")
    print(f"  Safety: {result3['safety_status']}")
    print(f"  Category: {result3['safety_category']}")
    assert result3['safety_status'] == 'Unsafe'
    assert result3['safety_category'] == 'S1'
    assert result3['confidence'] == 0.88
    print("  ✅ 通過\n")
    
    # 測試案例 4: 複雜的系統設計請求
    text4 = """
Intent: Code Generation
Confidence: 0.85
Complexity: 9.8
Safety: Safe
Category: None
"""
    
    result4 = analyzer._parse_s_category_format(text4)
    print(f"Test 4 - 複雜系統設計:")
    print(f"  Intent: {result4['intent']}")
    print(f"  Confidence: {result4['confidence']}")
    print(f"  Complexity: {result4['complexity_score']}")
    assert result4['complexity_score'] == 9.8
    assert result4['confidence'] == 0.85
    print("  ✅ 通過\n")
    
    # 測試案例 5: 向後兼容 - 只有 3 行（沒有 Confidence 和 Complexity）
    text5 = """
Intent: Open QA
Safety: Safe
Category: None
"""
    
    result5 = analyzer._parse_s_category_format(text5)
    print(f"Test 5 - 向後兼容 3 行格式:")
    print(f"  Intent: {result5['intent']}")
    print(f"  Confidence: {result5['confidence']} (自動推斷)")
    print(f"  Complexity: {result5['complexity_score']} (自動推斷)")
    assert result5['intent'] == 'qa_general'
    assert result5['confidence'] == 0.9  # Safe 預設
    assert result5['complexity_score'] == 3.0  # qa_general 預設
    print("  ✅ 通過（自動推斷）\n")
    
    # 測試案例 6: 各種 Intent 的 Complexity 精確值
    test_cases = [
        ("Open QA", 0.95, 2.0, "基本問答"),
        ("Code Generation", 0.88, 9.5, "複雜演算法"),
        ("Text Generation", 0.90, 6.5, "創意寫作"),
        ("Summarization", 0.92, 4.0, "文章摘要"),
    ]
    
    print(f"Test 6 - 各種 Intent 的精確 Complexity:")
    for intent, conf, comp, desc in test_cases:
        text = f"""
Intent: {intent}
Confidence: {conf}
Complexity: {comp}
Safety: Safe
Category: None
"""
        result = analyzer._parse_s_category_format(text)
        print(f"  {desc}: Complexity={result['complexity_score']} (期望={comp})")
        assert abs(result['complexity_score'] - comp) < 0.01
    print("  ✅ 全部通過\n")
    
    # 測試案例 7: 邊界值測試
    print(f"Test 7 - 邊界值測試:")
    
    # Confidence 超過 1.0 應該被限制為 1.0
    text7a = """
Intent: Open QA
Confidence: 1.5
Complexity: 5.0
Safety: Safe
Category: None
"""
    result7a = analyzer._parse_s_category_format(text7a)
    print(f"  Confidence > 1.0: {result7a['confidence']} (應被限制為 1.0)")
    assert result7a['confidence'] == 1.0
    
    # Complexity 超過 10 應該被限制為 10
    text7b = """
Intent: Code Generation
Confidence: 0.9
Complexity: 15.0
Safety: Safe
Category: None
"""
    result7b = analyzer._parse_s_category_format(text7b)
    print(f"  Complexity > 10: {result7b['complexity_score']} (應被限制為 10.0)")
    assert result7b['complexity_score'] == 10.0
    print("  ✅ 通過\n")


def test_s1_s14_mapping():
    """測試 S1-S14 映射（二分法：Safe/Unsafe）"""
    from lyrallm.models.safety import SafetyLabels, SafetyLevel
    
    analyzer = SLMAnalyzer()  # 不傳參數
    
    print("=" * 80)
    print("測試 S1-S14 映射（二分法）")
    print("=" * 80)
    
    test_cases = [
        ('S1', 'Unsafe', SafetyLevel.CRITICAL, 'violence'),
        ('S2', 'Unsafe', SafetyLevel.HIGH, None),
        ('S3', 'Unsafe', SafetyLevel.CRITICAL, 'sexual'),
        ('S9', 'Unsafe', SafetyLevel.CRITICAL, 'violence'),
        ('S10', 'Unsafe', SafetyLevel.CRITICAL, 'hate_speech'),
        ('S11', 'Unsafe', SafetyLevel.CRITICAL, 'self_harm'),
        ('S14', 'Unsafe', SafetyLevel.CRITICAL, None),
        ('None', 'Safe', SafetyLevel.NONE, None),
    ]
    
    for category, safety, expected_risk, field_name in test_cases:
        safety_labels = analyzer._map_s_category_to_safety_labels(category, safety)
        
        print(f"\n{category} ({safety}):")
        print(f"  Risk Level: {safety_labels.risk_level}")
        print(f"  Details: {safety_labels.details}")
        
        assert safety_labels.risk_level == expected_risk, \
            f"{category} should have risk_level={expected_risk}, got {safety_labels.risk_level}"
        
        if field_name:
            field_value = getattr(safety_labels, field_name)
            assert field_value is not None and field_value != SafetyLevel.NONE, \
                f"{category} should have {field_name} set"
        
        print(f"  ✅ 通過")
    
    print("\n" + "=" * 80)
    print("✅ S1-S14 所有類別映射正確（二分法）")
    print("=" * 80)


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🧪 測試 5 行格式解析（Confidence + Complexity）")
    print("=" * 80 + "\n")
    
    try:
        test_parse_5_line_format()
        test_s1_s14_mapping()
        
        print("\n" + "=" * 80)
        print("✅ 所有測試通過！")
        print("=" * 80)
        print("\n新格式特點：")
        print("  1. ✅ SLM 直接提供 Confidence (0.0-1.0)")
        print("  2. ✅ SLM 直接提供 Complexity (1-10)")
        print("  3. ✅ Safety 改為二分法 (Safe/Unsafe)")
        print("  4. ✅ 向後兼容 3 行格式（自動推斷 Confidence/Complexity）")
        print("  5. ✅ 邊界值自動限制（Confidence ≤1.0, Complexity ≤10）")
        print("  6. ✅ 移除 Controversial 狀態")
        
    except AssertionError as e:
        print(f"\n❌ 測試失敗: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
        raise
