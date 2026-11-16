# SQL & Database Analytics Agent

A natural-language analytics application built with LangGraph, LangChain, SQLAlchemy, SQLGlot, NeMo Guardrails, SQLite, Streamlit, Pandas, and Plotly. The agent reflects the database schema, generates and validates SQL using Google Gemini, executes it read-only, and can use database errors to correct a query up to three times.

## Architecture and technologies

The LangGraph `StateGraph` keeps the user question, generated SQL, query results, error, and correction retry count. Before schema inspection, the raw question passes through the deterministic safety filter. Live NeMo input-model inspection is a separate, explicit opt-in; its deterministic safety checks remain active without it. The workflow reflects the SQLite schema with SQLAlchemy, asks the configured Gemini chat model for one query, validates it with SQLGlot, and executes it through a read-only SQLite connection. A database error is passed with the reflected schema to the correction step, which may retry up to three times. Streamlit presents the result table, SQL, logs, correction history, and suitable Plotly charts.

Technologies: Python 3.11, LangGraph, LangChain, `langchain-google-genai`, SQLAlchemy, SQLGlot, NeMo Guardrails, SQLite, Streamlit, Plotly, Pandas, pytest, and python-dotenv. `langchain-openai` is retained only for the optional live NeMo inference integration; SQL generation uses Gemini.

## Requirements

- Windows 10 64-bit
- Python 3.11
- A Google AI Studio API key and a model currently eligible for the Gemini API free tier

## Setup (PowerShell)

From the project directory, create a virtual environment and install the dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create `.env` only if one does not already exist, then edit it to add your Gemini settings. Do not overwrite an existing `.env` because it may contain local credentials:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `GOOGLE_API_KEY` to your Google AI Studio key and `GOOGLE_MODEL` to a model ID shown as free for your project in AI Studio. Free-tier eligibility, quotas, and available model IDs can change, so verify the model in AI Studio and Google's current pricing page. Keep the project on the free tier and do not link a paid billing account if you want to avoid charges. Also set `DATABASE_URL=sqlite:///database/analytics.db` and `NEMO_GUARDRAILS_CONFIG=config/guardrails` as shown in `.env.example`. Keep `NEMO_LIVE_INFERENCE=false` for Gemini-only use. Keep `.env` private; it is excluded by `.gitignore`.

No OpenAI key is required for SQL generation. Live NeMo model inspection is separate and disabled by default. Setting `NEMO_LIVE_INFERENCE=true` opts into the existing OpenAI-backed NeMo model path and requires its own `OPENAI_API_KEY`; that mode can incur OpenAI charges. The deterministic input filter and NeMo configuration remain enabled while live NeMo model calls are off.

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

The automated tests use temporary SQLite databases and mocked model responses. They cover read-only SQL validation, provider configuration, database execution, and correction behavior without Google or OpenAI credentials and without paid API calls.

## Security behavior

- SQLGlot parses using SQLite rules and accepts one read-only `SELECT` statement. It rejects malformed or multiple statements, write operations, `SELECT INTO`, locking clauses, and selected SQLite file/extension functions before execution. The same validator runs on initial SQL, corrected SQL, and again immediately before database execution.
- The app opens SQLite with URI `mode=ro` after the database has been seeded.
- Raw user input is checked before schema inspection or SQL generation. A deterministic prefilter blocks destructive SQL, common `OR 1=1` tautologies, SQL comment syntax, and script tags. Live NeMo `self check input` inference runs only when `NEMO_LIVE_INFERENCE=true` and a separate `OPENAI_API_KEY` is configured; otherwise only the deterministic fallback runs. If NeMo configuration, initialization, or opted-in inference fails, the request is blocked (fail closed).
- Gemini SQL generation reads `GOOGLE_API_KEY` and `GOOGLE_MODEL` from `.env`. A local provider check confirms both are set without making a network call or displaying the key.
- API credentials are not written to prompts or logs. The `.env` file is excluded by `.gitignore`.
- Results are capped at 1,000 rows.

The tests mock Gemini and NeMo model calls. They verify the NeMo configuration can load and initialize locally; they do not make live Gemini or NeMo inference calls.

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

- Live SQL generation requires a valid Gemini API key, an eligible model, network access, and available free-tier quota. Automated tests mock the model; a live Gemini request has not been verified.
- Live NeMo model inspection remains a separate optional OpenAI-backed integration. It is disabled unless `NEMO_LIVE_INFERENCE=true`; that mode has not been exercised live and may incur charges.
- Without a key, the deterministic prefilter blocks the implemented common attack patterns, but it does not provide broad semantic prompt-injection classification. The UI labels this path as the fallback.
- Chart selection is heuristic and relies on meaningful result column names and types; ambiguous date columns may need a recognizable date/time name.
- Results are limited to 1,000 rows. The sample database is SQLite and the seed command rebuilds its `customers`, `orders`, and `sales` tables.
