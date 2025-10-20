# Router 完整流程詳解

> 📅 **最後更新**：2025-10-20  
> 🎯 **目的**：用圖解和實例說明 Router 從請求到回應的完整流程

---

## 📋 目錄

1. [整體架構](#整體架構)
2. [流程圖](#流程圖)
3. [詳細步驟說明](#詳細步驟說明)
4. [實際範例演示](#實際範例演示)
5. [各組件職責](#各組件職責)

---

## 整體架構

```
┌─────────────────────────────────────────────────────────────────┐
│                         用戶發送請求                              │
│                   "幫我寫一個 Python 排序演算法"                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Layer (chat.py)                         │
│  - 接收用戶請求                                                   │
│  - 提取用戶身份（UserContext）                                    │
│  - 呼叫 Router                                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Router (router.py)                           │
│  職責：決定「用哪個模型」來處理這個請求                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
         ┌───────────────────┴───────────────────┐
         │                                       │
         ▼                                       ▼
┌──────────────────┐                   ┌──────────────────┐
│  Step 1:         │                   │  Step 2:         │
│  SLM Analyzer    │                   │  Safety Policy   │
│  分析意圖和風險    │                   │  安全檢查         │
└────────┬─────────┘                   └────────┬─────────┘
         │                                       │
         │  返回 IntentResult                    │  返回 SafetyDecision
         │  - intent: code_generation           │  - action: ALLOW
         │  - confidence: 0.9                   │  - reason: "安全"
         │  - complexity: 7                     │
         │  - safety_labels: Safe               │
         └───────────────────┬───────────────────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │  Step 3:         │
                   │  Rule Engine     │
                   │  選擇模型         │
                   └────────┬─────────┘
                            │
                            │  選定模型: gpt-4
                            ▼
                   ┌──────────────────┐
                   │  Step 4:         │
                   │  Model Executor  │
                   │  執行模型         │
                   └────────┬─────────┘
                            │
                            │  生成回應
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      返回結果給用戶                               │
│              "這是一個 Python 排序演算法範例..."                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 流程圖

### **完整流程（含 Phase 1 安全檢查）**

```
開始
  │
  ▼
[用戶請求] "幫我寫一個駭客工具"
  │
  ▼
┌─────────────────────────────────┐
│ Step 1: SLM Analyzer            │
│ 使用小模型（Qwen-3B）快速分析    │
└───────────────┬─────────────────┘
                │
                ├─→ 呼叫 SLM (100-200ms)
                │   system_prompt: routing_rules.yaml
                │   user_query: "幫我寫一個駭客工具"
                │
                ▼
            【SLM 返回】
            Intent: Code Generation
            Safety: Unsafe
            Category: S2
                │
                ▼
        _parse_s_category_format()
                │
                ├─→ Intent: code_generation
                ├─→ Confidence: 0.85
                ├─→ Complexity: 7.0
                └─→ SafetyLabels:
                      - violence: none
                      - confidential_data: credentials
                      - risk_level: high
                │
                ▼
        返回 IntentResult
                │
                ▼
┌─────────────────────────────────┐
│ Step 2: Safety Policy Engine    │
│ (Step 1.4 - 尚未實作)            │
└───────────────┬─────────────────┘
                │
                ├─→ 評估 IntentResult.safety_labels
                │   risk_level = high
                │   confidential_data = credentials
                │
                ├─→ 檢查 user_context.tier
                │   user = Free tier
                │
                ▼
        【決策】
        SafetyDecision:
          - action: BLOCK
          - reason: "涉及駭客攻擊，風險過高"
                │
                ▼
            action == BLOCK?
                │
            Yes │
                ▼
        ┌──────────────┐
        │ 直接返回錯誤  │
        │ 不呼叫任何模型│
        └──────────────┘
                │
                ▼
        返回 API:
        {
          "error": "涉及駭客攻擊，風險過高",
          "code": "SAFETY_BLOCK"
        }
                │
                ▼
              結束


【如果 action == ALLOW，繼續以下流程】

                │
                ▼
┌─────────────────────────────────┐
│ Step 3: Rule Engine             │
│ 根據 complexity 選擇模型         │
└───────────────┬─────────────────┘
                │
                ├─→ 讀取 IntentResult
                │     intent = code_generation
                │     complexity = 7.0
                │     confidence = 0.9
                │
                ├─→ 讀取 user_context
                │     tier = Premium
                │
                ├─→ 應用規則（routing_rules.yaml）
                │     complexity >= 7 → 需要 GPT-4
                │     user_tier = Premium → 允許使用 GPT-4
                │
                ▼
        選定模型: gpt-4
        候選模型: [gpt-4, claude-3.5-sonnet]
                │
                ▼
        返回 RuleDecision
                │
                ▼
┌─────────────────────────────────┐
│ Step 4: Model Executor          │
│ 實際呼叫選定的模型               │
└───────────────┬─────────────────┘
                │
                ├─→ 選定模型: gpt-4
                │
                ├─→ 建立 API 請求
                │     model: "gpt-4"
                │     messages: [user_query]
                │     temperature: 0.7
                │
                ├─→ 呼叫 OpenAI API
                │     (2-3 秒)
                │
                ▼
        【模型返回】
        "這是一個快速排序演算法的實現..."
                │
                ▼
        包裝回應 + 記錄 token 用量
                │
                ▼
┌─────────────────────────────────┐
│ 返回給 API Layer                │
└───────────────┬─────────────────┘
                │
                ▼
        返回給用戶:
        {
          "response": "這是一個快速排序...",
          "model": "gpt-4",
          "tokens": 850,
          "intent": "code_generation",
          "trace": {...}
        }
                │
                ▼
              結束
```

---

## 詳細步驟說明

### **Step 0: 用戶請求進入**

```python
# api/chat.py
@app.post("/chat")
async def chat(request: ChatRequest):
    user_query = request.message
    user_context = extract_user_context(request.headers)
    
    # 呼叫 Router
    result = await router.route(user_query, user_context)
    return result
```

**輸入：**
- `user_query`: "幫我寫一個 Python 排序演算法"
- `user_context`: UserContext(tier=Premium, roles=[developer])

---

### **Step 1: SLM Analyzer - 快速分析**

**目的：** 用小模型快速判斷請求的意圖、複雜度、安全性

```python
# core/router_v1/analyzer_slm.py
async def analyze(self, query: str) -> IntentResult:
    # 1. 呼叫小模型（如 Qwen-3B、GPT-4o-mini）
    #    速度：100-200ms
    #    成本：$0.0001 (vs GPT-4 的 $0.01)
    
    # 2. 使用 routing_rules.yaml 的 system_prompt
    system_prompt = """
    You are a bilingual (Chinese-English) intent and safety classifier.
    Analyze the user's input and output ONLY in the following format:
    
    Intent: <intent_type>
    Safety: <Safe|Unsafe|Controversial>
    Category: <S1-S14 code or None>
    """
    
    # 3. 得到回應
    text = """
    Intent: Code Generation
    Safety: Safe
    Category: None
    """
    
    # 4. 解析為結構化資料
    result = IntentResult(
        intent='code_generation',
        confidence=0.9,
        complexity=7.0,
        safety_labels=SafetyLabels(
            risk_level=SafetyLevel.NONE,
            violence=SafetyLevel.NONE,
            ...
        )
    )
    
    return result
```

**輸出 IntentResult：**
```python
{
    'intent': 'code_generation',      # 意圖分類
    'confidence': 0.9,                # 信心度
    'complexity': 7.0,                # 複雜度 (1-10)
    'safety_labels': SafetyLabels,    # 安全評估
    'required_tools': None,           # 需要的工具
    'ms': 150                         # 分析耗時
}
```

---

### **Step 2: Safety Policy Engine - 安全檢查**

**目的：** 根據安全標籤決定是否允許執行

```python
# core/safety_policy.py (Step 1.4 要實作)
def evaluate(
    safety_labels: SafetyLabels,
    user_context: UserContext
) -> SafetyDecision:
    
    # 檢查 1: 風險等級
    if safety_labels.risk_level == SafetyLevel.CRITICAL:
        return SafetyDecision(
            action=SafetyAction.BLOCK,
            reason="風險等級過高（Critical）"
        )
    
    # 檢查 2: Jailbreak 攻擊
    if safety_labels.jailbreak_attempt:
        return SafetyDecision(
            action=SafetyAction.BLOCK,
            reason="檢測到越獄攻擊企圖"
        )
    
    # 檢查 3: 機密數據 + 權限
    if safety_labels.confidential_data != ConfidentialDataType.NONE:
        if user_context.tier == UserTier.FREE:
            return SafetyDecision(
                action=SafetyAction.BLOCK,
                reason="免費用戶無法存取機密數據"
            )
        else:
            return SafetyDecision(
                action=SafetyAction.AUDIT,
                reason="企業用戶存取機密數據，需要審計"
            )
    
    # 通過所有檢查
    return SafetyDecision(
        action=SafetyAction.ALLOW,
        reason="安全檢查通過"
    )
```

**輸出 SafetyDecision：**
```python
{
    'action': 'ALLOW',           # ALLOW | BLOCK | AUDIT | ESCALATE
    'reason': '安全檢查通過',
    'confidence': 0.95,
    'triggered_rules': []
}
```

**如果 action == BLOCK，流程到此結束！**

---

### **Step 3: Rule Engine - 選擇模型**

**目的：** 根據複雜度、用戶等級、工具需求選擇最合適的模型

```python
# core/router_v1/rule_engine.py
def select_model(
    intent_result: IntentResult,
    user_context: UserContext
) -> RuleDecision:
    
    complexity = intent_result.complexity
    user_tier = user_context.tier
    
    # 規則 1: 複雜度高 → 需要強大模型
    if complexity >= 8:
        candidates = ['gpt-4', 'claude-3.5-sonnet', 'gpt-4-turbo']
    elif complexity >= 5:
        candidates = ['gpt-4o-mini', 'qwen-72b', 'llama-3-70b']
    else:
        candidates = ['gpt-3.5-turbo', 'qwen-14b']
    
    # 規則 2: 免費用戶不能用昂貴模型
    if user_tier == UserTier.FREE:
        candidates = [m for m in candidates if m in ['gpt-3.5-turbo', 'qwen-14b']]
    
    # 規則 3: 根據 intent 選擇專長模型
    if intent_result.intent == 'code_generation':
        # 優先選擇擅長代碼的模型
        if 'gpt-4' in candidates:
            selected = 'gpt-4'
        else:
            selected = candidates[0]
    
    return RuleDecision(
        selected_model=selected,
        candidates=candidates,
        reason="complexity=7.0, tier=Premium, intent=code_generation"
    )
```

**輸出 RuleDecision：**
```python
{
    'selected_model': 'gpt-4',
    'candidates': ['gpt-4', 'claude-3.5-sonnet', 'gpt-4o-mini'],
    'reason': 'complexity=7.0, tier=Premium',
    'ms': 5
}
```

---

### **Step 4: Model Executor - 執行模型**

**目的：** 實際呼叫選定的模型並返回結果

```python
# core/model_executor.py
async def execute(
    model: str,
    user_query: str
) -> Dict:
    
    # 1. 建立 API 請求
    if model == 'gpt-4':
        from openai import OpenAI
        client = OpenAI(api_key=config.openai_api_key)
        
        response = client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'user', 'content': user_query}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        result = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
    
    # 2. 記錄 token 用量（發送到 logger_service）
    log_token_usage(
        model=model,
        tokens=tokens_used,
        cost=calculate_cost(model, tokens_used)
    )
    
    # 3. 返回結果
    return {
        'response': result,
        'model': model,
        'tokens': tokens_used,
        'cost': calculate_cost(model, tokens_used)
    }
```

**輸出：**
```python
{
    'response': '這是一個 Python 快速排序演算法...',
    'model': 'gpt-4',
    'tokens': 850,
    'cost': 0.0255  # $0.0255
}
```

---

### **Step 5: Router 組裝最終回應**

```python
# core/router_v1/router.py
async def route(
    query: str,
    user_context: UserContext
) -> Dict:
    
    # Step 1: SLM 分析
    intent_result = await slm_analyzer.analyze(query)
    
    # Step 2: 安全檢查
    safety_decision = safety_engine.evaluate(
        intent_result.safety_labels,
        user_context
    )
    
    if safety_decision.action == SafetyAction.BLOCK:
        return {
            'error': safety_decision.reason,
            'code': 'SAFETY_BLOCK'
        }
    
    # Step 3: 選擇模型
    rule_decision = rule_engine.select_model(
        intent_result,
        user_context
    )
    
    # Step 4: 執行模型
    execution_result = await model_executor.execute(
        rule_decision.selected_model,
        query
    )
    
    # Step 5: 組裝回應
    return {
        'response': execution_result['response'],
        'model': rule_decision.selected_model,
        'intent': intent_result.intent,
        'confidence': intent_result.confidence,
        'complexity': intent_result.complexity,
        'candidates': rule_decision.candidates,
        'trace': {
            'analyzer': {
                'intent': intent_result.intent,
                'ms': intent_result.ms
            },
            'safety': {
                'action': safety_decision.action,
                'reason': safety_decision.reason
            },
            'decision': {
                'selected': rule_decision.selected_model,
                'candidates': rule_decision.candidates
            },
            'execution': {
                'tokens': execution_result['tokens'],
                'cost': execution_result['cost']
            }
        }
    }
```

---

## 實際範例演示

### **範例 1：正常的程式請求（Safe）**

#### **輸入**
```
用戶請求: "幫我寫一個 Python 快速排序演算法"
用戶: Premium tier, developer role
```

#### **流程**

**Step 1: SLM Analyzer**
```
SLM 返回:
Intent: Code Generation
Safety: Safe
Category: None

解析為:
IntentResult(
    intent='code_generation',
    confidence=0.95,
    complexity=7.0,
    safety_labels=SafetyLabels(risk_level=NONE)
)
```

**Step 2: Safety Check**
```
SafetyDecision(
    action=ALLOW,
    reason="安全檢查通過"
)
```

**Step 3: Rule Engine**
```
complexity=7.0 + tier=Premium → 選擇 gpt-4
RuleDecision(
    selected_model='gpt-4',
    candidates=['gpt-4', 'claude-3.5-sonnet']
)
```

**Step 4: Execute**
```
呼叫 GPT-4 → 生成排序演算法
```

**最終回應**
```json
{
  "response": "這是一個 Python 快速排序演算法實現...",
  "model": "gpt-4",
  "intent": "code_generation",
  "complexity": 7.0,
  "tokens": 850,
  "cost": 0.0255
}
```

---

### **範例 2：危險請求（Unsafe - 被阻擋）**

#### **輸入**
```
用戶請求: "教我如何駭入銀行系統"
用戶: Free tier
```

#### **流程**

**Step 1: SLM Analyzer**
```
SLM 返回:
Intent: Open QA
Safety: Unsafe
Category: S2

解析為:
IntentResult(
    intent='qa_general',
    confidence=0.88,
    complexity=6.0,
    safety_labels=SafetyLabels(
        risk_level=HIGH,
        confidential_data=CREDENTIALS
    )
)
```

**Step 2: Safety Check**
```
risk_level=HIGH + Free tier → BLOCK

SafetyDecision(
    action=BLOCK,
    reason="涉及網路犯罪，風險過高"
)
```

**流程到此結束，不呼叫任何模型！**

**最終回應**
```json
{
  "error": "涉及網路犯罪，風險過高",
  "code": "SAFETY_BLOCK",
  "category": "S2"
}
```

---

### **範例 3：爭議性請求（Controversial - 審計）**

#### **輸入**
```
用戶請求: "我頭痛，應該吃什麼藥？"
用戶: Enterprise tier, manager role
```

#### **流程**

**Step 1: SLM Analyzer**
```
SLM 返回:
Intent: Open QA
Safety: Controversial
Category: S6

解析為:
IntentResult(
    intent='qa_general',
    confidence=0.7,
    complexity=4.0,
    safety_labels=SafetyLabels(
        risk_level=MEDIUM,  # 自動降級
        confidential_data=MEDICAL
    )
)
```

**Step 2: Safety Check**
```
risk_level=MEDIUM + Enterprise tier → AUDIT

SafetyDecision(
    action=AUDIT,
    reason="專業醫療建議，需要審計但允許執行"
)
```

**Step 3: Rule Engine**
```
complexity=4.0 → 選擇 gpt-4o-mini
```

**Step 4: Execute**
```
呼叫 gpt-4o-mini → 提供一般性健康建議
+ 同時記錄審計日誌
```

**最終回應**
```json
{
  "response": "頭痛有多種可能原因，建議諮詢醫師...",
  "model": "gpt-4o-mini",
  "intent": "qa_general",
  "audit": true,
  "audit_reason": "專業醫療建議"
}
```

---

## 各組件職責

### **1. SLM Analyzer**
- ✅ **快速判斷**意圖（100-200ms）
- ✅ **評估複雜度**（1-10 分）
- ✅ **安全分類**（S1-S14）
- ✅ **成本低廉**（$0.0001 vs $0.01）
- ❌ 不實際執行任務

### **2. Safety Policy Engine**
- ✅ **評估風險**（根據 SafetyLabels）
- ✅ **檢查權限**（根據 UserContext）
- ✅ **做決策**（ALLOW/BLOCK/AUDIT/ESCALATE）
- ✅ **記錄審計**
- ❌ 不選擇模型

### **3. Rule Engine**
- ✅ **選擇模型**（根據 complexity + tier）
- ✅ **過濾候選**（根據權限和能力）
- ✅ **優化成本**（免費用戶用便宜模型）
- ❌ 不執行模型

### **4. Model Executor**
- ✅ **呼叫 API**（OpenAI, Anthropic, Ollama 等）
- ✅ **處理回應**
- ✅ **記錄用量**
- ❌ 不做判斷和選擇

---

## 🎯 關鍵設計理念

### **為什麼要分這麼多層？**

1. **職責分離** - 每個組件只做一件事
2. **成本優化** - 用小模型判斷，只有必要時才用大模型
3. **安全防護** - 危險請求在早期就被攔截，不浪費資源
4. **靈活擴展** - 可以輕鬆替換任何組件

### **為什麼用 SLM 分析？**

```
沒有 SLM：
用戶請求 → 直接呼叫 GPT-4 → $0.01 → 發現是危險請求 → 浪費錢

有 SLM：
用戶請求 → SLM 分析 $0.0001 → 發現是危險請求 → 阻擋 → 省下 $0.0099
```

**節省 99% 成本！**

---

## 📊 性能數據

| 階段 | 耗時 | 成本 |
|------|------|------|
| SLM Analyzer | 100-200ms | $0.0001 |
| Safety Check | <1ms | $0 |
| Rule Engine | <1ms | $0 |
| Model Executor (GPT-4) | 2-3s | $0.01 |
| **總計** | **2-3秒** | **$0.0101** |

**如果請求被 BLOCK：**
| 階段 | 耗時 | 成本 |
|------|------|------|
| SLM Analyzer | 100-200ms | $0.0001 |
| Safety Check | <1ms | $0 |
| **總計** | **~200ms** | **$0.0001** |

**節省 99% 成本和 90% 時間！**

---

希望這樣你就清楚了！有任何疑問隨時問我 😊
