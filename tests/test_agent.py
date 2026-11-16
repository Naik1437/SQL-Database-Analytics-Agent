from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from app.graph import MAX_RETRIES, build_graph, execute_query_node, generate_sql_node, reflection_node
from database.seed import seed_database


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def allow_guardrails_without_api_key(monkeypatch):
    monkeypatch.setattr("app.graph.inspect_with_nemo", lambda _text: (True, ""))


def initial_state(query):
    return {"user_query": query, "retry_count": 0, "generated_sql": "", "db_result": [],
            "error_message": "", "schema": "", "logs": [], "history": []}


@pytest.fixture
def engine(tmp_path):
    path = seed_database(tmp_path / "analytics.db")
    return create_engine(f"sqlite:///{path}")


def test_graph_runs_generated_read_query(engine):
    graph = build_graph(engine=engine, llm=FakeLLM("SELECT COUNT(*) AS order_count FROM orders"))
    result = graph.invoke(initial_state("How many orders?"))
    assert result["error_message"] == ""
    assert result["db_result"] == [{"order_count": 10}]


def test_graph_corrects_created_at_using_reflected_schema(engine):
    llm = FakeLLM(
        "SELECT id, created_at FROM orders ORDER BY created_at",
        "SELECT id, order_date FROM orders ORDER BY order_date",
    )
    result = build_graph(engine=engine, llm=llm).invoke(initial_state("Show orders sorted by date."))

    assert result["error_message"] == ""
    assert result["retry_count"] == 1
    assert result["db_result"] == [
        {"id": 1, "order_date": "2025-01-12"},
        {"id": 2, "order_date": "2025-01-19"},
        {"id": 3, "order_date": "2025-02-03"},
        {"id": 4, "order_date": "2025-02-17"},
        {"id": 5, "order_date": "2025-03-08"},
        {"id": 6, "order_date": "2025-03-21"},
        {"id": 7, "order_date": "2025-04-02"},
        {"id": 8, "order_date": "2025-04-16"},
        {"id": 9, "order_date": "2025-05-05"},
        {"id": 10, "order_date": "2025-05-22"},
    ]
    assert len(result["history"]) == 1
    assert "created_at" in result["history"][0]["sql"]
    assert "no such column" in result["history"][0]["error"].lower()
    assert "orders(id INTEGER" in llm.prompts[1]
    assert "no such column" in llm.prompts[1].lower()
    assert any("Self-correction attempt 1" in log for log in result["logs"])


def test_graph_stops_after_three_correction_retries(engine):
    llm = FakeLLM(
        "SELECT created_at FROM orders",
        "SELECT missing_one FROM orders",
        "SELECT missing_two FROM orders",
        "SELECT missing_three FROM orders",
    )
    result = build_graph(engine=engine, llm=llm).invoke(initial_state("Show orders."))

    assert result["retry_count"] == MAX_RETRIES == 3
    assert len(llm.prompts) == 1 + MAX_RETRIES
    assert len(result["history"]) == 1 + MAX_RETRIES
    assert len(result["db_result"]) == 0
    assert result["error_message"]
    assert sum("Self-correction attempt" in log for log in result["logs"]) == MAX_RETRIES


def test_successful_query_does_not_trigger_correction(engine):
    llm = FakeLLM("SELECT id, order_date FROM orders ORDER BY order_date LIMIT 2")
    result = build_graph(engine=engine, llm=llm).invoke(initial_state("Show the first two orders."))

    assert result["error_message"] == ""
    assert result["retry_count"] == 0
    assert result["history"] == []
    assert result["db_result"] == [
        {"id": 1, "order_date": "2025-01-12"},
        {"id": 2, "order_date": "2025-01-19"},
    ]
    assert len(llm.prompts) == 1


def test_gemini_timeout_returns_clear_error_without_leaking_provider_details(engine):
    class TimedOutLLM:
        def invoke(self, _prompt):
            raise TimeoutError("request timed out; api_key=do-not-display")

    result = build_graph(engine=engine, llm=TimedOutLLM()).invoke(initial_state("How many orders?"))

    assert result["error_message"] == (
        "Gemini request timed out after 30 seconds. Check the network and selected model, then retry."
    )
    assert result["llm_error"] is True
    assert "do-not-display" not in result["error_message"]
    assert result["db_result"] == []


