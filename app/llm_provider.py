"""Gemini SQL-generation provider configuration and client factory."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Mapping


GEMINI_REQUEST_TIMEOUT_SECONDS = 30.0


class GeminiConfigurationError(ValueError):
    """Raised when Gemini cannot be configured safely from the environment."""


@dataclass(frozen=True)
class GeminiProviderStatus:
    configured: bool
    message: str
    model: str | None = None


def _read_settings(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    values = os.environ if environ is None else environ
    api_key = values.get("GOOGLE_API_KEY", "").strip()
    model = values.get("GOOGLE_MODEL", "").strip()
    missing = []
    if not api_key or "your_" in api_key.casefold() or "placeholder" in api_key.casefold():
        missing.append("GOOGLE_API_KEY")
    if not model or "your_" in model.casefold() or "placeholder" in model.casefold():
        missing.append("GOOGLE_MODEL")
    if missing:
        raise GeminiConfigurationError(
            "Gemini is not configured. Set " + " and ".join(missing) + " in .env."
        )
    return model, api_key


def check_gemini_provider_configuration(
    environ: Mapping[str, str] | None = None,
) -> GeminiProviderStatus:
    """Check local settings without making a network request or exposing keys."""
    try:
        model, _api_key = _read_settings(environ)
    except GeminiConfigurationError as exc:
        return GeminiProviderStatus(False, str(exc))
    return GeminiProviderStatus(True, f"Gemini is configured for model '{model}'.", model)


def create_gemini_chat_model(
    environ: Mapping[str, str] | None = None,
    *,
    model_factory: Callable[..., object] | None = None,
):
    """Construct ChatGoogleGenerativeAI without performing model inference."""
    model, api_key = _read_settings(environ)
    if model_factory is None:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise GeminiConfigurationError(
                "Gemini integration package is unavailable. Install dependencies from requirements.txt."
            ) from None
        model_factory = ChatGoogleGenerativeAI
    try:
        return model_factory(
            model=model,
            api_key=api_key,
            vertexai=False,
            temperature=0,
            # ChatGoogleGenerativeAI otherwise allows six SDK retries and an
            # unbounded request duration, which can leave Streamlit waiting.
            request_timeout=GEMINI_REQUEST_TIMEOUT_SECONDS,
            retries=0,
        )
    except Exception:
        # Provider exceptions can include request/configuration details; do not
        # propagate a diagnostic that might contain credential material.
        raise GeminiConfigurationError(
            "Gemini client initialization failed. Check the selected model and local configuration."
        ) from None
