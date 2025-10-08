"""Config package exports for semantic_kernel.

Expose commonly used items so callers can import from
`semantic_kernel.config` instead of referencing module files directly.
"""
from .config_manager import config_manager
from .plugin_manager import plugin_manager
from .dynamic_features import DynamicFeaturesFactory

__all__ = ["config_manager", "plugin_manager", "DynamicFeaturesFactory"]
"""semantic_kernel.config package

This module re-exports common helpers so callers can do:
  from lyrallm.config import config_manager

Keep the file minimal to avoid side-effects on import.
"""
from .config_manager import config_manager

__all__ = ["config_manager"]
# Semantic Kernel API Gateway - Config Module