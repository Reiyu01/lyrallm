"""
Policy Engine - 策略引擎

實現 Palantir AIP 風格的策略引擎，支援：
1. 多層策略決策（Organization → Team → User）
2. 策略繼承與覆蓋
3. 條件式策略（if-then-else）
4. 策略衝突解決
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PolicyAction(str, Enum):
    """策略動作"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_MFA = "require_mfa"
    REDACT = "redact"
    ENCRYPT = "encrypt"
    LOG_ONLY = "log_only"
    BLOCK_AND_ALERT = "block_and_alert"


class PolicyScope(str, Enum):
    """策略範圍"""
    GLOBAL = "global"
    ORGANIZATION = "organization"
    TEAM = "team"
    USER = "user"
    RESOURCE = "resource"


@dataclass
class PolicyCondition:
    """策略條件"""
    field: str  # 要檢查的欄位，如 "user.tier", "content.safety_level"
    operator: str  # eq, ne, gt, lt, in, contains, regex
    value: Any  # 比較值
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """評估條件是否滿足"""
        try:
            # 使用點號表示法取得嵌套值，如 "user.tier"
            field_value = self._get_nested_value(context, self.field)
            
            if self.operator == "eq":
                return field_value == self.value
            elif self.operator == "ne":
                return field_value != self.value
            elif self.operator == "gt":
                return field_value > self.value
            elif self.operator == "lt":
                return field_value < self.value
            elif self.operator == "gte":
                return field_value >= self.value
            elif self.operator == "lte":
                return field_value <= self.value
            elif self.operator == "in":
                return field_value in self.value
            elif self.operator == "not_in":
                return field_value not in self.value
            elif self.operator == "contains":
                return self.value in field_value
            elif self.operator == "regex":
                import re
                return bool(re.match(self.value, str(field_value)))
            else:
                logger.warning(f"Unknown operator: {self.operator}")
                return False
        except Exception as e:
            logger.error(f"Error evaluating condition {self.field} {self.operator} {self.value}: {e}")
            return False
    
    @staticmethod
    def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
        """取得嵌套字典值，如 "user.tier" -> data["user"]["tier"]"""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


@dataclass
class PolicyRule:
    """策略規則"""
    rule_id: str
    name: str
    description: str
    
    # 條件（所有條件都必須滿足）
    conditions: List[PolicyCondition] = field(default_factory=list)
    
    # 動作
    action: PolicyAction = PolicyAction.ALLOW
    
    # 優先級（數字越大優先級越高）
    priority: int = 0
    
    # 例外情況（滿足條件時忽略規則）
    exceptions: List[PolicyCondition] = field(default_factory=list)
    
    # 元數據
    tags: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)
    enabled: bool = True
    
    def matches(self, context: Dict[str, Any]) -> bool:
        """檢查規則是否匹配給定上下文"""
        if not self.enabled:
            return False
        
        # 檢查例外條件
        if any(exc.evaluate(context) for exc in self.exceptions):
            return False
        
        # 所有條件都必須滿足
        return all(cond.evaluate(context) for cond in self.conditions)


