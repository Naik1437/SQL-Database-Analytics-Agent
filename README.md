# SQL & Database Analytics Agent

A natural-language analytics application built with LangGraph, LangChain, SQLAlchemy, SQLGlot, NeMo Guardrails, SQLite, Streamlit, Pandas, and Plotly. The agent reflects the database schema, generates and validates SQL, executes it read-only, and can use database errors to correct a query up to three times.

## Architecture and technologies

The LangGraph `StateGraph` keeps the user question, generated SQL, query results, error, and correction retry count. Before schema inspection, the raw question passes through the deterministic safety filter and configured NeMo input rail (or the documented deterministic-only fallback when no API key is set). The workflow reflects the SQLite schema with SQLAlchemy, asks the configured chat model for one query, validates it with SQLGlot, and executes it through a read-only SQLite connection. A database error is passed with the reflected schema to the correction step, which may retry up to three times. Streamlit presents the result table, SQL, logs, correction history, and suitable Plotly charts.

Technologies: Python 3.11, LangGraph, LangChain, LangChain-OpenAI, SQLAlchemy, SQLGlot, NeMo Guardrails, SQLite, Streamlit, Plotly, Pandas, pytest, and python-dotenv.

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

The dashboard shows query results in a dataframe and keeps generated SQL, execution telemetry, and self-correction history in separate collapsed panels. When the result contains a meaningful category/date and numeric measure, it suggests an interactive Plotly bar chart; date dimensions can also use a line chart, and categories with a small number of groups can use a pie chart. Identifier columns such as `id` and `customer_id` are excluded from chart suggestions. Text-only or empty results are shown without a chart.

Example questions:

- Show orders sorted by date.
- Which product categories generated the most revenue?
- Show monthly sales revenue.
- Who are the top five customers by order value?
- How many orders were placed in each status?

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated tests use a temporary seeded SQLite database and mocked LLM responses. They cover read-only SQL validation, database execution, and correction behavior without requiring a live API key.

## Security behavior

- SQLGlot parses using SQLite rules and accepts one read-only `SELECT` statement. It rejects malformed or multiple statements, write operations, `SELECT INTO`, locking clauses, and selected SQLite file/extension functions before execution. The same validator runs on initial SQL, corrected SQL, and again immediately before database execution.
- The app opens SQLite with URI `mode=ro` after the database has been seeded.
- Raw user input is checked before schema inspection or SQL generation. A deterministic prefilter blocks destructive SQL, common `OR 1=1` tautologies, SQL comment syntax, and script tags. If `OPENAI_API_KEY` is configured, NeMo Guardrails' `self check input` rail also receives the original user text. The application reports whether NeMo ran or the no-key deterministic fallback was used.
- The deterministic filter is not a substitute described as NeMo inference. Without an API key, NeMo's configuration is initialized and validated, but its model inference is skipped. If NeMo configuration, initialization, or inference fails, the request is blocked (fail closed).
- The app reads API credentials from `.env`; secrets are not embedded in prompts or output.
- Results are capped at 1,000 rows.

The tests mock SQL-generation and NeMo model calls. They verify the actual NeMo configuration can load and its rails can initialize locally; they do not make paid/live API requests.

## Project layout

```text
app.py                    Root Streamlit entry point
app/graph.py               LangGraph nodes and workflow
app/security.py            SQLGlot validation and basic input checks
app/guardrails.py          NeMo adapter and deterministic prefilter
app/streamlit_app.py       Streamlit UI and Plotly rendering
config/guardrails/         NeMo configuration and Colang refusal
database/seed.py           SQLite schema and sample data seeder
tests/                     Graph, security, guardrails, and dashboard tests
.env.example               Environment variable template
requirements.txt           Python dependencies
README.md                  Setup, architecture, and usage documentation
```

## Known limitations

- Live SQL generation and NeMo model inspection require a valid OpenAI API key and network access. Automated tests mock model calls; live NeMo inference has not been verified as part of this project test suite.
- Without a key, the deterministic prefilter blocks the implemented common attack patterns, but it does not provide broad semantic prompt-injection classification. The UI labels this path as the fallback.
- Chart selection is heuristic and relies on meaningful result column names and types; ambiguous date columns may need a recognizable date/time name.
- Results are limited to 1,000 rows. The sample database is SQLite and the seed command rebuilds its `customers`, `orders`, and `sales` tables.
