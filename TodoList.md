# LyraLLM 增強功能實施 TODO List

> 📅 **開始日期**：2025-10-17  
> 🎯 **目標**：為 LyraLLM 添加工具檢測、安全標籤和身份感知路由功能  
> 📊 **整體進度**：2/15 步驟完成 (13.3%)

---

## 📋 Phase 1：基礎資料模型與 SLM 整合 (1-2 週)

### ✅ 步驟 1.1：創建資料模型 (已完成)
**完成日期**：2025-10-17  
**耗時**：約 2 小時

- [x] 創建 `models/safety.py`
  - [x] `SafetyLevel` 枚舉（5 級安全等級）
  - [x] `ConfidentialDataType` 枚舉（7 種機密資料類型）
  - [x] `SafetyLabels` 類別（完整安全評估）
  - [x] 實用方法：`is_safe()`, `requires_escalation()`, `requires_privileged_access()`
  
- [x] 創建 `models/user_context.py`
  - [x] `UserTier` 枚舉（4 種使用者等級）
  - [x] `UserRole` 枚舉（7 種角色）
  - [x] `DataAccessLevel` 枚舉（4 級資料存取權限）
  - [x] `ResourceQuota` 類別（資源配額管理）
  - [x] `UserContext` 類別（完整使用者上下文）
  - [x] 工廠方法：`create_default_free_user()`, `create_enterprise_user()`
  
- [x] 創建 `models/tool_requirements.py`
  - [x] `ToolType` 枚舉（9 種工具類型）
  - [x] `ToolPriority` 枚舉（3 級優先級）
  - [x] `ToolRequirement` 類別（單一工具需求）
  - [x] `ToolRequirements` 類別（工具需求集合）
  - [x] `ToolAuthorization` 類別（工具授權管理）
  - [x] 工廠方法：`create_web_search()`, `create_code_interpreter()` 等
  
- [x] 更新 `models/__init__.py`（統一匯出）

- [x] 創建 `models/model_introduce.md`
  - [x] 超詳細文檔（8000+ 字）
  - [x] 20+ 個程式碼範例
  - [x] 10+ 個對照表
  - [x] 5+ 個流程圖

**產出檔案**：
- ✅ `models/safety.py` (236 行)
- ✅ `models/user_context.py` (299 行)
- ✅ `models/tool_requirements.py` (374 行)
- ✅ `models/__init__.py` (51 行)
- ✅ `models/model_introduce.md` (800+ 行)

---

### ✅ 步驟 1.2：擴展 SLM Prompt (已完成)
**完成日期**：2025-10-17  
**耗時**：約 1.5 小時

- [x] 修改 `config/routing_rules.yaml`
  - [x] 擴展 `system_prompt`（從 800 字元 → 3105 字元）
  - [x] 加入工具需求判斷說明（9 種工具）
  - [x] 加入安全標籤分析說明（5 個維度 + Jailbreak 檢測）
  - [x] 加入權限需求分析說明（等級、角色、權限）
  - [x] 提供完整的 JSON 輸出格式範例
  
- [x] 新增 7 個範例說明（examples）
  - [x] 一般安全對話
  - [x] 需要網頁搜尋
  - [x] 代碼執行需求
  - [x] 涉及機密資料
  - [x] Jailbreak 攻擊
  - [x] 暴力內容
  - [x] 複雜多工具需求
  
- [x] 創建 `test_enhanced_slm_analysis.py`
  - [x] 10 個測試案例
  - [x] 模擬 SLM 分析邏輯
  - [x] 自動驗證功能
  - [x] 測試通過率：90% (9/10)

**產出檔案**：
- ✅ `config/routing_rules.yaml` (已修改，新增 ~200 行)
- ✅ `test_enhanced_slm_analysis.py` (420 行)

**測試結果**：
```
✅ 通過: 9/10
❌ 失敗: 1/10
📈 通過率: 90.0%
```

---

### ⏳ 步驟 1.3：修改 SLM Analyzer 解析新格式 (進行中)
**預計完成**：2025-10-17  
**預計耗時**：1-2 小時

- [ ] 擴展 `IntentResult` 資料類別
  - [ ] 加入 `required_tools: Optional[ToolRequirements]` 欄位
  - [ ] 加入 `safety_labels: Optional[SafetyLabels]` 欄位
  - [ ] 加入 `required_permissions: Optional[Dict[str, Any]]` 欄位
  - [ ] 保持向後兼容（所有新欄位都是 Optional）
  
