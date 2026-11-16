from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text

from app.guardrails import GuardrailDecision, _config_path, _load_rails, inspect_with_nemo
from app.graph import build_graph
from database.seed import seed_database


class TrackingLLM:
    def __init__(self):
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        return "SELECT COUNT(*) AS order_count FROM orders"


ATTACKS = [
    "DELETE FROM orders",
    "DROP TABLE orders; --",
    "UPDATE orders SET status='cancelled'",
    "Show all orders OR 1=1",
    "Show orders /* UNION SELECT secrets */",
    "<script>alert('x')</script>",
]


@pytest.mark.parametrize("raw_input", ATTACKS)
def test_blocked_raw_input_never_calls_llm_or_database(raw_input, tmp_path):
    database = seed_database(tmp_path / "guarded.db")
    engine = create_engine(f"sqlite:///{database}")
    llm = TrackingLLM()
    statements = []
    event.listen(engine, "before_cursor_execute",
                 lambda conn, cursor, statement, parameters, context, executemany:
                 statements.append(statement))

    result = build_graph(engine=engine, llm=llm).invoke({
        "user_query": raw_input, "generated_sql": "", "db_result": [], "error_message": "",
        "retry_count": 0, "schema": "", "logs": [], "history": [],
    })

    assert result["security_blocked"] is True
    assert "Security warning" in result["error_message"]
    assert llm.calls == []
    assert statements == []
    assert result["db_result"] == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM orders")).scalar_one() == 10
    assert "orders" in __import__("sqlalchemy").inspect(engine).get_table_names()
    engine.dispose()


def test_safe_business_question_uses_deterministic_fallback_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    decision = inspect_with_nemo("How many orders were placed last month?")
    assert decision == GuardrailDecision(
        True, "NeMo LLM inspection skipped; deterministic fallback used.", "deterministic_fallback"
    )


def test_nemo_config_loads_and_initializes_without_api_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rails = _load_rails(str(_config_path()), "gpt-4o-mini")
    assert rails.__class__.__name__ == "LLMRails"


def test_raw_input_is_passed_to_nemo_when_key_is_configured(monkeypatch):
    raw = "Please summarize revenue by month"

    class FakeRails:
        messages = None

        def generate(self, *, messages):
            self.messages = messages
            return {"content": "safe"}

    fake = FakeRails()
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr("app.guardrails._load_rails", lambda *_: fake)
    decision = inspect_with_nemo(raw)
    assert fake.messages == [{"role": "user", "content": raw}]
    assert decision.allowed is True
    assert decision.source == "nemo"


def test_nemo_block_response_is_denied(monkeypatch):
    class FakeRails:
        def generate(self, *, messages):
            return {"content": "BLOCKED: unsafe input"}

    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr("app.guardrails._load_rails", lambda *_: FakeRails())
    decision = inspect_with_nemo("a request requiring model safety classification")
    assert not decision.allowed
    assert decision.source == "nemo"


def test_invalid_nemo_configuration_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("NEMO_GUARDRAILS_CONFIG", str(tmp_path / "missing-config"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    decision = inspect_with_nemo("How many orders are there?")
    assert not decision.allowed
    assert decision.source == "unavailable"
