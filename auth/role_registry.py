import logging
from dataclasses import dataclass, field
from threading import RLock
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Set

from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoleDefinition:
    """Resolved role definition with inherited permissions and policies applied."""

    name: str
    description: str
    inherits: List[str] = field(default_factory=list)
    permissions: FrozenSet[str] = field(default_factory=frozenset)
    feature_flags: FrozenSet[str] = field(default_factory=frozenset)
    routing_policies: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    allowed_models: Optional[FrozenSet[str]] = None

    def has_permission(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions

    def allows_feature(self, feature: str) -> bool:
        return "*" in self.feature_flags or feature in self.feature_flags

    def allows_model(self, model_name: str) -> bool:
        """Check if the role allows access to the specified model.
        
        Returns:
            True if model is allowed or if allowed_models is None (unrestricted).
        """
        # None = 允許所有模型（無限制模式）
        if self.allowed_models is None:
            return True
        if not self.allowed_models:
            return True
        if "*" in self.allowed_models:
            return True
        return model_name in self.allowed_models


class RoleRegistry:
    """Registry responsible for resolving role inheritance and effective permissions."""

    def __init__(self):
        self._config_manager = config_manager
        self._lock = RLock()
        self._cache: Dict[str, RoleDefinition] = {}
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the role cache from configuration."""
        roles_cfg = self._config_manager.get_roles_config() or {}
        resolved: Dict[str, RoleDefinition] = {}

        for name in roles_cfg.keys():
            self._resolve_role(name, roles_cfg, resolved, stack=set())

        with self._lock:
            self._cache = resolved

        logger.info("Role registry refreshed with %d roles", len(self._cache))

    def list_roles(self) -> List[RoleDefinition]:
        with self._lock:
            return list(self._cache.values())

    def get_role(self, role_name: Optional[str]) -> Optional[RoleDefinition]:
        if not role_name:
            return None
        with self._lock:
            role = self._cache.get(role_name)
        if role:
            return role

        # Attempt a refresh if role was not found (config may have changed)
        self.refresh()
        with self._lock:
            return self._cache.get(role_name)

    def get_default_role(self) -> Optional[RoleDefinition]:
        default_name = self._config_manager.get_default_role_name()
        return self.get_role(default_name)

    def has_permission(self, role_name: str, permission: str) -> bool:
        role = self.get_role(role_name)
        if not role:
            return False
        return role.has_permission(permission)

    def allows_feature(self, role_name: str, feature: str) -> bool:
        role = self.get_role(role_name)
        if not role:
            return False
        return role.allows_feature(feature)

    def allows_model(self, role_name: str, model_name: str) -> bool:
        role = self.get_role(role_name)
        if not role:
            return False
        return role.allows_model(model_name)

    def _resolve_role(
        self,
        name: str,
        roles_cfg: Dict[str, Dict[str, Any]],
        resolved: Dict[str, RoleDefinition],
        stack: Set[str],
    ) -> Optional[RoleDefinition]:
        if name in resolved:
            return resolved[name]

        if name in stack:
            logger.error("Detected cyclic inheritance in role configuration: %s -> %s", stack, name)
            return None

        base = roles_cfg.get(name)
        if not base:
            logger.warning("Role '%s' referenced but not defined in configuration", name)
            return None

        stack.add(name)

        inherits: List[str] = list(base.get('inherits', [])) if isinstance(base.get('inherits'), list) else []
        permissions: Set[str] = set(base.get('permissions', []))
        features: Set[str] = set(base.get('feature_flags', []))
        allowed_models: Set[str] = set(base.get('allowed_models', []))
        routing_policies: Dict[str, Any] = dict(base.get('routing_policies', {}))
        metadata: Dict[str, Any] = dict(base.get('metadata', {}))

        for parent_name in inherits:
            parent = self._resolve_role(parent_name, roles_cfg, resolved, stack)
            if not parent:
                continue

            permissions.update(parent.permissions)
            features.update(parent.feature_flags)

            if parent.allowed_models:
                if "*" in parent.allowed_models:
                    allowed_models = {"*"}
                elif "*" not in allowed_models:
                    if allowed_models:
                        allowed_models.update(parent.allowed_models)
                    else:
                        allowed_models = set(parent.allowed_models)

            # Child overrides parent routing settings
            if parent.routing_policies:
                merged_routing = dict(parent.routing_policies)
                merged_routing.update(routing_policies)
                routing_policies = merged_routing

            if parent.metadata:
                merged_meta = dict(parent.metadata)
                merged_meta.update(metadata)
                metadata = merged_meta

        stack.remove(name)

        permissions_fs = frozenset(permissions)
        features_fs = frozenset(features)
        allowed_models_fs: Optional[FrozenSet[str]] = None
        if "*" in allowed_models:
            allowed_models_fs = frozenset({"*"})
        elif allowed_models:
            allowed_models_fs = frozenset(allowed_models)

        role_def = RoleDefinition(
            name=name,
            description=base.get('description', ''),
            inherits=inherits,
            permissions=permissions_fs,
            feature_flags=features_fs,
            routing_policies=MappingProxyType(dict(routing_policies)),
            metadata=MappingProxyType(dict(metadata)),
            allowed_models=allowed_models_fs,
        )
        resolved[name] = role_def
        return role_def


role_registry = RoleRegistry()
