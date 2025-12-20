"""
表格解析器 (Table Parser)
支持 CSV、Excel、JSON 格式，自動識別列類型並提取 Schema
"""

import io
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import re


class ColumnType(str, Enum):
    """列數據類型"""
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    STRING = "string"
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    ENUM = "enum"
    REFERENCE = "reference"  # 外鍵引用
    JSON = "json"


class SecurityClassification(str, Enum):
    """根據列名自動推斷安全等級"""
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"


@dataclass
class ColumnSchema:
    """列 Schema 定義"""
    name: str
    display_name: str
    data_type: ColumnType
    nullable: bool
    unique: bool
    primary_key: bool
    foreign_key: Optional[str] = None
    enum_values: Optional[List[str]] = None
    sample_values: List[Any] = None
    security_classification: SecurityClassification = SecurityClassification.PUBLIC
    description: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "data_type": self.data_type.value,
            "nullable": self.nullable,
            "unique": self.unique,
            "primary_key": self.primary_key,
            "foreign_key": self.foreign_key,
            "enum_values": self.enum_values,
            "sample_values": self.sample_values[:5] if self.sample_values else [],
            "security_classification": self.security_classification.value,
            "description": self.description,
        }


@dataclass
class TableSchema:
    """表格 Schema 定義"""
    table_name: str
    columns: List[ColumnSchema]
    row_count: int
    primary_keys: List[str]
    foreign_keys: Dict[str, str]
    suggested_object_type: str
    suggested_security_level: SecurityClassification
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "table_name": self.table_name,
            "columns": [col.to_dict() for col in self.columns],
            "row_count": self.row_count,
            "primary_keys": self.primary_keys,
            "foreign_keys": self.foreign_keys,
            "suggested_object_type": self.suggested_object_type,
            "suggested_security_level": self.suggested_security_level.value,
            "metadata": self.metadata,
        }