def test_reflection_gemini_failure_stops_correction_loop(engine):
    class FailsOnCorrection:
        def __init__(self):
            self.calls = 0

        def invoke(self, _prompt):
            self.calls += 1
            if self.calls == 1:
                return "SELECT created_at FROM orders"
            raise TimeoutError("deadline exceeded")

    llm = FailsOnCorrection()
    result = build_graph(engine=engine, llm=llm).invoke(initial_state("Show order dates."))

    assert llm.calls == 2
    assert result["retry_count"] == 1
    assert result["llm_error"] is True
    assert "timed out" in result["error_message"]
    assert len(result["history"]) == 1


def test_execution_validates_before_database(engine):
    executed_statements = []
    event.listen(engine, "before_cursor_execute",
                 lambda conn, cursor, statement, parameters, context, executemany:
                 executed_statements.append(statement))

    result = execute_query_node({"generated_sql": "DELETE FROM orders", "logs": []}, engine=engine)

    assert result["db_result"] == []
    assert "Only read-only SELECT queries" in result["error_message"]
    assert executed_statements == []


def test_reflection_uses_schema_and_database_error():
    llm = FakeLLM("SELECT COUNT(*) AS total FROM orders")
    result = reflection_node({"schema": "orders(order_id INTEGER)",
                              "generated_sql": "SELECT total FROM orders",
                              "error_message": "no such column: total", "retry_count": 0,
                              "logs": []}, llm=llm)
    assert result["generated_sql"] == "SELECT COUNT(*) AS total FROM orders"
    assert result["retry_count"] == 1
    assert "no such column" in llm.prompts[0]


def test_reflection_rejects_unsafe_llm_fix():
    result = reflection_node({"schema": "orders(order_id INTEGER)", "generated_sql": "SELECT 1",
                              "error_message": "bad query", "retry_count": 0, "logs": []},
                             llm=FakeLLM("DROP TABLE orders"))
    assert result["generated_sql"] == ""
    assert result["retry_count"] == 1


@pytest.mark.parametrize("response", [
    "```sql\nSELECT * FROM orders\n```",
    "SELECT * FROM orders",
])
def test_generate_sql_normalizes_fenced_and_unfenced_responses(response):
    result = generate_sql_node({"schema": "orders(id INTEGER, order_date TEXT)",
                                "user_query": "Show orders", "logs": []},
                               llm=FakeLLM(response))

    assert result["generated_sql"] == "SELECT * FROM orders"
    assert result["error_message"] == ""


def test_generate_sql_extracts_text_from_gemini_content_blocks():
    class GeminiMessage:
        content = [{"type": "text", "text": "SELECT * FROM orders"}]

    result = generate_sql_node({"schema": "orders(id INTEGER)", "user_query": "Show orders", "logs": []},
                               llm=FakeLLM(GeminiMessage()))

    assert result["generated_sql"] == "SELECT * FROM orders"
    assert result["error_message"] == ""


@pytest.mark.parametrize("unsafe_sql", ["DELETE FROM orders", "DROP TABLE orders"])
def test_unsafe_reflection_correction_never_reaches_database(engine, unsafe_sql):
    executed_statements = []
    event.listen(engine, "before_cursor_execute",
                 lambda conn, cursor, statement, parameters, context, executemany:
                 executed_statements.append(statement))
    llm = FakeLLM(
        "SELECT id, created_at FROM orders",
        unsafe_sql,
        "SELECT id, order_date FROM orders ORDER BY order_date LIMIT 1",
    )

    result = build_graph(engine=engine, llm=llm).invoke(initial_state("Show the first order."))

    assert result["error_message"] == ""
    assert result["retry_count"] == 2
    assert result["db_result"] == [{"id": 1, "order_date": "2025-01-12"}]
    assert any("Correction output failed validation." in log for log in result["logs"])
    assert all(unsafe_sql.upper() not in statement.upper() for statement in executed_statements)
