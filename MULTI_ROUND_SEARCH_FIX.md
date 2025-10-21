# Agent系統多輪搜尋修復 - 解決任務不執行問題

## 問題診斷

### 發現的問題
從日誌可以看到：

1. **策略制定成功**：Agent正確識別需要3個搜尋任務
   ```
   SEARCH_TASKS: 
   1. 查詢內部技術規範的詳細內容（例如技術文檔、標準規範） | 
   2. 搜尋目前主流技術標準或行業標準的相關信息 | 
   3. 比較內部技術規範與主流技術標準的差異

   SEARCH_TYPES: RAG | WEB | MIXED
   ```

2. **解析問題**：只解析出1個任務，應該是3個
   ```
   📝 搜尋任務: 1 個
   └─ 任務 1: (RAG) 1. 查詢內部技術規範的詳細內容...
   ```

3. **決策邏輯問題**：Agent判斷需要更多資料，但沒有執行第二輪搜尋
   ```
   SUFFICIENT: NO  
   🔄 ThinkerAgent Agent決定繼續搜尋以獲取更多資料
   🔄 ThinkerAgent 開始生成最終回答...  // 直接跳到最終回答！
   ```

## 修復方案

### 1. 修復策略解析邏輯
**問題**：多行格式的SEARCH_TASKS只解析了第一行
**解決**：支持編號格式的多行任務解析

```python
# 新的解析邏輯：支持編號格式
tasks_match = re.search(r'SEARCH_TASKS:\s*\n*(.*?)(?=\n\w+:|$)', strategy_text, re.IGNORECASE | re.DOTALL)
if tasks_match:
    tasks_content = tasks_match.group(1).strip()
    if re.search(r'\d+\.', tasks_content):
        # 按編號分割：1. 任務1  2. 任務2
        tasks = re.findall(r'\d+\.\s*([^|]+)', tasks_content)
        strategy['tasks'] = [task.strip() for task in tasks if task.strip()]
```

### 2. 重構多輪搜尋邏輯
**問題**：固定的for循環無法動態添加任務
**解決**：改為while循環，支持動態添加搜尋任務

```python
# 新邏輯：動態執行搜尋任務
task_index = 0
while task_index < len(search_tasks) and task_index < max_rounds:
    # 執行搜尋
    search_result = await self._execute_search_with_validation(current_task, current_type)
    
    # Agent評估並建議下一個搜尋
    should_continue, next_search = await self._smart_continuation_decision(user_query, task_index + 1, len(search_tasks))
    
    # 動態添加新任務
    if should_continue and next_search:
        if next_search.get('type') not in existing_types:
            search_tasks.append(next_search['query'])
            search_types.append(next_search['type'])
```

### 3. 增強決策系統
**問題**：Agent決策後沒有具體的搜尋建議
**解決**：讓Agent同時返回決策和搜尋建議

```python
# 增強的決策提示
請按此格式回應：
SUFFICIENT: [YES|NO] (資料是否足夠)
CONFIDENCE: [1-10] (信心分數)
REASON: [決策理由]
MISSING: [如果不足夠，缺少什麼關鍵資訊]
NEXT_SEARCH_TYPE: [如果需要繼續，建議RAG或WEB]
NEXT_SEARCH_QUERY: [如果需要繼續，建議具體的搜尋查詢]

# 新的返回值
return (should_continue, next_search_suggestion)
```

### 4. 智能搜尋類型選擇
**邏輯**：
- 如果只有RAG搜尋，建議WEB搜尋獲取外部資料
- 如果只有WEB搜尋，建議RAG搜尋獲取內部資料  
- 避免重複相同類型的搜尋

## 修改的文件

### `/agents/thinker_agent.py`
1. ✅ 修復 `_parse_strategy` - 支持多行編號格式任務解析
2. ✅ 重構 `_multi_round_search_process` - 動態任務執行邏輯
3. ✅ 增強 `_smart_continuation_decision` - 返回具體搜尋建議
4. ✅ 修改方法簽名 - 返回tuple[bool, dict]

## 預期修復效果

### 策略制定階段
```
📝 搜尋任務: 3 個
  └─ 任務 1: (RAG) 查詢內部技術規範的詳細內容
  └─ 任務 2: (WEB) 搜尋目前主流技術標準或行業標準的相關信息  
  └─ 任務 3: (MIXED) 比較內部技術規範與主流技術標準的差異
```

### 執行階段
```
🔍 第 1 輪搜尋 (RAG): 查詢內部技術規範...
✅ 第 1 輪搜尋完成
🤔 Agent評估：資料不足，建議WEB搜尋
🔍 第 2 輪搜尋 (WEB): 搜尋主流技術標準...
✅ 第 2 輪搜尋完成  
🤔 Agent評估：資料充足，開始生成回答
```

### 最終結果
- ✅ 完整的RAG + WEB搜尋流程
- ✅ 基於內外部資料的詳細比較分析
- ✅ 智能的決策過程，避免過度或不足搜尋

## 測試建議

使用同樣的查詢再次測試：
```
我們的技術規範與目前主流技術標準（請上網搜尋），再做兩者的比較
```

**期望看到的日誌**：
1. 解析出3個搜尋任務
2. 執行第1輪RAG搜尋
3. Agent評估不足夠，建議WEB搜尋
4. 執行第2輪WEB搜尋
5. Agent評估充足，生成最終回答

如果仍有問題，可進一步調試：
- 檢查策略解析是否正確提取了所有任務
- 確認Agent決策回應的格式
- 驗證動態任務添加邏輯