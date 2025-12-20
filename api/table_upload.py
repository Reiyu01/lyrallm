"""
表格上傳 API
處理文件上傳、解析、預覽和本體生成
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import pandas as pd
import numpy as np
import io

from ontology.table_parser import parse_table_file, TableSchema, ColumnSchema, TableParser
from ontology.ontology_generator import OntologyGenerator, GenerationResult
from ontology.store import ontology_store
from auth.dependencies import get_request_security_context, RequestSecurityContext


router = APIRouter(prefix="/api/table", tags=["Table Upload"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TableUploadResponse(BaseModel):
    """表格上傳響應"""
    upload_id: str
    schema: Dict[str, Any]
    preview_data: List[Dict[str, Any]]
    row_count: int
    column_count: int
    suggested_mappings: Dict[str, Any]


class ColumnMappingUpdate(BaseModel):
    """列映射更新"""
    column_name: str
    display_name: Optional[str] = None
    data_type: Optional[str] = None
    security_classification: Optional[str] = None
    description: Optional[str] = None
    visible: bool = True


class SchemaConfirmation(BaseModel):
    """Schema 確認請求"""
    upload_id: str
    table_name: str
    object_type: str
    security_level: str
    column_mappings: List[ColumnMappingUpdate]
    generate_ontology: bool = True


class OntologyGenerationResponse(BaseModel):
    """本體生成響應"""
    success: bool
    ontology_id: str
    object_count: int
    relationship_count: int = 0
    message: str


# ============================================================================
# 臨時存儲 (生產環境應使用 Redis 或數據庫)
# ============================================================================
upload_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Helper Functions
# ============================================================================

def _convert_to_serializable(value: Any) -> Any:
    """
    將 pandas/numpy 類型轉換為可序列化的 Python 原生類型
    
    Args:
        value: 待轉換的值
        
    Returns:
        可序列化的 Python 原生類型
    """
    # 處理 NaN/None
    if pd.isna(value):
        return None
    
    # 處理 numpy 布爾類型
    if isinstance(value, np.bool_):
        return bool(value)
    
    # 處理 numpy 整數類型
    if isinstance(value, np.integer):
        return int(value)
    
    # 處理 numpy 浮點類型
    if isinstance(value, np.floating):
        return float(value)
    
    # 處理時間類型
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    
    # 處理 numpy 字符串類型
    if isinstance(value, np.str_):
        return str(value)
    
    # 通用 numpy 類型處理（有 .item() 方法）
    if hasattr(value, 'item'):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    
    # 其他類型直接返回
    return value


def _apply_column_mappings(
    table_schema: TableSchema,
    mappings: List[ColumnMappingUpdate]
) -> TableSchema:
    """
    應用用戶的列映射配置到 TableSchema
    
    Args:
        table_schema: 原始 TableSchema
        mappings: 用戶的列映射更新
        
    Returns:
        TableSchema: 更新後的 TableSchema
    """
    from ontology.table_parser import ColumnType, SecurityClassification
    
    # 創建映射字典
    mapping_dict = {m.column_name: m for m in mappings}
    
    # 更新每個列的配置
    for column in table_schema.columns:
        if column.name in mapping_dict:
            mapping = mapping_dict[column.name]
            
            # 更新顯示名稱
            if mapping.display_name:
                column.display_name = mapping.display_name
            
            # 更新數據類型
            if mapping.data_type:
                try:
                    column.data_type = ColumnType(mapping.data_type.lower())
                except ValueError:
                    pass  # 忽略無效的類型
            
            # 更新安全分類
            if mapping.security_classification:
                try:
                    column.security_classification = SecurityClassification(
                        mapping.security_classification.upper()
                    )
                except ValueError:
                    pass
            
            # 更新描述
            if mapping.description:
                column.description = mapping.description
    
    return table_schema


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/upload", response_model=TableUploadResponse)
async def upload_table_file(
    file: UploadFile = File(...),
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """
    上傳表格文件並解析 Schema
    
    支持格式: CSV, Excel (.xlsx, .xls), JSON
    最大文件大小: 50MB
    """
    # 驗證文件類型
    allowed_extensions = ['.csv', '.xlsx', '.xls', '.json', '.tsv']
    file_ext = '.' + file.filename.split('.')[-1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件類型。允許的類型: {', '.join(allowed_extensions)}"
        )
    
    # 驗證文件大小 (50MB)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="文件大小超過 50MB 限制"
        )
    
    try:
        # 解析表格
        parser = TableParser()
        schema = parser.parse_file(content, file.filename)
        
        # 獲取完整的 DataFrame（parser.df 已經在 parse_file 中設置）
        full_dataframe = parser.df
        
        # 提取預覽數據（前 10 行）- 確保所有值都可序列化
        preview_df = full_dataframe.head(10)
        # 將所有值轉換為可序列化的 Python 原生類型
        preview_data = []
        for _, row in preview_df.iterrows():
            row_dict = {col_name: _convert_to_serializable(value) 
                       for col_name, value in row.items()}
            preview_data.append(row_dict)
        
        # 生成上傳 ID
        upload_id = str(uuid.uuid4())
        
        # 緩存解析結果
        upload_cache[upload_id] = {
            "schema": schema,
            "preview_data": preview_data,
            "dataframe": full_dataframe,
            "filename": file.filename,
            "user_id": security_ctx.user_id or "anonymous",
            "uploaded_at": schema.metadata["parsed_at"],
        }
        
        # 生成建議的映射配置
        suggested_mappings = {
            "object_type": schema.suggested_object_type,
            "security_level": schema.suggested_security_level.value,
            "primary_keys": schema.primary_keys,
            "foreign_keys": schema.foreign_keys,
        }
        
        return TableUploadResponse(
            upload_id=upload_id,
            schema=schema.to_dict(),
            preview_data=preview_data,
            row_count=schema.row_count,
            column_count=len(schema.columns),
            suggested_mappings=suggested_mappings,
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失敗: {str(e)}")


@router.get("/upload/{upload_id}")
async def get_upload_info(
    upload_id: str,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """獲取上傳的表格信息"""
    if upload_id not in upload_cache:
        raise HTTPException(status_code=404, detail="上傳記錄不存在或已過期")
    
    cached = upload_cache[upload_id]
    
    # 驗證用戶權限
    user_id = security_ctx.user_id or "anonymous"
    if cached["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="無權訪問此上傳記錄")
    
    schema = cached["schema"]
    suggested_mappings = {
        "object_type": schema.suggested_object_type,
        "security_level": schema.suggested_security_level.value,
        "primary_keys": schema.primary_keys,
        "foreign_keys": schema.foreign_keys,
    }

    return {
        "upload_id": upload_id,
        "schema": schema.to_dict(),
        "preview_data": cached["preview_data"],
        "filename": cached["filename"],
        "uploaded_at": cached["uploaded_at"],
        "row_count": schema.row_count,
        "column_count": len(schema.columns),
        "suggested_mappings": suggested_mappings,
    }


@router.post("/confirm", response_model=OntologyGenerationResponse)
async def confirm_schema_and_generate_ontology(
    confirmation: SchemaConfirmation,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """
    確認 Schema 映射並生成本體
    
    這個端點將在後續實現中調用本體生成器
    """
    # 驗證上傳記錄
    if confirmation.upload_id not in upload_cache:
        raise HTTPException(status_code=404, detail="上傳記錄不存在或已過期")
    
    cached = upload_cache[confirmation.upload_id]
    
    # 驗證用戶權限
    user_id = security_ctx.user_id or "anonymous"
    if cached["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="無權訪問此上傳記錄")
    
    try:
        # 應用用戶的 column_mappings（如果有的話）
        table_schema = cached["schema"]
        dataframe = cached["dataframe"]
        
        # 更新 schema 根據用戶的映射配置
        if confirmation.column_mappings:
            table_schema = _apply_column_mappings(
                table_schema,
                confirmation.column_mappings
            )
        
        # 調用本體生成器
        generator = OntologyGenerator()
        result = generator.generate_from_table(
            table_schema=table_schema,
            table_data=dataframe,
            user_id=security_ctx.user_id or "anonymous",
            organization_id=None  # TODO: Extract from security_ctx if needed
        )
        
        # 保存到本體存儲
        ontology_store.save_ontology(result)
        
        ontology_id = result.ontology_id
        object_count = result.object_count
        relationship_count = len(result.relationships)
        
        # 清理緩存
        del upload_cache[confirmation.upload_id]
        
        return OntologyGenerationResponse(
            success=True,
            ontology_id=ontology_id,
            object_count=object_count,
            relationship_count=relationship_count,
            message=f"成功生成 {object_count} 個本體對象，{relationship_count} 個關係"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"本體生成失敗: {str(e)}")


@router.delete("/upload/{upload_id}")
async def delete_upload(
    upload_id: str,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """刪除上傳記錄"""
    if upload_id not in upload_cache:
        raise HTTPException(status_code=404, detail="上傳記錄不存在")
    
    cached = upload_cache[upload_id]
    user_id = security_ctx.user_id or "anonymous"
    if cached["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="無權刪除此上傳記錄")
    
    del upload_cache[upload_id]
    return {"message": "上傳記錄已刪除"}


@router.get("/uploads")
async def list_uploads(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context)
):
    """列出當前用戶的所有上傳記錄"""
    user_uploads = []
    user_id = security_ctx.user_id or "anonymous"
    for upload_id, cached in upload_cache.items():
        if cached["user_id"] == user_id:
            user_uploads.append({
                "upload_id": upload_id,
                "filename": cached["filename"],
                "uploaded_at": cached["uploaded_at"],
                "row_count": cached["schema"].row_count,
                "column_count": len(cached["schema"].columns),
            })
    
    return {"uploads": user_uploads, "total": len(user_uploads)}
