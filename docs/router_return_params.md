# Router 回傳參數完整統整文檔

> 📅 **最後更新**：2025-10-17  
> 🎯 **用途**：統整 RouterV1 目前和未來會回傳的所有參數，方便修正 Agent 固定化問題  
> 📌 **重要**：此文檔僅供參考，不涉及程式碼修改

---

## 📊 目錄

1. [目前的 Router 回傳結構](#目前的-router-回傳結構)
2. [IntentResult 資料結構](#intentresult-資料結構)
3. [RuleDecision 資料結構](#ruledecision-資料結構)
4. [完整回傳範例](#完整回傳範例)
5. [未來擴展後的回傳結構](#未來擴展後的回傳結構)
6. [Agent 可用的動態參數](#agent-可用的動態參數)
7. [使用建議](#使用建議)

---

## 目前的 Router 回傳結構

### 📦 RouterV1.route() 完整回傳格式

```python
{
    # === 頂層欄位（直接可用） ===
    'intent': str,              # 意圖分類（如 'code_generation', 'qa_general'）
    'confidence': float,        # 信心度 (0-1)
    'complexity': float,        # 複雜度評分 (1-10)
    'model': str,               # 選定的模型名稱（如 'gpt-4', 'llama-3-8b'）
    'candidates': List[str],    # 候選模型清單
    
    # === trace 欄位（詳細追蹤資訊） ===
    'trace': {
        'router': str,          # Router 版本（如 'RouterV1'）
        
        # --- SLM 分析器資訊 ---
        'analyzer': {
            'intent': str,              # 意圖
            'confidence': float,        # 信心度
            'complexity': float,        # 複雜度
            'ms': int,                  # SLM 分析耗時（毫秒）
            'slm_model': str,           # 使用的 SLM 模型（可選）
            'effective_slm_model': str, # 實際嘗試的 SLM 模型（可選）
            'fallback': bool,           # 是否降級到預設值（可選）
        },
        
        # --- 決策引擎資訊 ---
        'decision': {
            'selected': str,                    # 選定的模型
            'candidates': List[str],            # 候選模型清單
            'threshold': float,                 # 複雜度閾值
            'used_bucket': str,                 # 使用的桶（'high', 'low', 'capability'）
            'capability_details': List[Dict],   # 能力評分詳情（可選）
        },
        
        # --- 時間追蹤 ---
        'timings': {
            'total_ms': int,    # 總耗時（毫秒）
        },
        
        # --- 決策路徑 ---
        'decision_path': List[str],  # 決策流程路徑（如 ['slm_analyze', 'rules_capability']）
    }
}
```

---

## IntentResult 資料結構

### 📋 SLM Analyzer 回傳的分析結果

```python
@dataclass
class IntentResult:
    # === 核心欄位 ===
    intent: str                         # 意圖分類
    confidence: float                   # 信心度 (0-1)
    complexity: float                   # 複雜度評分 (1-10)
    
    # === 可選欄位 ===
    domain: Optional[str] = None        # 領域分類（如 'finance', 'tech'）
    language: Optional[str] = None      # 語言（如 'zh-TW', 'en-US'）
    estimated_tokens: Optional[int] = None  # 預估回應 token 數
    
    # === 元資料 ===
    ms: int = 0                         # 分析耗時（毫秒）
    raw: Optional[Dict[str, Any]] = None  # 原始 JSON 回應
    slm_model: Optional[str] = None     # 使用的 SLM 模型名稱
    effective_slm_model: Optional[str] = None  # 實際嘗試的模型
    fallback: bool = False              # 是否使用降級預設值
```

### 🔍 意圖類別 (intent) 可能值

目前系統支援的意圖類別：

```python
INTENT_TYPES = [
    'code_generation',      # 程式碼生成
    'data_analysis',        # 資料分析
    'text_summary',         # 文本摘要
    'qa_general',           # 一般問答（預設值）
    'creative_writing',     # 創意寫作
    'translation',          # 翻譯
    'math_reasoning',       # 數學推理
    'finance',              # 金融/財經相關
]
```

---

## RuleDecision 資料結構

### 📋 規則引擎回傳的決策結果

```python
@dataclass
class RuleDecision:
    selected: str                       # 選定的模型名稱
    candidates: List[str]               # 候選模型清單（已排序）
    threshold: float                    # 複雜度閾值
    used_bucket: str                    # 使用的分類桶
    capability_details: Optional[List[Dict[str, Any]]] = None  # 能力評分詳情
```

### 🗂️ used_bucket 可能值

```python
BUCKET_TYPES = [
    'capability',   # 能力匹配模式（根據 IQ/PR/Level 評分）
    'high',         # 高複雜度桶（complexity >= threshold）
    'low',          # 低複雜度桶（complexity < threshold）
]
```

### 📊 capability_details 結構（當 used_bucket='capability' 時）

```python
capability_details: List[Dict] = [
    {
        'model': str,           # 模型名稱（如 'gpt-4'）
        'level': float,         # 能力等級（1-10）
        'target': float,        # 目標能力等級（= complexity）
        'required': float,      # 需要的能力等級（= complexity）
        'meets': bool,          # 是否滿足需求（level >= required）
        'diff': float,          # 能力差距（|level - target|）
        'pr': float,            # 處理速度評分
        'iq': float,            # 智商評分
        'intent_match': bool,   # 是否匹配意圖
    },
    # ... 更多候選模型 ...
]
```

**排序邏輯**：
1. 優先選擇 `intent_match=True` 的模型
2. 其次選擇 `diff` 最小的（能力最接近需求）
3. 最後按 `level` 排序（能力較高者優先）

---

## 完整回傳範例

### 範例 1：Capability 模式（有 IQ 評分）

```json
{
    "intent": "code_generation",
    "confidence": 0.95,
    "complexity": 7.5,
    "model": "gpt-4",
    "candidates": ["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
    "trace": {
        "router": "RouterV1",
        "analyzer": {
            "intent": "code_generation",
            "confidence": 0.95,
            "complexity": 7.5,
            "ms": 245,
            "slm_model": "o3-mini",
            "effective_slm_model": "o3-mini",
            "fallback": false
        },
        "decision": {
            "selected": "gpt-4",
            "candidates": ["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
            "threshold": 7.0,
            "used_bucket": "capability",
            "capability_details": [
                {
                    "model": "gpt-4",
                    "level": 9.0,
                    "target": 7.5,
                    "required": 7.5,
                    "meets": true,
                    "diff": 1.5,
                    "pr": 8.0,
                    "iq": 9.5,
                    "intent_match": true
                },
                {
                    "model": "claude-3-opus",
                    "level": 8.5,
                    "target": 7.5,
                    "required": 7.5,
                    "meets": true,
                    "diff": 1.0,
                    "pr": 7.5,
                    "iq": 9.0,
                    "intent_match": true
                },
                {
                    "model": "gpt-3.5-turbo",
                    "level": 6.0,
                    "target": 7.5,
                    "required": 7.5,
                    "meets": false,
                    "diff": 1.5,
                    "pr": 9.5,
                    "iq": 6.5,
                    "intent_match": true
                }
            ]
        },
        "timings": {
            "total_ms": 268
        },
        "decision_path": ["slm_analyze", "rules_capability"]
    }
}
```

### 範例 2：傳統 High/Low 桶模式（無 IQ 評分）

```json
{
    "intent": "qa_general",
    "confidence": 0.85,
    "complexity": 3.0,
    "model": "llama-3-8b",
    "candidates": ["llama-3-8b", "gpt-3.5-turbo"],
    "trace": {
        "router": "RouterV1",
        "analyzer": {
            "intent": "qa_general",
            "confidence": 0.85,
            "complexity": 3.0,
            "ms": 180,
            "slm_model": "llama-3.2-3b",
            "fallback": false
        },
        "decision": {
            "selected": "llama-3-8b",
            "candidates": ["llama-3-8b", "gpt-3.5-turbo"],
            "threshold": 5.0,
            "used_bucket": "low",
            "capability_details": null
        },
        "timings": {
            "total_ms": 195
        },
        "decision_path": ["slm_analyze", "rules_low"]
    }
}
```

### 範例 3：SLM 降級模式（分析失敗）

```json
{
    "intent": "qa_general",
    "confidence": 0.5,
    "complexity": 3.0,
    "model": "gpt-3.5-turbo",
    "candidates": ["gpt-3.5-turbo"],
    "trace": {
        "router": "RouterV1",
        "analyzer": {
            "intent": "qa_general",
            "confidence": 0.5,
            "complexity": 3.0,
            "ms": 1520,
            "slm_model": "o3-mini",
            "effective_slm_model": "o3-mini",
            "fallback": true
        },
        "decision": {
            "selected": "gpt-3.5-turbo",
            "candidates": ["gpt-3.5-turbo"],
            "threshold": 3.0,
            "used_bucket": "low",
            "capability_details": null
        },
        "timings": {
            "total_ms": 1535
        },
        "decision_path": ["slm_analyze", "rules_low"]
    }
}
```

---

## 未來擴展後的回傳結構

### 🚀 Phase 1 完成後（步驟 1.3 - 1.7）

新增欄位將包含在 `IntentResult` 中，並通過 Router 傳遞：

```python
{
    # === 現有欄位 ===
    'intent': str,
    'confidence': float,
    'complexity': float,
    'model': str,
    'candidates': List[str],
    
    # === 新增：工具需求 ===
    'required_tools': List[Dict] = [
        {
            'tool_type': str,       # 工具類型（如 'web_search', 'code_interpreter'）
            'priority': str,        # 優先級（'required', 'recommended', 'optional'）
            'reason': str,          # 需要該工具的原因
            'parameters': Dict,     # 工具特定參數
        }
    ],
    'needs_tools': bool,            # 是否需要任何工具
    
    # === 新增：安全標籤 ===
    'safety_labels': {
        'violence': str,            # 暴力程度（'none', 'low', 'medium', 'high', 'critical'）
        'sexual': str,              # 色情程度
        'hate_speech': str,         # 仇恨言論程度
        'self_harm': str,           # 自殘內容程度
        'confidential_data': str,   # 機密資料類型（'none', 'pii', 'financial', etc.）
        'jailbreak_attempt': bool,  # 是否嘗試 jailbreak 攻擊
        'risk_level': str,          # 整體風險等級
        'details': List[str],       # 詳細說明
        'is_safe': bool,            # 是否安全可處理
        'requires_escalation': bool, # 是否需要升級處理
    },
    
    # === 新增：權限需求 ===
    'required_permissions': {
        'min_tier': str,            # 最低使用者等級（'free', 'pro', 'enterprise', 'admin'）
        'roles': List[str],         # 需要的角色（如 ['developer', 'analyst']）
        'permissions': List[str],   # 需要的權限（如 ['use_web_search']）
        'data_access_level': str,   # 資料存取等級（'public', 'internal', 'confidential', 'restricted'）
        'reason': str,              # 需要該權限的原因
    },
    
    # === 新增：安全決策（步驟 1.4 後） ===
    'safety_decision': {
        'action': str,              # 決策行動（'allow', 'block', 'audit', 'escalate'）
        'reason': str,              # 決策理由
        'blocked': bool,            # 是否被攔截
        'audit_required': bool,     # 是否需要審計
    },
    
    # === 新增：工具授權檢查（步驟 2.2 後） ===
    'tool_authorization': {
        'authorized': bool,         # 是否全部授權
        'authorized_tools': List[str],   # 已授權的工具
        'unauthorized_tools': List[str], # 未授權的工具
        'upgrade_required': bool,   # 是否需要升級方案
    },
    
    # === 新增：使用者資訊（步驟 1.6 後） ===
    'user_context': {
        'user_id': str,
        'tier': str,                # 使用者等級
        'quota_remaining': {
            'tokens': int,          # 剩餘 token 配額
            'requests': int,        # 剩餘請求次數
        },
        'quota_exceeded': bool,     # 是否超過配額
    },
    
    # === trace 擴展 ===
    'trace': {
        # ... 現有欄位 ...
        
        # 新增：安全檢查追蹤
        'safety_check': {
            'ms': int,
            'risk_level': str,
            'action': str,
        },
        
        # 新增：工具授權追蹤
        'tool_auth_check': {
            'ms': int,
            'authorized': bool,
        },
        
        # 新增：配額檢查追蹤
        'quota_check': {
            'ms': int,
            'exceeded': bool,
        },
    }
}
```

---

## Agent 可用的動態參數

### 🎯 關鍵參數：避免 Agent 固定化

如果你的 Agent 目前是固定的（寫死），可以使用以下 Router 回傳的參數來動態化：

#### 1️⃣ **模型選擇（必須動態化）**

```python
# ❌ 不好：固定模型
selected_model = "gpt-4"

# ✅ 好：使用 Router 決定
routing_result = await router.route(user_query)
selected_model = routing_result['model']  # 動態選擇
```

#### 2️⃣ **意圖與複雜度（用於 Agent 策略調整）**

```python
intent = routing_result['intent']         # 如 'code_generation'
complexity = routing_result['complexity']  # 如 7.5

# 根據意圖調整 Agent 行為
if intent == 'code_generation':
    # 啟用代碼執行器
    agent.enable_code_interpreter()
elif intent == 'data_analysis':
    # 啟用資料分析工具
    agent.enable_data_analysis()
```

#### 3️⃣ **工具需求（未來）**

```python
# Phase 1 完成後可用
if routing_result.get('needs_tools'):
    required_tools = routing_result['required_tools']
    for tool in required_tools:
        if tool['tool_type'] == 'web_search' and tool['priority'] == 'required':
            # 必須啟用網頁搜尋
            agent.enable_web_search()
```

#### 4️⃣ **安全檢查（未來）**

```python
# Phase 1 完成後可用
safety = routing_result.get('safety_labels', {})
if not safety.get('is_safe', True):
    # 內容不安全，拒絕處理
    return {"error": "內容違反安全政策", "details": safety.get('details')}
```

#### 5️⃣ **使用者等級與權限（未來）**

```python
# Phase 1 完成後可用
user_tier = routing_result.get('user_context', {}).get('tier', 'free')

if user_tier == 'free':
    # 免費使用者限制
    agent.set_max_tokens(1000)
elif user_tier == 'pro':
    # 專業版使用者
    agent.set_max_tokens(4000)
elif user_tier == 'enterprise':
    # 企業版使用者
    agent.set_max_tokens(32000)
```

---

## 使用建議

### ✅ 最佳實踐

1. **永遠使用 `routing_result['model']`**
   - 不要寫死模型名稱
   - 讓 Router 動態決定

2. **根據 `intent` 調整 Agent 行為**
   - 不同意圖需要不同策略
   - 例如：`code_generation` 需要代碼工具

3. **利用 `candidates` 實現降級**
   - 如果首選模型失敗，嘗試候選清單中的下一個
   ```python
   for model in routing_result['candidates']:
       try:
           response = await agent.call_model(model, query)
           break
       except Exception:
           continue
   ```

4. **記錄 `trace` 資訊用於除錯**
   - 完整的決策路徑
   - 各階段耗時
   - 降級標記

5. **準備好接收未來的新欄位**
   - 使用 `.get()` 而不是直接存取
   - 提供預設值
   ```python
   tools = routing_result.get('required_tools', [])
   safety = routing_result.get('safety_labels', {})
   ```

### ⚠️ 避免的錯誤

1. ❌ **不要寫死模型名稱**
   ```python
   # 錯誤
   model = "gpt-4"
   ```

2. ❌ **不要忽略 Router 的決策**
   ```python
   # 錯誤：取得 routing_result 但不使用
   routing_result = await router.route(query)
   model = "gpt-4"  # 仍然使用固定模型
   ```

3. ❌ **不要假設欄位一定存在**
   ```python
   # 錯誤
   tools = routing_result['required_tools']  # 可能不存在
   
   # 正確
   tools = routing_result.get('required_tools', [])
   ```

---

## 🔄 版本演進對照表

| 欄位 | 目前版本 | Phase 1 後 | Phase 2 後 |
|------|---------|-----------|-----------|
| `intent` | ✅ | ✅ | ✅ |
| `confidence` | ✅ | ✅ | ✅ |
| `complexity` | ✅ | ✅ | ✅ |
| `model` | ✅ | ✅ | ✅ |
| `candidates` | ✅ | ✅ | ✅ |
| `required_tools` | ❌ | ✅ | ✅ |
| `safety_labels` | ❌ | ✅ | ✅ |
| `required_permissions` | ❌ | ✅ | ✅ |
| `safety_decision` | ❌ | ✅ | ✅ |
| `tool_authorization` | ❌ | ❌ | ✅ |
| `user_context` | ❌ | ✅ | ✅ |
| `quota_info` | ❌ | ❌ | ✅ |

---

## 📚 相關文件

- `models/model_introduce.md` - 資料模型詳細說明
- `TodoList.md` - 實施步驟追蹤
- `config/routing_rules.yaml` - Router 配置檔
- `core/router_v1/router.py` - Router 實現
- `core/router_v1/analyzer_slm.py` - SLM Analyzer 實現

---

> 💡 **給開發者的提示**：
> - 使用 `routing_result['model']` 而不是固定模型名稱
> - 使用 `routing_result['intent']` 來調整 Agent 行為
> - 使用 `routing_result['candidates']` 實現降級機制
> - 準備好接收未來的新欄位（使用 `.get()` 方法）

> 📅 **最後更新**：2025-10-17 23:55  
> 👤 **整理者**：GitHub Copilot  
> 🔄 **版本**：v1.0 (目前版本統整)
