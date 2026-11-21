"""Step 4 - Create the normalized PostgreSQL tables (schema 'ops') and load the clean CSVs."""
from __future__ import annotations

import pandas as pd

from src import config
from src.db import execute_sql_file, get_engine

# parent tables first, so foreign keys are always satisfied
LOAD_ORDER = [
    ("plans", "plans", []),
    ("customers", "customers", ["signup_date"]),
    ("subscriptions", "subscription_history", ["start_date", "end_date"]),
    ("transactions", "transactions", ["transaction_date"]),
]


def _to_python_dates(series: pd.Series) -> list:
    parsed = pd.to_datetime(series)
    return [d.date() if pd.notna(d) else None for d in parsed]


def run() -> None:
    engine = get_engine()
    execute_sql_file(engine, "01_operational_schema.sql")
    print("Operational schema 'ops' created.")
    for table, csv_name, date_cols in LOAD_ORDER:
        df = pd.read_csv(config.CLEAN_DIR / f"{csv_name}.csv", dtype=str, keep_default_na=False,
                         na_values=[""])
        for col in date_cols:
            df[col] = _to_python_dates(df[col])
        for col in ("monthly_price", "amount"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
        df.to_sql(table, engine, schema="ops", if_exists="append", index=False,
                  method="multi", chunksize=2000)
        print(f"  loaded ops.{table:14s} {len(df):>8,d} rows")


if __name__ == "__main__":
    run()
