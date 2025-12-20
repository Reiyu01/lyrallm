"""
Data Lineage - 資料血緣追蹤系統

實現 Palantir AIP 風格的資料血緣追蹤：
1. 追蹤資料的來源、轉換、使用
2. 記錄所有存取事件
3. 支援審計與合規
4. 提供完整的資料生命週期視圖
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from uuid import uuid4
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LineageEventType(str, Enum):
    """血緣事件類型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    TRANSFORM = "transform"
    COPY = "copy"
    SHARE = "share"
    EXPORT = "export"
    ARCHIVE = "archive"


class DataSource(str, Enum):
    """資料來源類型"""
    USER_INPUT = "user_input"
    API_CALL = "api_call"
    FILE_UPLOAD = "file_upload"
    DATABASE_QUERY = "database_query"
    EXTERNAL_API = "external_api"
    MODEL_OUTPUT = "model_output"
    TRANSFORMATION = "transformation"


@dataclass
class LineageNode:
    """血緣節點 - 代表資料生命週期中的一個點"""
    node_id: str = field(default_factory=lambda: str(uuid4()))
    
    # 資料身份
    object_id: str = ""  # 關聯的本體論物件 ID
    object_type: str = ""
    
    # 事件資訊
    event_type: LineageEventType = LineageEventType.READ
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 操作者資訊
    actor_id: str = ""  # 誰執行了這個操作
    actor_type: str = "user"  # user, system, model, service
    
    # 來源追蹤
    source_type: DataSource = DataSource.USER_INPUT
    source_id: Optional[str] = None  # 來源物件 ID
    
    # 轉換資訊
    transformation_type: Optional[str] = None
    transformation_details: Dict[str, Any] = field(default_factory=dict)
    
    # 上下文
    context: Dict[str, Any] = field(default_factory=dict)
    
    # 父節點（資料從哪裡來）
    parent_nodes: List[str] = field(default_factory=list)
    
    # 子節點（資料去了哪裡）
    child_nodes: List[str] = field(default_factory=list)
    
    # 元數據
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'node_id': self.node_id,
            'object_id': self.object_id,
            'object_type': self.object_type,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'actor_id': self.actor_id,
            'actor_type': self.actor_type,
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'transformation_type': self.transformation_type,
            'parent_nodes': self.parent_nodes,
            'child_nodes': self.child_nodes,
            'metadata': self.metadata,
        }


@dataclass
class AccessEvent:
    """存取事件 - 記錄資料存取的詳細資訊"""
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 主體（誰）
    user_id: str = ""
    user_roles: List[str] = field(default_factory=list)
    organization_id: Optional[str] = None
    
    # 客體（什麼）
    resource_id: str = ""
    resource_type: str = ""
    resource_classification: str = "PUBLIC"
    
    # 動作（做了什麼）
    action: str = "read"  # read, write, delete, share, export
    result: str = "success"  # success, denied, error
    denial_reason: Optional[str] = None
    
    # 上下文
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    
    # 資料範圍
    fields_accessed: List[str] = field(default_factory=list)
    records_count: int = 0
    
    # 策略相關
    policy_decisions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 額外資訊
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'user_roles': self.user_roles,
            'organization_id': self.organization_id,
            'resource_id': self.resource_id,
            'resource_type': self.resource_type,
            'resource_classification': self.resource_classification,
            'action': self.action,
            'result': self.result,
            'denial_reason': self.denial_reason,
            'ip_address': self.ip_address,
            'metadata': self.metadata,
        }


@dataclass
class TransformationEvent:
    """轉換事件 - 記錄資料轉換的詳細資訊"""
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 輸入
    input_objects: List[str] = field(default_factory=list)
    
    # 輸出
    output_objects: List[str] = field(default_factory=list)
    
    # 轉換類型
    transformation_type: str = ""  # summarize, translate, embed, classify, etc.
    model_used: Optional[str] = None
    
    # 轉換詳情
    transformation_config: Dict[str, Any] = field(default_factory=dict)
    
    # 品質指標
    confidence_score: Optional[float] = None
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # 執行資訊
    execution_time_ms: Optional[float] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    
    # 元數據
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'input_objects': self.input_objects,
            'output_objects': self.output_objects,
            'transformation_type': self.transformation_type,
            'model_used': self.model_used,
            'confidence_score': self.confidence_score,
            'execution_time_ms': self.execution_time_ms,
            'tokens_used': self.tokens_used,
            'cost_usd': self.cost_usd,
            'metadata': self.metadata,
        }


