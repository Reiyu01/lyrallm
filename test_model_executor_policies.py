import asyncio

from lyrallm.auth.dependencies import RequestSecurityContext
from lyrallm.auth.role_registry import role_registry
from lyrallm.core.model_executor import ModelExecutor


def _build_security_ctx(role_name: str) -> RequestSecurityContext:
    role = role_registry.get_role(role_name)
    assert role is not None, f"Role {role_name} should be defined in config.yaml"
    return RequestSecurityContext(
        role=role,
        permissions=role.permissions,
        feature_flags=role.feature_flags,
        routing_policies=role.routing_policies,
        allowed_models=role.allowed_models,
        requested_role=role.name,
    )


def test_sensitive_category_triggers_fallback(monkeypatch):
    executor = ModelExecutor()

    async def fake_route_model(self, messages, request_id):
        return "gpt-4o", {
            "model": "gpt-4o",
            "category": "S7",
            "intent": "qa_general",
            "confidence": 0.9,
        }

    async def fake_generate(self, model_name, model_cfg, messages, temperature,
                            max_tokens, features, start_time, request_id, routing_info):
        return {
            "id": "test",
            "created": 0,
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "text": "ok",
            "meta": {"latency_ms": 0, "routing_info": routing_info},
        }

    monkeypatch.setattr(ModelExecutor, "_route_model", fake_route_model, raising=False)
    monkeypatch.setattr(ModelExecutor, "_generate_real_response", fake_generate, raising=False)

    security_ctx = _build_security_ctx("standard_user")
    async def _run():
        return await executor.generate(
            model_name="auto",
            messages=[{"role": "user", "content": "包含個人資訊"}],
            security_ctx=security_ctx,
        )

    result = asyncio.run(_run())

    assert result["model"] == "gpt-oss:20b"
    routing_info = result["meta"]["routing_info"]
    assert routing_info["policy_enforced_model"] == "gpt-oss:20b"
    assert routing_info["policy_actions"][0]["category"] == "S7"


def test_no_fallback_when_category_not_matched(monkeypatch):
    executor = ModelExecutor()

    async def fake_route_model(self, messages, request_id):
        return "gpt-4o", {
            "model": "gpt-4o",
            "category": "S5",
            "intent": "qa_general",
            "confidence": 0.9,
        }

    async def fake_generate(self, model_name, model_cfg, messages, temperature,
                            max_tokens, features, start_time, request_id, routing_info):
        return {
            "id": "test",
            "created": 0,
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "text": "ok",
            "meta": {"latency_ms": 0, "routing_info": routing_info},
        }

    monkeypatch.setattr(ModelExecutor, "_route_model", fake_route_model, raising=False)
    monkeypatch.setattr(ModelExecutor, "_generate_real_response", fake_generate, raising=False)

    security_ctx = _build_security_ctx("standard_user")
    async def _run():
        return await executor.generate(
            model_name="auto",
            messages=[{"role": "user", "content": "一般問題"}],
            security_ctx=security_ctx,
        )

    result = asyncio.run(_run())

    assert result["model"] == "gpt-4o"
    routing_info = result["meta"]["routing_info"]
    assert "policy_enforced_model" not in routing_info