class TableParser:
    """表格解析器主類"""
    
    # 敏感欄位關鍵詞 (用於自動推斷安全等級)
    SENSITIVE_KEYWORDS = {
        SecurityClassification.SECRET: [
            "password", "secret", "token", "key", "credit_card", "ssn", 
            "social_security", "passport", "tax_id", "密碼", "密鑰", "信用卡"
        ],
        SecurityClassification.CONFIDENTIAL: [
            "salary", "income", "revenue", "profit", "financial", "confidential",
            "private", "internal_only", "薪資", "收入", "機密", "私密"
        ],
        SecurityClassification.INTERNAL: [
            "employee", "staff", "internal", "department", "team", 
            "員工", "內部", "部門"
        ],
    }
    
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.file_type: Optional[str] = None
    
    def parse_file(self, file_content: bytes, filename: str) -> TableSchema:
        """
        解析文件並提取 Schema
        
        Args:
            file_content: 文件二進制內容
            filename: 文件名（用於判斷類型）
        
        Returns:
            TableSchema 對象
        """
        # 判斷文件類型
        self.file_type = self._detect_file_type(filename)
        
        # 讀取文件到 DataFrame
        self.df = self._read_file(file_content, self.file_type)
        
        # 提取表名（從文件名）
        table_name = self._extract_table_name(filename)
        
        # 分析列 Schema
        columns = self._analyze_columns()
        
        # 檢測主鍵和外鍵
        primary_keys = self._detect_primary_keys(columns)
        foreign_keys = self._detect_foreign_keys(columns)
        
        # 推斷對象類型
        suggested_object_type = self._suggest_object_type(table_name, columns)
        
        # 推斷整體安全等級
        suggested_security_level = self._suggest_security_level(columns)
        
        # 構建元數據
        metadata = {
            "file_type": self.file_type,
            "original_filename": filename,
            "parsed_at": datetime.utcnow().isoformat(),
            "column_count": len(columns),
            "has_header": True,
        }
        
        return TableSchema(
            table_name=table_name,
            columns=columns,
            row_count=len(self.df),
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            suggested_object_type=suggested_object_type,
            suggested_security_level=suggested_security_level,
            metadata=metadata,
        )
    
    def _detect_file_type(self, filename: str) -> str:
        """根據文件名檢測文件類型"""
        ext = filename.lower().split('.')[-1]
        if ext in ['csv', 'tsv']:
            return 'csv'
        elif ext in ['xls', 'xlsx', 'xlsm']:
            return 'excel'
        elif ext == 'json':
            return 'json'
        else:
            raise ValueError(f"不支持的文件類型: {ext}")
    
    def _read_file(self, file_content: bytes, file_type: str) -> pd.DataFrame:
        """讀取文件到 DataFrame"""
        try:
            if file_type == 'csv':
                # 嘗試不同編碼
                for encoding in ['utf-8', 'gbk', 'gb2312', 'big5']:
                    try:
                        return pd.read_csv(io.BytesIO(file_content), encoding=encoding)
                    except UnicodeDecodeError:
                        continue
                raise ValueError("無法解析 CSV 文件編碼")
            
            elif file_type == 'excel':
                return pd.read_excel(io.BytesIO(file_content))
            
            elif file_type == 'json':
                return pd.read_json(io.BytesIO(file_content))
            
        except Exception as e:
            raise ValueError(f"文件解析失敗: {str(e)}")
    
    def _extract_table_name(self, filename: str) -> str:
        """從文件名提取表名"""
        # 去除擴展名和特殊字符
        name = filename.rsplit('.', 1)[0]
        name = re.sub(r'[^\w\u4e00-\u9fff]+', '_', name)
        return name.lower()
    
    def _analyze_columns(self) -> List[ColumnSchema]:
        """分析所有列的 Schema"""
        columns = []
        for col_name in self.df.columns:
            column_schema = self._analyze_single_column(col_name)
            columns.append(column_schema)
        return columns
    
    def _analyze_single_column(self, col_name: str) -> ColumnSchema:
        """分析單個列的 Schema"""
        series = self.df[col_name]
        
        # 基本屬性
        nullable = bool(series.isnull().any())
        unique = bool(series.nunique() == len(series))
        
        # 檢測數據類型
        data_type = self._infer_data_type(series)
        
        # 枚舉值檢測（如果唯一值少於 20 個）
        enum_values = None
        if data_type == ColumnType.STRING and series.nunique() < 20:
            data_type = ColumnType.ENUM
            enum_values = series.dropna().unique().tolist()
        
        # 主鍵檢測（id 或唯一且非空）
        primary_key = self._is_primary_key(col_name, series, unique, nullable)
        
        # 外鍵檢測
        foreign_key = self._detect_foreign_key(col_name)
        if foreign_key:
            data_type = ColumnType.REFERENCE
        
        # 安全等級推斷
        security_classification = self._infer_security_classification(col_name)
        
        # 生成顯示名稱
        display_name = self._generate_display_name(col_name)
        
        # 取樣本值
        # 確保轉換為 Python 原生類型
        raw_samples = series.dropna().head(5).tolist()
        sample_values = []
        for val in raw_samples:
            if hasattr(val, 'item'):
                sample_values.append(val.item())
            elif isinstance(val, (pd.Timestamp, datetime)):
                sample_values.append(val.isoformat())
            else:
                sample_values.append(val)
        
        return ColumnSchema(
            name=col_name,
            display_name=display_name,
            data_type=data_type,
            nullable=nullable,
            unique=unique,
            primary_key=primary_key,
            foreign_key=foreign_key,
            enum_values=enum_values,
            sample_values=sample_values,
            security_classification=security_classification,
            description=None,
        )
    
    def _infer_data_type(self, series: pd.Series) -> ColumnType:
        """推斷列的數據類型"""
        # 跳過空值
        non_null_series = series.dropna()
        if len(non_null_series) == 0:
            return ColumnType.STRING
        
        dtype = series.dtype
        
        # Pandas 類型映射
        if pd.api.types.is_integer_dtype(dtype):
            return ColumnType.INTEGER
        elif pd.api.types.is_float_dtype(dtype):
            return ColumnType.FLOAT
        elif pd.api.types.is_bool_dtype(dtype):
            return ColumnType.BOOLEAN
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            return ColumnType.DATETIME
        
        # 字符串類型需要進一步分析
        if pd.api.types.is_string_dtype(dtype) or pd.api.types.is_object_dtype(dtype):
            # 嘗試解析為日期
            if self._is_date_column(non_null_series):
                return ColumnType.DATE
            
            # 檢查是否為 JSON
            if self._is_json_column(non_null_series):
                return ColumnType.JSON
            
            # 長文本判斷
            avg_length = non_null_series.astype(str).str.len().mean()
            if avg_length > 200:
                return ColumnType.TEXT
            
            return ColumnType.STRING
        
        return ColumnType.STRING
    
    def _is_date_column(self, series: pd.Series) -> bool:
        """檢查是否為日期列"""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                pd.to_datetime(series.head(10), errors='raise')
                return True
            except:
                return False
    
    def _is_json_column(self, series: pd.Series) -> bool:
        """檢查是否為 JSON 列"""
        import json
        try:
            for val in series.head(5):
                json.loads(str(val))
            return True
        except:
            return False
    
    def _is_primary_key(self, col_name: str, series: pd.Series, unique: bool, nullable: bool) -> bool:
        """判斷是否為主鍵"""
        # 常見主鍵名稱
        pk_patterns = [r'^id$', r'.*_id$', r'.*_key$', r'.*_code$']
        is_pk_name = any(re.match(pattern, col_name.lower()) for pattern in pk_patterns)
        
        return is_pk_name and unique and not nullable
    
    def _detect_foreign_key(self, col_name: str) -> Optional[str]:
        """檢測外鍵關係"""
        # 常見外鍵命名模式
        fk_pattern = r'^(.+)_id$'
        match = re.match(fk_pattern, col_name.lower())
        if match:
            referenced_table = match.group(1)
            return referenced_table
        return None
    
    def _infer_security_classification(self, col_name: str) -> SecurityClassification:
        """根據列名推斷安全等級"""
        col_lower = col_name.lower()
        
        # 檢查敏感關鍵詞
        for level, keywords in self.SENSITIVE_KEYWORDS.items():
            if any(keyword in col_lower for keyword in keywords):
                return level
        
        return SecurityClassification.PUBLIC
    
    def _generate_display_name(self, col_name: str) -> str:
        """生成友好的顯示名稱"""
        # 去除下劃線，首字母大寫
        words = col_name.replace('_', ' ').split()
        return ' '.join(word.capitalize() for word in words)
    
    def _detect_primary_keys(self, columns: List[ColumnSchema]) -> List[str]:
        """檢測所有主鍵"""
        return [col.name for col in columns if col.primary_key]
    
    def _detect_foreign_keys(self, columns: List[ColumnSchema]) -> Dict[str, str]:
        """檢測所有外鍵關係"""
        fks = {}
        for col in columns:
            if col.foreign_key:
                fks[col.name] = col.foreign_key
        return fks
    
    def _suggest_object_type(self, table_name: str, columns: List[ColumnSchema]) -> str:
        """根據表名和列推斷對象類型"""
        # 常見對象類型映射
        type_keywords = {
            "user": ["user", "account", "member", "customer", "用戶", "客戶"],
            "document": ["document", "file", "attachment", "文檔", "文件"],
            "conversation": ["conversation", "chat", "message", "對話", "消息"],
            "organization": ["organization", "company", "org", "組織", "公司"],
            "model": ["model", "ai_model", "algorithm", "模型"],
            "dataset": ["dataset", "data", "table", "數據集", "表格"],
        }
        
        table_lower = table_name.lower()
        for obj_type, keywords in type_keywords.items():
            if any(keyword in table_lower for keyword in keywords):
                return obj_type
        
        return "dataset"  # 默認為數據集
    
    def _suggest_security_level(self, columns: List[ColumnSchema]) -> SecurityClassification:
        """根據列的安全等級推斷整體安全等級（取最高級別）"""
        levels = [SecurityClassification.PUBLIC, SecurityClassification.INTERNAL, 
                  SecurityClassification.CONFIDENTIAL, SecurityClassification.SECRET]
        
        max_level = SecurityClassification.PUBLIC
        for col in columns:
            if levels.index(col.security_classification) > levels.index(max_level):
                max_level = col.security_classification
        
        return max_level
    
    def get_preview_data(self, limit: int = 10) -> List[Dict[str, Any]]:
        """獲取預覽數據"""
        if self.df is None:
            return []
        
        preview_df = self.df.head(limit)
        return preview_df.to_dict('records')


# 便利函數
def parse_table_file(file_content: bytes, filename: str) -> Tuple[TableSchema, List[Dict[str, Any]]]:
    """
    解析表格文件並返回 Schema 和預覽數據
    
    Returns:
        (TableSchema, preview_data)
    """
    parser = TableParser()
    schema = parser.parse_file(file_content, filename)
    preview_data = parser.get_preview_data(limit=10)
    
    return schema, preview_data