@dataclass
class SecurityPolicy:
    """安全策略"""
    policy_id: str
    name: str
    description: str
    scope: PolicyScope = PolicyScope.GLOBAL
    
    # 策略規則（按優先級排序）
    rules: List[PolicyRule] = field(default_factory=list)
    
    # 繼承的策略
    inherits_from: List[str] = field(default_factory=list)
    
    # 元數據
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[str] = None
    enabled: bool = True
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[PolicyRule]:
        """
        評估策略，返回第一個匹配的規則
        
        Returns:
            匹配的規則，如果沒有匹配則返回 None
        """
        if not self.enabled:
            return None
        
        # 按優先級排序規則
        sorted_rules = sorted(self.rules, key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if rule.matches(context):
                return rule
        
        return None


@dataclass
class AccessPolicy(SecurityPolicy):
    """存取控制策略"""
    
    # 允許的角色
    allowed_roles: Set[str] = field(default_factory=set)
    
    # 拒絕的角色
    denied_roles: Set[str] = field(default_factory=set)
    
    # 需要的權限
    required_permissions: Set[str] = field(default_factory=set)


@dataclass
class DataPolicy(SecurityPolicy):
    """資料處理策略"""
    
    # 資料分類
    data_classification: Optional[str] = None
    
    # 保留期限（天）
    retention_days: Optional[int] = None
    
    # 是否需要加密
    requires_encryption: bool = False
    
    # 是否需要遮罩
    requires_masking: bool = False
    
    # 允許的處理地區
    allowed_regions: List[str] = field(default_factory=list)


@dataclass
class PolicyDecision:
    """策略決策結果"""
    action: PolicyAction
    policy_id: Optional[str] = None
    rule_id: Optional[str] = None
    reason: str = ""
    
    # 匹配的規則
    matched_rules: List[PolicyRule] = field(default_factory=list)
    
    # 需要的額外動作
    additional_actions: List[str] = field(default_factory=list)
    
    # 決策時間
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 決策追蹤
    evaluation_trace: List[str] = field(default_factory=list)
    
    def is_allowed(self) -> bool:
        """是否允許操作"""
        return self.action in [PolicyAction.ALLOW, PolicyAction.LOG_ONLY]
    
    def requires_approval(self) -> bool:
        """是否需要核准"""
        return self.action == PolicyAction.REQUIRE_APPROVAL
    
    def is_denied(self) -> bool:
        """是否拒絕操作"""
        return self.action in [PolicyAction.DENY, PolicyAction.BLOCK_AND_ALERT]
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'action': self.action.value,
            'policy_id': self.policy_id,
            'rule_id': self.rule_id,
            'reason': self.reason,
            'is_allowed': self.is_allowed(),
            'requires_approval': self.requires_approval(),
            'additional_actions': self.additional_actions,
            'timestamp': self.timestamp.isoformat(),
            'evaluation_trace': self.evaluation_trace,
        }


