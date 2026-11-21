"""Step 6 - Run every analytical query and save each result as CSV in outputs/analytics/."""
from __future__ import annotations

import pandas as pd

from src import config
from src.db import get_engine, load_named_queries, run_query


def run() -> dict[str, pd.DataFrame]:
    engine = get_engine()
    out_dir = config.OUTPUT_DIR / "analytics"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, sql in load_named_queries("04_analytics_queries.sql").items():
        df = run_query(engine, sql)
        df.to_csv(out_dir / f"{name}.csv", index=False)
        results[name] = df
        print(f"\n=== {name} ({len(df)} rows) ===")
        print(df.head(8).to_string(index=False))
    print(f"\nCSV results saved in {out_dir}")
    return results


if __name__ == "__main__":
    run()
