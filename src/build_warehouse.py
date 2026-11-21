"""Step 5 - Build the star schema (schema 'dw') from the operational tables.

Order: create tables -> DIM_DATE (python) -> DIM_CUSTOMER, DIM_PLAN, FACT (sql/03_load_warehouse.sql)
"""
from __future__ import annotations

import calendar

import pandas as pd

from src.db import execute_sql_file, get_engine


def build_dim_date(engine) -> int:
    with engine.connect() as conn:
        first_start, last_start, last_end = conn.exec_driver_sql(
            "SELECT MIN(start_date), MAX(start_date), MAX(end_date) FROM ops.subscriptions").one()
        last_txn = conn.exec_driver_sql("SELECT MAX(transaction_date) FROM ops.transactions").scalar()
    last = max(d for d in (last_start, last_end, last_txn) if d is not None)
    periods = pd.period_range(pd.Timestamp(first_start), pd.Timestamp(last), freq="M")
    rows = []
    for i, p in enumerate(periods, start=1):
        rows.append(dict(
            month_start_date=p.start_time.date(),
            month_end_date=p.end_time.date(),
            month_number=p.month,
            month_name=calendar.month_name[p.month],
            calendar_quarter=p.quarter,
            calendar_year=p.year,
            year_month=f"{p.year}-{p.month:02d}",
            month_index=i,
        ))
    pd.DataFrame(rows).to_sql("dim_date", engine, schema="dw", if_exists="append", index=False)
    return len(rows)


def run() -> None:
    engine = get_engine()
    execute_sql_file(engine, "02_warehouse_schema.sql")
    print("Warehouse schema 'dw' created.")
    n_months = build_dim_date(engine)
    print(f"  loaded dw.dim_date            {n_months:>8,d} rows")
    execute_sql_file(engine, "03_load_warehouse.sql")
    with engine.connect() as conn:
        for table in ("dim_customer", "dim_plan", "fact_subscription_monthly"):
            n = conn.exec_driver_sql(f"SELECT COUNT(*) FROM dw.{table}").scalar()
            print(f"  loaded dw.{table:26s} {n:>8,d} rows")


if __name__ == "__main__":
    run()
