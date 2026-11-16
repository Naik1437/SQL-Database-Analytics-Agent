# SQL & Database Analytics Agent

A natural-language business analytics application that turns questions into safe SQL, executes queries against SQLite, and displays results in a Streamlit dashboard. The workflow uses LangGraph, SQLAlchemy, SQLGlot, Google Gemini, NeMo Guardrails, Pandas, and Plotly.

## Assessment verification status

- **Live Gemini generation:** Verified with the configured `gemini-3.5-flash-lite` model using the standalone provider diagnostic.
- **End-to-end workflow:** A live Gemini-backed LangGraph query asking how many orders were placed generated a read-only query and returned an order count of **10** from SQLite.
- **Automated tests:** The most recent full run completed with **63 passed** and one NeMo deprecation warning. Automated tests mock Gemini and NeMo model inference; they do not make live model requests.
- **Live NeMo inference:** Not tested. It is disabled by default and is not needed for Gemini SQL generation.

The live Gemini verification is separate from pytest. The tests do not make API calls and do not require a real Google or OpenAI API key.

## Architecture

The LangGraph `StateGraph` tracks `user_query`, `generated_sql`, `db_result`, `error_message`, and `retry_count`. Its workflow:

1. Checks the raw question with deterministic input guardrails and, if explicitly enabled, the NeMo input rail.
2. Inspects the available tables and columns using SQLAlchemy reflection.
3. Asks the configured Gemini chat model to generate one SQLite query.
4. Validates generated SQL with SQLGlot before executing it through a read-only SQLite connection.
5. On a database error, sends the error and reflected schema to the correction step. It allows at most three SQL correction retries.
6. Presents the status, SQL, execution history, result table, and suitable Plotly charts in Streamlit.

Gemini requests have a 30-second timeout and automatic SDK retries are disabled. Gemini 3 models use the supported low thinking level without deprecated sampling parameters. The graph also has a finite recursion limit as a final safeguard.

## Technology and requirements

- Windows 10, 64-bit
- Python 3.11
- LangGraph and LangChain
- `langchain-google-genai` for Gemini SQL generation
- SQLAlchemy and SQLGlot
- NeMo Guardrails
- SQLite, Streamlit, Plotly, and Pandas
- pytest and python-dotenv

`langchain-openai` is retained for the optional OpenAI-backed NeMo inference path only. The normal SQL generation workflow uses Gemini and does not require an OpenAI key.

## Setup (PowerShell)

Run commands from the project directory. Create the virtual environment with Python 3.11:

```powershell
py -3.11 -m venv .venv
```

Install the project dependencies using that environment's interpreter:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If PowerShell allows virtual environment activation, you may activate it with:

```powershell
.\.venv\Scripts\Activate.ps1
```

If activation is blocked by the execution policy, keep using the explicit `.venv\Scripts\python.exe` and `.venv\Scripts\streamlit.exe` commands below. There is no need to change the machine's execution policy.

## Configure Gemini and the database

Create `.env` from the template only if you do not already have a local `.env` file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open the local file to configure the required values:

```powershell
notepad .env
```

Set `GOOGLE_API_KEY` to a Google AI Studio key and `GOOGLE_MODEL` to a model that is currently available to your project on the Gemini API free tier. `gemini-3.5-flash-lite` is the model verified for this project; model availability and quotas can change. Check the model and project tier in AI Studio before use. Do not attach paid billing if your goal is to avoid charges.

Keep these settings in the local `.env` file:

- `GOOGLE_API_KEY`: your private Google AI Studio API key.
- `GOOGLE_MODEL`: the Gemini API model ID to use.
- `DATABASE_URL=sqlite:///database/analytics.db`
- `NEMO_GUARDRAILS_CONFIG=config/guardrails`
- `NEMO_LIVE_INFERENCE=false` for Gemini-only usage.

Never paste an API key into source code, prompts, logs, screenshots, or Git. The `.env` file is excluded by `.gitignore`; share only `.env.example`, which contains placeholders and safe defaults.

### Optional NeMo live inference

Live NeMo model inspection is disabled by default. In the default configuration, the deterministic prefilter blocks the implemented destructive SQL, tautology, SQL-comment, and script-tag patterns before schema inspection or Gemini invocation. NeMo configuration initialization is checked locally, but NeMo does not send an inference request in this default mode.

Setting `NEMO_LIVE_INFERENCE=true` enables the separate OpenAI-backed NeMo `self check input` inference path. It requires a separate `OPENAI_API_KEY` and may incur OpenAI charges. Live NeMo inference has **not** been tested for this project. Do not enable it for Gemini-only use.

## Seed the SQLite database

The seed script creates the sample `customers`, `orders`, and `sales` tables. The `orders` table includes the required `id` and `order_date` columns and retains `order_id` for related sales records. **Running the seed script drops and recreates those sample tables.**

```powershell
.\.venv\Scripts\python.exe -m database.seed
```

