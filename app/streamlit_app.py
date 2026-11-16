"""Streamlit interface for the analytics agent."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from app.graph import build_graph, create_engine_from_url

load_dotenv()


def main() -> None:
    st.set_page_config(page_title="SQL Analytics Agent", page_icon="📊", layout="wide")
    st.title("SQL & Database Analytics Agent")
    st.caption("Ask a question about sample sales data. Queries are validated and run read-only.")
    if not os.getenv("OPENAI_API_KEY"):
        st.info("Set OPENAI_API_KEY in your local .env file to enable natural-language queries.")
    query = st.text_area("Your analytics question", placeholder="Which product categories generated the most revenue?")
    if st.button("Analyze", type="primary", disabled=not query.strip()):
        try:
            graph = build_graph(engine=create_engine_from_url())
            with st.spinner("Inspecting data and generating a safe query…"):
                st.session_state["last_run"] = graph.invoke({
                    "user_query": query, "generated_sql": "", "db_result": [], "error_message": "",
                    "retry_count": 0, "schema": "", "logs": [], "history": []
                })
        except Exception as exc:
            st.error(f"The query could not be completed: {exc}")

    state = st.session_state.get("last_run")
    if not state:
        st.markdown("#### Try asking\n- Monthly sales revenue\n- Top five customers by order value\n- Units sold by product category")
        return
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Generated SQL")
        st.code(state.get("generated_sql") or "No SQL generated", language="sql")
        st.subheader("Execution log")
        for item in state.get("logs", []):
            st.write("• " + item)
    with right:
        st.subheader("Results")
        frame = pd.DataFrame(state.get("db_result", []))
        if not frame.empty:
            st.dataframe(frame, use_container_width=True, hide_index=True)
            numeric = frame.select_dtypes(include="number").columns.tolist()
            categorical = [column for column in frame.columns if column not in numeric]
            if numeric and categorical:
                x_axis = st.selectbox("Chart category", categorical)
                y_axis = st.selectbox("Chart value", numeric)
                chart_type = st.selectbox("Chart type", ["Bar", "Line", "Scatter"])
                chart_fn = {"Bar": px.bar, "Line": px.line, "Scatter": px.scatter}[chart_type]
                st.plotly_chart(chart_fn(frame, x=x_axis, y=y_axis, title=f"{y_axis} by {x_axis}"), use_container_width=True)
        else:
            st.info("No result rows were returned.")
        if state.get("error_message"):
            st.error(state["error_message"])
    with st.expander("Self-correction history"):
        if state.get("history"):
            for attempt, entry in enumerate(state["history"], 1):
                st.markdown(f"**Attempt {attempt}**")
                st.code(entry.get("sql", ""), language="sql")
                st.caption(entry.get("error", ""))
        else:
            st.write("No correction attempts were needed.")


if __name__ == "__main__":
    main()
