"""
Ontology Objects - 本體論物件系統

定義企業級物件模型，包括：
- 文件（Documents）
- 對話（Conversations）
- 模型（Models）
- 使用者（Users）
- 組織（Organizations）

每個物件都包含安全標籤、存取控制、審計日誌等。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, FrozenSet
from datetime import datetime
from uuid import uuid4


class ObjectType(str, Enum):
    """物件類型枚舉"""
    DOCUMENT = "document"
    CONVERSATION = "conversation"
    MODEL = "model"
    USER = "user"
    ORGANIZATION = "organization"
    API_KEY = "api_key"
    DATASET = "dataset"
    PROMPT_TEMPLATE = "prompt_template"


@dataclass
class SecurityLabel:
    """安全標籤"""
    classification: str  # PUBLIC, INTERNAL, CONFIDENTIAL, SECRET
    categories: Set[str] = field(default_factory=set)  # PII, FINANCIAL, MEDICAL, etc.
    handling_caveats: Set[str] = field(default_factory=set)  # NO_EXPORT, ENCRYPT_AT_REST, etc.
    expiry_date: Optional[datetime] = None
    
    def is_more_restrictive_than(self, other: 'SecurityLabel') -> bool:
        """判斷此標籤是否比另一個更嚴格"""
        hierarchy = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "SECRET": 3}
        return hierarchy.get(self.classification, 0) > hierarchy.get(other.classification, 0)


@dataclass
class AccessControl:
    """存取控制清單（ACL）"""
    owner_id: str
    owner_type: str  # user, organization, system
    
    # 角色基礎存取控制
    allowed_roles: FrozenSet[str] = field(default_factory=frozenset)
    denied_roles: FrozenSet[str] = field(default_factory=frozenset)
    
    # 使用者/組織基礎存取控制
    allowed_users: FrozenSet[str] = field(default_factory=frozenset)
    denied_users: FrozenSet[str] = field(default_factory=frozenset)
    allowed_organizations: FrozenSet[str] = field(default_factory=frozenset)
    denied_organizations: FrozenSet[str] = field(default_factory=frozenset)
    
    # 屬性基礎存取控制（ABAC）
    required_attributes: Dict[str, Any] = field(default_factory=dict)
    
    # 時間基礎存取控制
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    
    # IP/地理位置限制
    allowed_ip_ranges: List[str] = field(default_factory=list)
    allowed_countries: List[str] = field(default_factory=list)
    
    def can_access(self, user_id: str, user_roles: Set[str], 
                   organization_id: Optional[str] = None,
                   user_attributes: Optional[Dict[str, Any]] = None,
                   timestamp: Optional[datetime] = None,
                   ip_address: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        檢查使用者是否可以存取
        
        Returns:
            (can_access: bool, denial_reason: Optional[str])
        """
        # 1. 檢查時間限制
        now = timestamp or datetime.now()
        if self.valid_from and now < self.valid_from:
            return False, f"Access not yet valid (starts {self.valid_from})"
        if self.valid_until and now > self.valid_until:
            return False, f"Access expired (ended {self.valid_until})"
        
        # 2. 檢查明確拒絕
        if user_id in self.denied_users:
            return False, "User explicitly denied"
        if organization_id and organization_id in self.denied_organizations:
            return False, "Organization explicitly denied"
        if any(role in self.denied_roles for role in user_roles):
            return False, "Role explicitly denied"
        
        # 3. 檢查明確允許
        if user_id in self.allowed_users:
            return True, None
        if organization_id and organization_id in self.allowed_organizations:
            return True, None
        if any(role in self.allowed_roles for role in user_roles):
            return True, None
        
        # 4. 檢查屬性要求（ABAC）
        if self.required_attributes and user_attributes:
            for key, required_value in self.required_attributes.items():
                if user_attributes.get(key) != required_value:
                    return False, f"Required attribute not met: {key}"
        
        # 5. 預設拒絕（如果有任何限制但都不匹配）
        if (self.allowed_users or self.allowed_organizations or self.allowed_roles):
            return False, "Not in allowed list"
        
        # 6. 預設允許（無任何限制）
        return True, None


