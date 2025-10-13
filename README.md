# 🚀 LyraLLM - 企業級 AI Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

**LyraLLM** 是一個智能的企業級 AI Gateway，提供多模型路由、成本優化、負載平衡和用戶分層管理功能。

---

## 📋 目錄

- [🎯 專案概述](#專案概述)
- [✨ 核心功能](#核心功能)
- [🏗️ 架構設計](#架構設計)
- [📁 專案結構](#專案結構)
- [⚙️ 配置系統](#配置系統)
- [🚀 快速開始](#快速開始)
- [📊 功能狀態](#功能狀態)
- [🛣️ 發展路線圖](#發展路線圖)
- [🤝 貢獻指南](#貢獻指南)
- [📝 變更記錄](#變更記錄)

---

## 🎯 專案概述

### 專案定位
LyraLLM 是一個**智能 AI 請求路由系統**，類似於 API Gateway，但專為 AI 模型設計。它能夠：
- 自動選擇最適合的 AI 模型處理請求
- 優化成本和效能
- 提供企業級的穩定性和可控性

### 核心價值
- **🧠 智能路由**: 基於意圖分析自動選擇最佳模型
- **💰 成本優化**: 實時成本計算與預算控制
- **⚡ 效能最佳化**: 多層快取與負載平衡
- **🔒 企業級安全**: 用戶分層與權限管理
- **📈 可觀測性**: 完整的監控與分析

---

## ✨ 核心功能

### 🎯 智能路由系統

#### ✅ **已實現 - 向量相似度路由**
```python
# 現有 SemanticRouter 功能
- Elasticsearch 向量檢索
- 意圖投票機制 (confidence threshold: 0.55)
- 多種 Embedding 提供商支援
- 自動 fallback 機制
```

#### 🚧 **開發中 - 混合智能路由**
```yaml
兩階段路由架構:
  階段1_聚合意圖分析:
    - Vector 檢索 (5-20ms) + O3-mini 推理 (200-500ms)
    - 並行/漸進式處理模式
    - 智能融合與衝突解決
    
  階段2_規則決策執行:
    - 企業級規則引擎
    - 成本與效能優化
    - 用戶分層權限控制
```

### 💰 成本管理系統

#### ✅ **已實現 - 價格資料庫**
- 完整的模型價格表 (23,000+ 模型配置)
- 實時成本計算 API
- 預算管理配置

#### 🚧 **開發中 - 動態成本優化**
- 用戶分層預算控制
- 成本感知路由決策
- 預算預警與緊急停止

### 🏢 企業級功能

#### ✅ **已實現 - 配置管理**
```yaml
分離式配置架構:
- config.yaml: 系統核心配置
- routing_rules.yaml: 業務路由規則  
- model_prices_*.json: 價格資訊
- 支援熱更新與環境變數
```

#### 🚧 **規劃中 - 高可用性**
- 多層故障轉移
- 熔斷器模式
- 健康檢查與自動恢復

---

## 🏗️ 架構設計

### 系統架構圖
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   用戶請求       │ →  │  FastAPI Gateway │ →  │   ModelExecutor  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                        ┌─────────────────────────────┴─────────────────────────────┐
                        │                                                           │
              ┌─────────▼─────────┐                                    ┌─────────▼─────────┐
              │  HybridRouter     │                                    │  Direct Routing   │
              │  (智能路由)        │                                    │  (直接指定模型)    │
              └─────────┬─────────┘                                    └───────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
┌───────▼───────┐              ┌───────▼───────┐
│ 階段1_意圖分析  │              │ 階段2_規則決策  │
│               │              │               │
│ ┌───────────┐ │              │ ┌───────────┐ │
│ │ Vector    │ │              │ │ 企業規則   │ │
│ │ 檢索      │ │              │ │ 引擎      │ │
│ └───────────┘ │              │ └───────────┘ │
│       +       │              │       │      │
│ ┌───────────┐ │              │ ┌───────────┐ │
│ │ O3-mini   │ │              │ │ 成本控制   │ │
│ │ SLM 分析  │ │              │ │ 模組      │ │
│ └───────────┘ │              │ └───────────┘ │
└───────────────┘              └───────┬───────┘
        │                              │
        └──────────────┬─────────────────┘
                       │
               ┌───────▼───────┐
               │  最終模型選擇   │
               │  Azure OpenAI │
               │  OpenAI       │
               │  Anthropic    │
               │  Ollama       │
               └───────────────┘
```

### 技術棧
```yaml
後端框架:
  - FastAPI: REST API 服務
  - Semantic Kernel: AI 模型整合
  - Pydantic: 資料驗證

資料儲存:
  - Elasticsearch: 向量資料庫
  - Redis: 快取與事件匯流排  
  - PostgreSQL: 分析資料 (可選)

AI 整合:
  - Azure OpenAI: GPT-4o, O1, O3-mini
  - OpenAI: 原生 API 支援
  - Anthropic: Claude 系列
  - Ollama: 本地模型部署

監控分析:
  - ELK Stack: 日誌分析
  - 自定義分析適配器
  - 效能指標追蹤
```

---

## 📁 專案結構

```
lyrallm/
├── 📄 README.md                    # 專案說明文件
├── 📄 requirements.txt             # Python 依賴
├── 📄 main.py                      # FastAPI 應用程式入口
├── 📄 config.yaml                  # 系統核心配置
├── 📄 intents.json                 # 意圖範例資料
│
├── 📁 api/                         # REST API 層
│   ├── chat.py                     # 聊天完成 API
│   ├── models.py                   # 模型資訊 API
│   └── chat_backup*.py             # API 備份版本
│
├── 📁 core/                        # 核心業務邏輯
│   ├── __init__.py                 # 模組匯出
│   ├── model_executor.py           # ✅ 主要路由執行器
│   ├── semantic_router.py          # ✅ 向量語義路由
│   └── model_manager.py            # ✅ 模型健康管理
│
├── 📁 config/                      # 配置管理
│   ├── config_manager.py           # ✅ 配置載入器
│   ├── routing_rules.yaml          # ✅ 企業路由規則
│   ├── model_prices_*.json         # ✅ 模型價格資料
│   └── plugin_*.yaml               # 插件配置
│
├── 📁 adapters/                    # 外部服務適配器
│   ├── base.py                     # 適配器基類
│   ├── factory.py                  # 適配器工廠
│   ├── elasticsearch_adapter.py    # ✅ ES 向量檢索
│   └── postgres_adapter.py         # 關係型資料庫
│
├── 📁 embedding_provider.py        # ✅ 多提供商 Embedding
├── 📁 logger_service/              # 日誌與事件系統
├── 📁 agents/                      # Multi-Agent 系統  
├── 📁 plugins/                     # 插件系統
├── 📁 scripts/                     # 部署與工具腳本
├── 📁 infrastructure/              # 基礎設施配置
│   ├── kibana-dashboard.json       # Kibana 儀表板
│   └── logstash-*.conf            # Logstash 配置
│
└── 📁 tests/                       # 測試檔案
    ├── test_auto_routing.py        # ✅ 自動路由測試
    ├── test_enterprise_routing.py  # ✅ 企業級路由測試
    ├── test_config_separation.py   # ✅ 配置分離測試
    └── test_o3_mini_slm.py         # 🚧 O3-mini SLM 測試
```

**圖例說明:**
- ✅ **已實現**: 功能完整且測試通過
- 🚧 **開發中**: 正在實現或測試中
- 📋 **計劃中**: 已設計但未開始實現

---

## ⚙️ 配置系統

### 配置檔案架構

#### 1. **config.yaml** - 系統核心配置
```yaml
功能範圍:
  - 伺服器設定 (host, port, debug)
  - 模型註冊與提供商配置
  - 路由系統總開關與策略選擇
  - Vector+SLM 聯合分析配置
  - 外部服務整合 (ES, Redis, 等)

關鍵配置:
  models.routing.strategy: "hybrid"     # 路由策略
  models.routing.intent_analysis: {...} # 意圖分析配置
```

#### 2. **routing_rules.yaml** - 企業路由規則
```yaml
功能範圍:
  - 用戶分層管理 (basic/premium/enterprise)
  - 成本控制與預算管理
  - 優先級路由規則 (priority 1-10)
  - 故障轉移策略
  - O3-mini SLM 專用 Prompt

關鍵配置:
  user_tiers: {...}        # 用戶分層
  routing_rules: [...]     # 路由決策規則
  slm_analysis: {...}      # SLM 分析配置
```

#### 3. **model_prices_and_context_window.json** - 價格資料庫
```yaml
功能範圍:
  - 23,000+ 模型價格資訊
  - 輸入/輸出 token 成本
  - Context window 限制
  - 批次處理折扣價格
  - 快取讀取成本

使用場景:
  - 實時成本計算
  - 預算控制決策
  - 成本效益路由優化
```

### 環境變數
```bash
# Azure OpenAI 配置
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_O3MINI_DEPLOYMENT_NAME=o3-mini

# Elasticsearch 配置
ES_ENDPOINT=http://localhost:9200
ES_LOCAL_API_KEY=your-es-key

# Redis 配置 (可選)
REDIS_URL=redis://localhost:6379/0
```

---

## 🚀 快速開始

### 環境要求
- Python 3.8+
- Elasticsearch 7.0+
- Redis 6.0+ (可選，用於事件匯流排)

### 安裝步驟

#### 1. 克隆專案
```bash
git clone https://github.com/Reiyu01/lyrallm.git
cd lyrallm
```

#### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

#### 3. 配置環境變數
```bash
cp .env.example .env
# 編輯 .env 檔案，填入您的 API keys
```

#### 4. 啟動服務
```bash
# 開發模式
python main.py

# 生產模式
uvicorn main:app --host 0.0.0.0 --port 8081
```

#### 5. 測試路由功能
```bash
# 測試自動路由
python test_auto_routing.py

# 測試企業級路由
python test_enterprise_routing.py

# 測試配置載入
python test_config_separation.py
```

### API 使用範例

#### 基本聊天完成
```bash
curl -X POST "http://localhost:8081/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "請幫我寫一個 Python 排序函數"}
    ]
  }'
```

#### 指定模型
```bash
curl -X POST "http://localhost:8081/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "user", "content": "分析這份資料"}
    ],
    "temperature": 0.7,
    "max_tokens": 1000
  }'
```

---

## 📊 功能狀態

### ✅ 已完成功能

| 功能模組 | 狀態 | 說明 | 測試覆蓋 |
|---------|------|------|----------|
| **基礎路由系統** | ✅ 完成 | SemanticRouter + ModelExecutor | ✅ 測試完整 |
| **向量檢索路由** | ✅ 完成 | Elasticsearch 向量相似度匹配 | ✅ 測試完整 |
| **多提供商支援** | ✅ 完成 | Azure OpenAI, OpenAI, Ollama | ✅ 測試完整 |
| **配置管理系統** | ✅ 完成 | 分離式配置 + 熱更新支援 | ✅ 測試完整 |
| **價格資料庫** | ✅ 完成 | 23,000+ 模型價格 + 成本計算 API | ✅ 測試完整 |
| **Embedding 支援** | ✅ 完成 | 多提供商 embedding (Azure, OpenAI, SentenceTransformer) | ✅ 測試完整 |
| **事件匯流排** | ✅ 完成 | Redis Streams + 本地 Queue 雙模式 | ⚠️ 部分測試 |

### 🚧 開發中功能

| 功能模組 | 進度 | 說明 | 預計完成 |
|---------|------|------|----------|
| **O3-mini SLM 分析器** | 80% | 意圖分析 + JSON 結構化輸出 | 本週 |
| **Vector+SLM 聚合** | 60% | 並行/漸進式處理 + 智能融合 | 2週內 |
| **企業規則引擎** | 40% | 優先級規則 + 條件匹配邏輯 | 3週內 |
| **成本感知路由** | 30% | 預算控制 + 成本優化決策 | 1個月內 |

### 📋 計劃中功能

| 功能模組 | 優先級 | 說明 | 預計開始 |
|---------|--------|------|----------|
| **熔斷器模式** | 高 | 故障檢測 + 自動降級 | 下個月 |
| **負載平衡器** | 高 | 多策略負載分散 | 下個月 |
| **健康檢查系統** | 中 | 實時模型狀態監控 | 2個月內 |
| **Qdrant 支援** | 中 | 高效能向量資料庫選項 | 2個月內 |
| **機器學習優化** | 低 | 自適應路由參數調整 | 未來規劃 |

---

## 🛣️ 發展路線圖

### 📅 Q1 2025 - 核心智能路由
- [x] ~~基礎向量路由系統~~ ✅
- [x] ~~配置分離架構~~ ✅  
- [x] ~~價格資料庫整合~~ ✅
- [ ] O3-mini SLM 分析器完成
- [ ] Vector+SLM 聯合處理
- [ ] 企業規則引擎 MVP

### 📅 Q2 2025 - 企業級功能
- [ ] 用戶分層與權限管理
- [ ] 成本控制與預算管理
- [ ] 熔斷器與故障轉移
- [ ] 負載平衡策略
- [ ] 完整監控儀表板

### 📅 Q3 2025 - 效能與擴展
- [ ] Qdrant 向量資料庫支援
- [ ] 分散式部署架構
- [ ] 機器學習路由優化
- [ ] A/B 測試框架
- [ ] GraphQL API 支援

### 📅 Q4 2025 - 生態系統
- [ ] Plugin 系統完善
- [ ] Multi-Agent 協調
- [ ] 第三方整合 (LangChain, etc.)
- [ ] 企業 SSO 整合
- [ ] 合規性與稽核功能

---

## 🔧 開發指南

### 程式碼結構原則

#### 1. **關注點分離**
```python
# ✅ 良好的分離
core/model_executor.py     # 路由執行邏輯
core/semantic_router.py    # 向量檢索邏輯  
config/config_manager.py   # 配置管理邏輯
adapters/                  # 外部服務適配

# ❌ 避免混合關注點
# 不要在 API 層直接操作資料庫
# 不要在核心邏輯中硬編碼配置
```

#### 2. **依賴注入模式**
```python
# ✅ 使用依賴注入
class ModelExecutor:
    def __init__(self, config_manager, model_manager):
        self.config = config_manager
        self.models = model_manager

# ✅ 工廠模式創建
def get_default_executor():
    return ModelExecutor(
        config_manager=config_manager,
        model_manager=get_model_manager_sync()
    )
```

#### 3. **配置驅動設計**
```python
# ✅ 所有行為都可配置
routing_strategy = config_manager.get_routing_strategy()

if routing_strategy == "hybrid":
    router = HybridRouter()
elif routing_strategy == "vector_only":
    router = VectorOnlyRouter()
```

### 測試策略

#### 1. **單元測試** 
```python
# 每個核心類別都有對應測試
test_model_executor.py     # ModelExecutor 功能測試
test_semantic_router.py    # SemanticRouter 功能測試
test_config_manager.py     # ConfigManager 功能測試
```

#### 2. **整合測試**
```python
# 端到端功能測試
test_auto_routing.py       # 自動路由完整流程
test_enterprise_routing.py # 企業級功能測試
test_api_flow.py          # API 層整合測試
```

#### 3. **效能測試**
```python
# 效能基準測試
benchmark_routing_speed.py  # 路由決策延遲測試
benchmark_throughput.py     # 吞吐量測試
load_test_concurrent.py     # 併發負載測試
```

### 新功能開發流程

#### 1. **功能規劃階段**
1. 在 GitHub Issues 中創建功能需求
2. 更新 README.md 中的功能狀態表
3. 設計 API 介面和配置結構
4. 評估對現有系統的影響

#### 2. **實現階段**
1. 創建功能分支: `feature/smart-load-balancer`
2. 實現核心邏輯 (core/ 目錄)
3. 添加配置選項 (config.yaml, routing_rules.yaml)
4. 更新 ConfigManager (如需要)
5. 編寫單元測試

#### 3. **整合階段**  
1. 編寫整合測試
2. 更新 API 文檔
3. 效能測試與優化
4. 更新 README.md 功能狀態
5. 創建 Pull Request

#### 4. **部署階段**
1. 代碼審查 (Code Review)
2. CI/CD 管道測試
3. 漸進式部署 (Canary Deployment)
4. 監控與回饋收集

---

## 🔍 監控與偵錯

### 日誌系統
```yaml
日誌層級:
  - DEBUG: 詳細執行流程 (開發環境)
  - INFO: 關鍵操作記錄 (生產環境)  
  - WARNING: 異常但可恢復的情況
  - ERROR: 錯誤與異常情況

日誌檔案:
  - lyrallm.log: 主要應用程式日誌
  - semantic_kernel.log: Semantic Kernel 日誌  
  - service.log: 服務層日誌
```

### 效能指標
```yaml
關鍵指標:
  - 路由決策延遲 (target: <100ms)
  - API 回應時間 (target: <2s)
  - 模型成功率 (target: >95%)
  - 成本效益比 (持續優化)

監控工具:
  - ELK Stack: 日誌分析與視覺化
  - 自定義指標: Token 使用與成本追蹤
  - 健康檢查: 模型可用性監控
```

### 常見問題偵錯

#### 1. **路由決策問題**
```bash
# 檢查路由配置
python test_config_separation.py

# 測試特定路由邏輯
python test_auto_routing.py

# 檢查向量資料庫連接
curl -X GET "http://localhost:9200/_cluster/health"
```

#### 2. **模型連接問題**  
```bash
# 檢查模型配置
python -c "from lyrallm.config.config_manager import config_manager; print(config_manager.get_available_models())"

# 測試 Azure OpenAI 連接
python -c "import os; print('AZURE_OPENAI_ENDPOINT:', os.getenv('AZURE_OPENAI_ENDPOINT'))"
```

#### 3. **效能問題**
```bash
# 檢查系統資源
htop
df -h

# 檢查 Elasticsearch 效能
curl -X GET "http://localhost:9200/_nodes/stats"

# 檢查 Redis 連接 (如使用)
redis-cli ping
```

---

## 🤝 貢獻指南

### 參與方式
1. **功能建議**: 在 GitHub Issues 中提出新功能想法
2. **Bug 回報**: 提供詳細的錯誤重現步驟
3. **代碼貢獻**: Fork 專案並提交 Pull Request
4. **文檔改進**: 修正或擴展技術文檔
5. **測試用例**: 增加測試覆蓋率

### 代碼風格
```python
# 遵循 PEP 8 風格指南
# 使用 Black 格式化工具
# 類型註解 (Type Hints)
def route_model(query: str, context: Dict[str, Any]) -> RoutingResult:
    """Route request to appropriate model."""
    pass

# 清晰的文檔字串
class ModelExecutor:
    """Enterprise-grade model executor with intelligent routing.
    
    Features:
    - Auto model selection via semantic routing
    - Multi-provider support (Azure OpenAI, OpenAI, Ollama)  
    - Comprehensive error handling and fallback strategies
    """
```

### Commit 訊息格式
```
<type>(<scope>): <description>

feat(routing): add O3-mini SLM analyzer
fix(config): resolve environment variable loading issue  
docs(readme): update architecture diagram
test(routing): add enterprise routing test cases
refactor(core): improve model executor error handling
```

---

## 📞 聯絡資訊

### 專案維護者
- **主要開發者**: [GitHub Profile](https://github.com/Reiyu01)
- **專案倉庫**: [LyraLLM Repository](https://github.com/Reiyu01/lyrallm)

### 技術支援
- **Issues**: [GitHub Issues](https://github.com/Reiyu01/lyrallm/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Reiyu01/lyrallm/discussions)
- **Documentation**: [Wiki Pages](https://github.com/Reiyu01/lyrallm/wiki)

### 社群
- **Discord**: [加入討論群組](#) (待建立)
- **Slack**: [開發者頻道](#) (待建立)

---

## 📝 變更記錄

### v0.3.0 (2025-01-13) - 智能路由架構
- ✨ **新功能**: 添加 O3-mini SLM 分析器支援
- ✨ **新功能**: Vector+SLM 聯合意圖分析架構
- ✨ **新功能**: 企業級路由規則配置系統
- 🔧 **改進**: 配置檔案分離 (config.yaml + routing_rules.yaml)
- 🔧 **改進**: 完整的價格資料庫整合 (23,000+ 模型)
- 📚 **文檔**: 全面的 README.md 和架構說明

### v0.2.0 (2025-01-01) - 基礎路由系統
- ✨ **新功能**: SemanticRouter 向量相似度路由
- ✨ **新功能**: ModelExecutor 統一模型執行器
- ✨ **新功能**: 多提供商支援 (Azure OpenAI, OpenAI, Ollama)
- ✨ **新功能**: Elasticsearch 向量資料庫整合
- 🔧 **改進**: 配置管理系統 (ConfigManager)
- 🔧 **改進**: 事件匯流排架構 (Redis Streams + 本地 Queue)

### v0.1.0 (2024-12-01) - 專案初始化
- 🎉 **初始發布**: FastAPI 基礎架構
- ✨ **新功能**: 基本聊天完成 API
- ✨ **新功能**: Semantic Kernel 整合
- 🔧 **設置**: 專案結構和依賴管理

---

## 📄 授權條款

本專案採用 [MIT License](LICENSE) 開源授權。

```
MIT License

Copyright (c) 2024 LyraLLM Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,  
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🌟 致謝

### 開源專案感謝
- **FastAPI**: 現代高效能 Web 框架
- **Semantic Kernel**: Microsoft AI 編排框架
- **Elasticsearch**: 強大的搜索與分析引擎
- **Pydantic**: 資料驗證與設定管理
- **Redis**: 高效能記憶體資料庫

### 特別感謝
感謝所有為 LyraLLM 專案貢獻代碼、文檔、測試和想法的開發者與使用者! 🙏

---

<div align="center">

**🚀 LyraLLM - 讓 AI 路由更智能！**

[![GitHub stars](https://img.shields.io/github/stars/Reiyu01/lyrallm.svg?style=social&label=Star)](https://github.com/Reiyu01/lyrallm)
[![GitHub forks](https://img.shields.io/github/forks/Reiyu01/lyrallm.svg?style=social&label=Fork)](https://github.com/Reiyu01/lyrallm/fork)

[⭐ 給專案一個星星](https://github.com/Reiyu01/lyrallm) | [🐛 回報問題](https://github.com/Reiyu01/lyrallm/issues) | [💡 功能建議](https://github.com/Reiyu01/lyrallm/discussions)

</div>