- [ ] 修改 `core/router_v1/analyzer_slm.py`
  - [ ] 在檔案頂部導入新資料模型
    ```python
    from models import SafetyLabels, ToolRequirements, ToolType, ToolPriority
    ```
  - [ ] 修改 `_safe_parse_json()` 方法
    - [ ] 解析 `required_tools` 陣列
    - [ ] 解析 `safety_labels` 物件
    - [ ] 解析 `required_permissions` 物件
  - [ ] 創建新方法 `_parse_tool_requirements(data: Dict) -> ToolRequirements`
  - [ ] 創建新方法 `_parse_safety_labels(data: Dict) -> SafetyLabels`
  - [ ] 修改 `analyze()` 方法，返回擴展後的 `IntentResult`
  
- [ ] 加入降級處理（Fallback）
  - [ ] 如果 SLM 沒有返回新欄位，使用安全預設值
  - [ ] `SafetyLabels.create_safe_default()`
  - [ ] `ToolRequirements.create_no_tools()`
  
- [ ] 測試驗證
  - [ ] 使用真實 SLM (Ollama 或 Azure OpenAI) 測試
  - [ ] 確認能正確解析所有欄位
  - [ ] 確認向後兼容性

**需要修改的檔案**：
- ⏳ `core/router_v1/analyzer_slm.py`

**驗收標準**：
- [ ] `IntentResult` 包含新欄位
- [ ] 能解析完整的 SLM JSON 輸出
- [ ] 向後兼容（舊 prompt 也能用）
- [ ] 測試通過

---

### ⏸️ 步驟 1.4：創建 SafetyPolicyEngine (待開始)
**預計開始**：步驟 1.3 完成後  
**預計耗時**：2-3 小時

- [ ] 創建 `core/safety_policy.py`
  - [ ] `SafetyPolicyEngine` 類別
  - [ ] `evaluate(safety_labels: SafetyLabels, user_context: UserContext) -> SafetyDecision`
  - [ ] `SafetyDecision` 資料類別（allow, block, audit, escalate）
  
- [ ] 實現安全策略邏輯
  - [ ] 檢查 `is_safe()` 判斷是否允許
  - [ ] 檢查 `requires_escalation()` 決定是否告警
  - [ ] 檢查 `requires_privileged_access()` 驗證使用者權限
  - [ ] 根據使用者等級調整容忍度
  
- [ ] 實現攔截邏輯
  - [ ] Jailbreak 攻擊 → 立即攔截
  - [ ] 暴力內容 → 攔截並記錄
  - [ ] 機密資料 → 檢查權限，無權限則攔截
  
- [ ] 實現審計日誌
  - [ ] 記錄所有高風險請求
  - [ ] 記錄所有被攔截的請求
  - [ ] 格式：`{user_id, timestamp, safety_labels, decision, reason}`

**需要創建的檔案**：
- [ ] `core/safety_policy.py` (預計 150-200 行)
- [ ] `config/safety_policy.yaml` (可選，安全策略配置)

**驗收標準**：
- [ ] 能正確評估安全風險
- [ ] 能攔截危險內容
- [ ] 能記錄審計日誌
- [ ] 單元測試通過

---

### ⏸️ 步驟 1.5：整合到 Router (待開始)
**預計開始**：步驟 1.4 完成後  
**預計耗時**：2-3 小時

- [ ] 修改 `core/router_v1/router.py`
  - [ ] 導入 `SafetyPolicyEngine`
  - [ ] 在路由決策前加入安全檢查
  - [ ] 處理安全決策結果
    ```python
    # 偽代碼
    intent_result = await slm_analyzer.analyze(query)
    safety_decision = safety_engine.evaluate(
        intent_result.safety_labels, 
        user_context
    )
    if safety_decision.action == "block":
        return error_response
    ```
  
- [ ] 加入工具可用性檢查
  - [ ] 檢查使用者是否有權限使用所需工具
  - [ ] 如果沒有權限，返回升級提示或降級處理
  
- [ ] 修改模型選擇邏輯
  - [ ] 考慮 `user_context.tier` 過濾可用模型
  - [ ] 考慮 `required_tools` 選擇支援工具的模型
  - [ ] 考慮 `complexity` 和 `safety_labels.risk_level`

**需要修改的檔案**：
- [ ] `core/router_v1/router.py`
- [ ] `core/router_v1/rule_engine.py` (可能需要)

**驗收標準**：
- [ ] 安全檢查正常運作
- [ ] 危險請求被正確攔截
- [ ] 工具授權檢查正常
- [ ] 路由決策考慮新參數

---

### ⏸️ 步驟 1.6：更新 API 層傳遞 UserContext (待開始)
**預計開始**：步驟 1.5 完成後  
**預計耗時**：1-2 小時

- [ ] 修改 `api/chat.py`
  - [ ] 從請求頭或 JWT token 提取使用者資訊
  - [ ] 創建或載入 `UserContext`
  - [ ] 將 `UserContext` 傳遞給 Router
  
- [ ] 實現使用者識別邏輯
  - [ ] 如果有 JWT token → 解析使用者資訊
  - [ ] 如果沒有 token → 創建預設免費使用者
  - [ ] 從資料庫載入使用者配額和權限（可選）
  