@dataclass
class OntologyObject:
    """本體論物件基類"""
    object_id: str = field(default_factory=lambda: str(uuid4()))
    object_type: ObjectType = ObjectType.DOCUMENT
    
    # 基本資訊
    title: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[str] = None
    
    # 安全控制
    security_label: SecurityLabel = field(default_factory=lambda: SecurityLabel(classification="PUBLIC"))
    access_control: AccessControl = field(default_factory=lambda: AccessControl(owner_id="system", owner_type="system"))
    
    # 標籤與分類
    tags: Set[str] = field(default_factory=set)
    categories: Set[str] = field(default_factory=set)
    
    # 關聯
    parent_id: Optional[str] = None
    related_objects: List[str] = field(default_factory=list)
    
    # 元數據
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 審計
    version: int = 1
    checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'object_id': self.object_id,
            'object_type': self.object_type.value,
            'title': self.title,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'created_by': self.created_by,
            'security_label': {
                'classification': self.security_label.classification,
                'categories': list(self.security_label.categories),
                'handling_caveats': list(self.security_label.handling_caveats),
            },
            'tags': list(self.tags),
            'categories': list(self.categories),
            'metadata': self.metadata,
            'version': self.version,
        }


@dataclass
class Document(OntologyObject):
    """文件物件"""
    object_type: ObjectType = ObjectType.DOCUMENT
    
    # 文件內容
    content: str = ""
    content_type: str = "text/plain"
    content_hash: Optional[str] = None
    
    # 文件屬性
    size_bytes: int = 0
    language: str = "zh-TW"
    embedding: Optional[List[float]] = None
    
    # 來源追蹤
    source_type: Optional[str] = None  # upload, api, integration
    source_url: Optional[str] = None
    
    # 資料治理
    retention_days: Optional[int] = None
    deletion_date: Optional[datetime] = None
    is_encrypted: bool = False


@dataclass
class Conversation(OntologyObject):
    """對話物件"""
    object_type: ObjectType = ObjectType.CONVERSATION
    
    # 對話參與者
    user_id: str = ""
    model_id: Optional[str] = None
    
    # 對話內容
    messages: List[Dict[str, Any]] = field(default_factory=list)
    message_count: int = 0
    
    # 路由資訊
    routing_decision: Optional[Dict[str, Any]] = None
    models_used: List[str] = field(default_factory=list)
    
    # 成本追蹤
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    
    # 品質指標
    user_feedback: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None
    
    # 安全事件
    safety_violations: List[Dict[str, Any]] = field(default_factory=list)
    guardrail_triggers: List[str] = field(default_factory=list)


@dataclass
class Model(OntologyObject):
    """模型物件"""
    object_type: ObjectType = ObjectType.MODEL
    
    # 模型身份
    model_name: str = ""
    provider: str = ""
    deployment_id: Optional[str] = None
    
    # 模型能力
    capabilities: Set[str] = field(default_factory=set)  # chat, embedding, image_gen, etc.
    supported_intents: Set[str] = field(default_factory=set)
    max_context_window: int = 4096
    
    # 成本
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    
    # 效能指標
    avg_latency_ms: Optional[float] = None
    success_rate: Optional[float] = None
    health_status: str = "unknown"  # healthy, degraded, unhealthy
    
    # 配額限制
    rate_limit_rpm: Optional[int] = None  # requests per minute
    rate_limit_tpm: Optional[int] = None  # tokens per minute
    
    # 合規性
    compliance_certifications: Set[str] = field(default_factory=set)  # SOC2, HIPAA, GDPR, etc.
    data_residency: Optional[str] = None  # US, EU, Asia, etc.


@dataclass
class User(OntologyObject):
    """使用者物件"""
    object_type: ObjectType = ObjectType.USER
    
    # 身份資訊
    user_id: str = ""
    username: str = ""
    email: Optional[str] = None
    
    # 角色與權限
    roles: Set[str] = field(default_factory=set)
    permissions: Set[str] = field(default_factory=set)
    
    # 組織關係
    organization_id: Optional[str] = None
    department: Optional[str] = None
    
    # 使用者等級
    tier: str = "free"  # free, pro, enterprise
    
    # 配額
    monthly_token_quota: int = 0
    tokens_used_this_month: int = 0
    
    # 安全設定
    mfa_enabled: bool = False
    ip_whitelist: List[str] = field(default_factory=list)
    
    # 審計
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0


@dataclass
class Organization(OntologyObject):
    """組織物件"""
    object_type: ObjectType = ObjectType.ORGANIZATION
    
    # 組織資訊
    organization_id: str = ""
    organization_name: str = ""
    industry: Optional[str] = None
    
    # 成員
    member_count: int = 0
    admin_users: Set[str] = field(default_factory=set)
    
    # 配額與計費
    subscription_tier: str = "free"
    monthly_budget_usd: float = 0.0
    budget_used_this_month: float = 0.0
    
    # 安全政策
    enforce_mfa: bool = False
    allowed_ip_ranges: List[str] = field(default_factory=list)
    data_residency_requirement: Optional[str] = None
    
    # 合規要求
    compliance_requirements: Set[str] = field(default_factory=set)
    
    # SSO 設定
    sso_enabled: bool = False
    sso_provider: Optional[str] = None
    sso_metadata: Dict[str, Any] = field(default_factory=dict)
