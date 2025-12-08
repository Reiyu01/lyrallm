# 權限系統與效能測試指南

## 📋 概述

LyraLLM 的權限系統（RBAC）提供完整的模型和功能存取控制。為了進行公平的效能比較測試，系統支援臨時關閉權限檢查。

## ⚙️ 權限系統控制

### 1. 全局配置（config.yaml）

```yaml
auth:
  # 權限系統全局開關
  enabled: true  # true=啟用權限控制 | false=跳過所有權限檢查
  default_role: "standard_user"
  roles:
    # ... 角色定義
```

### 2. 效能測試模式

使用 benchmark 工具時，可透過 `--disable-auth` 參數臨時關閉權限檢查：

```bash
# 標準測試（啟用權限）
python benchmark_gateway_full.py --tests all

# 效能測試（關閉權限，用於公平比較）
python benchmark_gateway_full.py --tests all --disable-auth
```

## 🎯 使用場景

### 生產環境
```yaml
auth:
  enabled: true  # 必須啟用
```
- ✅ 完整 RBAC 權限控制
- ✅ 模型存取限制
- ✅ 功能權限管理
- ✅ 審計追蹤

### 效能測試
```bash
python benchmark_gateway_full.py --disable-auth
```
- ⚠️ 關閉權限檢查
- ✅ 公平比較 LyraLLM vs Portkey vs Ollama
- ✅ 排除權限開銷的效能數據
- ⚠️ 僅用於測試環境

### 開發環境
```yaml
auth:
  enabled: false  # 可選，方便開發
```
- 🔧 快速開發迭代
- 🔧 簡化測試流程
- ⚠️ 不建議用於生產

## 📊 效能影響分析

### 權限檢查開銷

| 場景 | 估計開銷 | 說明 |
|------|---------|------|
| **單次請求** | 0.1-0.5ms | 記憶體查詢（frozenset） |
| **高並發** | 可能更高 | Python GIL 影響 |
| **首次請求** | +50-100ms | 角色載入和快取 |

### 測試結果對比

**啟用權限時：**
- 延遲測試：+10% 開銷
- 並發測試：+43% 開銷（主要非權限因素）

**關閉權限時：**
- 應與 Portkey/Ollama 相近
- 用於驗證核心路由效能

## 🔒 安全建議

### ⚠️ 重要提醒

1. **生產環境必須啟用權限**
   ```yaml
   auth:
     enabled: true  # 永遠設為 true
   ```

2. **僅在測試環境關閉**
   - 本地開發環境
   - 效能 benchmark 測試
   - 隔離的測試環境

3. **不要透過 HTTP Header 控制**
   - ❌ 不安全：`X-Lyra-Auth-Disabled: true`
   - ✅ 安全：在 config.yaml 配置

4. **審計日誌**
   - 權限關閉時會記錄警告日誌
   - 定期檢查生產環境配置

## 🧪 測試範例

### 完整對比測試

```bash
# 測試 1：啟用權限（真實場景）
python benchmark_gateway_full.py --tests concurrent --concurrency 5

# 測試 2：關閉權限（公平比較）
python benchmark_gateway_full.py --tests concurrent --concurrency 5 --disable-auth

# 比較結果，評估權限系統實際開銷
```

### 快速驗證

```bash
# 驗證權限功能正常
curl -X POST http://localhost:8081/api/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Lyra-Role: standard_user" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]}'

# 應返回 403 Forbidden（如果 standard_user 沒有 gpt-4o 權限）
```

## 📈 效能優化建議

如果權限系統成為瓶頸，考慮：

1. **快取優化**
   - 角色定義已使用 frozen dataclass
   - 權限集合使用 frozenset（O(1) 查詢）

2. **非同步化**
   - 目前權限檢查是同步的
   - 可考慮非同步實現（極少數場景）

3. **連接池調整**
   - 並發問題主要來自連接池
   - 調整 `pool_connections` 和 `pool_maxsize`

4. **Kernel 快取鎖**
   - 檢查 model_executor 的鎖競爭
   - 考慮使用 asyncio.Lock 替代 threading.Lock

## 🔍 故障排除

### 權限關閉後仍有檢查？

檢查：
1. `config.yaml` 中 `auth.enabled: false`
2. 重啟服務載入新配置
3. 查看日誌確認：`Auth system disabled - granting unrestricted access`

### Benchmark 沒有使用 --disable-auth？

確認命令：
```bash
python benchmark_gateway_full.py --tests all --disable-auth
# 應看到：⚠️ 權限檢查已關閉（用於公平效能比較）
```

## 📚 相關文件

- [RBAC 角色管理](../config/README.md)
- [效能優化指南](./performance_optimization.md)
- [Benchmark 工具說明](../benchmark_gateway_full.py)
