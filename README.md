# Subscription Analytics Data Warehouse (Python + PostgreSQL + SQL)

A fictional streaming platform (Basic 199, Standard 399, Premium 599 INR per month).
The project generates raw subscription data, cleans it with Python/Pandas, loads a **normalized PostgreSQL database**,
builds a **star schema** (1 fact + 3 dimensions), answers business questions with **analytical SQL**, validates the
results and shows them in a **Streamlit dashboard**.

```
CSV files (Python) -> Pandas ETL -> PostgreSQL ops schema (normalized) -> dw schema (star) -> SQL analytics -> Streamlit
```

## 1. What you need to install (Windows)

| Software | Needed for | Notes |
|---|---|---|
| **Python 3.10 or newer** (python.org) | everything | During install tick **"Add python.exe to PATH"**. |
| **PostgreSQL 14 or newer** (postgresql.org / EDB installer) | operational DB + warehouse | Remember the password you set for user `postgres`. Keep port **5432**. pgAdmin is included. |
| Python packages | see `requirements.txt` | Installed with one `pip` command (below): pandas, SQLAlchemy, psycopg2-binary, python-dotenv, streamlit, plotly, pytest. |
| Optional: VS Code, Git/GitHub | editing / publishing | Not required to run. |
| Optional: Power BI Desktop | alternative to Streamlit | Connect to the `dw` schema in PostgreSQL. |

You do **not** need to create the database by hand; the pipeline creates `subscription_dwh` for you.

## 2. One-time setup (PowerShell, inside this folder)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env              # then open .env and set PG_PASSWORD
```

## 3. Run

```powershell
python run_pipeline.py              # generate -> ETL -> load -> warehouse -> analytics -> validate
streamlit run dashboard/app.py      # dashboard at http://localhost:8501
pytest -q                           # database-free unit tests (optional)
```

Useful options: `python run_pipeline.py --customers 2000`, `python run_pipeline.py --skip-generate`.
You can also run each step on its own:

```powershell
python -m src.generate_data
python -m src.etl_clean
python -m src.load_operational
python -m src.build_warehouse
python -m src.run_analytics
python -m src.validate
```

## 4. What you get

| Output | Location |
|---|---|
| Raw CSV files (with deliberate data-quality problems) | `data/raw/` |
| Clean CSV files / rejected rows with reasons | `data/clean/`, `data/rejects/` |
| ETL report (row counts and reject reasons) | `outputs/etl_report.json` |
| Result of every analytical query as CSV | `outputs/analytics/` |
| Validation results | `outputs/validation_report.md` |
| PostgreSQL schemas `ops` and `dw` | database `subscription_dwh` |

## 5. Project layout

```
subscription-dwh/
|-- run_pipeline.py            run everything
|-- requirements.txt  .env.example  .gitignore
|-- src/
|   |-- config.py              settings (.env), folders, plans, date range
|   |-- db.py                  connection, run .sql files, named queries
|   |-- generate_data.py       step 1: synthetic data + injected bad rows
|   |-- etl_clean.py           steps 2-3: mandatory columns, duplicates, FK checks, date checks, rejects
|   |-- load_operational.py    step 4: create/load normalized tables (schema ops)
|   |-- build_warehouse.py     step 5: dim_date + run sql/03 (dimensions, then fact)
|   |-- run_analytics.py       step 6: run all analytical queries, save CSV
|   `-- validate.py            step 7: SQL checks + pandas re-computation
|-- sql/
|   |-- 01_operational_schema.sql   normalized tables, PK/FK/CHECK, indexes
|   |-- 02_warehouse_schema.sql     star schema DDL
|   |-- 03_load_warehouse.sql       populate dimensions, then the fact table
|   |-- 04_analytics_queries.sql    MRR, active, new, churn, retention, revenue by plan ...
|   `-- 05_validation_checks.sql    orphan keys, duplicates, reconciliation, roll-forward
|-- dashboard/app.py           Streamlit dashboard
|-- tests/                     pytest tests (no database needed)
`-- docs/
    |-- schema.md              normalization (1NF-3NF), ER diagrams, star schema
    `-- metric_definitions.md  every metric and every modelling assumption
```

## 6. Business questions and the query that answers them

| Question | Query name (`sql/04_analytics_queries.sql`) |
|---|---|
| How many customers have active subscriptions? | `active_subscribers_monthly`, `active_by_plan_region_latest` |
| Recurring revenue per month? | `revenue_monthly` |
| How many customers cancel? / churn rate | `subscriber_rollforward`, `churn_customer_vs_subscription` |
| Which plan earns the most? | `revenue_by_plan_total`, `revenue_by_plan_monthly` |
| New customers per month? | `new_customers_monthly` |
| How many remain subscribed over time? | `cohort_retention` |
| Which months have the most cancellations? | `top_cancellation_months` |

## 7. Key design decisions (read `docs/metric_definitions.md` for details)

* Simplified billing: full price per calendar month, no proration; plan changes on the 1st; cancellations mid-month with no refund.
* Churn rate = cancellations in the month / active subscribers at the end of the previous month.
* Validation proves `ending = beginning + new - cancelled` for every month and reconciles warehouse revenue to the raw transactions.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `password authentication failed` / cannot connect | Check `PG_PASSWORD`, `PG_USER`, `PG_PORT` in `.env`; make sure the PostgreSQL service is running (Services app). |
| `psycopg2` install error | Use `psycopg2-binary` (already in requirements) and a 64-bit Python 3.10-3.12. |
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope Process Bypass` in that PowerShell window. |
| Dashboard shows "Could not read the warehouse" | Run `python run_pipeline.py` first. |
