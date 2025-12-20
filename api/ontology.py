from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from ontology.store import ontology_store
from auth.dependencies import get_request_security_context, RequestSecurityContext

router = APIRouter(prefix="/api/ontology", tags=["Ontology"])

@router.get("/stats/overview")
async def get_ontology_stats(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """獲取本體統計概覽"""
    return ontology_store.get_stats()

@router.get("/graph")
async def get_ontology_graph(
    max_nodes: int = Query(100, ge=1, le=1000),
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """獲取本體圖譜數據 (用於可視化)"""
    all_objects = ontology_store.get_all_objects()
    
    # 限制節點數量
    nodes = []
    edges = []
    
    # 簡單的節點選擇策略：取前 max_nodes 個
    # 實際生產中應該有更智能的查詢或過濾
    selected_objects = all_objects[:max_nodes]
    selected_ids = set(obj.object_id for obj in selected_objects)
    
    for obj in selected_objects:
        # 獲取對象名稱/標題
        label = obj.title if obj.title else obj.object_id[:8]
        
        # 獲取屬性 (從 metadata 中提取)
        attributes = obj.metadata.get("attributes", {})
        
        # 如果標題為空，嘗試從屬性中找到合適的標籤
        if not obj.title and attributes:
            for key in ['name', 'title', 'label', 'id', 'subject']:
                if key in attributes and attributes[key]:
                    label = str(attributes[key])
                    break
        
        nodes.append({
            "id": obj.object_id,
            "label": label,
            "type": obj.object_type.value if hasattr(obj.object_type, 'value') else str(obj.object_type),
            "properties": attributes
        })
        
    # 收集關係
    for ontology in ontology_store.get_all_ontologies():
        for rel in ontology.relationships:
            # 根據 ontology_generator.py 中的結構:
            # {"child_id": ..., "parent_id": ..., "type": "parent_child", ...}
            
            child_id = rel.get("child_id")
            parent_id = rel.get("parent_id")
            
            # 只返回兩端都在選定節點中的關係
            if child_id in selected_ids and parent_id in selected_ids:
                edges.append({
                    "source": parent_id, # Parent 指向 Child
                    "target": child_id,
                    "label": rel.get("type", "related_to")
                })
                
    return {
        "nodes": nodes,
        "edges": edges
    }
