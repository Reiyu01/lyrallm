"""
使用者上下文與身份資訊

定義了使用者等級、角色、權限、配額等資料結構。
用於身份感知路由（Identity-Aware Routing）和權限管理。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime


class UserTier(str, Enum):
    """使用者等級枚舉"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"


class UserRole(str, Enum):
    """使用者角色枚舉"""
    GUEST = "guest"
    USER = "user"
    ANALYST = "analyst"
    DEVELOPER = "developer"
    DATA_SCIENTIST = "data_scientist"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class DataAccessLevel(str, Enum):
    """資料存取等級枚舉"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class ResourceQuota:
    """
    資源配額資料結構
    
    追蹤使用者的資源使用情況和配額限制。
    """
    
    # 每月配額
    monthly_tokens: int = 0              # 每月 token 配額
    monthly_requests: int = 0            # 每月請求次數配額
    
    # 已使用量
    tokens_used: int = 0                 # 本月已使用 token 數
    requests_used: int = 0               # 本月已使用請求次數
    
    # 即時限制
    max_concurrent_requests: int = 1     # 最大併發請求數
    max_tokens_per_request: int = 4096   # 單次請求最大 token 數
    
    # 計費週期
    quota_reset_date: Optional[datetime] = None
    
    def is_quota_exceeded(self) -> bool:
        """
        檢查是否超過配額
        
        Returns:
            bool: True 表示已超過配額
        """
        if self.monthly_tokens > 0 and self.tokens_used >= self.monthly_tokens:
            return True
        if self.monthly_requests > 0 and self.requests_used >= self.monthly_requests:
            return True
        return False
    
    def get_remaining_tokens(self) -> int:
        """
        獲取剩餘 token 配額
        
        Returns:
            int: 剩餘 token 數量，-1 表示無限制
        """
        if self.monthly_tokens <= 0:
            return -1  # 無限制
        return max(0, self.monthly_tokens - self.tokens_used)
    
    def get_remaining_requests(self) -> int:
        """
        獲取剩餘請求次數配額
        
        Returns:
            int: 剩餘請求次數，-1 表示無限制
        """
        if self.monthly_requests <= 0:
            return -1  # 無限制
        return max(0, self.monthly_requests - self.requests_used)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'monthly_tokens': self.monthly_tokens,
            'monthly_requests': self.monthly_requests,
            'tokens_used': self.tokens_used,
            'requests_used': self.requests_used,
            'max_concurrent_requests': self.max_concurrent_requests,
            'max_tokens_per_request': self.max_tokens_per_request,
            'quota_reset_date': self.quota_reset_date.isoformat() if self.quota_reset_date else None,
            'is_quota_exceeded': self.is_quota_exceeded(),
            'remaining_tokens': self.get_remaining_tokens(),
            'remaining_requests': self.get_remaining_requests()
        }


@dataclass
class UserContext:
    """
    使用者上下文資料結構
    
    包含使用者的完整身份資訊、權限、配額等。
    用於身份感知路由和存取控制。
    """
    
    # 基本身份資訊
    user_id: str
    username: Optional[str] = None
    tier: UserTier = UserTier.FREE
    
    # 角色與權限
    roles: Set[UserRole] = field(default_factory=lambda: {UserRole.USER})
    permissions: Set[str] = field(default_factory=set)
    
    # 資料存取等級
    data_access_level: DataAccessLevel = DataAccessLevel.PUBLIC
    
    # 資源配額
    quota: ResourceQuota = field(default_factory=ResourceQuota)
    
    # 組織/租戶資訊（多租戶場景）
    organization_id: Optional[str] = None
    department: Optional[str] = None
    
    # 額外屬性
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def has_role(self, role: UserRole) -> bool:
        """
        檢查是否擁有特定角色
        
        Args:
            role: 要檢查的角色
            
        Returns:
            bool: True 表示擁有該角色
        """
        return role in self.roles
    
    def has_permission(self, permission: str) -> bool:
        """
        檢查是否擁有特定權限
        
        Args:
            permission: 要檢查的權限字串（例如 "use_web_search", "access_confidential_data"）
            
        Returns:
            bool: True 表示擁有該權限
        """
        return permission in self.permissions
    
    def can_access_data_level(self, required_level: DataAccessLevel) -> bool:
        """
        檢查是否可以存取特定等級的資料
        
        Args:
            required_level: 需要的資料存取等級
            
        Returns:
            bool: True 表示可以存取
        """
        level_order = {
            DataAccessLevel.PUBLIC: 0,
            DataAccessLevel.INTERNAL: 1,
            DataAccessLevel.CONFIDENTIAL: 2,
            DataAccessLevel.RESTRICTED: 3
        }
        
        user_level = level_order.get(self.data_access_level, 0)
        required = level_order.get(required_level, 0)
        
        return user_level >= required
    
    def is_admin(self) -> bool:
        """
        檢查是否為管理員
        
        Returns:
            bool: True 表示是管理員
        """
        return self.has_role(UserRole.ADMIN) or self.has_role(UserRole.SUPER_ADMIN)
    
    def is_enterprise(self) -> bool:
        """
        檢查是否為企業級使用者
        
        Returns:
            bool: True 表示是企業級使用者
        """
        return self.tier in [UserTier.ENTERPRISE, UserTier.ADMIN]
    
    def get_max_model_tier(self) -> str:
        """
        根據使用者等級獲取可使用的最高模型等級
        
        Returns:
            str: 模型等級 ("light", "medium", "heavy", "premium")
        """
        tier_to_model = {
            UserTier.FREE: "light",
            UserTier.PRO: "heavy",
            UserTier.ENTERPRISE: "premium",
            UserTier.ADMIN: "premium"
        }
        return tier_to_model.get(self.tier, "light")
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'tier': self.tier.value,
            'roles': [role.value for role in self.roles],
            'permissions': list(self.permissions),
            'data_access_level': self.data_access_level.value,
            'quota': self.quota.to_dict(),
            'organization_id': self.organization_id,
            'department': self.department,
            'metadata': self.metadata,
            'is_admin': self.is_admin(),
            'is_enterprise': self.is_enterprise(),
            'max_model_tier': self.get_max_model_tier()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserContext':
        """
        從字典創建 UserContext 實例
        
        Args:
            data: 包含使用者上下文資訊的字典
            
        Returns:
            UserContext: 新的實例
        """
        quota_data = data.get('quota', {})
        quota = ResourceQuota(
            monthly_tokens=quota_data.get('monthly_tokens', 0),
            monthly_requests=quota_data.get('monthly_requests', 0),
            tokens_used=quota_data.get('tokens_used', 0),
            requests_used=quota_data.get('requests_used', 0),
            max_concurrent_requests=quota_data.get('max_concurrent_requests', 1),
            max_tokens_per_request=quota_data.get('max_tokens_per_request', 4096)
        )
        
        return cls(
            user_id=data['user_id'],
            username=data.get('username'),
            tier=UserTier(data.get('tier', 'free')),
            roles={UserRole(role) for role in data.get('roles', ['user'])},
            permissions=set(data.get('permissions', [])),
            data_access_level=DataAccessLevel(data.get('data_access_level', 'public')),
            quota=quota,
            organization_id=data.get('organization_id'),
            department=data.get('department'),
            metadata=data.get('metadata', {})
        )
    
    @classmethod
    def create_default_free_user(cls, user_id: str) -> 'UserContext':
        """
        創建預設的免費使用者上下文
        
        Args:
            user_id: 使用者 ID
            
        Returns:
            UserContext: 免費使用者實例
        """
        return cls(
            user_id=user_id,
            tier=UserTier.FREE,
            roles={UserRole.USER},
            permissions=set(),
            data_access_level=DataAccessLevel.PUBLIC,
            quota=ResourceQuota(
                monthly_tokens=100000,      # 免費版每月 10 萬 tokens
                monthly_requests=1000,      # 每月 1000 次請求
                max_concurrent_requests=1,  # 單一併發
                max_tokens_per_request=4096 # 單次最多 4K tokens
            )
        )
    
    @classmethod
    def create_enterprise_user(cls, user_id: str, organization_id: str) -> 'UserContext':
        """
        創建企業級使用者上下文
        
        Args:
            user_id: 使用者 ID
            organization_id: 組織 ID
            
        Returns:
            UserContext: 企業級使用者實例
        """
        return cls(
            user_id=user_id,
            tier=UserTier.ENTERPRISE,
            roles={UserRole.USER, UserRole.DEVELOPER, UserRole.ANALYST},
            permissions={
                'use_web_search',
                'use_code_interpreter',
                'use_image_generation',
                'use_data_analysis',
                'access_internal_data',
                'access_confidential_data'
            },
            data_access_level=DataAccessLevel.CONFIDENTIAL,
            organization_id=organization_id,
            quota=ResourceQuota(
                monthly_tokens=-1,           # 無限制
                monthly_requests=-1,         # 無限制
                max_concurrent_requests=10,  # 10 個併發
                max_tokens_per_request=32768 # 單次最多 32K tokens
            )
        )