- [ ] 更新 API 響應
  - [ ] 返回安全決策資訊（如果被攔截，說明原因）
  - [ ] 返回配額資訊（剩餘 tokens、請求次數）
  - [ ] 返回升級提示（如果需要更高等級）

**需要修改的檔案**：
- [ ] `api/chat.py`
- [ ] `api/models.py` (可能需要加入新的 Request/Response 模型)

**驗收標準**：
- [ ] API 能正確提取使用者資訊
- [ ] UserContext 正確傳遞給 Router
- [ ] API 響應包含新資訊
- [ ] 測試通過

---

### ⏸️ 步驟 1.7：創建測試腳本驗證完整流程 (待開始)
**預計開始**：步驟 1.6 完成後  
**預計耗時**：1-2 小時

- [ ] 創建 `test_phase1_integration.py`
  - [ ] 測試完整的請求流程（API → Router → SLM → Safety → Response）
  - [ ] 測試各種使用者等級（free, pro, enterprise）
  - [ ] 測試安全攔截（jailbreak, violence, confidential data）
  - [ ] 測試工具授權（有權限 vs 無權限）
  
- [ ] 測試案例
  - [ ] 免費使用者請求網頁搜尋 → 應該被拒絕
  - [ ] 專業版使用者請求網頁搜尋 → 應該成功
  - [ ] 任何使用者請求暴力內容 → 應該被攔截
  - [ ] 免費使用者超過配額 → 應該被拒絕
  - [ ] 企業使用者存取機密資料 → 應該成功
  
- [ ] 效能測試
  - [ ] 測試路由決策延遲（應該 < 500ms）
  - [ ] 測試安全檢查延遲（應該 < 50ms）
  - [ ] 測試完整請求延遲（應該 < 2s）

**需要創建的檔案**：
- [ ] `test_phase1_integration.py` (預計 300-400 行)

**驗收標準**：
- [ ] 所有測試案例通過
- [ ] 效能符合預期
- [ ] 無明顯 bug

---

## 📋 Phase 2：權限管理與工具授權 (2-3 週)

### ⏸️ 步驟 2.1：創建 PermissionManager (待開始)
**預計開始**：Phase 1 完成後  
**預計耗時**：3-4 小時

- [ ] 創建 `core/permission_manager.py`
  - [ ] `PermissionManager` 類別
  - [ ] `check_permission(user: UserContext, permission: str) -> bool`
  - [ ] `check_role(user: UserContext, role: UserRole) -> bool`
  - [ ] `check_data_access(user: UserContext, level: DataAccessLevel) -> bool`
  
- [ ] 實現權限檢查邏輯
  - [ ] 角色繼承（admin 擁有所有權限）
  - [ ] 權限組合（某些操作需要多個權限）
  - [ ] 動態權限（從資料庫載入）
  
- [ ] 實現 RBAC (Role-Based Access Control)
  - [ ] 定義角色權限對應表
  - [ ] 實現角色檢查
  - [ ] 實現權限繼承

**需要創建的檔案**：
- [ ] `core/permission_manager.py` (預計 150-200 行)
- [ ] `config/permissions.yaml` (權限配置檔)

---

### ⏸️ 步驟 2.2：創建 ToolAuthorizationManager (待開始)
**預計開始**：步驟 2.1 完成後  
**預計耗時**：2-3 小時

- [ ] 創建 `core/tool_authorization.py`
  - [ ] `ToolAuthorizationManager` 類別
  - [ ] `get_authorization(user: UserContext) -> ToolAuthorization`
  - [ ] `check_tool_access(user: UserContext, tool: ToolType) -> bool`
  - [ ] `validate_tool_requirements(user: UserContext, requirements: ToolRequirements) -> ValidationResult`
  
- [ ] 實現工具授權邏輯
  - [ ] 根據使用者等級返回授權
  - [ ] 檢查單一工具權限
  - [ ] 驗證完整工具需求清單
  - [ ] 返回未授權工具清單

**需要創建的檔案**：
- [ ] `core/tool_authorization.py` (預計 100-150 行)
- [ ] `config/tool_permissions.yaml` (工具權限配置)

---

### ⏸️ 步驟 2.3：創建 QuotaManager (待開始)
**預計開始**：步驟 2.2 完成後  
**預計耗時**：3-4 小時

- [ ] 創建 `core/quota_manager.py`
  - [ ] `QuotaManager` 類別
  - [ ] `check_quota(user: UserContext) -> bool`
  - [ ] `consume_tokens(user: UserContext, tokens: int) -> bool`
  - [ ] `consume_request(user: UserContext) -> bool`
  - [ ] `reset_quota(user: UserContext) -> None`
  
