# 📤 RAG 文檔上傳使用指南

## 🚀 快速開始

### 使用統一上傳腳本
```bash
# 進入專案目錄
cd /home/b225nkust/open_web_ui_nkust/lyrallm

# 執行上傳腳本（會自動上傳 RAG_docs 中的所有文檔）
python3 scripts/upload_documents.py
```

## 📋 腳本功能說明

### ✅ 前置檢查
- Elasticsearch 連線檢查
- Embedding Provider 檢查

### 📄 文檔處理
- 支援格式：`.md`, `.txt`, `.json`
- 自動文檔分塊
- 生成語意 embedding
- 上傳到 Elasticsearch

### 📊 詳細統計
- 總檔案數統計
- 成功/失敗上傳計數
- 詳細錯誤報告
- 處理時間記錄

## 🔧 自定義使用

### 程式化使用 DocumentUploader
```python
from tools.document_uploader import DocumentUploader

# 初始化
uploader = DocumentUploader()

# 上傳單個檔案
result = await uploader.upload_file("/path/to/document.md")

# 上傳整個目錄
result = await uploader.upload_directory("/path/to/documents/")
```

### 配置選項
- `index_name`: 指定 Elasticsearch 索引名稱
- `intent`: 文檔意圖標籤（預設：`nkust_im_docs`）

## 🏢 企業文檔資料

### 目前包含的企業模擬文檔
- 📋 **員工手冊.md**: 公司政策與規範
- 🔧 **技術規範.md**: 開發標準與最佳實踐  
- 📊 **專案管理指南.md**: 專案流程與方法論
- 🎓 **課程資訊.md**: 培訓與學習資源
- ❓ **常見問題集.md**: FAQ 與疑難排解

### 文檔位置
```
/home/b225nkust/open_web_ui_nkust/lyrallm/RAG_docs/
```

## 🔍 驗證上傳結果

### 檢查 Elasticsearch 索引
```bash
# 檢查文檔數量
curl -X GET "localhost:9200/semantic_index/_count?pretty" \
  -H "Authorization: ApiKey YOUR_API_KEY"

# 搜尋測試
curl -X GET "localhost:9200/semantic_index/_search?pretty" \
  -H "Authorization: ApiKey YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": {"match": {"text": "員工"}}}'
```

## 🧠 與 RAG Agent 整合

上傳完成後，文檔會自動整合到 RAG 系統中：

1. **RAG Agent** 會自動檢索相關文檔
2. 提供**語意搜尋**功能
3. 支援**多語言**查詢
4. 返回**結構化結果**

## ⚠️ 注意事項

1. **API Key**: 確保 Elasticsearch API key 設定正確
2. **網路連線**: 確保能連接到 Azure OpenAI 服務
3. **檔案格式**: 僅支援 `.md`, `.txt`, `.json` 格式
4. **檔案編碼**: 支援 UTF-8, GBK, Big5 等編碼

## 🆘 常見問題

### Q: 上傳失敗怎麼辦？
A: 檢查日誌輸出，確認 Elasticsearch 和 Azure OpenAI 連線正常

### Q: 如何添加新的文檔格式？
A: 修改 `DocumentUploader` 中的 `supported_extensions` 設定

### Q: 如何更改索引名稱？
A: 修改 `config.yaml` 中的 `vectordb.index` 設定