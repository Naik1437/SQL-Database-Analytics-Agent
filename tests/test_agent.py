from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from app.graph import build_graph, execute_query_node, reflection_node
from database.seed import seed_database


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


@pytest.fixture
def engine(tmp_path):
    path = seed_database(tmp_path / "analytics.db")
    return create_engine(f"sqlite:///{path}")


def test_graph_runs_generated_read_query(engine):
    graph = build_graph(engine=engine, llm=FakeLLM("SELECT COUNT(*) AS order_count FROM orders"))
    result = graph.invoke({"user_query": "How many orders?", "retry_count": 0,
                           "generated_sql": "", "db_result": [], "error_message": "",
                           "schema": "", "logs": [], "history": []})
    assert result["error_message"] == ""
    assert result["db_result"] == [{"order_count": 10}]


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
