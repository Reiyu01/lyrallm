"""
Semantic Kernel Plugins 套件
"""

from .ollama_web_search_plugin import OllamaWebSearchPlugin
from .ollama_config import ollama_config, OllamaConfig

__all__ = [
    "OllamaWebSearchPlugin",
    "ollama_config", 
    "OllamaConfig"
]