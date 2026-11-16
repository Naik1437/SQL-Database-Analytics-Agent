# SQL & Database Analytics Agent

A modular natural-language analytics application built with LangGraph, LangChain, SQLAlchemy, SQLGlot, NeMo Guardrails, SQLite, Streamlit, Pandas, and Plotly. The agent inspects the actual database schema, generates a query, validates its SQL AST, executes it in read-only mode, and uses database feedback for up to three correction attempts.

## Security behavior

- Every model-produced query is parsed by SQLGlot and must be one read-only `SELECT` (including read-only set operations).
- Multiple statements and mutating operations are rejected before execution.
- SQLite connections use URI `mode=ro`; SQLAlchemy sends the query through a read-only connection.
- NeMo Guardrails inspects user input. The deterministic input gate also rejects empty/oversized prompts and common injection or mutation phrases.
- API keys are read from `.env` and are never included in prompts, logs, SQL output, or UI.
- Query results are capped at 1,000 rows for display.

## Requirements

Windows 10 64-bit, Python 3.11, Git, and an OpenAI API key. The project uses the existing virtual environment when available. Install missing packages only if needed.

## Setup (PowerShell)

```powershell
cd C:\Users\HANMANTHU\SQL-Database-Analytics-Agent
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
notepad .env
python -m database.seed
```

Set `OPENAI_API_KEY` in `.env` to your own key. Optionally set `OPENAI_MODEL`, `DATABASE_URL`, and `NEMO_GUARDRAILS_CONFIG`. Do not paste keys into source files or commit `.env`.

If the environment is new, install dependencies using `python -m pip install -r requirements.txt`. Pin/lock versions for a production deployment after selecting a supported Python and package set.

## Run

```powershell
streamlit run app/streamlit_app.py
```

The sample database is `database/analytics.db`; reseed it with `python -m database.seed`. The seed script is for local development and recreates its sample tables.

## Test

```powershell
pytest -q
```

Tests use a temporary seeded database and mocked LLM responses. They verify SQL write/multi-statement rejection, validation before execution, successful query execution, and correction behavior without requiring an API key.

## Project layout

```text
app/                 LangGraph, guardrails, validation, Streamlit UI
config/guardrails/   NeMo Guardrails config and input policy
database/            SQLite seed script and generated local database
tests/               Security and self-correction tests
.env.example         Environment variable template
```

## Manual steps

1. Restore/install Python 3.11 if the project virtual environment cannot start, then recreate it with `py -3.11 -m venv .venv`.
2. Activate `.venv`, install any missing requirements, and seed the database.
3. Add your OpenAI API key to the ignored `.env` file.
4. Start Streamlit and ask a question about orders, customers, or sales.

The API key is required only for live natural-language generation; tests use fake model responses.
