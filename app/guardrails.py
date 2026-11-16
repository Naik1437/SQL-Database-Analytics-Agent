"""NeMo Guardrails input inspection adapter."""
from __future__ import annotations

import os
from pathlib import Path


def inspect_with_nemo(text: str) -> tuple[bool, str]:
    """Use configured NeMo rails when available, with fail-closed behavior on errors."""
    config_path = os.getenv("NEMO_GUARDRAILS_CONFIG", "config/guardrails")
    if not Path(config_path).exists():
        # Basic policy checks remain active when the optional rails config is unavailable.
        lowered = text.lower()
        suspicious = ("ignore all previous", "reveal the system prompt", "drop table",
                      "delete from", "insert into", "update ")
        if any(term in lowered for term in suspicious):
            return False, "This request was blocked by the safety policy."
        return True, ""
    try:
        from nemoguardrails import RailsConfig, LLMRails
        rails = LLMRails(RailsConfig.from_path(config_path))
        answer = rails.generate(messages=[{"role": "user", "content": text}])
        response = answer.get("content", "") if isinstance(answer, dict) else str(answer)
        if response.startswith("BLOCKED:"):
            return False, "This request was blocked by the safety policy."
        return True, ""
    except Exception:
        return False, "Safety inspection is unavailable; the request was blocked."
