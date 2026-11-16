"""Credential-safe connectivity and inference diagnostic for Gemini."""
from __future__ import annotations

import socket
import ssl
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable

from dotenv import load_dotenv

from app.llm_provider import (
    GEMINI_REQUEST_TIMEOUT_SECONDS,
    GeminiConfigurationError,
    check_gemini_provider_configuration,
    create_gemini_chat_model,
)


def _safe_failure(exc: Exception, *, elapsed_seconds: float | None = None) -> str:
    """Summarize provider failures without printing SDK diagnostics or secrets."""
    name = type(exc).__name__.casefold()
    details = str(exc).casefold()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if "timeout" in name or "deadline" in name or "timeout" in details:
        return f"Request timed out ({GEMINI_REQUEST_TIMEOUT_SECONDS:g}s)."
    if status == 401 or "unauthenticated" in details or "invalid api key" in details:
        return "Authentication failed. Check GOOGLE_API_KEY in the local .env file."
    if status == 403 or "permission denied" in details or "forbidden" in details:
        return "The API key or project does not have access to this Gemini model."
    if status == 404 or "not found" in details or "unknown model" in details:
        return "The configured Gemini model is unavailable at this API endpoint."
    if status == 429 or "resource_exhausted" in details or "quota" in details or "rate limit" in details:
        return "Gemini free-tier quota or rate limit was reached."
    if any(word in name for word in ("connect", "socket", "dns")) or any(
        word in details for word in ("connection refused", "name resolution", "temporary failure")
    ):
        return "Could not connect to the Gemini API. Check network access and proxy settings."
    if status == 400 or "invalid argument" in details or "bad request" in details:
        return "Gemini rejected the request configuration. Check model/API compatibility."
    if status == 503 or "service unavailable" in details or "overloaded" in details:
        return "The Gemini generation service returned HTTP/API 503 (temporarily unavailable or overloaded)."
    if elapsed_seconds is not None and elapsed_seconds >= GEMINI_REQUEST_TIMEOUT_SECONDS * 0.75:
        return (
            f"Generation ended after {elapsed_seconds:.1f}s (exception {type(exc).__name__}); "
            "this is consistent with a request timeout."
        )
    safe_status = f", API status {status}" if isinstance(status, (int, str)) else ""
    return (
        f"Gemini request failed (exception {type(exc).__name__}{safe_status}). "
        "Check the model, API key configuration, and quota."
    )


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not installed"


def run_diagnostic(
    *,
    model_factory: Callable[[], Any] = create_gemini_chat_model,
    output: Callable[[str], Any] = print,
) -> int:
    """Check DNS/TLS reachability, model access, then a tiny real generation."""
    load_dotenv()
    status = check_gemini_provider_configuration()
    output("Gemini API diagnostic (credential values are never displayed)")
    output(f"langchain-google-genai: {_package_version('langchain-google-genai')}")
    output(f"google-genai: {_package_version('google-genai')}")
    if not status.configured:
        output(f"Configuration: failed — {status.message}")
        return 1

    model_name = status.model or "unknown"
    output(f"Model: {model_name}")
    try:
        host = "generativelanguage.googleapis.com"
        with socket.create_connection((host, 443), timeout=5) as connection:
            with ssl.create_default_context().wrap_socket(connection, server_hostname=host):
                pass
    except OSError as exc:
        output(f"Network: failed — {_safe_failure(exc)}")
        return 1
    output("Network: DNS lookup and verified TLS handshake succeeded.")

    try:
        model = model_factory()
    except GeminiConfigurationError as exc:
        output(f"Client: failed — {_safe_failure(exc)}")
        return 1
    except Exception as exc:
        output(f"Client: failed — {_safe_failure(exc)}")
        return 1

    try:
        # The model lookup is metadata-only; it confirms the key can access
        # this model before issuing the small generation smoke test.
        model.client.models.get(model=model_name)
    except Exception as exc:
        output(f"Model access: failed — {_safe_failure(exc)}")
        return 1
    output("Model access: succeeded.")

    generation_started = time.monotonic()
    try:
        model.invoke("Reply with exactly the single word OK.")
    except Exception as exc:
        elapsed = time.monotonic() - generation_started
        output(f"Generation: failed — {_safe_failure(exc, elapsed_seconds=elapsed)}")
        return 1
    output("Generation: succeeded using the configured LangChain Gemini client.")
    return 0


def main() -> int:
    return run_diagnostic()


if __name__ == "__main__":
    raise SystemExit(main())
