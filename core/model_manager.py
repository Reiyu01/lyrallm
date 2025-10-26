"""
Enterprise Model Manager for LyraLLM Gateway
Handles model health checks, load balancing, and performance monitoring
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model availability status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"


@dataclass
class ModelMetrics:
    """Model performance metrics."""
    name: str
    status: ModelStatus = ModelStatus.HEALTHY
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    error_rate: float = 0.0
    recent_latencies: List[float] = field(default_factory=list)
    
    def update_success(self, latency_ms: float):
        """Record successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.last_success = datetime.now()
        
        # Update latency metrics (keep last 100 measurements)
        self.recent_latencies.append(latency_ms)
        if len(self.recent_latencies) > 100:
            self.recent_latencies.pop(0)
        
        self.avg_latency_ms = sum(self.recent_latencies) / len(self.recent_latencies)
        self._update_error_rate()
        self._update_status()
    
    def update_failure(self, error: str):
        """Record failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_failure = datetime.now()
        
        logger.warning(f"Model {self.name} request failed: {error}")
        self._update_error_rate()
        self._update_status()
    
    def _update_error_rate(self):
        """Calculate current error rate."""
        if self.total_requests > 0:
            self.error_rate = self.failed_requests / self.total_requests
    
    def _update_status(self):
        """Update model status based on metrics."""
        if self.error_rate > 0.5:  # More than 50% failures
            self.status = ModelStatus.UNHEALTHY
        elif self.error_rate > 0.1 or self.avg_latency_ms > 30000:  # 10% error rate or >30s latency
            self.status = ModelStatus.DEGRADED
        else:
            self.status = ModelStatus.HEALTHY


class ModelManager:
    """Enterprise model manager with health monitoring and load balancing."""
    
    def __init__(self):
        self.metrics: Dict[str, ModelMetrics] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._check_interval = 300  # 5 minutes
        
    async def start(self):
        """Start model manager and health checking."""
        logger.info("Starting ModelManager...")
        
        # Initialize metrics for all configured models
        self._initialize_metrics()
        
        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info("ModelManager started successfully")
    
    async def stop(self):
        """Stop model manager."""
        logger.info("Stopping ModelManager...")
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("ModelManager stopped")
    
    def _initialize_metrics(self):
        """Initialize metrics for all configured models."""
        models = config_manager.get_all_models()
        for model in models:
            model_name = model.get('name')
            if model_name and model_name not in self.metrics:
                self.metrics[model_name] = ModelMetrics(name=model_name)
                
                # Set status based on configuration
                if not model.get('enabled', False):
                    self.metrics[model_name].status = ModelStatus.DISABLED
                    
        logger.info(f"Initialized metrics for {len(self.metrics)} models")
    
    async def _health_check_loop(self):
        """Periodic health check loop."""
        while True:
            try:
                await asyncio.sleep(self._check_interval)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def _perform_health_checks(self):
        """Perform health checks on all active models."""
        logger.info("Performing model health checks...")
        
        healthy_count = 0
        for model_name, metrics in self.metrics.items():
            if metrics.status == ModelStatus.DISABLED:
                continue
                
            # Check if model has been inactive for too long
            if metrics.last_success:
                time_since_success = datetime.now() - metrics.last_success
                if time_since_success > timedelta(hours=1):
                    logger.warning(f"Model {model_name} inactive for {time_since_success}")
            
            if metrics.status == ModelStatus.HEALTHY:
                healthy_count += 1
        
        logger.info(f"Health check complete: {healthy_count} healthy models")
    
    def get_best_model_for_intent(self, intent: str) -> Optional[str]:
        """Select the best available model for a given intent."""
        # Get models that support this intent
        candidate_models = []
        
        for model in config_manager.get_available_models():
            model_name = model.get('name')
            model_intents = model.get('intents', [])

            if not model_name or model_name not in self.metrics:
                continue

            metrics = self.metrics[model_name]

            # Skip unhealthy or disabled models
            if metrics.status in [ModelStatus.UNHEALTHY, ModelStatus.DISABLED]:
                continue

            # Skip virtual/pseudo models like 'auto' that are not invokable providers
            provider = model.get('provider')
            if model_name == 'auto' or provider == 'auto':
                continue
            
            # Check if model supports this intent
            if intent in model_intents or not model_intents:  # Empty intents = supports all
                score = self._calculate_model_score(metrics)
                candidate_models.append((model_name, score, metrics.status))
        
        if not candidate_models:
            logger.warning(f"No healthy models found for intent: {intent}")
            return config_manager.get_default_model()
        
        # Sort by score (higher is better) and status priority
        candidate_models.sort(key=lambda x: (
            x[2] == ModelStatus.HEALTHY,  # Prefer healthy models
            x[1]  # Then by score
        ), reverse=True)
        
        selected_model = candidate_models[0][0]
        logger.info(f"Selected model {selected_model} for intent {intent} "
                   f"(score: {candidate_models[0][1]:.3f})")
        
        return selected_model
    
    def _calculate_model_score(self, metrics: ModelMetrics) -> float:
        """Calculate model performance score (0-1, higher is better)."""
        # Base score from success rate
        success_rate = 1.0 - metrics.error_rate
        
        # Latency penalty (normalize to 0-1, prefer <5s responses)
        latency_score = max(0, 1.0 - (metrics.avg_latency_ms / 5000))
        
        # Combine metrics (weighted)
        score = (success_rate * 0.7) + (latency_score * 0.3)
        
        return min(1.0, max(0.0, score))
    
    def record_request_success(self, model_name: str, latency_ms: float):
        """Record successful model request."""
        if model_name in self.metrics:
            self.metrics[model_name].update_success(latency_ms)
    
    def record_request_failure(self, model_name: str, error: str):
        """Record failed model request."""
        if model_name in self.metrics:
            self.metrics[model_name].update_failure(error)
    
    def get_model_status(self, model_name: str) -> Optional[ModelStatus]:
        """Get current status of a model."""
        return self.metrics.get(model_name, {}).status if model_name in self.metrics else None
    
    def get_all_metrics(self) -> Dict[str, ModelMetrics]:
        """Get metrics for all models."""
        return self.metrics.copy()
    
    def get_healthy_models(self) -> List[str]:
        """Get list of currently healthy models."""
        return [
            name for name, metrics in self.metrics.items()
            if metrics.status == ModelStatus.HEALTHY
        ]


# Global model manager instance
_model_manager: Optional[ModelManager] = None


async def get_model_manager() -> ModelManager:
    """Get global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
        await _model_manager.start()
    return _model_manager


def get_model_manager_sync() -> Optional[ModelManager]:
    """Get model manager synchronously (may be None if not started)."""
    return _model_manager
