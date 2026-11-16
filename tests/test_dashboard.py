import pandas as pd

from app.streamlit_app import (
    _chart_data,
    _safe_display_text,
    build_chart_figure,
    chart_dimensions,
    chart_types_for,
)


def test_chart_dimensions_exclude_identifiers_and_select_meaningful_fields():
    frame = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "category": ["Books", "Games", "Books"],
        "revenue": [10.0, 20.0, 5.0],
    })

    labels, measures = chart_dimensions(frame)

    assert labels == ["category"]
    assert measures == ["revenue"]
    assert chart_types_for(frame, "category", "revenue") == ["Bar", "Pie"]


def test_time_dimension_supports_line_and_bar_but_not_pie():
    frame = pd.DataFrame({
        "order_date": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "revenue": [10, 20, 15],
    })

    labels, measures = chart_dimensions(frame)

    assert labels == ["order_date"]
    assert measures == ["revenue"]
    assert chart_types_for(frame, "order_date", "revenue") == ["Bar", "Line"]


def test_text_only_results_have_no_chart_suggestion():
    labels, measures = chart_dimensions(pd.DataFrame({
        "customer": ["A", "B"], "region": ["North", "South"]
    }))
    assert labels == ["customer", "region"]
    assert measures == []


def test_chart_data_drops_missing_values_and_aggregates_categories():
    frame = pd.DataFrame({
        "category": ["Books", "Books", "Games", None],
        "revenue": [10, 5, 20, 100],
    })

    result = _chart_data(frame, "category", "revenue")

    assert result.to_dict("records") == [
        {"category": "Books", "revenue": 15},
        {"category": "Games", "revenue": 20},
    ]


def test_dashboard_redacts_credential_like_error_text():
    safe = _safe_display_text("api_key=sk-test1234567890abcdef and sqlite://user:secret@host/db")
    assert "sk-test1234567890abcdef" not in safe
    assert "user:secret" not in safe
    assert "[REDACTED]" in safe


def test_plotly_figures_are_created_for_bar_line_and_pie():
    category_data = pd.DataFrame({"category": ["Books", "Games", "Music"], "revenue": [10, 20, 5]})
    date_data = pd.DataFrame({"order_date": ["2025-01-01", "2025-02-01"], "revenue": [10, 20]})

    assert build_chart_figure(category_data, "category", "revenue", "Bar").data[0].type == "bar"
    assert build_chart_figure(category_data, "category", "revenue", "Pie").data[0].type == "pie"
    assert build_chart_figure(date_data, "order_date", "revenue", "Line").data[0].type == "scatter"
    assert build_chart_figure(category_data, "category", "revenue", "Line") is None
