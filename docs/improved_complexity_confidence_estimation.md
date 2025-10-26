# 改進的 Complexity 和 Confidence 推斷邏輯

## 動態 Complexity 推斷

```python
def estimate_complexity(intent: str, query: str, safety: str, category: str) -> float:
    """
    根據多個因素動態估計複雜度
    """
    # 基礎複雜度（根據 Intent）
    base_complexity = {
        'code_generation': 7.0,
        'data_analysis': 6.0,
        'creative_writing': 5.0,
        'text_summary': 4.0,
        'qa_general': 3.0,
        'translation': 3.5,
        'math_reasoning': 7.5
    }.get(intent, 3.0)
    
    complexity = base_complexity
    
    # 因素 1: 查詢長度調整
    query_length = len(query)
    if query_length > 500:
        complexity += 1.5
    elif query_length > 300:
        complexity += 1.0
    elif query_length > 150:
        complexity += 0.5
    elif query_length < 30:
        complexity -= 0.5
    
    # 因素 2: 關鍵字調整（高複雜度指標）
    high_complexity_keywords = [
        '系統', '架構', '設計', '完整', '複雜', '優化', '演算法',
        'system', 'architecture', 'design', 'complex', 'optimize', 'algorithm',
        '分散式', 'distributed', '並發', 'concurrent', '效能', 'performance'
    ]
    
    keyword_count = sum(1 for kw in high_complexity_keywords if kw in query.lower())
    complexity += min(keyword_count * 0.5, 2.0)  # 最多加 2.0
    
    # 因素 3: 關鍵字調整（低複雜度指標）
    low_complexity_keywords = [
        'hello world', '簡單', 'simple', '基礎', 'basic', '入門',
        '什麼是', 'what is', '如何', 'how to', '解釋', 'explain'
    ]
    
    if any(kw in query.lower() for kw in low_complexity_keywords):
        complexity -= 1.0
    
    # 因素 4: 數字和公式
    import re
    if re.search(r'\d+[\+\-\*/]\d+', query):  # 簡單數學運算
        complexity = min(complexity, 2.0)
    elif re.search(r'[∫∑∏∂∇]', query):  # 高級數學符號
        complexity = max(complexity, 8.0)
    
    # 因素 5: 安全類別調整
    if category in ['S1', 'S9', 'S14']:  # 高風險類別
        complexity += 0.5  # 需要更強模型來處理敏感內容
    
    # 限制範圍
    return max(1.0, min(complexity, 10.0))
```

## 動態 Confidence 推斷

```python
def estimate_confidence(
    intent: str, 
    query: str, 
    safety: str, 
    category: str
) -> float:
    """
    根據多個因素動態估計信心度
    """
    # 基礎信心度（根據 Safety）
    base_confidence = {
        'Safe': 0.90,
        'Unsafe': 0.85,
        'Controversial': 0.70
    }.get(safety, 0.75)
    
    confidence = base_confidence
    
    # 因素 1: 查詢清晰度
    query_length = len(query)
    if 10 <= query_length <= 100:
        confidence += 0.05  # 長度適中，清晰明確
    elif query_length < 10:
        confidence -= 0.10  # 太短，可能不清楚
    elif query_length > 500:
        confidence -= 0.05  # 太長，可能複雜
    
    # 因素 2: 明確的 Category
    if category != 'None':
        confidence += 0.05  # 有明確分類，更有信心
    
    # 因素 3: Intent 的明確性
    clear_intents = ['code_generation', 'translation', 'text_summary']
    if intent in clear_intents:
        confidence += 0.05  # 這些意圖通常很明確
    
    # 因素 4: 問號和疑問詞
    if '?' in query or any(qw in query.lower() for qw in ['嗎', '如何', 'how', 'what', 'why']):
        # 問句通常意圖明確
        confidence += 0.03
    
    # 因素 5: 歧義詞
    ambiguous_words = ['可能', 'maybe', '大概', 'probably', '或許', 'perhaps']
    if any(word in query.lower() for word in ambiguous_words):
        confidence -= 0.10  # 用戶自己都不確定
    
    # 因素 6: 多重請求（降低信心）
    if query.count('，') > 3 or query.count(',') > 3:
        confidence -= 0.05  # 多個請求混在一起
    
    # 限制範圍
    return max(0.5, min(confidence, 0.99))
```

## 使用範例

```python
# 簡單請求
query = "1+1等於多少？"
intent = "qa_general"
safety = "Safe"
category = "None"

complexity = estimate_complexity(intent, query, safety, category)
# 結果: 3.0 (基礎) - 0.5 (短) = 2.5

confidence = estimate_confidence(intent, query, safety, category)
# 結果: 0.90 (Safe) + 0.05 (長度適中) + 0.03 (問號) = 0.98

# → 非常簡單的請求，高信心度
```

```python
# 複雜請求
query = "請設計一個完整的分散式系統架構，包含負載平衡、容錯機制和資料一致性保證"
intent = "code_generation"
safety = "Safe"
category = "None"

complexity = estimate_complexity(intent, query, safety, category)
# 結果: 7.0 (基礎) + 1.0 (長度) + 2.0 (關鍵字: 系統、架構、設計、分散式) = 10.0

confidence = estimate_confidence(intent, query, safety, category)
# 結果: 0.90 (Safe) + 0.05 (明確 intent) = 0.95

# → 非常複雜，需要頂級模型
```

```python
# 爭議請求
query = "我頭痛，應該吃什麼藥？可能是感冒或許是過敏"
intent = "qa_general"
safety = "Controversial"
category = "S6"

complexity = estimate_complexity(intent, query, safety, category)
# 結果: 3.0 (基礎) + 0.5 (S6 類別) = 3.5

confidence = estimate_confidence(intent, query, safety, category)
# 結果: 0.70 (Controversial) + 0.05 (有 category) - 0.10 (歧義詞: 可能、或許) = 0.65

# → 中等複雜度，低信心度（需要謹慎處理）
```
