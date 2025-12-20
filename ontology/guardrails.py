"""
Guardrails - 護欄系統

實現 Palantir AIP 風格的護欄機制：
1. 內容護欄（Content Guardrails）- 過濾不當內容
2. 成本護欄（Cost Guardrails）- 控制支出
3. 速率護欄（Rate Limit Guardrails）- 防止濫用
4. 合規護欄（Compliance Guardrails）- 確保合規
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class GuardrailSeverity(str, Enum):
    """護欄違規嚴重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class GuardrailAction(str, Enum):
    """護欄觸發動作"""
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"
    REDIRECT = "redirect"
    THROTTLE = "throttle"


@dataclass
class GuardrailViolation:
    """護欄違規記錄"""
    violation_id: str
    guardrail_id: str
    guardrail_name: str
    
    # 違規詳情
    severity: GuardrailSeverity
    action: GuardrailAction
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    # 上下文
    user_id: Optional[str] = None
    resource_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 處理資訊
    handled: bool = False
    handler_action: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            'violation_id': self.violation_id,
            'guardrail_id': self.guardrail_id,
            'guardrail_name': self.guardrail_name,
            'severity': self.severity.value,
            'action': self.action.value,
            'reason': self.reason,
            'details': self.details,
            'user_id': self.user_id,
            'resource_id': self.resource_id,
            'timestamp': self.timestamp.isoformat(),
            'handled': self.handled,
        }


class Guardrail(ABC):
    """護欄基類"""
    
    def __init__(self, guardrail_id: str, name: str, enabled: bool = True):
        self.guardrail_id = guardrail_id
        self.name = name
        self.enabled = enabled
        self.violation_count = 0
    
    @abstractmethod
    def check(self, context: Dict[str, Any]) -> Optional[GuardrailViolation]:
        """
        檢查是否違反護欄規則
        
        Args:
            context: 檢查上下文
            
        Returns:
            違規記錄，如果沒有違規則返回 None
        """
        pass
    
    def _create_violation(self, severity: GuardrailSeverity, 
                         action: GuardrailAction, reason: str,
                         context: Dict[str, Any]) -> GuardrailViolation:
        """建立違規記錄"""
        from uuid import uuid4
        self.violation_count += 1
        
        return GuardrailViolation(
            violation_id=str(uuid4()),
            guardrail_id=self.guardrail_id,
            guardrail_name=self.name,
            severity=severity,
            action=action,
            reason=reason,
            details=context,
            user_id=context.get('user_id'),
            resource_id=context.get('resource_id'),
        )


class ContentGuardrail(Guardrail):
    """內容護欄 - 檢查內容安全性"""
    
    def __init__(self, guardrail_id: str = "content_safety", 
                 name: str = "Content Safety Guardrail",
                 enabled: bool = True):
        super().__init__(guardrail_id, name, enabled)
        
        # 敏感詞庫
        self.blocked_keywords: Set[str] = set()
        
        # PII 檢測模式
        self.pii_patterns: List[str] = []
        
        # 最大風險等級
        self.max_allowed_risk = "MEDIUM"
    
    def check(self, context: Dict[str, Any]) -> Optional[GuardrailViolation]:
        """檢查內容安全性"""
        if not self.enabled:
            return None
        
        content = context.get('content', '')
        safety_labels = context.get('safety_labels', {})
        
        # 檢查安全標籤
        if isinstance(safety_labels, dict):
            risk_level = safety_labels.get('risk_level', 'NONE')
            if self._is_risk_too_high(risk_level):
                return self._create_violation(
                    severity=GuardrailSeverity.ERROR,
                    action=GuardrailAction.BLOCK,
                    reason=f"Content risk level {risk_level} exceeds maximum allowed {self.max_allowed_risk}",
                    context=context
                )
            
            # 檢查 Jailbreak 嘗試
            if safety_labels.get('jailbreak_attempt'):
                return self._create_violation(
                    severity=GuardrailSeverity.CRITICAL,
                    action=GuardrailAction.BLOCK,
                    reason="Jailbreak attempt detected",
                    context=context
                )
        
        # 檢查敏感詞
        if self.blocked_keywords:
            content_lower = content.lower()
            for keyword in self.blocked_keywords:
                if keyword.lower() in content_lower:
                    return self._create_violation(
                        severity=GuardrailSeverity.WARNING,
                        action=GuardrailAction.WARN,
                        reason=f"Blocked keyword detected: {keyword}",
                        context=context
                    )
        
        return None
    
    def _is_risk_too_high(self, risk_level: str) -> bool:
        """檢查風險等級是否過高"""
        hierarchy = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        return hierarchy.get(risk_level, 0) > hierarchy.get(self.max_allowed_risk, 2)


