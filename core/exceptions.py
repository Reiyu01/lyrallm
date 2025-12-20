class LyraError(Exception):
    """Base exception for LyraLLM"""
    def __init__(self, message: str, code: str = "internal_error", status_code: int = 500, details: dict = None):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ModelNotFoundError(LyraError):
    def __init__(self, model_name: str):
        super().__init__(
            message=f"Model '{model_name}' not found",
            code="model_not_found",
            status_code=404,
            details={"model": model_name}
        )

class FeatureNotAllowedError(LyraError):
    def __init__(self, features: list, role: str):
        super().__init__(
            message=f"Role '{role}' is not permitted to use features: {features}",
            code="feature_not_allowed",
            status_code=403,
            details={"features": features, "role": role}
        )

class ModelNotAllowedError(LyraError):
    def __init__(self, model: str, role: str):
        super().__init__(
            message=f"Role '{role}' is not allowed to invoke model '{model}'",
            code="model_not_allowed",
            status_code=403,
            details={"model": model, "role": role}
        )

class AgentExecutionError(LyraError):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="agent_execution_error",
            status_code=500
        )

class RoutingError(LyraError):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="routing_error",
            status_code=500
        )
