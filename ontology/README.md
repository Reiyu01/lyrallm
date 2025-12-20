# 🏛️ LyraLLM Ontology System - 本體論安全架構

## 📋 目錄

- [概述](#概述)
- [架構設計](#架構設計)
- [核心組件](#核心組件)
- [與 Palantir AIP 的對比](#與-palantir-aip-的對比)
- [整合指南](#整合指南)
- [使用案例](#使用案例)
- [最佳實踐](#最佳實踐)

---

## 🎯 概述

LyraLLM Ontology System 是參考 **Palantir AIP** 設計的企業級安全框架，為 AI Gateway 提供：

### 核心特性

1. **📦 物件管理（Objects）** - 企業知識圖譜
   - 結構化的業務實體（文件、對話、使用者等）
   - 物件級安全標籤
   - 細粒度存取控制（RBAC + ABAC）

2. **🔐 策略引擎（Policy Engine）** - 自動化安全決策
   - 多層策略（Global → Organization → Team → User）
   - 條件式策略（if-then-else）
   - 策略繼承與衝突解決

3. **🔍 資料血緣（Data Lineage）** - 完整追蹤
   - 追蹤資料來源、轉換、使用
   - 審計追蹤（Audit Trail）
   - 合規報告生成

4. **🛡️ 護欄系統（Guardrails）** - 主動防護
   - 內容安全護欄
   - 成本控制護欄
   - 速率限制護欄
   - 合規性護欄

---

## 🏗️ 架構設計

### 整體架構圖

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LyraLLM Gateway                             │
│                         (FastAPI + Router)                           │
└─────────────┬───────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Ontology Security Layer                        │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │   Objects   │  │  Policies   │  │   Lineage   │  │Guardrails│ │
│  │             │  │             │  │             │  │          │ │
│  │ • Document  │  │ • PolicyEng │  │ • Tracker   │  │ • Content│ │
│  │ • Conversat │  │ • Rules     │  │ • Access    │  │ • Cost   │ │
│  │ • User      │  │ • Condition │  │ • Transform │  │ • Rate   │ │
│  │ • Model     │  │ • Decision  │  │ • Audit     │  │ • Compli │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │
└─────────────┬───────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage & Analytics Layer                      │
│                                                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────┐ │
│  │Elasticsearch│  │ PostgreSQL │  │   Redis    │  │  S3/Blob    │ │
│  │            │  │            │  │            │  │             │ │
│  │ • Objects  │  │ • Audit Log│  │ • Cache    │  │ • Documents │ │
│  │ • Lineage  │  │ • Events   │  │ • Session  │  │ • Backups   │ │
│  └────────────┘  └────────────┘  └────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 資料流程

```
1. 使用者請求 → 2. 護欄檢查 → 3. 策略評估 → 4. 存取控制 → 5. 執行處理 → 6. 血緣追蹤
     ↓              ↓              ↓              ↓              ↓              ↓
   解析請求      內容安全       權限判斷       物件存取        AI 處理       審計記錄
   提取上下文    成本檢查       角色匹配       資料讀寫       模型調用       事件追蹤
   使用者識別    速率限制       策略決策       操作執行       結果生成       合規報告
```

---

## 📦 核心組件

### 1. Objects（物件系統）

#### **OntologyObject（基類）**
所有物件的基類，包含：
- 🆔 物件身份（object_id, object_type）
- 🔐 安全標籤（SecurityLabel）
- 🔑 存取控制（AccessControl）
- 🏷️ 標籤與分類（tags, categories）
- 📝 審計資訊（version, checksum）

#### **具體物件類型**

| 物件類型 | 用途 | 關鍵屬性 |
|---------|------|---------|
| `Document` | 文件資料 | content, embedding, retention_days |
| `Conversation` | AI 對話 | messages, routing_decision, total_cost |
| `Model` | AI 模型 | capabilities, cost, health_status |
| `User` | 使用者 | roles, permissions, quota |
| `Organization` | 組織 | subscription_tier, budget, compliance |

#### **SecurityLabel（安全標籤）**

```python
SecurityLabel(
    classification="CONFIDENTIAL",  # PUBLIC, INTERNAL, CONFIDENTIAL, SECRET
    categories={"FINANCIAL", "PII"},
    handling_caveats={"NO_EXPORT", "ENCRYPT_AT_REST"},
    expiry_date=datetime(2025, 12, 31)
)
```

#### **AccessControl（存取控制）**

支援多種存取控制模式：
- **RBAC** (Role-Based Access Control) - 基於角色
- **ABAC** (Attribute-Based Access Control) - 基於屬性
- **TBAC** (Time-Based Access Control) - 基於時間
- **Location-Based** - 基於地理位置

```python
AccessControl(
    owner_id="org_acme",
    allowed_roles=frozenset(["ADMIN", "CFO"]),
    denied_users=frozenset(["user_malicious"]),
    required_attributes={"clearance_level": "top_secret"},
    valid_from=datetime(2025, 1, 1),
    valid_until=datetime(2025, 12, 31),
    allowed_ip_ranges=["192.168.1.0/24"],
    allowed_countries=["US", "UK"]
)
```

---

### 2. Policies（策略引擎）

#### **PolicyEngine（策略引擎）**

負責評估和執行安全策略，支援：
- 多層策略（Global → Organization → Team → User → Resource）
- 策略繼承
- 條件式規則
- 衝突解決（Deny 優先原則）

#### **PolicyRule（策略規則）**

```python
PolicyRule(
    rule_id="rule_deny_public_pii",
    name="Deny Public Access to PII",
    description="Block public access to documents containing PII",
    conditions=[
        PolicyCondition(field="resource.categories", operator="contains", value="PII"),
        PolicyCondition(field="user.tier", operator="eq", value="free"),
    ],
    action=PolicyAction.DENY,
    priority=100,
    exceptions=[
        PolicyCondition(field="user.roles", operator="in", value=["DATA_PROTECTION_OFFICER"])
    ]
)
```

#### **PolicyDecision（策略決策）**

評估結果包含：
- `action`: ALLOW, DENY, REQUIRE_APPROVAL, REQUIRE_MFA
- `matched_rules`: 匹配的規則
- `reason`: 決策原因
- `evaluation_trace`: 評估追蹤

---

### 3. Lineage（資料血緣）

#### **LineageTracker（血緣追蹤器）**

追蹤資料的完整生命週期：
- **CREATE** - 資料建立
- **READ** - 資料讀取
- **UPDATE** - 資料更新
- **DELETE** - 資料刪除
- **TRANSFORM** - 資料轉換（AI 處理）
- **SHARE** - 資料分享
- **EXPORT** - 資料匯出

#### **血緣圖結構**

```
Root Object (Document)
    │
    ├─ Create Event (user_alice, 2025-01-15)
    │
    ├─ Access Event (user_bob, read, 2025-01-16)
    │
    ├─ Transform Event (gpt-4o, summarize, 2025-01-17)
    │   │
    │   └─ Output Object (Summary)
    │       │
    │       └─ Access Event (user_charlie, read, 2025-01-18)
    │
    └─ Export Event (user_admin, PDF, 2025-01-20)
```

#### **AccessEvent（存取事件）**

記錄每次資料存取：
```python
AccessEvent(
    user_id="user_bob",
    user_roles=["ANALYST"],
    resource_id="doc_123",
    resource_classification="CONFIDENTIAL",
    action="read",
    result="success",
    ip_address="192.168.1.100",
    fields_accessed=["content", "metadata"],
    policy_decisions=[...]
)
```

#### **TransformationEvent（轉換事件）**

記錄資料轉換：
```python
TransformationEvent(
    input_objects=["doc_123"],
    output_objects=["summary_456"],
    transformation_type="summarization",
    model_used="gpt-4o",
    confidence_score=0.95,
    execution_time_ms=1200,
    tokens_used=1500,
    cost_usd=0.15
)
```

---

### 4. Guardrails（護欄系統）

#### **GuardrailEngine（護欄引擎）**

主動防護機制，包含：
1. **ContentGuardrail** - 內容安全
2. **CostGuardrail** - 成本控制
3. **RateLimitGuardrail** - 速率限制
4. **ComplianceGuardrail** - 合規檢查（待實作）

#### **ContentGuardrail（內容護欄）**

```python
content_guardrail = ContentGuardrail()
content_guardrail.max_allowed_risk = "MEDIUM"
content_guardrail.blocked_keywords = {"password", "ssn", "credit_card"}
content_guardrail.pii_patterns = [r"\d{3}-\d{2}-\d{4}"]  # SSN pattern

violation = content_guardrail.check({
    "content": "My SSN is 123-45-6789",
    "safety_labels": {"risk_level": "HIGH"}
})
# Returns: GuardrailViolation(action=BLOCK, reason="PII detected")
```

#### **CostGuardrail（成本護欄）**

```python
cost_guardrail = CostGuardrail()
cost_guardrail.per_request_limit_usd = 1.0
cost_guardrail.daily_limit_usd = 50.0
cost_guardrail.monthly_limit_usd = 1000.0

violation = cost_guardrail.check({
    "user_id": "user_alice",
    "estimated_cost_usd": 2.5
})
# Returns: GuardrailViolation(action=REQUIRE_APPROVAL, reason="Cost exceeds limit")
```

#### **RateLimitGuardrail（速率護欄）**

```python
rate_limit = RateLimitGuardrail()
rate_limit.requests_per_minute = 60
rate_limit.requests_per_hour = 1000
rate_limit.tokens_per_minute = 100000

violation = rate_limit.check({
    "user_id": "user_alice",
    "estimated_tokens": 5000
})
# Returns: GuardrailViolation(action=THROTTLE, reason="Rate limit exceeded")
```

---

## 🆚 與 Palantir AIP 的對比

| 特性 | Palantir AIP | LyraLLM Ontology |
|-----|-------------|-----------------|
| **本體論物件** | ✅ Objects, Properties, Links | ✅ OntologyObject, Attributes, Relations |
| **物件級安全** | ✅ Object-Level Security | ✅ SecurityLabel + AccessControl |
| **策略引擎** | ✅ Policy Engine | ✅ PolicyEngine + Rules |
| **資料血緣** | ✅ Data Lineage | ✅ LineageTracker + Events |
| **護欄機制** | ✅ Guardrails | ✅ GuardrailEngine + Checks |
| **審計追蹤** | ✅ Audit Logs | ✅ AccessEvent + TransformationEvent |
| **角色存取控制** | ✅ RBAC | ✅ RBAC + ABAC + TBAC |
| **AI Actions** | ✅ Approved Actions | 🚧 待實作（Router + Tools） |
| **Human-in-the-Loop** | ✅ Approval Workflows | 🚧 待實作（需 Workflow Engine） |
| **UI/UX** | ✅ Foundry Platform | ❌ 後端 API Only |

### 優勢

- ✅ **開源** - 完全開放原始碼
- ✅ **可客製化** - 易於擴展和修改
- ✅ **輕量級** - 無需複雜基礎設施
- ✅ **Python 原生** - 與 LyraLLM 無縫整合
- ✅ **API 優先** - 易於整合到現有系統

### 差距

- ❌ 無圖形化介面
- ❌ 無 Workflow Engine
- ❌ 無進階分析功能
- ❌ 無多租戶隔離（需自行實作）

---

## 🔌 整合指南

### 步驟1: 初始化本體論系統

```python
from lyrallm.ontology import get_policy_engine, get_lineage_tracker, get_guardrail_engine

# 初始化全域實例
policy_engine = get_policy_engine()
lineage_tracker = get_lineage_tracker()
guardrail_engine = get_guardrail_engine()
```

### 步驟2: 整合到 FastAPI Middleware

```python
# lyrallm/api/middleware/ontology_middleware.py

from fastapi import Request
from lyrallm.ontology import get_guardrail_engine, get_policy_engine, get_lineage_tracker

async def ontology_middleware(request: Request, call_next):
    """本體論安全中介軟體"""
    
    # 1. 提取請求上下文
    user_id = request.headers.get("X-User-ID")
    user_roles = request.headers.get("X-User-Roles", "").split(",")
    
    # 2. 護欄檢查
    guardrail_engine = get_guardrail_engine()
    violations = guardrail_engine.check_all({
        "user_id": user_id,
        "content": await request.body(),
        "estimated_cost_usd": 0.1,  # 預估
    })
    
    if guardrail_engine.should_block(violations):
        return JSONResponse(
            status_code=403,
            content={"error": "Request blocked by guardrails", "violations": [v.to_dict() for v in violations]}
        )
    
    # 3. 策略評估
    policy_engine = get_policy_engine()
    decision = policy_engine.evaluate({
        "user": {"id": user_id, "roles": user_roles},
        "action": "process_request"
    })
    
    if decision.is_denied():
        return JSONResponse(
            status_code=403,
            content={"error": "Policy denied", "reason": decision.reason}
        )
    
    # 4. 執行請求
    response = await call_next(request)
    
    # 5. 資料血緣追蹤
    lineage_tracker = get_lineage_tracker()
    lineage_tracker.track_access(AccessEvent(
        user_id=user_id,
        action="process_request",
        result="success"
    ))
    
    return response
```

### 步驟3: 整合到 ModelExecutor

```python
# lyrallm/core/model_executor.py

class ModelExecutor:
    async def generate(self, model_name: str, messages: List[Any], **kwargs):
        # ... existing code ...
        
        # 1. 建立對話物件
        from lyrallm.ontology import Conversation, SecurityLabel
        conversation = Conversation(
            user_id=kwargs.get("user_id"),
            messages=messages,
            security_label=SecurityLabel(classification="INTERNAL")
        )
        
        # 2. 護欄檢查
        from lyrallm.ontology import get_guardrail_engine
        guardrail_engine = get_guardrail_engine()
        violations = guardrail_engine.check_all({
            "user_id": conversation.user_id,
            "content": messages[-1].get("content"),
            "estimated_cost_usd": self._estimate_cost(model_name, messages),
        })
        
        if guardrail_engine.should_block(violations):
            raise GuardrailViolationError(violations)
        
        # 3. 執行生成
        result = await self._generate_real_response(...)
        
        # 4. 追蹤轉換
        from lyrallm.ontology import get_lineage_tracker, TransformationEvent
        tracker = get_lineage_tracker()
        tracker.track_transformation(TransformationEvent(
            input_objects=[conversation.object_id],
            output_objects=[conversation.object_id],
            transformation_type="chat_completion",
            model_used=model_name,
            tokens_used=result["usage"]["total_tokens"],
            cost_usd=result["cost_usd"]
        ))
        
        return result
```

### 步驟4: 配置策略

```yaml
# config/security_policies.yaml

policies:
  - policy_id: "pol_confidential_data"
    name: "Confidential Data Access Policy"
    scope: "organization"
    rules:
      - rule_id: "rule_deny_free_users"
        name: "Deny Free Users from Confidential Data"
        conditions:
          - field: "resource.classification"
            operator: "eq"
            value: "CONFIDENTIAL"
          - field: "user.tier"
            operator: "eq"
            value: "free"
        action: "deny"
        priority: 100
      
      - rule_id: "rule_require_mfa"
        name: "Require MFA for Secret Data"
        conditions:
          - field: "resource.classification"
            operator: "eq"
            value: "SECRET"
        action: "require_mfa"
        priority: 90
```

---

## 💼 使用案例

### 案例1: 金融機構資料保護

**需求**: 
- 客戶 PII 必須加密
- 只有授權人員可存取
- 所有存取必須審計

**實作**:
```python
# 1. 建立客戶文件
customer_doc = Document(
    title="Customer Profile - John Doe",
    content="SSN: 123-45-6789, Account: 9876543210",
    security_label=SecurityLabel(
        classification="CONFIDENTIAL",
        categories={"PII", "FINANCIAL"},
        handling_caveats={"ENCRYPT_AT_REST", "NO_EXPORT"}
    ),
    access_control=AccessControl(
        owner_id="org_bank",
        allowed_roles=frozenset(["RELATIONSHIP_MANAGER", "COMPLIANCE_OFFICER"]),
        required_attributes={"department": "wealth_management"}
    )
)

# 2. 策略檢查
policy_engine.register_policy(SecurityPolicy(
    policy_id="pol_pii_protection",
    rules=[
        PolicyRule(
            conditions=[
                PolicyCondition("resource.categories", "contains", "PII")
            ],
            action=PolicyAction.REQUIRE_MFA
        )
    ]
))

# 3. 審計追蹤
lineage_tracker.track_access(AccessEvent(
    user_id="user_rm_alice",
    resource_id=customer_doc.object_id,
    action="read",
    fields_accessed=["ssn", "account_number"]
))
```

### 案例2: 醫療資料合規（HIPAA）

**需求**:
- PHI (Protected Health Information) 必須嚴格控制
- 符合 HIPAA 合規要求
- 記錄所有存取以供審計

**實作**:
```python
# 1. 醫療記錄
medical_record = Document(
    title="Patient Medical Record",
    content="Diagnosis: ..., Treatment: ...",
    security_label=SecurityLabel(
        classification="CONFIDENTIAL",
        categories={"MEDICAL", "PHI"},
        handling_caveats={"HIPAA_PROTECTED", "ENCRYPT_AT_REST"}
    ),
    access_control=AccessControl(
        allowed_roles=frozenset(["DOCTOR", "NURSE", "MEDICAL_ADMIN"]),
        allowed_organizations=frozenset(["hospital_123"]),
        valid_from=datetime.now(),
        valid_until=datetime.now() + timedelta(days=365)
    )
)

# 2. HIPAA 護欄
class HIPAAGuardrail(Guardrail):
    def check(self, context):
        # 檢查是否符合 HIPAA 最小必要原則
        if context.get("fields_requested") > context.get("fields_needed"):
            return GuardrailViolation(
                action=GuardrailAction.BLOCK,
                reason="Violates HIPAA minimum necessary principle"
            )
```

---

## 🎯 最佳實踐

### 1. 安全標籤設計

```python
# ✅ 良好的做法
security_label = SecurityLabel(
    classification="CONFIDENTIAL",  # 明確分類
    categories={"FINANCIAL", "PII"},  # 具體類別
    handling_caveats={"ENCRYPT_AT_REST", "NO_CROSS_BORDER"}  # 處理要求
)

# ❌ 避免
security_label = SecurityLabel(classification="SENSITIVE")  # 太模糊
```

### 2. 存取控制原則

```python
# ✅ 最小權限原則
access_control = AccessControl(
    allowed_roles=frozenset(["DATA_ANALYST"]),  # 只給需要的角色
    denied_users=frozenset(["user_suspended"]),  # 明確拒絕
    valid_until=datetime.now() + timedelta(days=30)  # 時間限制
)

# ❌ 避免過度寬鬆
access_control = AccessControl(
    allowed_roles=frozenset(["*"]),  # 允許所有人
)
```

### 3. 策略優先級設計

```python
# 高優先級 (100+): 安全關鍵規則
PolicyRule(priority=100, action=PolicyAction.DENY)

# 中優先級 (50-99): 一般業務規則
PolicyRule(priority=70, action=PolicyAction.REQUIRE_APPROVAL)

# 低優先級 (0-49): 預設規則
PolicyRule(priority=10, action=PolicyAction.ALLOW)
```

### 4. 審計追蹤

```python
# ✅ 詳細記錄
access_event = AccessEvent(
    user_id="user_alice",
    user_roles=["ANALYST"],
    resource_id="doc_123",
    action="read",
    fields_accessed=["name", "email"],  # 具體欄位
    ip_address="192.168.1.100",
    session_id="sess_xyz",
    request_id="req_abc"
)

# ❌ 避免資訊不足
access_event = AccessEvent(
    user_id="user_alice",
    action="read"
)
```

---

## 📚 延伸閱讀

- [Palantir AIP 官方文檔](https://www.palantir.com/platforms/aip/)
- [RBAC vs ABAC](https://www.okta.com/identity-101/rbac-vs-abac/)
- [Data Lineage Best Practices](https://www.snowflake.com/guides/data-lineage/)
- [HIPAA Compliance Guide](https://www.hhs.gov/hipaa/index.html)

---

## 🤝 貢獻

歡迎貢獻到 LyraLLM Ontology System！

- 回報 Bug: [GitHub Issues](https://github.com/Reiyu01/lyrallm/issues)
- 提交功能: [Pull Requests](https://github.com/Reiyu01/lyrallm/pulls)
- 討論想法: [Discussions](https://github.com/Reiyu01/lyrallm/discussions)

---

**LyraLLM Ontology - 企業級 AI 安全基礎設施** 🏛️✨