class CostGuardrail(Guardrail):
    """成本護欄 - 控制支出"""
    
    def __init__(self, guardrail_id: str = "cost_control",
                 name: str = "Cost Control Guardrail",
                 enabled: bool = True):
        super().__init__(guardrail_id, name, enabled)
        
        # 成本限制
        self.daily_limit_usd: Optional[float] = None
        self.monthly_limit_usd: Optional[float] = None
        self.per_request_limit_usd: Optional[float] = None
        
        # 使用追蹤
        self.daily_usage: Dict[str, float] = {}
        self.monthly_usage: Dict[str, float] = {}
    
    def check(self, context: Dict[str, Any]) -> Optional[GuardrailViolation]:
        """檢查成本限制"""
        if not self.enabled:
            return None
        
        user_id = context.get('user_id', 'unknown')
        estimated_cost = context.get('estimated_cost_usd', 0.0)
        
        # 檢查單次請求成本
        if self.per_request_limit_usd and estimated_cost > self.per_request_limit_usd:
            return self._create_violation(
                severity=GuardrailSeverity.WARNING,
                action=GuardrailAction.REQUIRE_APPROVAL,
                reason=f"Request cost ${estimated_cost:.4f} exceeds per-request limit ${self.per_request_limit_usd:.4f}",
                context=context
            )
        
        # 檢查每日限制
        if self.daily_limit_usd:
            today = datetime.now().strftime('%Y-%m-%d')
            user_daily_key = f"{user_id}:{today}"
            current_daily = self.daily_usage.get(user_daily_key, 0.0)
            
            if current_daily + estimated_cost > self.daily_limit_usd:
                return self._create_violation(
                    severity=GuardrailSeverity.ERROR,
                    action=GuardrailAction.BLOCK,
                    reason=f"Daily budget ${self.daily_limit_usd:.2f} exceeded (current: ${current_daily:.2f})",
                    context=context
                )
        
        # 檢查每月限制
        if self.monthly_limit_usd:
            month = datetime.now().strftime('%Y-%m')
            user_monthly_key = f"{user_id}:{month}"
            current_monthly = self.monthly_usage.get(user_monthly_key, 0.0)
            
            if current_monthly + estimated_cost > self.monthly_limit_usd:
                return self._create_violation(
                    severity=GuardrailSeverity.CRITICAL,
                    action=GuardrailAction.BLOCK,
                    reason=f"Monthly budget ${self.monthly_limit_usd:.2f} exceeded (current: ${current_monthly:.2f})",
                    context=context
                )
        
        return None
    
    def record_usage(self, user_id: str, cost_usd: float):
        """記錄使用成本"""
        today = datetime.now().strftime('%Y-%m-%d')
        month = datetime.now().strftime('%Y-%m')
        
        daily_key = f"{user_id}:{today}"
        monthly_key = f"{user_id}:{month}"
        
        self.daily_usage[daily_key] = self.daily_usage.get(daily_key, 0.0) + cost_usd
        self.monthly_usage[monthly_key] = self.monthly_usage.get(monthly_key, 0.0) + cost_usd


