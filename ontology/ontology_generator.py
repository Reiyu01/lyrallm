"""
Ontology Generator: 從表格數據自動生成本體對象

此模組負責將解析的表格數據轉換為實際的 OntologyObject 實例，
並建立對象之間的關係（基於外鍵）。
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
import uuid
import pandas as pd
from collections import defaultdict

from .table_parser import TableSchema, ColumnSchema, SecurityClassification
from .schema_mapper import (
    SchemaMapper,
    OntologyMapping,
    AttributeMapping,
    MappingOptimizer,
    OntologyObjectType,
    OntologyAttributeType
)
from .objects import (
    OntologyObject,
    ObjectType,
    SecurityLabel,
    AccessControl
)


class GenerationResult:
    """本體生成結果"""
    
    def __init__(
        self,
        ontology_id: str,
        object_count: int,
        table_name: str,
        objects: List[OntologyObject],
        relationships: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.ontology_id = ontology_id
        self.object_count = object_count
        self.table_name = table_name
        self.objects = objects
        self.relationships = relationships
        self.metadata = metadata or {}
        self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "ontology_id": self.ontology_id,
            "object_count": self.object_count,
            "table_name": self.table_name,
            "object_ids": [obj.object_id for obj in self.objects],
            "relationship_count": len(self.relationships),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    def get_object_by_id(self, object_id: str) -> Optional[OntologyObject]:
        """根據 ID 獲取對象"""
        for obj in self.objects:
            if obj.object_id == object_id:
                return obj
        return None


class OntologyGenerator:
    """本體對象生成器"""
    
    def __init__(self):
        self.mapper = SchemaMapper()
        self.optimizer = MappingOptimizer()
        self.generated_ontologies: Dict[str, GenerationResult] = {}
    
    def generate_from_table(
        self,
        table_schema: TableSchema,
        table_data: pd.DataFrame,
        user_id: str,
        organization_id: Optional[str] = None
    ) -> GenerationResult:
        """
        從表格數據生成本體對象
        
        Args:
            table_schema: 表格 schema
            table_data: 表格數據（DataFrame）
            user_id: 創建者 ID
            organization_id: 組織 ID
            
        Returns:
            GenerationResult: 生成結果
        """
        # Step 1: 創建映射
        mapping = self.mapper.map_table_schema(table_schema)
        mapping = self.optimizer.optimize_mapping(mapping)
        
        # Step 2: 生成 ontology_id
        ontology_id = self._generate_ontology_id(table_schema.table_name)
        
        # Step 3: 為每一行創建 OntologyObject
        objects = []
        primary_key_map = {}  # 用於建立關係: {primary_key_value: object_id}
        
        for idx, row in table_data.iterrows():
            obj = self._create_object_from_row(
                row=row,
                mapping=mapping,
                ontology_id=ontology_id,
                user_id=user_id,
                organization_id=organization_id,
                row_index=idx
            )
            objects.append(obj)
            
            # 記錄主鍵映射
            pk_attrs = mapping.get_primary_key_attributes()
            if pk_attrs:
                pk_value = row[pk_attrs[0].source_column]
                primary_key_map[pk_value] = obj.object_id
        
        # Step 4: 建立關係（基於外鍵）
        relationships = self._establish_relationships(
            objects=objects,
            table_data=table_data,
            mapping=mapping,
            primary_key_map=primary_key_map
        )
        
        # Step 5: 創建生成結果
        result = GenerationResult(
            ontology_id=ontology_id,
            object_count=len(objects),
            table_name=table_schema.table_name,
            objects=objects,
            relationships=relationships,
            metadata={
                "source_file": table_schema.metadata.get("source_file"),
                "row_count": table_schema.row_count,
                "column_count": len(table_schema.columns),
                "security_classification": table_schema.suggested_security_level.value,
                "created_by": user_id,
                "organization_id": organization_id
            }
        )
        
        # 存儲結果
        self.generated_ontologies[ontology_id] = result
        
        return result
    
    def _generate_ontology_id(self, table_name: str) -> str:
        """生成唯一的 ontology ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_suffix = str(uuid.uuid4())[:8]
        return f"ontology_{table_name}_{timestamp}_{unique_suffix}"
    
    def _create_object_from_row(
        self,
        row: pd.Series,
        mapping: OntologyMapping,
        ontology_id: str,
        user_id: str,
        organization_id: Optional[str],
        row_index: int
    ) -> OntologyObject:
        """
        從表格的一行創建 OntologyObject
        
        Args:
            row: DataFrame 的一行
            mapping: 本體映射
            ontology_id: 本體 ID
            user_id: 創建者 ID
            organization_id: 組織 ID
            row_index: 行索引
            
        Returns:
            OntologyObject: 本體對象
        """
        # 生成對象 ID
        object_id = f"{ontology_id}_row_{row_index}"
        
        # 構建屬性字典
        attributes = {}
        for attr_mapping in mapping.attributes:
            column_name = attr_mapping.source_column
            if column_name in row.index:
                value = row[column_name]
                # 處理 NaN 值
                if pd.isna(value):
                    value = None
                else:
                    # 類型轉換
                    value = self._convert_value_type(value, attr_mapping.attribute_type)
                
                attributes[attr_mapping.target_attribute] = value
        
        # 創建安全標籤
        security_label = self._create_security_label(mapping.security_classification)
        
        # 創建訪問控制
        access_control = self._create_access_control(
            user_id=user_id,
            organization_id=organization_id,
            security_classification=mapping.security_classification
        )
        
        # 創建 OntologyObject
        obj = OntologyObject(
            object_id=object_id,
            object_type=self._map_to_object_type(mapping.object_type),
            title=f"{mapping.display_name} (Row {row_index})",
            description=f"從表格 {mapping.table_name} 第 {row_index} 行生成",
            security_label=security_label,
            access_control=access_control,
            created_by=user_id,
            parent_id=None,  # 稍後會根據外鍵設置
            metadata={
                "ontology_id": ontology_id,
                "table_name": mapping.table_name,
                "row_index": row_index,
                "source": "table_upload",
                "attributes": attributes
            }
        )
        
        return obj
    
    def _convert_value_type(
        self,
        value: Any,
        target_type: OntologyAttributeType
    ) -> Any:
        """
        轉換值類型
        
        Args:
            value: 原始值
            target_type: 目標類型
            
        Returns:
            Any: 轉換後的值
        """
        if value is None or pd.isna(value):
            return None
        
        try:
            if target_type == OntologyAttributeType.INTEGER:
                return int(value)
            elif target_type == OntologyAttributeType.FLOAT:
                return float(value)
            elif target_type == OntologyAttributeType.BOOLEAN:
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ['true', '1', 'yes', 'y']
            elif target_type == OntologyAttributeType.STRING:
                return str(value)
            elif target_type == OntologyAttributeType.TEXT:
                return str(value)
            elif target_type in [OntologyAttributeType.DATE, OntologyAttributeType.DATETIME]:
                if isinstance(value, (datetime, pd.Timestamp)):
                    return value.isoformat()
                return str(value)
            elif target_type == OntologyAttributeType.JSON:
                # 如果已經是字典或列表，直接返回
                if isinstance(value, (dict, list)):
                    return value
                return str(value)
            elif target_type == OntologyAttributeType.REFERENCE:
                return str(value)
            else:
                return str(value)
        except Exception:
            # 轉換失敗時返回字符串
            return str(value)
    
    def _create_security_label(
        self,
        classification: SecurityClassification
    ) -> SecurityLabel:
        """創建安全標籤"""
        return SecurityLabel(
            classification=classification.value.upper(),
            categories=set(),
            handling_caveats=set()
        )
    
    def _create_access_control(
        self,
        user_id: str,
        organization_id: Optional[str],
        security_classification: SecurityClassification
    ) -> AccessControl:
        """創建訪問控制"""
        # 基於安全分類設置訪問控制
        roles = []
        
        if security_classification == SecurityClassification.PUBLIC:
            roles = ["public", "user", "admin"]
        elif security_classification == SecurityClassification.INTERNAL:
            roles = ["user", "admin"]
        elif security_classification == SecurityClassification.CONFIDENTIAL:
            roles = ["manager", "admin"]
        elif security_classification == SecurityClassification.SECRET:
            roles = ["admin"]
        
        return AccessControl(
            owner_id=user_id,
            owner_type="user",
            allowed_roles=frozenset(roles),
            allowed_users=frozenset([user_id] if user_id else []),
            denied_users=frozenset(),
            allowed_organizations=frozenset([organization_id] if organization_id else [])
        )
    
    def _map_to_object_type(self, ontology_object_type: OntologyObjectType) -> ObjectType:
        """映射本體對象類型到 ObjectType"""
        if ontology_object_type == OntologyObjectType.ENTITY:
            return ObjectType.DOCUMENT
        elif ontology_object_type == OntologyObjectType.COLLECTION:
            return ObjectType.CONVERSATION
        elif ontology_object_type == OntologyObjectType.RELATIONSHIP:
            return ObjectType.DOCUMENT
        else:
            return ObjectType.DOCUMENT
    
    def _establish_relationships(
        self,
        objects: List[OntologyObject],
        table_data: pd.DataFrame,
        mapping: OntologyMapping,
        primary_key_map: Dict[Any, str]
    ) -> List[Dict[str, Any]]:
        """
        建立對象之間的關係（基於外鍵）
        
        Args:
            objects: 生成的對象列表
            table_data: 表格數據
            mapping: 本體映射
            primary_key_map: 主鍵值 -> 對象 ID 的映射
            
        Returns:
            List[Dict[str, Any]]: 關係列表
        """
        relationships = []
        fk_attrs = mapping.get_foreign_key_attributes()
        
        if not fk_attrs:
            return relationships
        
        # 遍歷每個對象
        for idx, obj in enumerate(objects):
            row = table_data.iloc[idx]
            
            # 檢查每個外鍵
            for fk_attr in fk_attrs:
                fk_column = fk_attr.source_column
                if fk_column in row.index:
                    fk_value = row[fk_column]
                    
                    # 跳過空值
                    if pd.isna(fk_value):
                        continue
                    
                    # 查找父對象
                    parent_object_id = primary_key_map.get(fk_value)
                    
                    if parent_object_id:
                        # 設置 parent_id
                        obj.parent_id = parent_object_id
                        
                        # 記錄關係
                        relationships.append({
                            "child_id": obj.object_id,
                            "parent_id": parent_object_id,
                            "relationship_type": "belongs_to",
                            "foreign_key": fk_column,
                            "foreign_key_value": fk_value,
                            "target_table": fk_attr.reference_table
                        })
        
        return relationships
    
    def get_generation_result(self, ontology_id: str) -> Optional[GenerationResult]:
        """獲取生成結果"""
        return self.generated_ontologies.get(ontology_id)
    
    def list_generated_ontologies(self) -> List[str]:
        """列出所有已生成的本體 ID"""
        return list(self.generated_ontologies.keys())
    
    def delete_ontology(self, ontology_id: str) -> bool:
        """刪除生成的本體"""
        if ontology_id in self.generated_ontologies:
            del self.generated_ontologies[ontology_id]
            return True
        return False


