import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, FrozenSet, Mapping

from fastapi import Depends, Header, HTTPException

from .role_registry import RoleDefinition, RoleRegistry, role_registry
from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


@dataclass
class RequestSecurityContext:
    """Per-request security context resolved from headers & configuration."""

    role: RoleDefinition
    permissions: FrozenSet[str] = field(default_factory=frozenset)
    feature_flags: FrozenSet[str] = field(default_factory=frozenset)
    routing_policies: Mapping[str, Any] = field(default_factory=dict)
    allowed_models: Optional[FrozenSet[str]] = None
    requested_role: Optional[str] = None

    def has_permission(self, permission: str) -> bool:
        return self.role.has_permission(permission)

    def allows_feature(self, feature: str) -> bool:
        return self.role.allows_feature(feature)

    def allows_model(self, model_name: str) -> bool:
        return self.role.allows_model(model_name)

    def to_payload(self) -> Dict[str, Any]:
        """Serialize context for downstream analytics/routing."""
        return {
            "role": self.role.name,
            "permissions": sorted(self.permissions),
            "feature_flags": sorted(self.feature_flags),
            "routing_policies": dict(self.routing_policies),
            "allowed_models": sorted(self.allowed_models) if self.allowed_models else None,
        }


def get_role_registry() -> RoleRegistry:
    return role_registry


async def get_request_security_context(
    role_header: Optional[str] = Header(None, alias="X-Lyra-Role"),
    registry: RoleRegistry = Depends(get_role_registry),
) -> RequestSecurityContext:
    """Resolve the caller's security context based on configured RBAC."""
    requested_role = (role_header or "").strip() or None

    role = registry.get_role(requested_role)
    if not role:
        default_role = registry.get_default_role()
        if requested_role:
            logger.warning("Role '%s' not found; falling back to default role '%s'", requested_role, default_role.name if default_role else None)
        role = default_role

    if not role:
        logger.error("No default role configured; cannot build security context")
        raise HTTPException(status_code=500, detail="RBAC roles not configured")

    return RequestSecurityContext(
        role=role,
        permissions=role.permissions,
        feature_flags=role.feature_flags,
        routing_policies=role.routing_policies,
        allowed_models=role.allowed_models,
        requested_role=requested_role or role.name,
    )


def require_permission(permission: str):
    """Dependency factory that enforces the presence of a permission."""

    async def _dependency(security_ctx: RequestSecurityContext = Depends(get_request_security_context)) -> RequestSecurityContext:
        if not security_ctx.has_permission(permission):
            raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
        return security_ctx

    return _dependency
