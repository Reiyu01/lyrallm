# 聊天系統完整流程說明文檔

## 總覽

本文檔詳細說明聊天系統從API請求到最終回應的完整流程，包含所有可能的分支路徑。流程編號按照最複雜的完整狀況（所有功能都啟用）進行編排。

## 流程架構圖

```
HTTP請求 → API入口 → 模式決策 → Agent協調 → 工具執行 → 結果返回
   #001      #002       #003      #004-020    #021-029    #050
```

## 詳細流程說明

### 第一階段：API接入層 (chat.py)

#### #001: API請求入口點
- **文件**: `/api/chat.py` - `create_chat_completion()`
- **功能**: 接收所有聊天完成的HTTP請求
- **說明**: 整個聊天流程的起點，處理OpenAI格式的聊天API請求

#### #002: 模式決策點 
- **文件**: `/api/chat.py` - 模式判斷邏輯
- **功能**: 根據前端傳來的features參數決定處理方式
- **分支條件**: 
  - 如果 `request.features` 中有任何功能啟用 → 進入Agent模式 (#003A)
  - 如果沒有特殊功能 → 進入直接模式 (#003B)

#### #003A: Agent模式分支
- **文件**: `/api/chat.py` - Agent模式處理
- **功能**: 當啟用任何特殊功能(web_search, image_generation, code_interpreter)時走此分支
- **後續流程**: 調用 `handle_agent_mode_request()` → #004

#### #003B: 直接模式分支 
- **文件**: `/api/chat.py` - 標準模型處理
- **功能**: 使用基本聊天功能，不啟用特殊功能
- **特點**: 跳過Agent協調，直接使用Semantic Kernel基礎功能

### 第二階段：Agent模式處理 (chat.py)

#### #004: Agent模式處理入口
- **文件**: `/api/chat.py` - `handle_agent_mode_request()`
- **功能**: 初始化Agent協調器和聊天服務
- **處理**: 創建模型聊天服務、準備用戶消息

#### #005: 創建Agent協調器
- **文件**: `/api/chat.py` → `practical_agent_orchestrator.py`
- **功能**: 創建PracticalAgentOrchestrator實例
- **作用**: 建立多Agent協作的核心控制器

#### #006: 動態能力註冊
- **文件**: `/api/chat.py` - 能力添加邏輯
- **功能**: 根據features動態啟用相應功能
- **支持功能**:
  - `web_search`: 啟用網路搜尋能力
  - `image_generation`: 圖像生成（未實現）
  - `code_interpreter`: 代碼解釋器（未實現）

#### #007: 處理用戶請求
- **文件**: `/api/chat.py` - 調用orchestrator.process_request()
- **功能**: 將處理權交給Agent協調器
- **流程**: 開始進入多Agent協作流程 → #008

### 第三階段：Agent協調器 (practical_agent_orchestrator.py)

#### #008: Agent協調器主處理流程入口
- **文件**: `practical_agent_orchestrator.py` - `process_request()`
- **功能**: Agent協調器的主要處理邏輯入口
- **初始化**: 重置對話歷史，準備新的請求處理

#### #009: 確定活躍能力
- **文件**: `practical_agent_orchestrator.py` - 能力判斷邏輯
- **功能**: 根據features參數確定當前可用的功能
- **邏輯**: 檢查用戶啟用的功能與系統可用功能的交集

#### #010A: 直接處理分支
- **條件**: 沒有特殊能力時
- **文件**: `practical_agent_orchestrator.py` - `_direct_response()`
- **功能**: 基於現有知識直接回答，不使用外部工具
- **結束**: 直接返回回答 → #050

#### #011: Thinker分析階段
- **文件**: `practical_agent_orchestrator.py` - Thinker分析邏輯
- **功能**: 使用Thinker Agent智能分析用戶請求
- **處理**: 
  1. 調用 `analyze_and_decide()` 生成分析提示
  2. 使用語言模型進行任務分析和決策
  3. 記錄分析結果

#### #012: 決策分支點
- **文件**: `practical_agent_orchestrator.py` - 決策判斷邏輯
- **功能**: 根據Thinker的分析結果選擇處理方式
- **分支條件**:
  - 如果決策包含 "DECISION: WEB_SEARCH" → #013A (WebSearch分支)
  - 其他情況 → #013B (直接回答分支)

#### #013A: WebSearch分支
- **文件**: `practical_agent_orchestrator.py` - `_use_web_search()`
- **功能**: 啟動網路搜尋流程
- **後續**: 進入MCP搜尋流程 → #014

#### #013B: 直接回答分支
- **文件**: `practical_agent_orchestrator.py` - `_extract_or_generate_response()`
- **功能**: 基於Thinker分析結果生成回答
- **結束**: 返回回答 → #050

### 第四階段：WebSearch處理流程 (practical_agent_orchestrator.py)

#### #014: WebSearch處理流程入口
- **文件**: `practical_agent_orchestrator.py` - `_use_web_search()`
- **功能**: WebSearch能力的主要處理邏輯
- **初始化**: 檢查MCP客戶端狀態

#### #015: MCP客戶端初始化檢查
- **文件**: `practical_agent_orchestrator.py` - MCP初始化邏輯
- **功能**: 確保MCP客戶端已正確啟動和配置
- **處理**: 
  1. 檢查web_search_via模式
  2. 創建WebSearchMCPClient實例（如需要）
  3. 啟動MCP連接（如需要）

#### #016: 時間獲取
- **文件**: `practical_agent_orchestrator.py` - 時間獲取邏輯
- **功能**: 獲取當前時間以優化搜尋
- **目的**: 為時效性搜尋（如新聞）提供時間上下文
- **調用**: `mcp_client.get_current_time("readable")` → #026D

#### #017: 搜尋規劃
- **文件**: `practical_agent_orchestrator.py` - 搜尋準備邏輯
- **功能**: 基於時間和分析結果準備搜尋關鍵詞
- **處理**:
  1. 結合用戶請求、Thinker分析、當前時間
  2. 生成搜尋準備提示
  3. 使用語言模型規劃搜尋策略

#### #018: 關鍵詞提取
- **文件**: `practical_agent_orchestrator.py` - 關鍵詞處理邏輯
- **功能**: 從搜尋計劃中提取最佳搜尋關鍵詞
- **邏輯**: 使用正則表達式提取"KEYWORDS:"後的內容

#### #019: MCP搜尋執行
- **文件**: `practical_agent_orchestrator.py` - 搜尋調用邏輯
- **功能**: 調用MCP客戶端執行實際搜尋
- **調用**: `mcp_client.search(query=search_keywords, max_results=5)` → #026A

#### #020: 結果分析合成
- **文件**: `practical_agent_orchestrator.py` - 結果處理邏輯
- **功能**: 分析搜尋結果並生成最終回答
- **處理**: 結合原始請求、搜尋結果、時間信息生成綜合回答

### 第五階段：MCP客戶端層 (web_search_mcp_client.py)

#### #021: MCP客戶端啟動
- **文件**: `web_search_mcp_client.py` - `start()`
- **功能**: 建立與MCP服務器的連接
- **處理**:
  1. 檢查MCP可用性
  2. 創建Semantic Kernel實例
  3. 配置MCPStdioPlugin

#### #022: MCP插件配置
- **文件**: `web_search_mcp_client.py` - MCPStdioPlugin配置
- **功能**: 配置MCP連接參數和工具載入
- **設置**:
  - 名稱: "WebSearchMCP"
  - 載入工具: True
  - 載入提示: False
  - 超時: 30秒

#### #023: MCP工具調用
- **文件**: `web_search_mcp_client.py` - `_invoke_tool()`
- **功能**: 通過Semantic Kernel執行MCP工具
- **處理**: 將工具調用轉換為Kernel函式調用

#### #024: Kernel工具執行
- **文件**: `web_search_mcp_client.py` - Kernel執行邏輯
- **功能**: 使用Semantic Kernel的函式調用機制
- **技術**: KernelArguments + kernel.invoke()

#### #025: 結果處理
- **文件**: `web_search_mcp_client.py` - 結果格式化
- **功能**: 處理和格式化工具執行結果
- **處理**: 提取TextContent中的文字內容

#### #026A-D: 具體工具調用
- **#026A**: `search()` - 執行網路搜尋
- **#026B**: `web_fetch()` - 抓取指定網頁內容  
- **#026C**: `get_search_status()` - 檢查搜尋服務狀態
- **#026D**: `get_current_time()` - 獲取當前時間

### 第六階段：MCP服務器層 (web_search_mcp_server.py)

#### #027: MCP服務器創建
- **文件**: `web_search_mcp_server.py` - `create_server()`
- **功能**: 創建FastMCP服務器並註冊工具
- **架構**: FastMCP + OllamaWebSearchPlugin

#### #028A-D: 工具實現
- **#028A**: `search()` - 搜尋工具實現，執行實際網路搜尋
- **#028B**: `web_fetch()` - 網頁抓取工具實現
- **#028C**: `get_search_status()` - 狀態查詢工具實現
- **#028D**: `get_current_time()` - 時間工具實現

#### #029: MCP服務器啟動
- **文件**: `web_search_mcp_server.py` - `main()`
- **功能**: 啟動stdio傳輸模式的MCP服務器
- **模式**: 子進程模式，通過stdin/stdout與客戶端通信

### 第七階段：結果返回 (chat.py)

#### #050: 格式轉換
- **文件**: `/api/chat.py` - OpenAI格式轉換
- **功能**: 將Agent結果轉換為OpenAI兼容的聊天完成格式
- **輸出**: 返回給前端的最終HTTP響應

## Agent定義層

#### #030: Thinker Agent定義
- **文件**: `thinker_agent.py` - ThinkerAgent類
- **功能**: 主控思考協調者，負責任務分析和決策
- **作用**: 提供決策邏輯和指令模板

#### #040: WebSearch Agent定義  
- **文件**: `web_search_agent.py` - WebSearchAgent類
- **功能**: 專業網路搜尋執行者
- **注意**: 在MCP架構下主要提供指令模板，實際搜尋由MCP Server執行

## 分支路徑總結

### 完整WebSearch流程
```
#001 → #002 → #003A → #004 → #005 → #006 → #007 → #008 → #009 → #011 → #012 → #013A → #014 → #015 → #016 → #017 → #018 → #019 → (#021-#029) → #020 → #050
```

### 直接回答流程（Agent模式）
```
#001 → #002 → #003A → #004 → #005 → #006 → #007 → #008 → #009 → #011 → #012 → #013B → #050
```

### 無特殊能力流程（Agent模式）
```
#001 → #002 → #003A → #004 → #005 → #006 → #007 → #008 → #009 → #010A → #050
```

### 基本聊天流程（直接模式）
```
#001 → #002 → #003B → #050
```

## 技術特點

1. **模組化設計**: 每個階段都有明確的職責分工
2. **多分支支援**: 支援不同複雜度的處理路徑
3. **MCP架構**: 使用Model Context Protocol實現工具調用
4. **時間感知**: 智能處理時效性搜尋需求
5. **錯誤容忍**: 多層級的錯誤處理和降級機制
6. **異步處理**: 全程使用異步模式確保性能

## 調試要點

- **流程追蹤**: 每個編號對應的日誌輸出可用於追蹤執行路徑
- **分支判斷**: 注意#002、#009、#012等關鍵決策點的條件
- **MCP連接**: #015、#021-#022是MCP連接的關鍵檢查點
- **錯誤處理**: 每個階段都有對應的異常處理機制

此流程文檔提供了系統的完整運行邏輯，可用於開發調試、性能優化和功能擴展。