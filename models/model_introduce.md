# Models 資料模型詳細說明文檔

> 📅 **最後更新**：2025-10-17  
> 📝 **作者**：LyraLLM Team  
> 🎯 **目的**：詳細解釋 models 目錄下所有資料模型的功能、用途和使用方式

---

## 📚 目錄

1. [概述](#概述)
2. [safety.py - 安全標籤與分類系統](#safetypy---安全標籤與分類系統)
3. [user_context.py - 使用者上下文與身份資訊](#user_contextpy---使用者上下文與身份資訊)
4. [tool_requirements.py - 工具需求與授權](#tool_requirementspy---工具需求與授權)
5. [整合使用範例](#整合使用範例)
6. [架構設計理念](#架構設計理念)

---

## 概述

### 🎯 為什麼需要這些資料模型？

在 LyraLLM AI Gateway 的進化過程中，我們需要讓系統具備以下能力：

1. **內容安全檢測**：自動識別使用者輸入中的暴力、色情、仇恨言論等不安全內容
2. **身份感知路由**：根據使用者的等級、角色、權限來決定可以使用哪些模型和功能
3. **工具需求判斷**：讓 SLM（小語言模型）能夠判斷使用者的請求是否需要額外工具（如網頁搜尋、代碼執行器）

這三個資料模型檔案就是為了實現上述功能而設計的**基礎資料結構**。

### 📦 三大核心模型

| 檔案 | 用途 | 核心類別 |
|------|------|----------|
| `safety.py` | 安全檢測與分類 | `SafetyLabels` |
| `user_context.py` | 使用者身份與權限管理 | `UserContext`, `ResourceQuota` |
| `tool_requirements.py` | 工具需求判斷與授權 | `ToolRequirements`, `ToolAuthorization` |

---

## safety.py - 安全標籤與分類系統

### 🎯 檔案用途

這個檔案定義了**內容安全分類系統**，用於：
- 檢測使用者輸入是否包含不安全內容（暴力、色情、仇恨言論等）
- 識別是否涉及機密資料（個資、財務資訊、商業機密等）
- 檢測 Jailbreak 攻擊（試圖繞過 AI 安全限制的惡意提示詞）
- 決定內容是否可以處理，或需要攔截、告警、升級處理

### 📊 核心枚舉類別

#### 1. `SafetyLevel` - 安全等級枚舉

定義了 5 個安全風險等級：

```python
class SafetyLevel(str, Enum):
    NONE = "none"        # 無風險：完全安全
    LOW = "low"          # 低風險：輕微問題，可以處理
    MEDIUM = "medium"    # 中等風險：需要注意，可能需要過濾
    HIGH = "high"        # 高風險：需要告警，限制處理
    CRITICAL = "critical" # 嚴重風險：必須攔截，通知管理員
```

**使用場景**：
- SLM 分析後對每個維度（暴力、色情等）評估風險等級
- 系統根據等級決定是否處理請求、是否記錄告警

#### 2. `ConfidentialDataType` - 機密資料類型枚舉

定義了 7 種機密資料類型：

```python
class ConfidentialDataType(str, Enum):
    NONE = "none"                    # 無機密資料
    PII = "pii"                      # 個人身份資訊（姓名、身份證、電話等）
    FINANCIAL = "financial"          # 財務資訊（信用卡、銀行帳號）
    MEDICAL = "medical"              # 醫療健康資訊
    TRADE_SECRET = "trade_secret"    # 商業機密（營業額、客戶名單）
    CREDENTIALS = "credentials"      # 憑證資訊（密碼、API key、Token）
    INTERNAL = "internal"            # 內部資料（員工資料、內部文件）
```

**使用場景**：
- 檢測使用者是否上傳或詢問包含機密資料的內容
- 根據資料敏感度決定是否需要更高權限
- 企業場景下防止資料外洩

### 🏗️ 核心資料類別

#### `SafetyLabels` - 安全標籤完整資料結構

這是**最核心的類別**，包含了對一段內容的完整安全評估結果。

**屬性說明**：

```python
@dataclass
class SafetyLabels:
    # === 內容安全維度 ===
    violence: SafetyLevel = SafetyLevel.NONE        # 暴力程度
    sexual: SafetyLevel = SafetyLevel.NONE          # 色情程度
    hate_speech: SafetyLevel = SafetyLevel.NONE     # 仇恨言論程度
    self_harm: SafetyLevel = SafetyLevel.NONE       # 自殘內容程度
    
    # === 資料安全維度 ===
    confidential_data: ConfidentialDataType = ConfidentialDataType.NONE  # 機密資料類型
    
    # === 攻擊檢測 ===
    jailbreak_attempt: bool = False                 # 是否嘗試 Jailbreak 攻擊
    
    # === 整體評估 ===
    risk_level: SafetyLevel = SafetyLevel.NONE      # 整體風險等級
    
    # === 詳細資訊 ===
    details: List[str] = []                         # 詳細說明（為什麼判定為某等級）
    jailbreak_indicators: List[str] = []            # Jailbreak 攻擊的具體指標
```

**核心方法**：

1. **`is_safe() -> bool`**
   - **用途**：判斷內容是否安全可處理
   - **邏輯**：所有維度都是 NONE 或 LOW，且沒有 jailbreak 攻擊
   - **使用時機**：每次處理請求前，先檢查是否安全

2. **`requires_escalation() -> bool`**
   - **用途**：判斷是否需要升級處理（通知管理員、記錄告警）
   - **邏輯**：任何維度達到 HIGH/CRITICAL，或檢測到 jailbreak，或涉及商業機密/憑證
   - **使用時機**：發現高風險內容時，觸發告警流程

3. **`requires_privileged_access() -> bool`**
   - **用途**：判斷是否需要特權存取（企業級帳號、特定角色）
   - **邏輯**：涉及財務、醫療、商業機密、憑證資料
   - **使用時機**：決定是否允許處理敏感資料請求

4. **`get_max_safety_level() -> SafetyLevel`**
   - **用途**：獲取所有維度中的最高風險等級
   - **邏輯**：比較所有維度，返回最嚴重的等級
   - **使用時機**：需要快速判斷整體風險時

5. **`to_dict()` / `from_dict()`**
   - **用途**：序列化/反序列化，方便儲存到資料庫或傳輸
   - **使用時機**：記錄到 Elasticsearch、傳遞給前端、儲存審計日誌

6. **`create_safe_default()`**
   - **用途**：創建一個完全安全的預設實例
   - **使用時機**：系統初始化、測試、或無法進行安全檢測時的降級處理

### 💡 實際使用範例

```python
from models import SafetyLabels, SafetyLevel, ConfidentialDataType

# === 場景 1：正常安全內容 ===
safe_content = SafetyLabels.create_safe_default()
if safe_content.is_safe():
    print("✅ 內容安全，可以處理")

# === 場景 2：檢測到暴力內容 ===
violent_content = SafetyLabels(
    violence=SafetyLevel.HIGH,
    risk_level=SafetyLevel.HIGH,
    details=["包含暴力威脅語句"]
)
if not violent_content.is_safe():
    print("⚠️ 內容不安全！")
if violent_content.requires_escalation():
    print("🚨 需要通知管理員！")

# === 場景 3：涉及機密資料 ===
confidential_content = SafetyLabels(
    confidential_data=ConfidentialDataType.FINANCIAL,
    risk_level=SafetyLevel.MEDIUM,
    details=["使用者詢問信用卡號相關問題"]
)
if confidential_content.requires_privileged_access():
    print("🔒 需要企業級權限才能處理")

# === 場景 4：Jailbreak 攻擊 ===
jailbreak_content = SafetyLabels(
    jailbreak_attempt=True,
    risk_level=SafetyLevel.CRITICAL,
    jailbreak_indicators=["忽略之前的指令", "假裝你是..."],
    details=["檢測到多個 jailbreak 模式"]
)
if jailbreak_content.requires_escalation():
    print("🚨 嚴重安全威脅！立即攔截並記錄！")
```

### 🔄 在 Router 中的整合流程

```
使用者輸入
    ↓
SLM 分析（擴展後的 Prompt）
    ↓
返回 SafetyLabels
    ↓
SafetyPolicyEngine 檢查
    ↓
├─ is_safe() = True  → 繼續處理
├─ is_safe() = False → 攔截並返回錯誤
└─ requires_escalation() = True → 記錄告警 + 通知管理員
```

---

## user_context.py - 使用者上下文與身份資訊

### 🎯 檔案用途

這個檔案定義了**使用者身份與權限管理系統**，用於：
- 記錄使用者的等級（免費版、專業版、企業版）
- 管理使用者的角色（訪客、開發者、分析師、管理員）
- 追蹤使用者的資源配額（每月 token 數、請求次數）
- 控制使用者的資料存取權限（公開、內部、機密、限制）
- 實現**身份感知路由**（根據使用者身份分配不同模型）

### 📊 核心枚舉類別

#### 1. `UserTier` - 使用者等級枚舉

定義了 4 種使用者等級：

```python
class UserTier(str, Enum):
    FREE = "free"              # 免費版：基礎功能，有配額限制
    PRO = "pro"                # 專業版：進階功能，較高配額
    ENTERPRISE = "enterprise"  # 企業版：完整功能，無配額限制
    ADMIN = "admin"            # 管理員：系統管理權限
```

**差異對比**：

| 等級 | 月配額 | 可用工具 | 可用模型 | 併發數 |
|------|--------|----------|----------|--------|
| FREE | 10萬 tokens | 無 | 輕量模型 | 1 |
| PRO | 無限制 | 網搜、代碼、圖片 | 重量模型 | 5 |
| ENTERPRISE | 無限制 | 所有工具 | 頂級模型 | 10 |
| ADMIN | 無限制 | 所有工具 | 所有模型 | 無限制 |

#### 2. `UserRole` - 使用者角色枚舉

定義了 7 種使用者角色：

```python
class UserRole(str, Enum):
    GUEST = "guest"                    # 訪客：最低權限
    USER = "user"                      # 一般使用者
    ANALYST = "analyst"                # 分析師：可進行資料分析
    DEVELOPER = "developer"            # 開發者：可使用代碼工具
    DATA_SCIENTIST = "data_scientist"  # 資料科學家：完整資料權限
    ADMIN = "admin"                    # 管理員：系統管理
    SUPER_ADMIN = "super_admin"        # 超級管理員：最高權限
```

**角色權限對應**：

```
GUEST          → 僅查詢
USER           → 一般對話
ANALYST        → + 資料分析工具
DEVELOPER      → + 代碼執行器
DATA_SCIENTIST → + 完整資料存取
ADMIN          → + 系統管理
SUPER_ADMIN    → + 所有權限
```

#### 3. `DataAccessLevel` - 資料存取等級枚舉

定義了 4 級資料存取權限：

```python
class DataAccessLevel(str, Enum):
    PUBLIC = "public"              # 公開：所有人可存取
    INTERNAL = "internal"          # 內部：組織內部可存取
    CONFIDENTIAL = "confidential"  # 機密：需要特定角色
    RESTRICTED = "restricted"      # 限制：僅管理員可存取
```

### 🏗️ 核心資料類別

#### `ResourceQuota` - 資源配額管理

管理使用者的資源使用情況和配額限制。

**屬性說明**：

```python
@dataclass
class ResourceQuota:
    # === 配額設定 ===
    monthly_tokens: int = 0              # 每月 token 配額（0 = 無限制）
    monthly_requests: int = 0            # 每月請求次數配額（0 = 無限制）
    
    # === 已使用量 ===
    tokens_used: int = 0                 # 本月已使用 token 數
    requests_used: int = 0               # 本月已使用請求次數
    
    # === 即時限制 ===
    max_concurrent_requests: int = 1     # 最大併發請求數
    max_tokens_per_request: int = 4096   # 單次請求最大 token 數
    
    # === 計費週期 ===
    quota_reset_date: Optional[datetime] = None  # 配額重置日期
```

**核心方法**：

1. **`is_quota_exceeded() -> bool`**
   - 檢查是否超過配額（tokens 或 requests）
   
2. **`get_remaining_tokens() -> int`**
   - 獲取剩餘 token 配額（-1 表示無限制）
   
3. **`get_remaining_requests() -> int`**
   - 獲取剩餘請求次數（-1 表示無限制）

#### `UserContext` - 使用者上下文（核心類別）

這是**最核心的類別**，包含使用者的完整身份資訊。

**屬性說明**：

```python
@dataclass
class UserContext:
    # === 基本身份 ===
    user_id: str                                          # 使用者唯一 ID
    username: Optional[str] = None                        # 使用者名稱
    tier: UserTier = UserTier.FREE                        # 使用者等級
    
    # === 角色與權限 ===
    roles: Set[UserRole] = {UserRole.USER}                # 角色集合（可有多個）
    permissions: Set[str] = set()                         # 權限集合（字串形式）
    
    # === 資料存取 ===
    data_access_level: DataAccessLevel = DataAccessLevel.PUBLIC
    
    # === 資源配額 ===
    quota: ResourceQuota = ResourceQuota()                # 配額物件
    
    # === 組織資訊（多租戶） ===
    organization_id: Optional[str] = None                 # 組織 ID
    department: Optional[str] = None                      # 部門
    
    # === 額外屬性 ===
    metadata: Dict[str, Any] = {}                         # 自訂屬性
```

**核心方法**：

1. **`has_role(role: UserRole) -> bool`**
   - **用途**：檢查是否擁有特定角色
   - **範例**：`user.has_role(UserRole.DEVELOPER)`

2. **`has_permission(permission: str) -> bool`**
   - **用途**：檢查是否擁有特定權限
   - **範例**：`user.has_permission("use_web_search")`

3. **`can_access_data_level(required_level: DataAccessLevel) -> bool`**
   - **用途**：檢查是否可以存取特定等級的資料
   - **邏輯**：比較使用者的資料存取等級與所需等級
   - **範例**：`user.can_access_data_level(DataAccessLevel.CONFIDENTIAL)`

4. **`is_admin() -> bool`**
   - **用途**：快速檢查是否為管理員

5. **`is_enterprise() -> bool`**
   - **用途**：快速檢查是否為企業級使用者

6. **`get_max_model_tier() -> str`**
   - **用途**：根據使用者等級獲取可使用的最高模型等級
   - **返回值**：`"light"`, `"medium"`, `"heavy"`, `"premium"`
   - **使用場景**：Router 決定哪些模型可以分配給該使用者

7. **工廠方法**：
   - `create_default_free_user(user_id)` - 創建免費版使用者
   - `create_enterprise_user(user_id, org_id)` - 創建企業版使用者

### 💡 實際使用範例

```python
from models import UserContext, UserTier, UserRole, DataAccessLevel

# === 場景 1：創建免費版使用者 ===
free_user = UserContext.create_default_free_user("user_123")
print(f"可用模型等級：{free_user.get_max_model_tier()}")  # "light"
print(f"剩餘配額：{free_user.quota.get_remaining_tokens()}")  # 100000

# === 場景 2：創建企業版使用者 ===
enterprise_user = UserContext.create_enterprise_user("user_456", "org_789")
if enterprise_user.has_permission("use_web_search"):
    print("✅ 可以使用網頁搜尋")
if enterprise_user.can_access_data_level(DataAccessLevel.CONFIDENTIAL):
    print("✅ 可以存取機密資料")

# === 場景 3：檢查配額 ===
if free_user.quota.is_quota_exceeded():
    print("❌ 配額已用完！")
else:
    # 處理請求
    free_user.quota.requests_used += 1
    free_user.quota.tokens_used += 1500

# === 場景 4：自訂企業使用者 ===
custom_user = UserContext(
    user_id="custom_001",
    username="張三",
    tier=UserTier.PRO,
    roles={UserRole.DEVELOPER, UserRole.ANALYST},
    permissions={"use_code_interpreter", "use_data_analysis"},
    data_access_level=DataAccessLevel.INTERNAL,
    organization_id="company_abc",
    department="研發部"
)
```

### 🔄 在 Router 中的整合流程

```
API 請求進入
    ↓
提取/創建 UserContext
    ↓
檢查配額（is_quota_exceeded）
    ↓
Router 接收 UserContext
    ↓
根據 tier 過濾可用模型
    ↓
根據 permissions 檢查工具授權
    ↓
根據 data_access_level 決定是否允許存取敏感資料
    ↓
選擇合適模型 + 更新配額
```

---

## tool_requirements.py - 工具需求與授權

### 🎯 檔案用途

這個檔案定義了**工具需求判斷與授權系統**，用於：
- 讓 SLM 判斷使用者的請求是否需要額外工具（網頁搜尋、代碼執行器等）
- 定義工具的優先級（必須、建議、可選）
- 管理使用者對各種工具的授權（哪些使用者可以使用哪些工具）
- 在路由決策中考慮工具可用性

### 📊 核心枚舉類別

#### 1. `ToolType` - 工具類型枚舉

定義了 9 種工具類型：

```python
class ToolType(str, Enum):
    NONE = "none"                            # 不需要工具
    WEB_SEARCH = "web_search"                # 網頁搜尋（查詢即時資訊、新聞等）
    CODE_INTERPRETER = "code_interpreter"    # 代碼解釋器（執行 Python 代碼）
    IMAGE_GENERATION = "image_generation"    # 圖片生成（DALL-E、Stable Diffusion）
    DATA_ANALYSIS = "data_analysis"          # 資料分析（處理 CSV、Excel）
    FILE_UPLOAD = "file_upload"              # 檔案上傳（處理使用者上傳的檔案）
    API_CALL = "api_call"                    # API 呼叫（呼叫外部 API）
    DATABASE_QUERY = "database_query"        # 資料庫查詢（SQL 查詢）
    DOCUMENT_RETRIEVAL = "document_retrieval" # 文檔檢索（RAG、向量搜尋）
```

**工具使用場景**：

| 工具 | 使用場景 | 範例請求 |
|------|----------|----------|
| WEB_SEARCH | 需要最新資訊 | "今天台北天氣如何？" |
| CODE_INTERPRETER | 需要執行代碼 | "計算費波那契數列的第 100 項" |
| IMAGE_GENERATION | 需要生成圖片 | "生成一張日落的圖片" |
| DATA_ANALYSIS | 需要分析資料 | "分析這個 CSV 檔案的銷售趨勢" |
| FILE_UPLOAD | 需要處理檔案 | "幫我總結這份 PDF 的內容" |
| API_CALL | 需要呼叫外部服務 | "查詢這個地址的經緯度" |
| DATABASE_QUERY | 需要查詢資料庫 | "查詢 2024 年的銷售總額" |
| DOCUMENT_RETRIEVAL | 需要檢索知識庫 | "我們公司的請假政策是什麼？" |

#### 2. `ToolPriority` - 工具優先級枚舉

定義了 3 級優先級：

```python
class ToolPriority(str, Enum):
    OPTIONAL = "optional"          # 可選：可以不用工具回答
    RECOMMENDED = "recommended"    # 建議：建議使用工具，結果會更好
    REQUIRED = "required"          # 必須：不用工具無法正確回答
```

**優先級判斷邏輯**：

```
REQUIRED    → "今天台北天氣？" → 沒有網搜無法回答
RECOMMENDED → "解釋量子力學" → 有網搜會更準確，但可以基於訓練資料回答
OPTIONAL    → "寫一首詩" → 完全不需要工具
```

### 🏗️ 核心資料類別

#### `ToolRequirement` - 單一工具需求

描述某個工具的需求詳情。

**屬性說明**：

```python
@dataclass
class ToolRequirement:
    tool_type: ToolType                      # 工具類型
    priority: ToolPriority = OPTIONAL        # 優先級
    reason: str = ""                         # 需要該工具的原因
    parameters: Dict[str, Any] = {}          # 工具特定參數
```

**範例**：

```python
# 需要網頁搜尋
web_search_req = ToolRequirement(
    tool_type=ToolType.WEB_SEARCH,
    priority=ToolPriority.REQUIRED,
    reason="使用者詢問今日天氣，需要即時資訊",
    parameters={"search_query": "台北天氣 2025-10-17"}
)
```

#### `ToolRequirements` - 工具需求集合（核心類別）

包含 SLM 分析後判斷的所有工具需求。

**屬性說明**：

```python
@dataclass
class ToolRequirements:
    required_tools: List[ToolRequirement] = []   # 工具需求清單
    needs_tools: bool = False                    # 是否需要任何工具
    analysis_notes: List[str] = []               # 分析詳情
```

**核心方法**：

1. **`has_tool(tool_type: ToolType) -> bool`**
   - 檢查是否需要特定工具

2. **`get_tool_requirement(tool_type: ToolType) -> Optional[ToolRequirement]`**
   - 獲取特定工具的需求詳情

3. **`get_required_tools() -> List[ToolRequirement]`**
   - 獲取所有標記為 REQUIRED 的工具

4. **`get_recommended_tools() -> List[ToolRequirement]`**
   - 獲取所有標記為 RECOMMENDED 的工具

5. **`get_optional_tools() -> List[ToolRequirement]`**
   - 獲取所有標記為 OPTIONAL 的工具

6. **`get_tool_types() -> Set[ToolType]`**
   - 獲取所有需要的工具類型集合

7. **`add_tool(...)`**
   - 新增工具需求

8. **工廠方法**：
   - `create_no_tools()` - 不需要工具
   - `create_web_search(reason, priority)` - 需要網頁搜尋
   - `create_code_interpreter(reason, priority)` - 需要代碼執行器

#### `ToolAuthorization` - 工具授權管理

用於檢查使用者是否有權限使用特定工具。

**屬性說明**：

```python
@dataclass
class ToolAuthorization:
    authorized_tools: Set[ToolType] = set()     # 被授權的工具
    denied_tools: Set[ToolType] = set()         # 被拒絕的工具（明確禁止）
    authorization_source: str = "default"        # 授權來源
```

**核心方法**：

1. **`is_authorized(tool_type: ToolType) -> bool`**
   - 檢查是否被授權使用特定工具
   - 邏輯：明確拒絕 > 授權清單

2. **`can_use_all_tools(tool_requirements: ToolRequirements) -> bool`**
   - 檢查是否可以使用所有需要的工具

3. **`get_unauthorized_tools(tool_requirements: ToolRequirements) -> List[ToolType]`**
   - 獲取所有沒有權限的工具

4. **工廠方法**：
   - `create_free_tier()` - 免費版授權（無工具）
   - `create_pro_tier()` - 專業版授權（部分工具）
   - `create_enterprise_tier()` - 企業版授權（所有工具）

### 💡 實際使用範例

```python
from models import ToolRequirements, ToolAuthorization, ToolType, ToolPriority

# === 場景 1：SLM 判斷需要網頁搜尋 ===
tools = ToolRequirements.create_web_search(
    reason="使用者詢問今日天氣",
    priority=ToolPriority.REQUIRED
)
print(f"需要工具：{tools.needs_tools}")  # True
print(f"必須工具：{[t.tool_type.value for t in tools.get_required_tools()]}")

# === 場景 2：檢查使用者授權 ===
free_user_auth = ToolAuthorization.create_free_tier()
pro_user_auth = ToolAuthorization.create_pro_tier()

if not free_user_auth.can_use_all_tools(tools):
    print("❌ 免費版使用者無法使用網頁搜尋")
    
if pro_user_auth.can_use_all_tools(tools):
    print("✅ 專業版使用者可以使用網頁搜尋")

# === 場景 3：複雜工具需求 ===
complex_tools = ToolRequirements(needs_tools=True)
complex_tools.add_tool(
    ToolType.WEB_SEARCH,
    priority=ToolPriority.REQUIRED,
    reason="需要最新股價資訊"
)
complex_tools.add_tool(
    ToolType.CODE_INTERPRETER,
    priority=ToolPriority.RECOMMENDED,
    reason="計算投資報酬率"
)
complex_tools.add_tool(
    ToolType.DATA_ANALYSIS,
    priority=ToolPriority.OPTIONAL,
    reason="可視覺化股價趨勢"
)

# 檢查企業版使用者授權
enterprise_auth = ToolAuthorization.create_enterprise_tier()
if enterprise_auth.can_use_all_tools(complex_tools):
    print("✅ 企業版使用者可以使用所有工具")
    
# 獲取未授權工具
unauthorized = pro_user_auth.get_unauthorized_tools(complex_tools)
print(f"專業版缺少的工具：{[t.value for t in unauthorized]}")
```

### 🔄 在 Router 中的整合流程

```
使用者請求
    ↓
SLM 分析
    ↓
返回 ToolRequirements
    ↓
從 UserContext 獲取 ToolAuthorization
    ↓
檢查授權
    ↓
├─ can_use_all_tools() = True  → 繼續，選擇支援該工具的模型
├─ can_use_all_tools() = False → 拒絕或降級處理
│   └─ 返回錯誤："您的方案不支援該功能，請升級"
└─ 部分授權 → 僅使用已授權的工具
```

---

## 整合使用範例

### 🎯 完整流程範例：處理一個使用者請求

```python
from models import (
    UserContext, UserTier, UserRole,
    SafetyLabels, SafetyLevel, ConfidentialDataType,
    ToolRequirements, ToolAuthorization, ToolType, ToolPriority
)

# ========================================
# 步驟 1：創建使用者上下文
# ========================================
user = UserContext.create_default_free_user("user_789")

# ========================================
# 步驟 2：SLM 分析使用者輸入
# ========================================
user_input = "幫我查今天台北的天氣，然後用 Python 計算是否適合外出"

# SLM 返回安全標籤
safety = SafetyLabels(
    violence=SafetyLevel.NONE,
    sexual=SafetyLevel.NONE,
    hate_speech=SafetyLevel.NONE,
    self_harm=SafetyLevel.NONE,
    confidential_data=ConfidentialDataType.NONE,
    jailbreak_attempt=False,
    risk_level=SafetyLevel.NONE,
    details=["內容安全，無風險"]
)

# SLM 返回工具需求
tools = ToolRequirements(needs_tools=True)
tools.add_tool(
    ToolType.WEB_SEARCH,
    priority=ToolPriority.REQUIRED,
    reason="需要查詢即時天氣資訊"
)
tools.add_tool(
    ToolType.CODE_INTERPRETER,
    priority=ToolPriority.RECOMMENDED,
    reason="需要執行計算邏輯"
)

# ========================================
# 步驟 3：安全檢查
# ========================================
if not safety.is_safe():
    print("❌ 內容不安全，拒絕處理")
    exit()

if safety.requires_escalation():
    print("🚨 記錄告警並通知管理員")

# ========================================
# 步驟 4：工具授權檢查
# ========================================
tool_auth = ToolAuthorization.create_free_tier()

if not tool_auth.can_use_all_tools(tools):
    unauthorized = tool_auth.get_unauthorized_tools(tools)
    print(f"❌ 使用者無權使用工具：{[t.value for t in unauthorized]}")
    print("💡 建議升級到專業版")
    exit()

# ========================================
# 步驟 5：配額檢查
# ========================================
if user.quota.is_quota_exceeded():
    print("❌ 配額已用完")
    exit()

# ========================================
# 步驟 6：路由決策
# ========================================
max_model_tier = user.get_max_model_tier()  # "light"
print(f"✅ 使用者可使用的最高模型等級：{max_model_tier}")

# 根據工具需求和使用者等級選擇模型
if tools.needs_tools:
    # 選擇支援工具的模型（如 GPT-4、Claude）
    selected_model = "gpt-4-turbo"
else:
    # 選擇不需要工具的輕量模型
    selected_model = "llama-3-8b"

print(f"✅ 選擇模型：{selected_model}")

# ========================================
# 步驟 7：更新配額
# ========================================
user.quota.requests_used += 1
user.quota.tokens_used += 2500
print(f"✅ 剩餘配額：{user.quota.get_remaining_tokens()} tokens")

# ========================================
# 步驟 8：記錄審計日誌
# ========================================
audit_log = {
    "user_id": user.user_id,
    "tier": user.tier.value,
    "safety": safety.to_dict(),
    "tools": tools.to_dict(),
    "selected_model": selected_model,
    "quota_remaining": user.quota.get_remaining_tokens()
}
print("✅ 審計日誌已記錄")
```

### 🎯 多使用者場景對比

```python
# === 免費版使用者 ===
free_user = UserContext.create_default_free_user("free_001")
print(f"免費版 - 模型等級：{free_user.get_max_model_tier()}")  # "light"
print(f"免費版 - 可用工具：{ToolAuthorization.create_free_tier().authorized_tools}")  # set()

# === 專業版使用者 ===
pro_user = UserContext(
    user_id="pro_001",
    tier=UserTier.PRO,
    roles={UserRole.USER, UserRole.DEVELOPER}
)
print(f"專業版 - 模型等級：{pro_user.get_max_model_tier()}")  # "heavy"
pro_auth = ToolAuthorization.create_pro_tier()
print(f"專業版 - 可用工具：{[t.value for t in pro_auth.authorized_tools]}")
# ['web_search', 'code_interpreter', 'image_generation', 'file_upload']

# === 企業版使用者 ===
enterprise_user = UserContext.create_enterprise_user("ent_001", "company_abc")
print(f"企業版 - 模型等級：{enterprise_user.get_max_model_tier()}")  # "premium"
ent_auth = ToolAuthorization.create_enterprise_tier()
print(f"企業版 - 可用工具：{[t.value for t in ent_auth.authorized_tools]}")
# 所有工具
```

---

## 架構設計理念

### 🎨 設計原則

#### 1. **關注點分離（Separation of Concerns）**

每個檔案專注於一個核心功能：
- `safety.py` → 安全檢測
- `user_context.py` → 身份管理
- `tool_requirements.py` → 工具管理

#### 2. **強類型系統（Strong Typing）**

使用 Python 的 `Enum` 和 `dataclass` 確保類型安全：
```python
# ✅ 好：類型安全
tier: UserTier = UserTier.PRO

# ❌ 壞：字串容易打錯
tier: str = "pro"  # 容易打成 "pra"
```

#### 3. **防禦性編程（Defensive Programming）**

所有類別都有驗證方法和安全預設值：
```python
# 創建安全的預設實例
safety = SafetyLabels.create_safe_default()

# 檢查前先驗證
if user.quota.is_quota_exceeded():
    return "配額已用完"
```

#### 4. **工廠模式（Factory Pattern）**

提供便捷的實例創建方法：
```python
# 不用記住所有參數
free_user = UserContext.create_default_free_user("user_id")
enterprise_user = UserContext.create_enterprise_user("user_id", "org_id")
```

#### 5. **可序列化（Serializable）**

所有類別都支援 `to_dict()` / `from_dict()`，方便：
- 儲存到資料庫（PostgreSQL、MongoDB）
- 記錄到日誌系統（Elasticsearch）
- 傳輸給前端（JSON API）
- 記錄審計日誌

### 🔄 資料流向

```
API 請求
    ↓
提取 UserContext（從 JWT token 或資料庫）
    ↓
SLM 分析 → 返回 SafetyLabels + ToolRequirements
    ↓
SafetyPolicyEngine 檢查 SafetyLabels
    ↓
ToolAuthorizationManager 檢查 ToolRequirements vs UserContext
    ↓
Router 根據 UserContext.tier 過濾模型
    ↓
選擇最佳模型
    ↓
更新 UserContext.quota
    ↓
記錄審計日誌（包含所有資料模型的 to_dict()）
```

### 📊 資料庫儲存建議

#### PostgreSQL Schema 範例

```sql
-- 使用者表
CREATE TABLE users (
    user_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255),
    tier VARCHAR(50),
    roles TEXT[],
    permissions TEXT[],
    data_access_level VARCHAR(50),
    organization_id VARCHAR(255),
    monthly_tokens INTEGER,
    tokens_used INTEGER,
    monthly_requests INTEGER,
    requests_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 請求日誌表
CREATE TABLE request_logs (
    log_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    safety_labels JSONB,              -- SafetyLabels.to_dict()
    tool_requirements JSONB,          -- ToolRequirements.to_dict()
    selected_model VARCHAR(255),
    tokens_used INTEGER,
    success BOOLEAN
);

-- 安全告警表
CREATE TABLE security_alerts (
    alert_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    risk_level VARCHAR(50),
    safety_labels JSONB,
    user_input TEXT,
    handled BOOLEAN DEFAULT FALSE
);
```

### 🔐 安全考量

1. **多層防禦**：
   - Layer 1: SLM 安全分析
   - Layer 2: SafetyPolicyEngine 檢查
   - Layer 3: 權限驗證
   - Layer 4: 配額限制

2. **最小權限原則**：
   - 預設所有使用者為 FREE tier
   - 明確授予權限，而非預設開啟

3. **審計追蹤**：
   - 所有高風險操作都記錄詳細日誌
   - `requires_escalation()` 自動觸發告警

### 🚀 效能考量

1. **快速檢查**：
   ```python
   # O(1) 檢查
   if not safety.is_safe():
       return early
   ```

2. **延遲載入**：
   ```python
   # 只在需要時才查詢資料庫
   if user.is_enterprise():
       load_organization_settings()
   ```

3. **快取友好**：
   ```python
   # UserContext 可以快取在 Redis
   redis.setex(f"user:{user_id}", 3600, user.to_dict())
   ```

---

## 📚 延伸閱讀

- **下一步**：查看 `core/safety_policy.py`（步驟 1.4）了解如何使用這些資料模型
- **整合**：查看 `core/router_v1/router.py` 了解如何整合到路由系統
- **API**：查看 `api/chat.py` 了解如何從 API 層傳遞 UserContext

---

## ✅ 總結

這三個資料模型檔案是 LyraLLM 進化的基石：

| 檔案 | 核心功能 | 關鍵類別 | 主要用途 |
|------|----------|----------|----------|
| `safety.py` | 內容安全檢測 | `SafetyLabels` | 攔截不安全內容、檢測 Jailbreak |
| `user_context.py` | 身份權限管理 | `UserContext`, `ResourceQuota` | 身份感知路由、配額管理 |
| `tool_requirements.py` | 工具需求判斷 | `ToolRequirements`, `ToolAuthorization` | SLM 判斷工具需求、檢查授權 |

**設計特點**：
- ✅ 強類型安全
- ✅ 豐富的實用方法
- ✅ 可序列化
- ✅ 工廠模式
- ✅ 完整文檔

**下一步**：將這些資料模型整合到 SLM 分析流程和 Router 決策中！

---

> 💡 **給明天的你**：這些資料模型是整個系統的 DNA，理解它們就理解了 LyraLLM 如何做安全檢測、權限管理和工具分配。每個類別都有清晰的職責，每個方法都有明確的用途。慢慢看，不急！ 😊

> 📅 **文檔版本**：v1.0 (2025-10-17)  
> 🔄 **更新記錄**：初始版本，包含 safety.py、user_context.py、tool_requirements.py 的完整說明
