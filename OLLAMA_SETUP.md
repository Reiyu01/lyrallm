# Ollama Web Search Plugin 配置指南

## 環境變數設定

在使用 Ollama Web Search Plugin 之前，請設定以下環境變數：

```bash
# 必需 - Ollama Web Search API Key
export OLLAMA_API_KEY="your_ollama_api_key_here"

# 可選 - Web Search API 基礎 URL (預設: https://ollama.com/api)
export OLLAMA_WEB_SEARCH_BASE_URL="https://ollama.com/api"

# 可選 - 請求超時時間(秒) (預設: 30)
export OLLAMA_WEB_SEARCH_TIMEOUT="30"

# 可選 - 最大搜尋結果數量 (預設: 10)
export OLLAMA_WEB_SEARCH_MAX_RESULTS="10"

# 可選 - 啟用/停用 Web Search 功能 (預設: true)
export OLLAMA_WEB_SEARCH_ENABLED="true"

# 可選 - 本地 Ollama 服務 URL (用於模型服務，預設: http://localhost:11434)
export OLLAMA_BASE_URL="http://localhost:11434"
```

## 設定 .env 檔案

1. 複製 `.env.example` 為 `.env`：
```bash
cp .env.example .env
```

2. 編輯 `.env` 檔案，設定您的 Ollama 配置：
```bash
# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434

# Ollama Web Search 配置
OLLAMA_API_KEY=your-ollama-web-search-api-key-here
OLLAMA_WEB_SEARCH_BASE_URL=https://ollama.com/api
OLLAMA_WEB_SEARCH_TIMEOUT=30
OLLAMA_WEB_SEARCH_MAX_RESULTS=10
OLLAMA_WEB_SEARCH_ENABLED=true
```

## 快速設定

### 方法 1: 使用設定腳本
```bash
cd /home/b225nkust/open_web_ui_nkust/semantic_kernel

# 複製環境變數範例檔案
cp .env.example .env

# 編輯 .env 檔案，設定您的 OLLAMA_API_KEY
nano .env

# 載入環境變數並檢查配置
source setup_ollama_env.sh
```

### 方法 2: 手動設定環境變數
```bash
export OLLAMA_API_KEY="your_ollama_api_key_here"
export OLLAMA_WEB_SEARCH_ENABLED="true"
# 其他參數會使用預設值
```

1. 前往 [Ollama 官網](https://ollama.com)
2. 註冊或登入您的帳戶
3. 在 [設定頁面](https://ollama.com/settings/keys) 創建 API Key
4. 將 API Key 設定為環境變數

## 配置檔案設定 (可選)

您也可以在 config.json 中添加 Ollama 配置：

```json
{
  "services": {
    "ollama_web_search": {
      "api_key": "your_ollama_api_key_here",
      "base_url": "https://ollama.com/api",
      "timeout": 30,
      "max_results": 10
    }
  }
}
```

## 測試配置

執行測試檔案來驗證配置：

```bash
cd /home/b225nkust/open_web_ui_nkust/semantic_kernel
python test_ollama_plugin.py
```

## 功能特性

### web_search 函數
- 執行網路搜尋
- 返回結構化搜尋結果
- 支援最大結果數量限制

### web_fetch 函數  
- 抓取指定 URL 的網頁內容
- 提取標題、內容和連結
- 自動內容長度限制

### get_search_status 函數
- 檢查服務狀態
- 列出可用功能
- 驗證 API 連接

## 使用範例

```python
from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin

# 創建 Plugin 實例 (自動從環境變數讀取配置)
plugin = OllamaWebSearchPlugin()

# 或者手動指定配置
plugin = OllamaWebSearchPlugin(
    api_key="your_api_key",
    base_url="https://ollama.com/api",
    timeout=30
)

# 執行搜尋
search_result = await plugin.web_search(
    query="What is Semantic Kernel?",
    max_results=5
)

# 抓取網頁
fetch_result = await plugin.web_fetch(
    url="https://example.com"
)
```

## 整合到 Semantic Kernel

Plugin 會自動整合到 Semantic Kernel 中：

```python
import semantic_kernel as sk

kernel = sk.Kernel()
# ... 添加 LLM 服務 ...

# Plugin 會自動添加 (如果 API Key 已配置)
# 可用函數: ollama_web_search.web_search, ollama_web_search.web_fetch
```

## 故障排除

### 常見錯誤

1. **API Key 錯誤**
   - 檢查環境變數 `OLLAMA_API_KEY` 是否正確設定
   - 驗證 API Key 是否有效且未過期

2. **網路連接問題**
   - 檢查網路連接
   - 確認防火牆設定允許存取 ollama.com

3. **超時錯誤**
   - 增加 `OLLAMA_TIMEOUT` 環境變數值
   - 檢查網路延遲

### 除錯模式

啟用詳細日誌：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 限制與建議

- 免費版有搜尋次數限制
- 建議設定合理的 `max_results` 避免過多資料
- 網頁抓取會自動限制內容長度
- 搜尋結果會截斷過長的內容片段