class PolicyEngine:
    """
    策略引擎 - 負責評估和執行安全策略
    
    特性：
    1. 多層策略（Global → Organization → Team → User）
    2. 策略繼承
    3. 衝突解決（Deny 優先）
    4. 審計追蹤
    """
    
    def __init__(self):
        self.policies: Dict[str, SecurityPolicy] = {}
        self.policy_cache: Dict[str, PolicyDecision] = {}
        self._cache_ttl = 300  # 5分鐘快取
    
    def register_policy(self, policy: SecurityPolicy):
        """註冊策略"""
        self.policies[policy.policy_id] = policy
        logger.info(f"Registered policy: {policy.name} ({policy.policy_id})")
    
    def unregister_policy(self, policy_id: str):
        """移除策略"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            logger.info(f"Unregistered policy: {policy_id}")
    
    def evaluate(self, context: Dict[str, Any], 
                 policy_ids: Optional[List[str]] = None) -> PolicyDecision:
        """
        評估策略並返回決策
        
        Args:
            context: 評估上下文（包含 user, resource, action 等資訊）
            policy_ids: 要評估的策略 ID 列表，如果為 None 則評估所有策略
            
        Returns:
            PolicyDecision: 策略決策結果
        """
        evaluation_trace = []
        matched_rules = []
        
        # 選擇要評估的策略
        policies_to_evaluate = []
        if policy_ids:
            policies_to_evaluate = [self.policies[pid] for pid in policy_ids if pid in self.policies]
        else:
            policies_to_evaluate = list(self.policies.values())
        
        # 按範圍排序（Global → Organization → Team → User）
        scope_priority = {
            PolicyScope.GLOBAL: 0,
            PolicyScope.ORGANIZATION: 1,
            PolicyScope.TEAM: 2,
            PolicyScope.USER: 3,
            PolicyScope.RESOURCE: 4,
        }
        policies_to_evaluate.sort(key=lambda p: scope_priority.get(p.scope, 999))
        
        # 評估所有策略
        for policy in policies_to_evaluate:
            evaluation_trace.append(f"Evaluating policy: {policy.name} ({policy.policy_id})")
            
            matched_rule = policy.evaluate(context)
            if matched_rule:
                evaluation_trace.append(f"  ✓ Matched rule: {matched_rule.name} -> {matched_rule.action.value}")
                matched_rules.append(matched_rule)
            else:
                evaluation_trace.append(f"  ✗ No match")
        
        # 衝突解決：Deny 優先
        final_action = PolicyAction.ALLOW
        final_rule = None
        final_policy = None
        
        for rule in matched_rules:
            if rule.action == PolicyAction.DENY or rule.action == PolicyAction.BLOCK_AND_ALERT:
                # Deny 優先
                final_action = rule.action
                final_rule = rule
                break
            elif rule.action == PolicyAction.REQUIRE_APPROVAL:
                # Require Approval 次之
                final_action = rule.action
                final_rule = rule
            elif final_action == PolicyAction.ALLOW:
                # 保留最後一個 Allow
                final_action = rule.action
                final_rule = rule
        
        # 建立決策
        decision = PolicyDecision(
            action=final_action,
            policy_id=final_policy.policy_id if final_policy else None,
            rule_id=final_rule.rule_id if final_rule else None,
            reason=final_rule.description if final_rule else "No matching rules",
            matched_rules=matched_rules,
            evaluation_trace=evaluation_trace,
        )
        
        logger.debug(f"Policy evaluation result: {final_action.value} - {decision.reason}")
        return decision
    
    def evaluate_data_access(self, user_id: str, user_roles: Set[str],
                            resource_id: str, resource_classification: str,
                            action: str = "read") -> PolicyDecision:
        """
        評估資料存取請求
        
        Args:
            user_id: 使用者 ID
            user_roles: 使用者角色集合
            resource_id: 資源 ID
            resource_classification: 資源分類（PUBLIC, INTERNAL, CONFIDENTIAL, SECRET）
            action: 操作類型（read, write, delete）
            
        Returns:
            PolicyDecision: 策略決策結果
        """
        context = {
            'user': {
                'id': user_id,
                'roles': list(user_roles),
            },
            'resource': {
                'id': resource_id,
                'classification': resource_classification,
            },
            'action': action,
            'timestamp': datetime.now().isoformat(),
        }
        
        return self.evaluate(context)
    
    def load_policies_from_config(self, config: Dict[str, Any]):
        """從配置檔案載入策略"""
        for policy_config in config.get('policies', []):
            policy = self._parse_policy_config(policy_config)
            if policy:
                self.register_policy(policy)
    
    def _parse_policy_config(self, config: Dict[str, Any]) -> Optional[SecurityPolicy]:
        """解析策略配置"""
        try:
            # 解析規則
            rules = []
            for rule_config in config.get('rules', []):
                conditions = [
                    PolicyCondition(
                        field=c['field'],
                        operator=c['operator'],
                        value=c['value']
                    )
                    for c in rule_config.get('conditions', [])
                ]
                
                rule = PolicyRule(
                    rule_id=rule_config['rule_id'],
                    name=rule_config['name'],
                    description=rule_config.get('description', ''),
                    conditions=conditions,
                    action=PolicyAction(rule_config.get('action', 'allow')),
                    priority=rule_config.get('priority', 0),
                    enabled=rule_config.get('enabled', True),
                )
                rules.append(rule)
            
            # 建立策略
            policy = SecurityPolicy(
                policy_id=config['policy_id'],
                name=config['name'],
                description=config.get('description', ''),
                scope=PolicyScope(config.get('scope', 'global')),
                rules=rules,
                enabled=config.get('enabled', True),
            )
            
            return policy
        except Exception as e:
            logger.error(f"Failed to parse policy config: {e}")
            return None


# 全域策略引擎實例
_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """取得全域策略引擎實例"""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
