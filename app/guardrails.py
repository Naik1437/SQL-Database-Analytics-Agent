"""Raw-input guardrails with an explicit deterministic fallback.

Known injection patterns are rejected locally before any NeMo call. The
unchanged user text is also inspected by NeMo's ``self check input`` rail only
when NEMO_LIVE_INFERENCE is explicitly enabled with its separate OpenAI key.
Otherwise the deterministic filter is used and no OpenAI inference is called.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import html
import os
from pathlib import Path
import re
from typing import Literal
from urllib.parse import unquote


GuardrailSource = Literal["deterministic_filter", "deterministic_fallback", "nemo", "unavailable"]


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    message: str
    source: GuardrailSource


_DESTRUCTIVE = re.compile(
    r"\b(?:DROP\s+(?:TABLE|DATABASE|INDEX|VIEW)|DELETE\s+FROM|UPDATE\s+[\w\"`\[.]+\s+SET|"
    r"INSERT\s+INTO|ALTER\s+TABLE|CREATE\s+(?:TABLE|TRIGGER|VIEW|INDEX)|TRUNCATE(?:\s+TABLE)?|"
    r"REPLACE\s+INTO)\b", re.IGNORECASE,
)
_TAUTOLOGY = re.compile(
    r"\bOR\s+(?:\(?\s*\d+\s*=\s*\d+\s*\)?|\(?\s*(['\"])(?:.*?)\1\s*=\s*(['\"])(?:.*?)\2\s*\)?)",
    re.IGNORECASE,
)
_SCRIPT = re.compile(r"<\s*/?\s*script\b", re.IGNORECASE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _deterministic_block_reason(user_text: str) -> str | None:
    # Decode common obfuscation before inspection; HTML tags are separately
    # detected against the decoded form.
    normalized = html.unescape(unquote(user_text)).casefold()
    if _SCRIPT.search(normalized):
        return "Script-tag input is not allowed."
    if "--" in normalized or _BLOCK_COMMENT.search(normalized):
        return "SQL comment syntax is not allowed in a request."
    if _TAUTOLOGY.search(normalized):
        return "SQL tautology or injection syntax was detected."
    if _DESTRUCTIVE.search(normalized):
        return "Database modification commands are not allowed."
    return None


def _config_path() -> Path:
    configured = Path(os.getenv("NEMO_GUARDRAILS_CONFIG", "config/guardrails"))
    if not configured.is_absolute():
        configured = Path(__file__).resolve().parent.parent / configured
    return configured.resolve()


@lru_cache(maxsize=4)
def _load_rails(config_path: str, model_name: str):
    from nemoguardrails import LLMRails, RailsConfig

    config = RailsConfig.from_path(config_path)
    # Resolve the optional NeMo model setting even if callers did not load .env.
    for model in config.models:
        if getattr(model, "type", None) == "main":
            model.model = model_name
    return LLMRails(config)


def _has_real_api_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and "your_" not in key.casefold() and "placeholder" not in key.casefold())


def _response_content(response) -> str:
    if isinstance(response, dict):
        response = response.get("content", "")
    else:
        response = getattr(response, "content", response)
    return str(response).strip()


def inspect_with_nemo(user_text: str) -> GuardrailDecision:
    """Inspect raw user text before schema access or SQL generation.

    NeMo configuration is initialized even in deterministic-only mode, which
    catches invalid installations/configuration. Live NeMo inference is a
    separate explicit opt-in; otherwise this function never calls OpenAI.
    Initialization/runtime failures fail closed.
    """
    reason = _deterministic_block_reason(user_text)
    if reason:
        return GuardrailDecision(False, reason, "deterministic_filter")

    config_path = _config_path()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        rails = _load_rails(str(config_path), model_name)
    except Exception:
        return GuardrailDecision(False, "Security inspection is unavailable; request blocked.", "unavailable")

    live_inference = os.getenv("NEMO_LIVE_INFERENCE", "false").strip().casefold() in {
        "1", "true", "yes", "on",
    }
    if not live_inference:
        return GuardrailDecision(True, "NeMo LLM inspection skipped; deterministic fallback used.",
                                 "deterministic_fallback")
    if not _has_real_api_key():
        return GuardrailDecision(
            False,
            "Live NeMo inference was requested but its separate OPENAI_API_KEY is not configured.",
            "unavailable",
        )
    try:
        response = rails.generate(messages=[{"role": "user", "content": user_text}])
        content = _response_content(response)
        if not content:
            return GuardrailDecision(False, "NeMo returned no safety decision; request blocked.", "unavailable")
        if content.upper().startswith("BLOCKED:"):
            return GuardrailDecision(False, content, "nemo")
        return GuardrailDecision(True, "Input passed NeMo Guardrails.", "nemo")
    except Exception:
        return GuardrailDecision(False, "NeMo safety inspection failed; request blocked.", "unavailable")