class BatchOntologyGenerator:
    """批量本體生成器（用於處理多個相關表格）"""
    
    def __init__(self):
        self.generator = OntologyGenerator()
        self.cross_table_relationships: List[Dict[str, Any]] = []
    
    def generate_from_multiple_tables(
        self,
        tables: List[Tuple[TableSchema, pd.DataFrame]],
        user_id: str,
        organization_id: Optional[str] = None
    ) -> List[GenerationResult]:
        """
        從多個表格批量生成本體
        
        Args:
            tables: (TableSchema, DataFrame) 的列表
            user_id: 創建者 ID
            organization_id: 組織 ID
            
        Returns:
            List[GenerationResult]: 生成結果列表
        """
        results = []
        all_primary_key_maps = {}  # {table_name: {pk_value: object_id}}
        
        # Step 1: 為每個表格生成本體
        for table_schema, table_data in tables:
            result = self.generator.generate_from_table(
                table_schema=table_schema,
                table_data=table_data,
                user_id=user_id,
                organization_id=organization_id
            )
            results.append(result)
            
            # 收集主鍵映射（用於跨表關係）
            pk_map = self._extract_primary_key_map(table_schema, table_data, result)
            all_primary_key_maps[table_schema.table_name] = pk_map
        
        # Step 2: 建立跨表關係
        self.cross_table_relationships = self._establish_cross_table_relationships(
            results=results,
            tables=tables,
            all_primary_key_maps=all_primary_key_maps
        )
        
        return results
    
    def _extract_primary_key_map(
        self,
        table_schema: TableSchema,
        table_data: pd.DataFrame,
        result: GenerationResult
    ) -> Dict[Any, str]:
        """提取主鍵映射"""
        pk_map = {}
        pk_columns = [col for col in table_schema.columns if col.primary_key]
        
        if pk_columns:
            pk_column = pk_columns[0].name
            for idx, row in table_data.iterrows():
                pk_value = row[pk_column]
                if not pd.isna(pk_value):
                    object_id = f"{result.ontology_id}_row_{idx}"
                    pk_map[pk_value] = object_id
        
        return pk_map
    
    def _establish_cross_table_relationships(
        self,
        results: List[GenerationResult],
        tables: List[Tuple[TableSchema, pd.DataFrame]],
        all_primary_key_maps: Dict[str, Dict[Any, str]]
    ) -> List[Dict[str, Any]]:
        """建立跨表關係"""
        cross_relationships = []
        
        # 遍歷每個表格
        for result, (table_schema, table_data) in zip(results, tables):
            # 查找外鍵欄位
            fk_columns = [col for col in table_schema.columns if col.foreign_key]
            
            for fk_col in fk_columns:
                target_table = fk_col.foreign_key
                
                # 檢查目標表是否存在
                if target_table not in all_primary_key_maps:
                    continue
                
                target_pk_map = all_primary_key_maps[target_table]
                
                # 遍歷當前表的每一行
                for idx, row in table_data.iterrows():
                    fk_value = row[fk_col.name]
                    
                    if pd.isna(fk_value):
                        continue
                    
                    # 查找目標對象
                    target_object_id = target_pk_map.get(fk_value)
                    
                    if target_object_id:
                        source_object_id = f"{result.ontology_id}_row_{idx}"
                        
                        cross_relationships.append({
                            "source_table": table_schema.table_name,
                            "target_table": target_table,
                            "source_object_id": source_object_id,
                            "target_object_id": target_object_id,
                            "relationship_type": "references",
                            "foreign_key": fk_col.name,
                            "foreign_key_value": fk_value
                        })
        
        return cross_relationships


# 使用範例
if __name__ == "__main__":
    print("Ontology Generator 初始化成功")
    print("支援功能:")
    print("  - 從表格數據生成 OntologyObject")
    print("  - 自動建立父子關係（基於外鍵）")
    print("  - 批量處理多個相關表格")
    print("  - 跨表關係建立")
