from app.gemini_diagnostic import _safe_failure


def test_diagnostic_masks_provider_messages_and_api_key_text():
    class FakeError(RuntimeError):
        code = 401

    error = FakeError("invalid API key: never-print-this-secret")

    message = _safe_failure(error)

    assert message == "Authentication failed. Check GOOGLE_API_KEY in the local .env file."
    assert "never-print-this-secret" not in message


def test_diagnostic_classifies_unsupported_model():
    class FakeError(RuntimeError):
        code = 404

    assert _safe_failure(FakeError("model not found")) == (
        "The configured Gemini model is unavailable at this API endpoint."
    )


def test_diagnostic_classifies_generation_service_503_safely():
    class FakeError(RuntimeError):
        code = 503

    assert _safe_failure(FakeError("temporary service failure")) == (
        "The Gemini generation service returned HTTP/API 503 (temporarily unavailable or overloaded)."
    )