@dataclass
class DataLineage:
    """資料血緣 - 完整的資料生命週期追蹤"""
    lineage_id: str = field(default_factory=lambda: str(uuid4()))
    
    # 根物件
    root_object_id: str = ""
    root_object_type: str = ""
    
    # 血緣圖（節點集合）
    nodes: Dict[str, LineageNode] = field(default_factory=dict)
    
    # 事件歷史
    access_events: List[AccessEvent] = field(default_factory=list)
    transformation_events: List[TransformationEvent] = field(default_factory=list)
    
    # 統計資訊
    total_accesses: int = 0
    unique_users: Set[str] = field(default_factory=set)
    
    # 時間範圍
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def add_node(self, node: LineageNode):
        """添加血緣節點"""
        self.nodes[node.node_id] = node
        self.last_updated = datetime.now()
    
    def add_access_event(self, event: AccessEvent):
        """添加存取事件"""
        self.access_events.append(event)
        self.total_accesses += 1
        self.unique_users.add(event.user_id)
        self.last_updated = datetime.now()
    
    def add_transformation_event(self, event: TransformationEvent):
        """添加轉換事件"""
        self.transformation_events.append(event)
        self.last_updated = datetime.now()
    
    def get_lineage_path(self, node_id: str) -> List[LineageNode]:
        """取得從根節點到指定節點的血緣路徑"""
        path = []
        current = self.nodes.get(node_id)
        
        while current:
            path.insert(0, current)
            if current.parent_nodes:
                parent_id = current.parent_nodes[0]
                current = self.nodes.get(parent_id)
            else:
                break
        
        return path
    
    def get_descendants(self, node_id: str) -> List[LineageNode]:
        """取得指定節點的所有後代"""
        descendants = []
        node = self.nodes.get(node_id)
        
        if node:
            for child_id in node.child_nodes:
                child = self.nodes.get(child_id)
                if child:
                    descendants.append(child)
                    descendants.extend(self.get_descendants(child_id))
        
        return descendants
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'lineage_id': self.lineage_id,
            'root_object_id': self.root_object_id,
            'root_object_type': self.root_object_type,
            'nodes': {nid: node.to_dict() for nid, node in self.nodes.items()},
            'access_events': [e.to_dict() for e in self.access_events],
            'transformation_events': [e.to_dict() for e in self.transformation_events],
            'total_accesses': self.total_accesses,
            'unique_users': list(self.unique_users),
            'created_at': self.created_at.isoformat(),
            'last_updated': self.last_updated.isoformat(),
        }


class LineageTracker:
    """
    血緣追蹤器 - 負責記錄和管理資料血緣
    
    特性：
    1. 自動追蹤所有資料操作
    2. 建立資料血緣圖
    3. 支援審計查詢
    4. 合規報告生成
    """
    
    def __init__(self):
        self.lineages: Dict[str, DataLineage] = {}
        self.event_buffer: List[AccessEvent] = []
        self._buffer_size = 1000
    
    def track_create(self, object_id: str, object_type: str, 
                     actor_id: str, source_type: DataSource,
                     metadata: Optional[Dict[str, Any]] = None) -> LineageNode:
        """追蹤物件建立"""
        # 建立新的血緣
        lineage = DataLineage(
            root_object_id=object_id,
            root_object_type=object_type
        )
        
        # 建立根節點
        node = LineageNode(
            object_id=object_id,
            object_type=object_type,
            event_type=LineageEventType.CREATE,
            actor_id=actor_id,
            source_type=source_type,
            metadata=metadata or {}
        )
        
        lineage.add_node(node)
        self.lineages[object_id] = lineage
        
        logger.info(f"Created lineage for object {object_id}")
        return node
    
    def track_access(self, event: AccessEvent):
        """追蹤存取事件"""
        lineage = self.lineages.get(event.resource_id)
        if lineage:
            lineage.add_access_event(event)
        
        # 添加到緩衝區（批次處理）
        self.event_buffer.append(event)
        if len(self.event_buffer) >= self._buffer_size:
            self._flush_events()
    
    def track_transformation(self, event: TransformationEvent):
        """追蹤轉換事件"""
        # 為所有輸出物件建立血緣節點
        for output_id in event.output_objects:
            lineage = self.lineages.get(output_id)
            if lineage:
                lineage.add_transformation_event(event)
                
                # 建立轉換節點
                node = LineageNode(
                    object_id=output_id,
                    event_type=LineageEventType.TRANSFORM,
                    transformation_type=event.transformation_type,
                    transformation_details={
                        'model_used': event.model_used,
                        'confidence_score': event.confidence_score,
                    },
                    parent_nodes=event.input_objects,
                )
                lineage.add_node(node)
    
    def get_lineage(self, object_id: str) -> Optional[DataLineage]:
        """取得物件的血緣"""
        return self.lineages.get(object_id)
    
    def get_access_history(self, object_id: str, 
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None) -> List[AccessEvent]:
        """取得物件的存取歷史"""
        lineage = self.lineages.get(object_id)
        if not lineage:
            return []
        
        events = lineage.access_events
        
        # 時間範圍過濾
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        
        return events
    
    def _flush_events(self):
        """刷新事件緩衝區（寫入持久化儲存）"""
        if not self.event_buffer:
            return
        
        # TODO: 實作持久化邏輯（寫入 Elasticsearch, PostgreSQL 等）
        logger.info(f"Flushing {len(self.event_buffer)} access events")
        self.event_buffer.clear()
    
    def generate_audit_report(self, object_id: str) -> Dict[str, Any]:
        """生成審計報告"""
        lineage = self.lineages.get(object_id)
        if not lineage:
            return {'error': 'Lineage not found'}
        
        return {
            'object_id': object_id,
            'total_accesses': lineage.total_accesses,
            'unique_users': len(lineage.unique_users),
            'created_at': lineage.created_at.isoformat(),
            'last_updated': lineage.last_updated.isoformat(),
            'access_events': [e.to_dict() for e in lineage.access_events[-100:]],  # 最近100條
            'transformation_events': [e.to_dict() for e in lineage.transformation_events],
        }


# 全域血緣追蹤器實例
_lineage_tracker: Optional[LineageTracker] = None


def get_lineage_tracker() -> LineageTracker:
    """取得全域血緣追蹤器實例"""
    global _lineage_tracker
    if _lineage_tracker is None:
        _lineage_tracker = LineageTracker()
    return _lineage_tracker