class RateLimitGuardrail(Guardrail):
    """速率限制護欄 - 防止濫用"""
    
    def __init__(self, guardrail_id: str = "rate_limit",
                 name: str = "Rate Limit Guardrail",
                 enabled: bool = True):
        super().__init__(guardrail_id, name, enabled)
        
        # 速率限制
        self.requests_per_minute: Optional[int] = None
        self.requests_per_hour: Optional[int] = None
        self.requests_per_day: Optional[int] = None
        
        # Token 限制
        self.tokens_per_minute: Optional[int] = None
        self.tokens_per_hour: Optional[int] = None
        
        # 使用追蹤
        self.request_history: Dict[str, List[datetime]] = {}
        self.token_history: Dict[str, List[tuple[datetime, int]]] = {}
    
    def check(self, context: Dict[str, Any]) -> Optional[GuardrailViolation]:
        """檢查速率限制"""
        if not self.enabled:
            return None
        
        user_id = context.get('user_id', 'unknown')
        estimated_tokens = context.get('estimated_tokens', 0)
        now = datetime.now()
        
        # 清理過期記錄
        self._cleanup_history(user_id, now)
        
        # 檢查請求速率
        if self.requests_per_minute:
            recent_requests = self._count_recent_requests(user_id, now, minutes=1)
            if recent_requests >= self.requests_per_minute:
                return self._create_violation(
                    severity=GuardrailSeverity.WARNING,
                    action=GuardrailAction.THROTTLE,
                    reason=f"Rate limit exceeded: {recent_requests}/{self.requests_per_minute} requests per minute",
                    context=context
                )
        
        if self.requests_per_hour:
            recent_requests = self._count_recent_requests(user_id, now, minutes=60)
            if recent_requests >= self.requests_per_hour:
                return self._create_violation(
                    severity=GuardrailSeverity.ERROR,
                    action=GuardrailAction.BLOCK,
                    reason=f"Rate limit exceeded: {recent_requests}/{self.requests_per_hour} requests per hour",
                    context=context
                )
        
        # 檢查 Token 速率
        if self.tokens_per_minute:
            recent_tokens = self._count_recent_tokens(user_id, now, minutes=1)
            if recent_tokens + estimated_tokens > self.tokens_per_minute:
                return self._create_violation(
                    severity=GuardrailSeverity.WARNING,
                    action=GuardrailAction.THROTTLE,
                    reason=f"Token rate limit exceeded: {recent_tokens}/{self.tokens_per_minute} tokens per minute",
                    context=context
                )
        
        return None
    
    def record_request(self, user_id: str, tokens: int = 0):
        """記錄請求"""
        now = datetime.now()
        
        if user_id not in self.request_history:
            self.request_history[user_id] = []
        self.request_history[user_id].append(now)
        
        if tokens > 0:
            if user_id not in self.token_history:
                self.token_history[user_id] = []
            self.token_history[user_id].append((now, tokens))
    
    def _count_recent_requests(self, user_id: str, now: datetime, minutes: int) -> int:
        """計算最近的請求數"""
        if user_id not in self.request_history:
            return 0
        
        cutoff = now - timedelta(minutes=minutes)
        return sum(1 for ts in self.request_history[user_id] if ts >= cutoff)
    
    def _count_recent_tokens(self, user_id: str, now: datetime, minutes: int) -> int:
        """計算最近的 token 數"""
        if user_id not in self.token_history:
            return 0
        
        cutoff = now - timedelta(minutes=minutes)
        return sum(tokens for ts, tokens in self.token_history[user_id] if ts >= cutoff)
    
    def _cleanup_history(self, user_id: str, now: datetime):
        """清理過期的歷史記錄"""
        cutoff = now - timedelta(days=1)
        
        if user_id in self.request_history:
            self.request_history[user_id] = [
                ts for ts in self.request_history[user_id] if ts >= cutoff
            ]
        
        if user_id in self.token_history:
            self.token_history[user_id] = [
                (ts, tokens) for ts, tokens in self.token_history[user_id] if ts >= cutoff
            ]


