# RBAC 與安全路由使用手冊

本文彙整 LyraLLM 目前的權限控管、模型路由與敏感資料策略。依下列流程操作，就能快速了解如何設定角色、如何測試，以及各角色在安全分類下的行為。

---

## 1. 系統概觀

1. **角色定義 (`config.yaml`)**  
   - `default_role`：指派預設角色，當 `X-Lyra-Role` 標頭缺失或無法映射時使用。  
   - `roles`：描述所有角色，包含繼承 (`inherits`)、權限 (`permissions`)、功能旗標 (`feature_flags`)、路由策略 (`routing_policies`) 與備註 (`metadata`)。

2. **安全上下文 (`RequestSecurityContext`)**  
   - FastAPI 端點會透過 `X-Lyra-Role` 取得角色資料並注入 `RequestSecurityContext`。  
   - Context 內含角色名稱、權限、功能旗標與路由策略，供後續流程判斷。

3. **模型路由 (`ModelExecutor` + `RouterV1`)**  
   - `RouterV1`：先由 SLM 進行意圖/複雜度/安全分類 (S1~S14) 分析，再由規則引擎決定候選模型。  
   - `ModelExecutor.generate()`：接收路由結果後，依角色的 `routing_policies` 決定是否改用 fallback 模型（例如遇到 S7 Privacy 時改派本地模型）。

4. **API 行為**  
   - `/api/chat/models`：依角色策略過濾模型清單。  
   - `/api/chat/completions`：檢查模型與 `features` 是否被允許；未授權時回傳 `403 model_not_allowed` 或 `403 feature_not_allowed`。  
   - `routing_info` 內含安全分類、策略動作等細節，方便稽核。

5. **測試**  
   - `pytest test_model_executor_policies.py`：驗證 S7 隱私情境會 fallback 到本地模型，以及一般情境不會被影響。

---

## 2. `auth` 區塊欄位對照表

| 欄位 | 說明 | 注意事項 |
| --- | --- | --- |
| `default_role` | 預設角色名稱。 | 建議指向權限最小的角色（目前為 `standard_user`）。 |
| `roles[].name` | 角色識別名稱。 | 於 `X-Lyra-Role` 中使用（字串區分大小寫）。 |
| `roles[].inherits` | 父角色列表。 | 權限與功能會累加；子項可覆蓋父項 `routing_policies`。 |
| `roles[].permissions` | 任意自訂權限標記。 | 可搭配 `require_permission("...")` 於 FastAPI 端點使用。 |
| `roles[].feature_flags` | 啟用的功能旗標。 | 例如 `web_search`、`code_interpreter`、`image_generation`。未開放的功能一律回 403。 |
| `roles[].routing_policies` | 自訂路由策略。 | 現行策略包含：<br>• `allow_external_providers` (bool)<br>• `preferred_tiers` (list)<br>• `audit_level` (string)<br>• `sensitive_categories` (list, 例如 `["S7"]`)<br>• `sensitive_fallback` / `sensitive_fallback_model` (遇敏感分類時的安全模型)<br>• `fallback` / `fallback_model` (一般失敗時的後援模型)<br>• 其他自訂旗標 (`escalate_on_sensitive` 等)。 |
| `roles[].metadata` | 角色備註。 | 可放負責人或其他資訊，供維運查閱。 |

> **繼承規則**  
> - 權限 (`permissions`) 與功能 (`feature_flags`) 會合併所有父角色。  
> - 子角色的 `routing_policies`、`metadata` 會覆蓋父角色同名欄位。  
> - 若 `inherits` 指向不存在的角色，系統會寫警告並使用 default role。 |

---

## 3. 目前角色設定摘要

| 角色 | 典型對象 | 功能旗標 | 路由策略重點 | 備註 |
| --- | --- | --- | --- | --- |
| `standard_user` | 一般員工 | 無 | `allow_external_providers: false`<br>`sensitive_categories: ["S7"]`<br>`sensitive_fallback: "gpt-oss:20b"` | 基本聊天；遇 S7 (Privacy) 自動改使用本地模型。 |
| `power_user` | 進階員工 | `web_search`,`code_interpreter` | `allow_external_providers: true`<br>`preferred_tiers: ["premium", "trusted"]` | 繼承 `standard_user`，因此同樣受 S7 規則影響。 |
| `reviewer` | 信任與安全審查者 | 無 | `allow_external_providers: true`<br>`audit_level: "review"` | 可查閱稽核紀錄、處理事件。 |
| `ops` | 營運/SRE | `web_search`,`internal_tools` | `allow_external_providers: true`<br>`preferred_fallback: "gpt-oss:20b"` | 可用外部模型並快速切換至本地。 |
| `security_officer` | 安全部門 | `web_search` | `allow_external_providers: true`<br>`escalate_on_sensitive: true`<br>`audit_level: "high"` | 可處理敏感資料；稽核等級較高。 |
| `admin` | 平台管理者 | 全部功能 | `allow_external_providers: true`<br>`audit_level: "full"` | 繼承 `security_officer` + `ops`，具備所有管理權限。 |

