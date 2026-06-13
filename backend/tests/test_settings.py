from app.kimi import KimiClient
from app.model_router import route_model
from app.models import TaskType
from app.settings import build_fallback_model_client_from_env, build_model_client_from_env
from app.tokenrouter import TokenRouterClient


def test_model_gateway_auto_selects_tokenrouter_when_key_exists(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_GATEWAY", raising=False)
    monkeypatch.setenv("TOKENROUTER_API_KEY", "tr-test-key")

    client = build_model_client_from_env()

    assert isinstance(client, TokenRouterClient)
    assert client.name == "tokenrouter"


def test_model_gateway_can_force_direct_kimi(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_GATEWAY", "kimi")
    monkeypatch.setenv("TOKENROUTER_API_KEY", "tr-test-key")

    client = build_model_client_from_env()

    assert isinstance(client, KimiClient)
    assert client.name == "kimi"


def test_tokenrouter_can_build_direct_kimi_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_GATEWAY", "tokenrouter")
    monkeypatch.setenv("MOONSHOT_API_KEY", "kimi-test-key")

    client = build_fallback_model_client_from_env("tokenrouter")

    assert isinstance(client, KimiClient)
    assert client.name == "kimi"


def test_route_model_uses_configured_task_models(monkeypatch) -> None:
    monkeypatch.setenv("AI_WORKSPACE_WEB_MODEL", "kimi-web-custom")
    monkeypatch.setenv("AI_WORKSPACE_CODING_MODEL", "kimi-code-custom")
    monkeypatch.setenv("AI_WORKSPACE_GENERAL_MODEL", "kimi-general-custom")

    assert route_model(TaskType.web, "research latest docs").model == "kimi-web-custom"
    assert route_model(TaskType.coding, "modify login").model == "kimi-code-custom"
    assert route_model(TaskType.general, "explain backend").model == "kimi-general-custom"
