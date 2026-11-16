import pytest

from app.llm_provider import (
    GEMINI_REQUEST_TIMEOUT_SECONDS,
    GeminiConfigurationError,
    check_gemini_provider_configuration,
    create_gemini_chat_model,
)


def test_gemini_provider_check_accepts_config_without_disclosing_key():
    api_key = "unit-test-gemini-key"
    status = check_gemini_provider_configuration({
        "GOOGLE_API_KEY": api_key,
        "GOOGLE_MODEL": "chosen-free-tier-model",
    })

    assert status.configured
    assert status.model == "chosen-free-tier-model"
    assert api_key not in status.message
    assert api_key not in repr(status)


def test_gemini_factory_uses_configured_model_without_network_call():
    captured = {}

    class FakeChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    model = create_gemini_chat_model(
        {"GOOGLE_API_KEY": "unit-test-key", "GOOGLE_MODEL": "gemini-test-model"},
        model_factory=FakeChatModel,
    )

    assert isinstance(model, FakeChatModel)
    assert captured == {
        "model": "gemini-test-model",
        "api_key": "unit-test-key",
        "vertexai": False,
        "temperature": 0,
        "request_timeout": GEMINI_REQUEST_TIMEOUT_SECONDS,
        "retries": 0,
    }


def test_installed_gemini_integration_constructs_without_inference():
    model = create_gemini_chat_model({
        "GOOGLE_API_KEY": "test-only-no-network",
        "GOOGLE_MODEL": "gemini-test-model",
    })
    assert model.__class__.__name__ == "ChatGoogleGenerativeAI"
    assert model.model == "gemini-test-model"
    # The installed integration aliases its constructor's request_timeout to
    # the normalized public `timeout` attribute.
    assert model.timeout == GEMINI_REQUEST_TIMEOUT_SECONDS
    assert model.max_retries == 0


def test_missing_google_api_key_fails_before_model_construction(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_MODEL", "gemini-test-model")
    constructed = False

    def forbidden_constructor(**_kwargs):
        nonlocal constructed
        constructed = True

    status = check_gemini_provider_configuration()
    assert not status.configured
    assert "GOOGLE_API_KEY" in status.message
    assert "unit-test-key" not in status.message

    with pytest.raises(GeminiConfigurationError, match="GOOGLE_API_KEY"):
        create_gemini_chat_model(model_factory=forbidden_constructor)
    assert not constructed


def test_placeholder_model_is_rejected_by_safe_check():
    status = check_gemini_provider_configuration({
        "GOOGLE_API_KEY": "unit-test-key",
        "GOOGLE_MODEL": "your_selected_free_tier_model",
    })
    assert not status.configured
    assert "GOOGLE_MODEL" in status.message


def test_graph_default_factory_uses_gemini_provider(monkeypatch):
    from app import graph

    sentinel = object()
    calls = []
    monkeypatch.setattr(graph, "create_gemini_chat_model", lambda: calls.append(True) or sentinel)

    assert graph._default_llm() is sentinel
    assert calls == [True]
