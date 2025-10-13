# 🎯 LyraLLM 專案快速概覽

## 什麼是 LyraLLM？
**智能 AI Gateway** - 自動選擇最適合的 AI 模型來處理用戶請求

```
用戶問："幫我寫一個 Python 函數" 
↓
LyraLLM 自動分析: 這是程式碼生成，複雜度高 
↓  
路由到: GPT-4 (最適合程式碼生成)
```

## 🚀 核心價值
- **自動路由**: 不用手動選模型，系統自動選最佳的
- **成本優化**: 簡單問題用便宜模型，複雜問題用好模型  
- **企業級**: 支援用戶分層、預算控制、故障轉移

## 📁 重要檔案
```
lyrallm/
├── README.md                    # 📖 完整專案說明
├── config.yaml                  # ⚙️ 系統設定
├── config/routing_rules.yaml    # 📋 路由規則
├── core/model_executor.py       # 🎯 主路由器
├── test_*.py                    # 🧪 測試檔案
```

## 🎛️ 目前狀態 (2025-01-13)

### ✅ 已完成
- 基礎向量路由 (SemanticRouter)
- 多 AI 供應商支援 (Azure OpenAI, OpenAI, Ollama)
- 價格資料庫 (23,000+ 模型價格)
- 配置管理系統

### 🚧 開發中
- O3-mini 智能分析器 (80% 完成)
- Vector+SLM 聯合路由 (60% 完成)
- 企業規則引擎 (40% 完成)

## 🔧 快速測試
```bash
# 測試基本路由
python test_auto_routing.py

# 測試配置載入
python test_config_separation.py

# 測試 O3-mini 分析器
python test_o3_mini_slm.py
```

## 🎯 下一步計劃
1. 完成 O3-mini SLM 分析器
2. 實現 Vector+SLM 聯合處理  
3. 企業規則引擎實現
4. 成本控制與預算管理

## 💡 給 AI Agent 的提示
- 專案使用 **FastAPI + Semantic Kernel** 架構
- 配置驅動設計，所有行為都可通過 YAML 配置
- 採用 **關注點分離** 原則，核心邏輯在 `core/` 目錄
- 測試驅動開發，每個功能都有對應測試
- 遵循 **企業級標準**，支援熱更新、故障轉移、監控

查看完整說明請參考 [README.md](./README.md)