The SQLite file is generated locally and is not committed; rerun the seeder to recreate it.

## Run the Streamlit application

The assessment entry point is the root-level `app.py`. With the virtual environment activated, run the assessment command:

```powershell
streamlit run app.py
```

Or launch Streamlit directly from the project virtual environment:

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

The dashboard includes a natural-language query form, a results dataframe, and separate collapsed expanders for generated SQL, execution telemetry, and self-correction history. It suggests interactive Plotly charts when the result has a meaningful category/date and numeric measure. Bar charts support categories; date dimensions can also use line charts; pie charts are offered for categories with a small number of groups. ID-like columns are excluded. Empty, text-only, or unsuitable results are shown without a chart.

Example questions:

- Show orders sorted by date.
- Which product categories generated the most revenue?
- Show monthly sales revenue.
- Who are the top five customers by order value?
- How many orders were placed in each status?

## Run tests

With the virtual environment activated, run:

```powershell
python -m pytest -q
```

Or use the explicit environment interpreter without activation:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite uses temporary SQLite databases and mocked Gemini/NeMo model inference. It covers read-only SQL validation, mutation and multi-statement rejection, raw-input blocking, schema reflection, database execution, retry limits, SQL correction, provider configuration, dashboard chart logic, and timeout/error display. It does not make live Gemini or NeMo inference calls.

## Security behavior

- SQLGlot parses with the SQLite dialect and accepts only one read-only query structure. It rejects malformed SQL, multiple statements, write operations such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, and `ALTER`, `SELECT INTO`, locking clauses, and selected SQLite file/extension functions.
- The same AST validator checks initial and corrected SQL and runs again immediately before database execution. Unsafe SQL is never sent to the database.
- SQLite connections use URI `mode=ro` after the database has been seeded. Results are limited to 1,000 rows.
- Raw user input is checked before schema inspection and SQL generation. The deterministic prefilter decodes common URL/HTML encodings and blocks destructive commands, common tautologies such as `OR 1=1`, SQL comments, and script tags.
- NeMo live `self check input` inference runs only when explicitly enabled and its separate OpenAI key is configured. Otherwise the deterministic fallback is used. Guardrails initialization or enabled-inference failures fail closed.
- Gemini settings are read from `.env`. The local configuration check does not make a network request or display the key. Dashboard errors are sanitized to avoid exposing credentials.

## Project structure

```text
SQL-Database-Analytics-Agent/
├── .env                         Local credentials; ignored by Git
├── .env.example                 Safe environment template
├── .gitignore                   Secret and generated-file exclusions
├── README.md                    Setup, architecture, verification, and usage
├── requirements.txt             Python dependencies
├── app.py                       Root Streamlit assessment entry point
├── app/
│   ├── __init__.py
│   ├── __main__.py               Module entry point
│   ├── gemini_diagnostic.py      Credential-safe Gemini connectivity check
│   ├── graph.py                  LangGraph state, nodes, and workflow
│   ├── guardrails.py             NeMo adapter and deterministic input filter
│   ├── llm_provider.py           Gemini provider configuration and factory
│   ├── security.py               SQLGlot validation and input checks
│   └── streamlit_app.py          Streamlit UI and Plotly visualization
├── config/
│   └── guardrails/
│       ├── config.yml            NeMo Guardrails configuration
│       └── rails.co              Colang refusal response
├── database/
│   ├── __init__.py
│   ├── analytics.db              Generated locally by the seed script; ignored
│   └── seed.py                   SQLite schema and sample-data seeder
└── tests/
    ├── __init__.py
    ├── test_agent.py             Graph, execution, retry, and correction tests
    ├── test_dashboard.py         Chart suitability and rendering tests
    ├── test_gemini_diagnostic.py Safe diagnostic error tests
    ├── test_guardrails.py        Input blocking and table-integrity tests
    ├── test_llm_provider.py      Gemini configuration tests
    ├── test_security.py          SQL AST security tests
    ├── test_seed.py              Seed schema and repeatability tests
    └── test_streamlit_timeout.py Streamlit error-rendering test
```

The virtual environment, Python caches, pytest cache, and local IDE settings are development artifacts and are not part of the application package.

## Known limitations

- Live Gemini generation and an end-to-end LangGraph query were tested with the configured free-tier model; a successful run returned an order count of 10 from SQLite. Availability, quota, network behavior, and free-tier eligibility depend on the Google AI Studio project.
- Automated tests mock Gemini and NeMo inference. They verify workflow behavior without spending API quota; the separate live Gemini verification is not part of pytest.
- Live NeMo inference remains disabled by default and has not been tested. Enabling it requires a separate OpenAI API key and may incur charges.
- The deterministic input filter catches common attack patterns but does not provide broad semantic prompt-injection classification when live NeMo inference is disabled.
- Chart selection is heuristic and depends on meaningful result column names and types. Ambiguous date columns may need a recognizable date/time name.
- The seed script recreates its sample tables; do not point it at a database containing data you need to preserve.
