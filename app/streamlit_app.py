"""Streamlit dashboard for the guarded SQL analytics workflow."""
from __future__ import annotations

import re
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from app.graph import build_graph, create_engine_from_url

load_dotenv()

_IDENTIFIER = re.compile(r"(^id$|_id$|^id_|identifier|^index$|postal|zip$)", re.IGNORECASE)
_TIME_NAME = re.compile(r"date|time|month|week|quarter|year", re.IGNORECASE)
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(://[^:/\s]+:)[^@/\s]+(@)"),
)


def _safe_display_text(value: object) -> str:
    message = str(value)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            message = pattern.sub(r"\1[REDACTED]\2" if pattern.groups == 2 else r"\1[REDACTED]", message)
        else:
            message = pattern.sub("[REDACTED]", message)
    return message


def _is_time_dimension(frame: pd.DataFrame, column: str) -> bool:
    series = frame[column]
    return bool(_TIME_NAME.search(str(column)) or pd.api.types.is_datetime64_any_dtype(series))


def chart_dimensions(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return meaningful category/date and measure columns, excluding IDs."""
    if frame.empty:
        return [], []
    labels: list[str] = []
    measures: list[str] = []
    for column in frame.columns:
        name = str(column)
        series = frame[column]
        if _IDENTIFIER.search(name):
            continue
        unique_count = series.nunique(dropna=True)
        if 2 <= unique_count <= 20 and (
            not pd.api.types.is_numeric_dtype(series) or _is_time_dimension(frame, column)
        ):
            labels.append(column)
        if (pd.api.types.is_numeric_dtype(series)
                and not pd.api.types.is_bool_dtype(series)
                and not _is_time_dimension(frame, column)
                and series.notna().any()):
            measures.append(column)
    return labels, measures


def chart_types_for(frame: pd.DataFrame, label: str, measure: str) -> list[str]:
    """List chart types suitable for a selected category and numeric measure."""
    if frame.empty or label not in frame or measure not in frame:
        return []
    data = frame[[label, measure]].copy()
    data[measure] = pd.to_numeric(data[measure], errors="coerce")
    data = data.dropna()
    if data.empty:
        return []
    types = ["Bar"]
    is_time = _is_time_dimension(frame, label)
    if is_time:
        types.append("Line")
    groups = data[label].nunique()
    if not is_time and 2 <= groups <= 8:
        types.append("Pie")
    return types


def _chart_data(frame: pd.DataFrame, label: str, measure: str) -> pd.DataFrame:
    data = frame[[label, measure]].copy()
    data[measure] = pd.to_numeric(data[measure], errors="coerce")
    data = data.dropna(subset=[label, measure])
    if data.empty:
        return data
    return data.groupby(label, as_index=False, observed=True)[measure].sum()


def build_chart_figure(frame: pd.DataFrame, label: str, measure: str, chart_type: str):
    """Build an interactive Plotly figure only for a suitable chart choice."""
    if chart_type not in chart_types_for(frame, label, measure):
        return None
    data = _chart_data(frame, label, measure)
    if data.empty:
        return None
    title = f"{measure} by {label}"
    if chart_type == "Bar":
        return px.bar(data, x=label, y=measure, title=title)
    if chart_type == "Line":
        if _is_time_dimension(frame, label):
            data[label] = pd.to_datetime(data[label], errors="coerce")
            data = data.dropna(subset=[label]).sort_values(label)
        return px.line(data, x=label, y=measure, markers=True, title=title)
    return px.pie(data, names=label, values=measure, title=title, hole=0.25)


def _render_chart(frame: pd.DataFrame) -> None:
    labels, measures = chart_dimensions(frame)
    if not labels or not measures:
        st.info("No chart suggestion: results need a meaningful category or date and a numeric measure.")
        return
    controls = st.columns(2)
    with controls[0]:
        label = st.selectbox("Chart category", labels, key="chart_category")
    with controls[1]:
        measure = st.selectbox("Chart measure", measures, key="chart_measure")
    options = chart_types_for(frame, label, measure)
    if not options:
        st.info("No chart can be drawn because the selected columns contain no usable values.")
        return
    if len(options) > 1:
        chart_type = st.selectbox("Chart type", options, key="chart_type")
    else:
        chart_type = options[0]
        st.caption(f"Suggested chart: {chart_type}")
    figure = build_chart_figure(frame, label, measure, chart_type)
    if figure is None:
        st.info("No chart can be drawn after missing or non-numeric values are removed.")
        return
    st.plotly_chart(figure, use_container_width=True)


def _final_status(state: dict) -> str:
    if state.get("security_blocked"):
        return "Blocked by security guardrails"
    if state.get("error_message"):
        return "Failed"
    if state.get("generated_sql"):
        return "Completed successfully"
    return "Not executed"


def main() -> None:
    st.set_page_config(page_title="SQL Analytics Agent", page_icon="📊", layout="wide")
    st.title("SQL & Database Analytics Agent")
    st.caption("Ask a business question about the sample sales data. Queries are guarded, validated, and executed read-only.")
    if not os.getenv("OPENAI_API_KEY"):
        st.info("Set OPENAI_API_KEY in your local .env file to enable live natural-language SQL generation.")

    with st.form("analytics_query"):
        query = st.text_area(
            "Business question",
            placeholder="Which product categories generated the most revenue?",
            help="Ask a question about customers, orders, or sales. Do not enter SQL commands.",
        )
        submitted = st.form_submit_button("Run query", type="primary")
    if submitted:
        if not query.strip():
            st.error("Enter a business question before running the query.")
        else:
            try:
                graph = build_graph(engine=create_engine_from_url())
                with st.spinner("Checking the request and running the analytics workflow…"):
                    st.session_state["last_run"] = graph.invoke({
                        "user_query": query, "generated_sql": "", "db_result": [], "error_message": "",
                        "retry_count": 0, "schema": "", "logs": [], "history": [],
                    })
            except Exception:
                # Do not render raw exceptions: provider/connection exceptions can
                # contain credentials. Detailed secrets stay out of the UI/logs.
                st.error("The query could not be completed. Check the database and model configuration, then try again.")

    state = st.session_state.get("last_run")
    if state is None:
        st.markdown("#### Example questions\n- Monthly sales revenue\n- Top five customers by order value\n- Units sold by product category")
        return

    if state.get("security_blocked"):
        st.error(_safe_display_text(state.get("error_message") or "Security warning: request blocked before processing."))
    elif state.get("error_message"):
        st.error(_safe_display_text(state["error_message"]))

    status = _final_status(state)
    st.metric("Final execution status", status)
    st.caption(f"Correction retries: {int(state.get('retry_count', 0))}")

    result = state.get("db_result")
    frame = pd.DataFrame(result) if isinstance(result, list) else pd.DataFrame()
    if state.get("security_blocked"):
        st.info("This request was blocked before schema inspection, SQL generation, or database execution.")
    elif state.get("error_message"):
        st.info("No successful result is available for this query.")
    elif not frame.empty:
        st.subheader("Query results")
        st.dataframe(frame, use_container_width=True, hide_index=True)
        _render_chart(frame)
    elif state.get("generated_sql"):
        st.info("The query completed successfully and returned no rows.")
    else:
        st.info("No query results are available.")

    with st.expander("Generated SQL query", expanded=False):
        st.code(state.get("generated_sql") or "No SQL was generated.", language="sql")
    with st.expander("Execution telemetry and logs", expanded=False):
        st.write(f"**Status:** {status}")
        st.write(f"**Correction retries:** {int(state.get('retry_count', 0))}")
        logs = state.get("logs", [])
        if logs:
            for entry in logs:
                st.write(f"• {entry}")
        else:
            st.write("No execution log entries.")
        if state.get("error_message"):
            st.write("**Final error:**")
            st.code(_safe_display_text(state["error_message"]))

    with st.expander("Self-correction history", expanded=False):
        history = state.get("history", [])
        if history:
            for attempt, entry in enumerate(history, 1):
                st.markdown(f"**Execution attempt {attempt}**")
                st.code(entry.get("sql", ""), language="sql")
                st.caption(_safe_display_text(entry.get("error", "")))
        else:
            st.write("No correction attempts were needed.")


if __name__ == "__main__":
    main()
