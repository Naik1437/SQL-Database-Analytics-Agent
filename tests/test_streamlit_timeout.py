from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class _TimedOutGraph:
    def invoke(self, _state, *, config):
        assert config["recursion_limit"] == 16
        return {
            "user_query": "How many orders were placed?",
            "generated_sql": "",
            "db_result": [],
            "error_message": (
                "Gemini request timed out after 30 seconds. "
                "Check the network and selected model, then retry."
            ),
            "retry_count": 0,
            "logs": ["Gemini request failed during SQL generation."],
            "history": [],
        }


def test_streamlit_renders_gemini_timeout_instead_of_leaving_spinner():
    project_root = Path(__file__).resolve().parents[1]
    with (
        patch("app.streamlit_app.build_graph", return_value=_TimedOutGraph()),
        patch("app.streamlit_app.create_engine_from_url", return_value=None),
    ):
        app = AppTest.from_file(str(project_root / "app.py")).run()
        app.text_area[0].set_value("How many orders were placed?")
        app.form_submit_button[0].click().run()

    assert not app.exception
    assert any("Gemini request timed out after 30 seconds" in alert.value for alert in app.error)
    assert any("No successful result is available" in alert.value for alert in app.info)
