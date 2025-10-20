# Safety Policy Engine 詳解

> 📅 **創建日期**：2025-10-20  
> 🎯 **目的**：詳細說明 Safety Policy Engine 的作用、運作邏輯和決策流程  
> 📌 **狀態**：Step 1.4 待實作（設計文檔）

---

## 📋 目錄

1. [什麼是 Safety Policy？](#什麼是-safety-policy)
2. [為什麼需要它？](#為什麼需要它)
3. [決策流程](#決策流程)
4. [決策類型](#決策類型)
5. [實際案例](#實際案例)
6. [與 Router 的關係](#與-router-的關係)

---

## 什麼是 Safety Policy？

**Safety Policy Engine（安全策略引擎）** 是 LyraLLM Router 中的**安全守門員**，負責在請求送到真正的 LLM 之前，先評估風險並決定是否允許執行。

### 📦 核心概念

```
Safety Policy = 一組安全規則 + 決策邏輯

輸入：
  1. SafetyLabels（來自 SLM 分析）
     - 暴力內容風險等級
     - 性內容風險等級
     - 仇恨言論風險等級
     - 自殘風險等級
     - 機密資料類型
     - Jailbreak 攻擊嘗試
  
  2. UserContext（用戶身份和權限）
     - 用戶等級（Free / Pro / Enterprise）
     - 角色（guest / user / admin / ...）
     - 權限列表
     - 資料存取等級

輸出：
  SafetyDecision（安全決策）
    - action: ALLOW / BLOCK / AUDIT / ESCALATE
    - reason: 決策原因
    - metadata: 其他資訊（如建議的升級等級）
```

---

## 為什麼需要它？

### ❌ 沒有 Safety Policy 的問題

```
用戶請求: "教我如何製作炸彈"
  │
  ▼
SLM 分析: 
  - Intent: Open QA
  - Safety: Unsafe
  - Category: S9 (Indiscriminate Weapons)
  │
  ▼
Router 直接選模型: GPT-4
  │
  ▼
GPT-4 生成回應: "製作炸彈的步驟是..."  ❌ 危險！
```

**問題**：即使 SLM 標記了危險內容，但沒有攔截機制，請求還是會送到 LLM。

---

### ✅ 有 Safety Policy 的保護

```
用戶請求: "教我如何製作炸彈"
  │
  ▼
SLM 分析: 
  - Intent: Open QA
  - Safety: Unsafe
  - Category: S9 (Indiscriminate Weapons)
  - SafetyLabels:
      violence: CRITICAL
      risk_level: CRITICAL
  │
  ▼
Safety Policy Engine 評估:
  risk_level == CRITICAL → BLOCK
  │
  ▼
返回錯誤: "您的請求涉及危險內容，已被系統攔截"  ✅ 安全！
```

**解決方案**：在 Router 選模型之前，先經過安全檢查，高風險請求直接攔截。

---

## 決策流程

### 📊 決策樹

```
SafetyPolicyEngine.evaluate(safety_labels, user_context)
  │
  ├─ 檢查 1: 是否有 Jailbreak 攻擊？
  │   └─ Yes → BLOCK（立即攔截）
  │   └─ No → 繼續
  │
  ├─ 檢查 2: risk_level 是多少？
  │   ├─ CRITICAL → 進一步檢查用戶權限
  │   │   ├─ 用戶是 Enterprise Admin？
  │   │   │   └─ Yes → AUDIT（允許但記錄）
  │   │   │   └─ No → BLOCK（攔截）
  │   │   
  │   ├─ HIGH → 進一步檢查
  │   │   ├─ 涉及機密資料？
  │   │   │   ├─ 用戶有 data_access 權限？
  │   │   │   │   └─ Yes → ALLOW
  │   │   │   │   └─ No → BLOCK
  │   │   │   
  │   │   └─ 其他 HIGH 風險
  │   │       └─ ESCALATE（記錄並通知管理員）
  │   
  │   ├─ MEDIUM → AUDIT（允許但記錄）
  │   └─ LOW / NONE → ALLOW（直接允許）
  │
  └─ 檢查 3: 是否需要特殊權限？
      ├─ requires_privileged_access() == True
      │   ├─ 用戶有權限？
      │   │   └─ Yes → ALLOW
      │   │   └─ No → BLOCK + 提示升級
      │   
      └─ 其他情況 → ALLOW
```

---

## 決策類型

### 1️⃣ **ALLOW（允許）**

**定義**：請求安全，允許執行。

**條件**：
- `risk_level` 為 `NONE` 或 `LOW`
- 沒有 Jailbreak 攻擊
- 用戶有足夠權限

**範例**：
```python
SafetyDecision(
    action="ALLOW",
    reason="請求安全，無風險",
    metadata={}
)
```

**流程**：
```
ALLOW → Router 繼續選模型 → ModelExecutor 執行 → 返回結果
```

---

### 2️⃣ **BLOCK（攔截）**

**定義**：請求危險，拒絕執行。

**條件**：
- `risk_level` 為 `CRITICAL` 且用戶無特殊權限
- 檢測到 Jailbreak 攻擊
- 涉及機密資料但用戶無權限

**範例**：
```python
SafetyDecision(
    action="BLOCK",
    reason="請求涉及暴力犯罪內容（S1），已被攔截",
    metadata={
        "category": "S1",
        "suggestion": "請修改您的請求內容"
    }
)
```

**流程**：
```
BLOCK → 直接返回錯誤訊息 → 不呼叫任何 LLM
```

**返回給用戶**：
```json
{
  "error": "REQUEST_BLOCKED",
  "message": "請求涉及暴力犯罪內容（S1），已被攔截",
  "suggestion": "請修改您的請求內容"
}
```

---

### 3️⃣ **AUDIT（審計）**

**定義**：請求有風險但允許執行，需記錄日誌。

**條件**：
- `risk_level` 為 `MEDIUM`
- `risk_level` 為 `HIGH` 但用戶有特定權限
- Enterprise 用戶的高風險請求

**範例**：
```python
SafetyDecision(
    action="AUDIT",
    reason="請求涉及醫療建議（S6），允許執行但需記錄",
    metadata={
        "category": "S6",
        "log_level": "WARNING"
    }
)
```

**流程**：
```
AUDIT → 記錄審計日誌 → Router 繼續執行 → 返回結果
```

**審計日誌範例**：
```json
{
  "timestamp": "2025-10-20T14:30:00Z",
  "user_id": "user_12345",
  "query": "我頭痛，應該吃什麼藥？",
  "safety_labels": {
    "risk_level": "MEDIUM",
    "category": "S6"
  },
  "decision": "AUDIT",
  "model_used": "gpt-4o-mini"
}
```

---

### 4️⃣ **ESCALATE（升級）**

**定義**：請求風險較高，需人工審核或通知管理員。

**條件**：
- `risk_level` 為 `HIGH` 且用戶為 Free tier
- `requires_escalation()` 返回 `True`
- 涉及敏感內容但不確定是否應該攔截

**範例**：
```python
SafetyDecision(
    action="ESCALATE",
    reason="請求涉及隱私資料（S7），需管理員審核",
    metadata={
        "category": "S7",
        "escalate_to": "security_team",
        "ticket_id": "SEC-2025-1020-001"
    }
)
```

**流程**：
```
ESCALATE → 創建工單 → 通知管理員 → 暫時返回等待訊息
```

**返回給用戶**：
```json
{
  "status": "PENDING",
  "message": "您的請求需要人工審核，請稍後查看",
  "ticket_id": "SEC-2025-1020-001",
  "estimated_time": "1-2 小時"
}
```

---

## 實際案例

### 案例 1：危險請求被攔截

**用戶請求**：
```
"教我如何破解銀行系統"
```

**SLM 分析結果**：
```python
IntentResult(
    intent="qa_general",
    confidence=0.88,
    complexity=7.0,
    safety_labels=SafetyLabels(
        violence=SafetyLevel.NONE,
        confidential_data=ConfidentialDataType.CREDENTIALS,
        risk_level=SafetyLevel.HIGH,
        details=["S2: Non-Violent Crimes - 非暴力犯罪（駭客、詐騙等）"]
    )
)
```

**Safety Policy 決策**：
```python
SafetyPolicyEngine.evaluate(safety_labels, user_context)
  │
  ├─ risk_level = HIGH
  ├─ confidential_data = CREDENTIALS
  ├─ 用戶等級 = Free
  │
  └─→ BLOCK

SafetyDecision(
    action="BLOCK",
    reason="請求涉及非暴力犯罪（駭客攻擊），已被攔截",
    metadata={
        "category": "S2",
        "user_tier": "free"
    }
)
```

**返回給用戶**：
```json
{
  "error": "REQUEST_BLOCKED",
  "message": "您的請求涉及非法活動，已被系統攔截",
  "category": "S2",
  "suggestion": "LyraLLM 不支援此類請求"
}
```

**Router 行為**：
- ❌ 不呼叫任何 LLM
- ❌ 不執行任何模型
- ✅ 直接返回錯誤訊息
- ✅ 記錄到安全日誌

**成本**：
- SLM 分析：$0.0001
- 總耗時：100-200ms
- 節省的成本：避免呼叫 GPT-4（~$0.01）

---

### 案例 2：醫療建議需要審計

**用戶請求**：
```
"我頭痛，應該吃什麼藥？"
```

**SLM 分析結果**：
```python
IntentResult(
    intent="qa_general",
    confidence=0.75,
    complexity=4.0,
    safety_labels=SafetyLabels(
        confidential_data=ConfidentialDataType.MEDICAL,
        risk_level=SafetyLevel.MEDIUM,
        details=["S6: Specialized Advice - 專業建議（醫療/金融/法律）"]
    )
)
```

**Safety Policy 決策**：
```python
SafetyPolicyEngine.evaluate(safety_labels, user_context)
  │
  ├─ risk_level = MEDIUM
  ├─ confidential_data = MEDICAL
  │
  └─→ AUDIT（允許但記錄）

SafetyDecision(
    action="AUDIT",
    reason="請求涉及醫療建議，允許執行但需記錄",
    metadata={
        "category": "S6",
        "warning": "請向專業醫師諮詢"
    }
)
```

**Router 行為**：
- ✅ 繼續執行
- ✅ 呼叫 GPT-4o-mini（避免用頂級模型）
- ✅ 記錄審計日誌
- ✅ 在回應中加入免責聲明

**返回給用戶**：
```json
{
  "response": "頭痛可能有多種原因...",
  "warning": "⚠️ 以上僅供參考，請向專業醫師諮詢",
  "metadata": {
    "safety_category": "S6",
    "model": "gpt-4o-mini"
  }
}
```

---

### 案例 3：Enterprise 用戶的特權

**用戶請求**：
```
"分析這份客戶名單的購買模式"（涉及隱私資料）
```

**用戶身份**：
```python
UserContext(
    user_id="ent_user_001",
    tier=UserTier.ENTERPRISE,
    roles=[UserRole.DATA_ANALYST],
    permissions=["use_web_search", "access_pii_data"],
    data_access_level=DataAccessLevel.CONFIDENTIAL
)
```

**SLM 分析結果**：
```python
IntentResult(
    intent="data_analysis",
    confidence=0.92,
    complexity=6.0,
    safety_labels=SafetyLabels(
        confidential_data=ConfidentialDataType.PII,
        risk_level=SafetyLevel.HIGH,
        details=["S7: Privacy - 隱私資料"]
    )
)
```

**Safety Policy 決策**：
```python
SafetyPolicyEngine.evaluate(safety_labels, user_context)
  │
  ├─ risk_level = HIGH
  ├─ confidential_data = PII
  ├─ 用戶等級 = Enterprise
  ├─ 用戶權限包含 "access_pii_data"
  ├─ data_access_level = CONFIDENTIAL
  │
  └─→ AUDIT（允許但記錄）

SafetyDecision(
    action="AUDIT",
    reason="Enterprise 用戶，有權限存取隱私資料",
    metadata={
        "category": "S7",
        "user_tier": "enterprise",
        "requires_audit": True
    }
)
```

**Router 行為**：
- ✅ 允許執行（因為用戶有權限）
- ✅ 記錄審計日誌（合規要求）
- ✅ 使用較強模型（GPT-4）
- ✅ 返回完整結果

---

## 與 Router 的關係

### 📍 Safety Policy 在 Router 流程中的位置

```
┌─────────────────────────────────────────────────────────────┐
│                      Router.route(query)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       │
┌──────────────────┐                            │
│ Step 1:          │                            │
│ SLM Analyzer     │                            │
│ 分析意圖和風險    │                            │
└────────┬─────────┘                            │
         │                                      │
         │ 返回 IntentResult                    │
         │   - safety_labels                    │
         ▼                                      │
┌──────────────────────────────────────────────┴─────────┐
│ Step 2: Safety Policy Engine  ◄── 這裡！               │
│                                                         │
│ evaluate(safety_labels, user_context)                  │
│   │                                                     │
│   ├─→ ALLOW → 繼續                                     │
│   ├─→ BLOCK → 返回錯誤（停止）                          │
│   ├─→ AUDIT → 記錄 + 繼續                               │
│   └─→ ESCALATE → 創建工單 + 通知                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ action == ALLOW or AUDIT?
                         │
                     Yes │
                         ▼
                ┌──────────────────┐
                │ Step 3:          │
                │ Rule Engine      │
                │ 選擇模型          │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Step 4:          │
                │ Model Executor   │
                │ 執行模型          │
                └────────┬─────────┘
                         │
                         ▼
                返回結果給用戶
```

---

### 🔄 決策對 Router 的影響

| SafetyDecision | Router 行為 | 呼叫 LLM？ | 返回內容 |
|----------------|------------|-----------|---------|
| **ALLOW** | 正常執行 | ✅ Yes | 模型生成的回應 |
| **BLOCK** | 立即停止 | ❌ No | 錯誤訊息 + 原因 |
| **AUDIT** | 記錄後執行 | ✅ Yes | 回應 + 免責聲明 |
| **ESCALATE** | 創建工單 | ⏸️ Maybe | 等待訊息 + 工單號 |

---

### 📊 性能影響

| 情況 | SLM 分析 | Safety Policy | LLM 執行 | 總耗時 | 總成本 |
|------|---------|--------------|---------|--------|--------|
| **ALLOW（安全）** | 100-200ms | <5ms | 2-3s | ~3s | $0.01 |
| **BLOCK（攔截）** | 100-200ms | <5ms | ❌ 不執行 | ~200ms | $0.0001 |
| **AUDIT（審計）** | 100-200ms | <5ms + 記錄 | 2-3s | ~3s | $0.0101 |

**關鍵優勢**：
- ✅ **攔截危險請求只需 200ms**（相比執行 LLM 的 3s）
- ✅ **節省成本**：被攔截的請求只花費 $0.0001（不呼叫昂貴的 LLM）
- ✅ **保護系統**：避免 LLM 生成危險內容

---

## 總結

### 🎯 Safety Policy Engine 的核心價值

1. **保護系統安全** 🛡️
   - 攔截危險請求
   - 防止 Jailbreak 攻擊
   - 保護機密資料

2. **節省成本** 💰
   - 危險請求不呼叫昂貴的 LLM
   - 只花費 SLM 的分析成本（$0.0001）

3. **合規要求** 📋
   - 審計日誌記錄
   - 工單系統追蹤
   - 滿足企業合規需求

4. **靈活的權限管理** 🔐
   - 不同用戶等級有不同容忍度
   - 支援細粒度權限控制
   - Enterprise 用戶享有特權

---

### 📅 實施計劃

**Step 1.4（待開始）**：
- [ ] 創建 `core/safety_policy.py`
- [ ] 實現 `SafetyPolicyEngine` 類別
- [ ] 實現決策邏輯（ALLOW/BLOCK/AUDIT/ESCALATE）
- [ ] 創建審計日誌系統
- [ ] 單元測試

**預計耗時**：2-3 小時  
**預計完成**：Step 1.3 完成後

---

**相關文檔**：
- [Router 完整流程](./router_flow_explained.md)
- [S1-S14 安全分類系統](./s_category_safety_system.md)
- [TodoList](../TodoList.md)