> 角色權限一律以 `config.yaml` 為準；上表只列出目前主要配置。

---

## 4. API 端檢查流程

### 4.1 模型與功能驗證

- **`POST /api/chat/completions`**：  
  1. 檢查 `RequestSecurityContext.allows_model(model)`；若角色禁止外部模型或 fallback 失敗，回 `403 model_not_allowed`。  
  2. 檢查 `features` 旗標是否都在 `feature_flags` 中；違規即 `403 feature_not_allowed`。  
  3. 呼叫 `ModelExecutor.generate()`，後續會根據 `routing_policies` 應用敏感降級策略。

- **`GET /api/chat/models`**：  
  - 使用角色策略過濾模型列表（例如 `allow_external_providers: false` 的角色看不到外部模型）。

### 4.2 敏感分類 Fallback

1. `RouterV1` 將 SLM 分析結果存成 `routing_info`（包含安全分類 `category`）。  
2. `ModelExecutor._enforce_security_policies` 讀取角色的 `routing_policies`：  
   - 若 `category` 在 `sensitive_categories` 內，且設定了 `sensitive_fallback`，就直接改用該模型。  
   - `routing_info` 中會新增 `policy_actions` 記錄本次策略執行。  
3. 更新後的流程已透過 `test_model_executor_policies.py` 驗證：  
   - S7 (Privacy) → fallback 成功。  
   - 非敏感分類 → 維持原本 router 決定。

---

## 5. 實際操作範例

### 5.1 取得模型列表
```bash
# 不帶標頭 (使用 default_role = standard_user)
curl http://localhost:8081/api/chat/models

# 以 reviewer 角色呼叫
curl -H "X-Lyra-Role: reviewer" http://localhost:8081/api/chat/models
```
不同角色將看到不同模型清單（依 `allow_external_providers` 及其他策略過濾）。

### 5.2 發送聊天請求並使用功能旗標
```bash
curl -X POST http://localhost:8081/api/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Lyra-Role: power_user" \
  -d '{
        "model": "auto",
        "messages": [{"role": "user", "content": "幫我整理季度報告"}],
        "features": {"web_search": true}
      }'
```
- 若改用 `standard_user` 角色，且 `features.web_search` 設為 `true`，會收到 `403 feature_not_allowed`。  
- 若輸入內容包含個資（導致 `category = S7`），即使角色允許外部模型仍會 fallback 到 `gpt-oss:20b`。

### 5.3 更新設定後重載
```bash
curl -X POST http://localhost:8081/api/chat/plugins/reload
```
或直接重啟後端服務，以載入最新的 `config.yaml`。

---

## 6. 疑難排查與建議

| 問題 | 可能原因 | 建議處理 |
| --- | --- | --- |
| `403 feature_not_allowed` | 功能旗標未在角色 `feature_flags` 內 | 編輯 `config.yaml` 增加旗標，再重載設定。 |
| `403 model_not_allowed` | 角色不允許外部模型或 fallback 失敗 | 檢查 `allow_external_providers`、`sensitive_fallback` 設置是否正確。 |
| 指定角色無效 | `X-Lyra-Role` 拼寫錯誤或角色不存在 | 修正標頭並確認 YAML 中有該角色。 |
| 策略未生效 | 未在 `routing_policies` 中設定敏感類別或 fallback 模型 | 加上 `sensitive_categories` 與 `sensitive_fallback` 並重啟。 |
| 想要更細部的 API 控制 | 需要額外權限檢查 | 在端點使用 `require_permission("...")`。 |

---

## 7. 實作與測試建議

1. **維持最小權限**：以 `standard_user` 為基礎，只對需要的角色開 external 模型或進階功能。  
2. **策略集中在 YAML**：將 `allow_external_providers`、`sensitive_categories`、`fallback` 等設定寫在 YAML，程式只負責執行。  
3. **自動化測試**：使用 `pytest test_model_executor_policies.py` 檢查 S7 fallback、以及新增其他安全分類測試案例。  
4. **觀測與稽核**：可將 `routing_info.policy_actions` 或 `security_ctx.to_payload()` 寫入 TokenUsage/event bus，做稽核與成本分析。  
5. **擴充敏感類別**：若想針對 S1~S6 等其他分類採取不同策略，只需在 YAML 添加，程式會自動套用。

---

## 8. 常用參考檔案

- `config.yaml`：角色、權限、路由策略設定。  
- `auth/role_registry.py`：角色繼承與快取邏輯。  
- `auth/dependencies.py`：`RequestSecurityContext` 建立與 `require_permission` helper。  
- `core/model_executor.py`：模型路由、敏感 fallback 的主要實作。  
- `config/routing_rules.yaml`：安全分類 (S1~S14) 定義與 SLM 分析 prompt。  
- `docs/router_flow_explained.md`、`docs/s_category_safety_system.md`：路由流程與安全分類說明。  
- `test_model_executor_policies.py`：敏感分類 fallback 測試。

如需進一步協助或客製策略，歡迎參考上述程式檔或聯絡平台維運團隊。祝開發順利！
