# SQL & Database Analytics Agent

A natural-language analytics application built with LangGraph, LangChain, SQLAlchemy, SQLGlot, NeMo Guardrails, SQLite, Streamlit, Pandas, and Plotly. The agent reflects the database schema, generates and validates SQL, executes it read-only, and can use database errors to correct a query up to three times.

## Requirements

- Windows 10 64-bit
- Python 3.11
- An OpenAI API key for live SQL generation

## Setup (PowerShell)

From the project directory, create a virtual environment and install the dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create your local environment file and edit it to add your API key:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `OPENAI_API_KEY` in `.env`. You can also configure `OPENAI_MODEL`, `DATABASE_URL`, and `NEMO_GUARDRAILS_CONFIG`. The sample database URL is `sqlite:///database/analytics.db`. Keep `.env` private; it is excluded by `.gitignore`.

If PowerShell blocks `Activate.ps1`, use the explicit `.venv\Scripts\python.exe` and `.venv\Scripts\streamlit.exe` paths in these instructions; there is no need to change the machine's execution policy.

## Seed the SQLite database

```powershell
.\.venv\Scripts\python.exe -m database.seed
```

The seed script recreates the sample `customers`, `orders`, and `sales` tables and inserts their sample records. `orders` includes `id` and `order_date`; its existing `order_id` key is retained for the related sales rows.

## Run the Streamlit application

With `.venv` activated, the assessment command is:

```powershell
streamlit run app.py
```

If the environment is not activated, run the same app through its environment executable:

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated tests use a temporary seeded SQLite database and mocked LLM responses. They cover read-only SQL validation, database execution, and correction behavior without requiring a live API key.

## Security behavior

- SQLGlot accepts one read-only `SELECT` statement and rejects write operations and multiple statements.
- The app opens SQLite with URI `mode=ro` after the database has been seeded.
- NeMo Guardrails inspects user input before the SQL-generation node.
- The app reads API credentials from `.env`; secrets are not embedded in prompts or output.
- Results are capped at 1,000 rows.

## Project layout

```text
app.py                 Root Streamlit entry point
app/                   LangGraph workflow, validation, guardrails, and UI
config/guardrails/     NeMo Guardrails configuration
database/              SQLite seed script and generated local database
tests/                 Security and self-correction tests
.env.example           Environment variable template
```
