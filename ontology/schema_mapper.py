"""
Schema Mapper: 表格 Schema 到本體對象的自動映射引擎

此模組負責將解析後的表格 schema 映射為本體對象結構，
包括類型轉換、關係建立、安全標籤繼承等功能。
"""

from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum
import re

from .table_parser import TableSchema, ColumnSchema, ColumnType, SecurityClassification
from .objects import OntologyObject, SecurityLabel, AccessControl


class OntologyAttributeType(str, Enum):
    """本體屬性類型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TEXT = "text"
    JSON = "json"
    REFERENCE = "reference"  # 外鍵引用


class OntologyObjectType(str, Enum):
    """本體對象類型"""
    ENTITY = "entity"           # 實體對象（對應表格的每一行）
    COLLECTION = "collection"   # 集合對象（對應整個表格）
    RELATIONSHIP = "relationship"  # 關係對象（對應外鍵）


class AttributeMapping:
    """屬性映射定義"""
    
    def __init__(
        self,
        source_column: str,
        target_attribute: str,
        attribute_type: OntologyAttributeType,
        is_required: bool = False,
        is_unique: bool = False,
        is_primary_key: bool = False,
        is_foreign_key: bool = False,
        reference_table: Optional[str] = None,
        security_classification: SecurityClassification = SecurityClassification.PUBLIC,
        description: Optional[str] = None,
        validation_rules: Optional[List[str]] = None
    ):
        self.source_column = source_column
        self.target_attribute = target_attribute
        self.attribute_type = attribute_type
        self.is_required = is_required
        self.is_unique = is_unique
        self.is_primary_key = is_primary_key
        self.is_foreign_key = is_foreign_key
        self.reference_table = reference_table
        self.security_classification = security_classification
        self.description = description
        self.validation_rules = validation_rules or []
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "source_column": self.source_column,
            "target_attribute": self.target_attribute,
            "attribute_type": self.attribute_type.value,
            "is_required": self.is_required,
            "is_unique": self.is_unique,
            "is_primary_key": self.is_primary_key,
            "is_foreign_key": self.is_foreign_key,
            "reference_table": self.reference_table,
            "security_classification": self.security_classification.value,
            "description": self.description,
            "validation_rules": self.validation_rules
        }


class OntologyMapping:
    """本體映射定義（整個表格的映射結構）"""
    
    def __init__(
        self,
        table_name: str,
        object_type: OntologyObjectType,
        display_name: str,
        description: Optional[str] = None,
        security_classification: SecurityClassification = SecurityClassification.PUBLIC,
        attributes: Optional[List[AttributeMapping]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.table_name = table_name
        self.object_type = object_type
        self.display_name = display_name
        self.description = description
        self.security_classification = security_classification
        self.attributes = attributes or []
        self.relationships = relationships or []
        self.metadata = metadata or {}
    
    def add_attribute(self, mapping: AttributeMapping):
        """添加屬性映射"""
        self.attributes.append(mapping)
    
    def add_relationship(self, rel_type: str, target_table: str, foreign_key: str):
        """添加關係映射"""
        self.relationships.append({
            "type": rel_type,
            "target_table": target_table,
            "foreign_key": foreign_key
        })
    
    def get_primary_key_attributes(self) -> List[AttributeMapping]:
        """獲取主鍵屬性"""
        return [attr for attr in self.attributes if attr.is_primary_key]
    
    def get_foreign_key_attributes(self) -> List[AttributeMapping]:
        """獲取外鍵屬性"""
        return [attr for attr in self.attributes if attr.is_foreign_key]
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "table_name": self.table_name,
            "object_type": self.object_type.value,
            "display_name": self.display_name,
            "description": self.description,
            "security_classification": self.security_classification.value,
            "attributes": [attr.to_dict() for attr in self.attributes],
            "relationships": self.relationships,
            "metadata": self.metadata
        }


class SchemaMapper:
    """表格 Schema 到本體對象的映射引擎"""
    
    # 類型映射表：ColumnType -> OntologyAttributeType
    TYPE_MAPPING = {
        ColumnType.INTEGER: OntologyAttributeType.INTEGER,
        ColumnType.FLOAT: OntologyAttributeType.FLOAT,
        ColumnType.DECIMAL: OntologyAttributeType.FLOAT,
        ColumnType.STRING: OntologyAttributeType.STRING,
        ColumnType.TEXT: OntologyAttributeType.TEXT,
        ColumnType.DATE: OntologyAttributeType.DATE,
        ColumnType.DATETIME: OntologyAttributeType.DATETIME,
        ColumnType.BOOLEAN: OntologyAttributeType.BOOLEAN,
        ColumnType.ENUM: OntologyAttributeType.STRING,
        ColumnType.REFERENCE: OntologyAttributeType.REFERENCE,
        ColumnType.JSON: OntologyAttributeType.JSON
    }
    
    def __init__(self):
        self.mappings: Dict[str, OntologyMapping] = {}
    
    def map_table_schema(self, table_schema: TableSchema) -> OntologyMapping:
        """
        將 TableSchema 映射為 OntologyMapping
        
        Args:
            table_schema: 表格 schema
            
        Returns:
            OntologyMapping: 本體映射結構
        """
        # 決定對象類型（預設為 ENTITY，表格的每一行對應一個實體）
        object_type = self._determine_object_type(table_schema)
        
        # 創建映射對象
        mapping = OntologyMapping(
            table_name=table_schema.table_name,
            object_type=object_type,
            display_name=table_schema.table_name,
            description=f"從表格 {table_schema.table_name} 自動生成的本體對象",
            security_classification=table_schema.suggested_security_level,
            metadata={
                "source_file": table_schema.metadata.get("source_file"),
                "row_count": table_schema.row_count,
                "created_at": datetime.now().isoformat()
            }
        )
        
        # 映射每一個欄位
        for column in table_schema.columns:
            attr_mapping = self._map_column_to_attribute(column)
            mapping.add_attribute(attr_mapping)
        
        # 建立關係映射（基於外鍵）
        for column in table_schema.columns:
            if column.foreign_key:
                mapping.add_relationship(
                    rel_type="belongs_to",
                    target_table=column.foreign_key,
                    foreign_key=column.name
                )
        
        # 存儲映射
        self.mappings[table_schema.table_name] = mapping
        
        return mapping
    
    def _determine_object_type(self, table_schema: TableSchema) -> OntologyObjectType:
        """
        根據表格特徵決定對象類型
        
        Args:
            table_schema: 表格 schema
            
        Returns:
            OntologyObjectType: 對象類型
        """
        # 規則：
        # 1. 如果表格名稱包含 "relationship", "mapping", "link" -> RELATIONSHIP
        # 2. 如果表格只有外鍵欄位（關聯表） -> RELATIONSHIP
        # 3. 否則 -> ENTITY
        
        table_name_lower = table_schema.table_name.lower()
        relationship_keywords = ["relationship", "mapping", "link", "assoc", "junction"]
        
        if any(keyword in table_name_lower for keyword in relationship_keywords):
            return OntologyObjectType.RELATIONSHIP
        
        # 檢查是否為純關聯表（只有外鍵和可能的主鍵）
        non_key_columns = [
            col for col in table_schema.columns
            if not col.primary_key and not col.foreign_key
        ]
        
        if len(non_key_columns) == 0 and len(table_schema.columns) >= 2:
            return OntologyObjectType.RELATIONSHIP
        
        return OntologyObjectType.ENTITY
    
    def _map_column_to_attribute(self, column: ColumnSchema) -> AttributeMapping:
        """
        將單個欄位映射為屬性
        
        Args:
            column: 欄位 schema
            
        Returns:
            AttributeMapping: 屬性映射
        """
        # 類型轉換
        ontology_type = self.TYPE_MAPPING.get(
            column.data_type,
            OntologyAttributeType.STRING
        )
        
        # 創建屬性映射
        return AttributeMapping(
            source_column=column.name,
            target_attribute=self._sanitize_attribute_name(column.name),
            attribute_type=ontology_type,
            is_required=column.nullable == False,
            is_unique=column.unique,
            is_primary_key=column.primary_key,
            is_foreign_key=bool(column.foreign_key),
            reference_table=column.foreign_key,
            security_classification=column.security_classification,
            description=f"來自欄位: {column.display_name}",
            validation_rules=self._generate_validation_rules(column)
        )
    
    def _sanitize_attribute_name(self, name: str) -> str:
        """
        清理屬性名稱（轉換為有效的識別符）
        
        Args:
            name: 原始名稱
            
        Returns:
            str: 清理後的名稱
        """
        # 1. 轉換為小寫
        # 2. 替換空格和特殊字符為下劃線
        # 3. 移除連續的下劃線
        sanitized = name.lower()
        sanitized = re.sub(r'[^\w\s-]', '_', sanitized)
        sanitized = re.sub(r'[-\s]+', '_', sanitized)
        sanitized = re.sub(r'_+', '_', sanitized)
        sanitized = sanitized.strip('_')
        
        return sanitized
    
    def _generate_validation_rules(self, column: ColumnSchema) -> List[str]:
        """
        根據欄位特徵生成驗證規則
        
        Args:
            column: 欄位 schema
            
        Returns:
            List[str]: 驗證規則列表
        """
        rules = []
        
        # 非空驗證
        if not column.nullable:
            rules.append("required")
        
        # 唯一性驗證
        if column.unique:
            rules.append("unique")
        
        # 類型驗證
        if column.data_type == ColumnType.INTEGER:
            rules.append("type:integer")
        elif column.data_type == ColumnType.FLOAT:
            rules.append("type:float")
        elif column.data_type == ColumnType.BOOLEAN:
            rules.append("type:boolean")
        elif column.data_type == ColumnType.DATE:
            rules.append("type:date")
        elif column.data_type == ColumnType.DATETIME:
            rules.append("type:datetime")
        
        # 外鍵驗證
        if column.foreign_key:
            rules.append(f"foreign_key:{column.foreign_key}")
        
        return rules
    
    def get_mapping(self, table_name: str) -> Optional[OntologyMapping]:
        """獲取指定表格的映射"""
        return self.mappings.get(table_name)
    
    def get_all_mappings(self) -> Dict[str, OntologyMapping]:
        """獲取所有映射"""
        return self.mappings
    
    def export_mappings(self) -> List[Dict[str, Any]]:
        """導出所有映射為字典格式"""
        return [mapping.to_dict() for mapping in self.mappings.values()]


class MappingOptimizer:
    """映射優化器：優化和調整自動生成的映射"""
    
    def __init__(self):
        self.optimization_rules = []
    
    def optimize_mapping(self, mapping: OntologyMapping) -> OntologyMapping:
        """
        優化映射配置
        
        Args:
            mapping: 原始映射
            
        Returns:
            OntologyMapping: 優化後的映射
        """
        optimized = mapping
        
        # 1. 合併重複的屬性
        optimized = self._merge_duplicate_attributes(optimized)
        
        # 2. 推斷隱式關係
        optimized = self._infer_implicit_relationships(optimized)
        
        # 3. 優化安全標籤
        optimized = self._optimize_security_labels(optimized)
        
        return optimized
    
    def _merge_duplicate_attributes(self, mapping: OntologyMapping) -> OntologyMapping:
        """合併重複的屬性（相同 source_column）"""
        seen: Set[str] = set()
        unique_attributes = []
        
        for attr in mapping.attributes:
            if attr.source_column not in seen:
                seen.add(attr.source_column)
                unique_attributes.append(attr)
        
        mapping.attributes = unique_attributes
        return mapping
    
    def _infer_implicit_relationships(self, mapping: OntologyMapping) -> OntologyMapping:
        """推斷隱式關係（例如：user_id 可能指向 users 表）"""
        # 規則：如果欄位名為 xxx_id，且不在 foreign_keys 中，嘗試推斷
        for attr in mapping.attributes:
            if attr.source_column.endswith("_id") and not attr.is_foreign_key:
                # 嘗試推斷表名
                potential_table = attr.source_column[:-3]  # 移除 _id
                potential_table_plural = potential_table + "s"
                
                # 添加為可能的關係
                if not any(rel["foreign_key"] == attr.source_column for rel in mapping.relationships):
                    mapping.add_relationship(
                        rel_type="possible_reference",
                        target_table=potential_table_plural,
                        foreign_key=attr.source_column
                    )
        
        return mapping
    
    def _optimize_security_labels(self, mapping: OntologyMapping) -> OntologyMapping:
        """
        優化安全標籤（繼承最高級別的安全分類）
        
        規則：如果任何屬性的安全級別高於對象級別，提升對象級別
        """
        highest_classification = mapping.security_classification
        
        for attr in mapping.attributes:
            if self._is_higher_classification(attr.security_classification, highest_classification):
                highest_classification = attr.security_classification
        
        mapping.security_classification = highest_classification
        return mapping
    
    def _is_higher_classification(
        self,
        level1: SecurityClassification,
        level2: SecurityClassification
    ) -> bool:
        """比較安全級別"""
        level_order = {
            SecurityClassification.PUBLIC: 0,
            SecurityClassification.INTERNAL: 1,
            SecurityClassification.CONFIDENTIAL: 2,
            SecurityClassification.SECRET: 3
        }
        return level_order[level1] > level_order[level2]


# 使用範例
if __name__ == "__main__":
    from .table_parser import TableParser
    
    # 創建映射器
    mapper = SchemaMapper()
    optimizer = MappingOptimizer()
    
    print("Schema Mapper 初始化成功")
    print(f"支援的類型映射: {len(SchemaMapper.TYPE_MAPPING)} 種")