- [ ] 實現配額追蹤
  - [ ] 即時配額檢查
  - [ ] 原子性配額扣除（防止競態條件）
  - [ ] 配額重置（每月 1 號）
  - [ ] 配額統計（使用率、趨勢）
  
- [ ] 整合資料庫
  - [ ] 將配額資訊儲存到 PostgreSQL
  - [ ] 即時更新配額使用量
  - [ ] 實現配額快取（Redis）

**需要創建的檔案**：
- [ ] `core/quota_manager.py` (預計 200-250 行)

---

### ⏸️ 步驟 2.4：創建 AuditLogger (待開始)
**預計開始**：步驟 2.3 完成後  
**預計耗時**：2-3 小時

- [ ] 創建 `core/audit_logger.py`
  - [ ] `AuditLogger` 類別
  - [ ] `log_request(user, query, intent_result, decision)`
  - [ ] `log_safety_alert(user, safety_labels, action)`
  - [ ] `log_permission_denied(user, permission, reason)`
  
- [ ] 實現審計日誌
  - [ ] 記錄所有請求（包含安全評估結果）
  - [ ] 記錄所有攔截事件
  - [ ] 記錄權限拒絕事件
  - [ ] 記錄配額超限事件
  
- [ ] 整合 Elasticsearch
  - [ ] 將審計日誌發送到 Elasticsearch
  - [ ] 定義索引結構
  - [ ] 實現日誌查詢 API

**需要創建的檔案**：
- [ ] `core/audit_logger.py` (預計 150-200 行)

---

## 📋 Phase 3：企業級功能 (1-2 個月)

### ⏸️ 步驟 3.1：完整的身份驗證系統 (待開始)
**預計耗時**：1-2 週

- [ ] JWT Token 生成與驗證
- [ ] OAuth2 整合（Google, Microsoft）
- [ ] API Key 管理
- [ ] Session 管理

---

### ⏸️ 步驟 3.2：多租戶支援 (待開始)
**預計耗時**：1-2 週

- [ ] 組織管理（Organization）
- [ ] 部門管理（Department）
- [ ] 租戶隔離（資料、配額、權限）
- [ ] 跨租戶存取控制

---

### ⏸️ 步驟 3.3：監控與告警 (待開始)
**預計耗時**：1 週

- [ ] Prometheus 指標匯出
- [ ] Grafana 儀表板
- [ ] 告警規則設定
- [ ] 郵件/Slack 通知

---

### ⏸️ 步驟 3.4：合規性報告 (待開始)
**預計耗時**：1 週

- [ ] 安全報告生成
- [ ] 使用量報告
- [ ] 配額報告
- [ ] 異常行為報告

---

## 📊 整體進度追蹤

### 已完成 (2/15)

- ✅ 步驟 1.1：創建資料模型
- ✅ 步驟 1.2：擴展 SLM Prompt

### 進行中 (1/15)

- ⏳ 步驟 1.3：修改 SLM Analyzer 解析新格式

### 待開始 (12/15)

- ⏸️ 步驟 1.4 - 1.7 (Phase 1 剩餘)
- ⏸️ 步驟 2.1 - 2.4 (Phase 2 完整)
- ⏸️ 步驟 3.1 - 3.4 (Phase 3 完整)

---

## 📈 里程碑

### 🎯 里程碑 1：Phase 1 完成 (預計 2025-10-24)
- 基礎資料模型 ✅
- SLM 整合 ⏳
- 安全檢查 ⏸️
- API 整合 ⏸️

### 🎯 里程碑 2：Phase 2 完成 (預計 2025-11-07)
- 權限管理系統
- 工具授權系統
- 配額管理系統
- 審計日誌系統

### 🎯 里程碑 3：Phase 3 完成 (預計 2025-12-31)
- 完整身份驗證
- 多租戶支援
- 監控告警
- 合規性報告

---

## 🔥 當前優先級

### 🚨 高優先級
1. **步驟 1.3**：修改 SLM Analyzer（今天完成）
2. **步驟 1.4**：創建 SafetyPolicyEngine（明天開始）
3. **步驟 1.5**：整合到 Router（後天開始）

### ⚠️ 中優先級
4. 步驟 1.6：更新 API 層
5. 步驟 1.7：整合測試

### 💡 低優先級
6. Phase 2 步驟（等 Phase 1 完成）
7. Phase 3 步驟（長期規劃）

---

## 📝 備註

- **每個步驟完成後記得更新此文檔**
- **遇到問題記錄在對應步驟下方**
- **完成後打勾 ✅，進行中標記 ⏳**
- **可以隨時調整優先級和預估時間**

---

> 💡 **給未來的自己**：一步一步來，不要急！每個步驟都很重要，確保測試通過再進行下一步。加油！ 💪

> 📅 **最後更新**：2025-10-17 23:45  
> 👤 **更新者**：GitHub Copilot