class GuardrailEngine:
    """
    護欄引擎 - 統一管理所有護欄
    
    特性：
    1. 多護欄並行檢查
    2. 違規記錄與追蹤
    3. 自動執行護欄動作
    4. 統計與報告
    """
    
    def __init__(self):
        self.guardrails: Dict[str, Guardrail] = {}
        self.violation_history: List[GuardrailViolation] = []
        self._max_history = 10000
    
    def register_guardrail(self, guardrail: Guardrail):
        """註冊護欄"""
        self.guardrails[guardrail.guardrail_id] = guardrail
        logger.info(f"Registered guardrail: {guardrail.name}")
    
    def unregister_guardrail(self, guardrail_id: str):
        """移除護欄"""
        if guardrail_id in self.guardrails:
            del self.guardrails[guardrail_id]
            logger.info(f"Unregistered guardrail: {guardrail_id}")
    
    def check_all(self, context: Dict[str, Any]) -> List[GuardrailViolation]:
        """
        檢查所有護欄
        
        Args:
            context: 檢查上下文
            
        Returns:
            所有違規記錄列表
        """
        violations = []
        
        for guardrail in self.guardrails.values():
            if not guardrail.enabled:
                continue
            
            try:
                violation = guardrail.check(context)
                if violation:
                    violations.append(violation)
                    self._record_violation(violation)
            except Exception as e:
                logger.error(f"Error checking guardrail {guardrail.name}: {e}")
        
        return violations
    
    def should_block(self, violations: List[GuardrailViolation]) -> bool:
        """判斷是否應該阻止操作"""
        return any(v.action == GuardrailAction.BLOCK for v in violations)
    
    def requires_approval(self, violations: List[GuardrailViolation]) -> bool:
        """判斷是否需要核准"""
        return any(v.action == GuardrailAction.REQUIRE_APPROVAL for v in violations)
    
    def get_blocking_violations(self, violations: List[GuardrailViolation]) -> List[GuardrailViolation]:
        """取得所有阻止性違規"""
        return [v for v in violations if v.action == GuardrailAction.BLOCK]
    
    def _record_violation(self, violation: GuardrailViolation):
        """記錄違規"""
        self.violation_history.append(violation)
        
        # 限制歷史記錄大小
        if len(self.violation_history) > self._max_history:
            self.violation_history = self.violation_history[-self._max_history:]
        
        # 記錄日誌
        if violation.severity in [GuardrailSeverity.ERROR, GuardrailSeverity.CRITICAL]:
            logger.warning(f"Guardrail violation: {violation.guardrail_name} - {violation.reason}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """取得統計資訊"""
        total_violations = len(self.violation_history)
        
        violations_by_severity = {}
        violations_by_guardrail = {}
        
        for v in self.violation_history:
            # 按嚴重程度統計
            severity = v.severity.value
            violations_by_severity[severity] = violations_by_severity.get(severity, 0) + 1
            
            # 按護欄統計
            name = v.guardrail_name
            violations_by_guardrail[name] = violations_by_guardrail.get(name, 0) + 1
        
        return {
            'total_violations': total_violations,
            'violations_by_severity': violations_by_severity,
            'violations_by_guardrail': violations_by_guardrail,
            'guardrails_registered': len(self.guardrails),
            'guardrails_enabled': sum(1 for g in self.guardrails.values() if g.enabled),
        }


# 全域護欄引擎實例
_guardrail_engine: Optional[GuardrailEngine] = None


def get_guardrail_engine() -> GuardrailEngine:
    """取得全域護欄引擎實例"""
    global _guardrail_engine
    if _guardrail_engine is None:
        _guardrail_engine = GuardrailEngine()
        
        # 註冊預設護欄
        _guardrail_engine.register_guardrail(ContentGuardrail())
        _guardrail_engine.register_guardrail(CostGuardrail())
        _guardrail_engine.register_guardrail(RateLimitGuardrail())
    
    return _guardrail_engine
