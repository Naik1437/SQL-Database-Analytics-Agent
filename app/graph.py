"""LangGraph pipeline for safe natural-language analytics."""
from __future__ import annotations

import os
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.guardrails import GuardrailDecision, inspect_with_nemo
from app.llm_provider import create_gemini_chat_model
from app.security import UnsafeQueryError, inspect_user_input, validate_read_only_sql

MAX_RETRIES = 3
MAX_GRAPH_STEPS = 16


class AgentState(TypedDict, total=False):
    user_query: str
    generated_sql: str
    db_result: list[dict[str, Any]]
    error_message: str
    retry_count: int
    schema: str
    logs: list[str]
    history: list[dict[str, str]]
    security_blocked: bool
    llm_error: bool


def create_engine_from_url(database_url: str | None = None) -> Engine:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///database/analytics.db")
    if url.startswith("sqlite:"):
        # SQLite URI mode=ro prevents mutation regardless of query validation.
        path = url.replace("sqlite:///", "", 1)
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        url = f"sqlite:///file:{path}?mode=ro&uri=true"
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def inspect_schema_node(state: AgentState, *, engine: Engine) -> AgentState:
    inspector = inspect(engine)
    tables = []
    for table in inspector.get_table_names():
        cols = ", ".join(f"{column['name']} {column['type']}" for column in inspector.get_columns(table))
        tables.append(f"{table}({cols})")
    schema = "\n".join(tables)
    if not schema:
        return {"schema": "", "error_message": "The database contains no tables.",
                "logs": state.get("logs", []) + ["Schema inspection found no tables."]}
    return {"schema": schema, "error_message": "",
            "logs": state.get("logs", []) + ["Inspected database schema."]}


def _default_llm():
    """Build the configured Gemini model used by generation and reflection."""
    return create_gemini_chat_model()


def _content(result: Any) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
            elif isinstance(getattr(part, "text", None), str):
                text_parts.append(part.text)
        return "\n".join(text_parts).strip()
    return str(content).strip()


def _normalize_sql_response(result: Any) -> str:
    """Remove optional Markdown SQL fences and return the contained SQL text."""
    sql = _content(result)
    if sql.startswith("```"):
        sql = sql[3:].strip()
        if sql.endswith("```"):
            sql = sql[:-3].strip()
    lines = sql.splitlines()
    if lines and lines[0].strip().lower() in {"sql", "sqlite"}:
        sql = "\n".join(lines[1:]).strip()
    else:
        # Also tolerate one-line fences such as ```sql SELECT ... ```.
        sql = re.sub(r"^(?:sql|sqlite)\s+(?=(?:SELECT|WITH)\b)", "", sql,
                     count=1, flags=re.IGNORECASE)
    return sql


class GeminiRequestError(RuntimeError):
    """Safe, credential-free message for a failed model request."""


def _invoke_llm(llm: Any, prompt: str) -> Any:
    """Invoke the model without allowing provider diagnostics to leak secrets."""
    try:
        return llm.invoke(prompt)
    except Exception as exc:
        error_name = type(exc).__name__.casefold()
        error_text = str(exc).casefold()
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if any(token in error_name or token in error_text for token in ("timeout", "deadline")):
            message = "Gemini request timed out after 30 seconds. Check the network and selected model, then retry."
        elif status == 503 or "service unavailable" in error_text or "overloaded" in error_text:
            message = (
                "Gemini generation is temporarily unavailable (API status 503). "
                "Retry later or select another currently available free-tier model."
            )
        elif status == 404 or "model not found" in error_text or "unknown model" in error_text:
            message = "The configured Gemini model is not available for generation at this API endpoint."
        elif status == 429 or "resource_exhausted" in error_text or "quota" in error_text:
            message = "Gemini free-tier quota or rate limit was reached. Wait for quota reset and retry."
        else:
            message = "Gemini request failed. Check the network, API key configuration, model name, and quota."
        raise GeminiRequestError(message) from None


def generate_sql_node(state: AgentState, *, llm: Any) -> AgentState:
    prompt = ("Write exactly one SQLite read-only SELECT query for the user request. "
              "Use only the schema below. Return SQL only.\n\nSchema:\n" + state.get("schema", "") +
              "\n\nQuestion: " + state.get("user_query", ""))
    try:
        response = _invoke_llm(llm, prompt)
    except GeminiRequestError as exc:
        return {"generated_sql": "", "error_message": str(exc), "llm_error": True,
                "logs": state.get("logs", []) + ["Gemini request failed during SQL generation."]}
    try:
        sql = validate_read_only_sql(_normalize_sql_response(response))
        return {"generated_sql": sql, "error_message": "",
                "logs": state.get("logs", []) + ["Generated and validated read-only SQL."]}
    except Exception as exc:
        return {"error_message": str(exc), "generated_sql": "",
                "logs": state.get("logs", []) + ["SQL generation or validation failed."]}


def execute_query_node(state: AgentState, *, engine: Engine) -> AgentState:
    try:
        sql = validate_read_only_sql(state.get("generated_sql", ""))
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = [dict(row) for row in result.mappings().fetchmany(1000)]
        return {"db_result": rows, "error_message": "",
                "logs": state.get("logs", []) + [f"Query returned {len(rows)} row(s)."]}
    except Exception as exc:
        message = str(exc)
        history = state.get("history", []) + [{"sql": state.get("generated_sql", ""), "error": message}]
        return {"db_result": [], "error_message": message, "history": history,
                "logs": state.get("logs", []) + ["Database rejected the query; preparing correction."]}


def reflection_node(state: AgentState, *, llm: Any) -> AgentState:
    if state.get("retry_count", 0) >= MAX_RETRIES:
        return {"error_message": "Maximum SQL correction attempts reached. " + state.get("error_message", ""),
                "logs": state.get("logs", []) + ["Stopped after 3 correction attempts."]}
    prompt = ("Correct the SQL using the actual schema and database error. Return exactly one SQLite "
              "read-only SELECT query, SQL only.\nSchema:\n" + state.get("schema", "") +
              "\nFailed SQL:\n" + state.get("generated_sql", "") + "\nDatabase error:\n" +
              state.get("error_message", ""))
    try:
        response = _invoke_llm(llm, prompt)
    except GeminiRequestError as exc:
        return {"generated_sql": "", "retry_count": state.get("retry_count", 0) + 1,
                "error_message": str(exc), "llm_error": True,
                "logs": state.get("logs", []) + ["Gemini request failed during SQL correction."]}
    try:
        sql = validate_read_only_sql(_normalize_sql_response(response))
        return {"generated_sql": sql, "retry_count": state.get("retry_count", 0) + 1,
                "error_message": "", "logs": state.get("logs", []) +
                [f"Self-correction attempt {state.get('retry_count', 0) + 1} generated validated SQL."]}
    except Exception as exc:
        return {"generated_sql": "", "retry_count": state.get("retry_count", 0) + 1,
                "error_message": str(exc),
                "logs": state.get("logs", []) + ["Correction output failed validation."]}


def build_graph(*, engine: Engine | None = None, llm: Any = None):
    engine = engine or create_engine_from_url()
    llm = llm or _default_llm()

    def guard(state: AgentState) -> AgentState:
        okay, reason = inspect_user_input(state.get("user_query", ""))
        decision = None
        if okay:
            decision = inspect_with_nemo(state.get("user_query", ""))
            # Keep compatibility with older external test doubles while the
            # application itself uses a typed, auditable decision.
            if isinstance(decision, tuple):
                okay, reason = decision
            else:
                okay, reason = decision.allowed, decision.message
        blocked = not okay and decision is not None
        if blocked:
            reason = "Security warning: " + reason
        if not okay:
            status = "Input blocked by security guardrails."
        elif decision is None:
            status = "Input passed basic request checks."
        elif isinstance(decision, GuardrailDecision):
            status = {
                "deterministic_filter": "Input blocked by deterministic security filter.",
                "deterministic_fallback": "Input passed deterministic fallback; NeMo LLM inspection skipped.",
                "nemo": "Input passed NeMo Guardrails.",
                "unavailable": "Input blocked because guardrails could not inspect the request.",
            }[decision.source]
        else:
            status = "Input passed safety inspection."
        return {"error_message": "" if okay else reason,
                "security_blocked": blocked,
                "logs": state.get("logs", []) + [status]}

    def select_after_guard(state): return "inspect_schema_node" if not state.get("error_message") else "done"
    def select_after_generate(state): return "execute_query_node" if not state.get("error_message") else "done"
    def select_after_execute(state): return "reflection_node" if state.get("error_message") and state.get("retry_count", 0) < MAX_RETRIES else "done"
    def select_after_reflect(state): return "execute_query_node" if state.get("generated_sql") and not state.get("error_message") else ("reflection_node" if not state.get("llm_error") and state.get("retry_count", 0) < MAX_RETRIES else "done")

    graph = StateGraph(AgentState)
    graph.add_node("guard", guard)
    graph.add_node("inspect_schema_node", lambda s: inspect_schema_node(s, engine=engine))
    graph.add_node("generate_sql_node", lambda s: generate_sql_node(s, llm=llm))
    graph.add_node("execute_query_node", lambda s: execute_query_node(s, engine=engine))
    graph.add_node("reflection_node", lambda s: reflection_node(s, llm=llm))
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", select_after_guard,
                                {"inspect_schema_node": "inspect_schema_node", "done": END})
    graph.add_edge("inspect_schema_node", "generate_sql_node")
    graph.add_conditional_edges("generate_sql_node", select_after_generate, {"execute_query_node": "execute_query_node", "done": END})
    graph.add_conditional_edges("execute_query_node", select_after_execute, {"reflection_node": "reflection_node", "done": END})
    graph.add_conditional_edges("reflection_node", select_after_reflect, {"execute_query_node": "execute_query_node", "reflection_node": "reflection_node", "done": END})
    return graph.compile()


def run_query(query: str, *, engine: Engine | None = None, llm: Any = None) -> AgentState:
    state = {"user_query": query, "generated_sql": "", "db_result": [], "error_message": "",
             "retry_count": 0, "schema": "", "logs": [], "history": []}
    return build_graph(engine=engine, llm=llm).invoke(
        state, config={"recursion_limit": MAX_GRAPH_STEPS}
    )
