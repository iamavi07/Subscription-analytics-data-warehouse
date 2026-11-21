"""Step 7 - Test and validate.

1. SQL checks (sql/05_validation_checks.sql): each must return 0 problems.
2. Independent re-computation in pandas from the CLEAN CSV files, compared with the
   numbers the warehouse produces (raw data vs warehouse consistency).
3. Row-count reconciliation CSV -> ops tables.
Writes outputs/validation_report.md and returns True when everything passes.
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.db import get_engine, load_named_queries, run_query


def reference_metrics() -> pd.DataFrame:
    """Compute monthly metrics straight from the clean CSVs (no database involved)."""
    h = pd.read_csv(config.CLEAN_DIR / "subscription_history.csv", parse_dates=["start_date", "end_date"])
    t = pd.read_csv(config.CLEAN_DIR / "transactions.csv", parse_dates=["transaction_date"])
    last = max(t["transaction_date"].max(), h["start_date"].max(), h["end_date"].max())
    rows = []
    for p in pd.period_range(h["start_date"].min(), last, freq="M"):
        ms, me = p.start_time.normalize(), p.end_time.normalize()
        in_month = lambda s: (s >= ms) & (s <= me)  # noqa: E731
        rows.append(dict(
            year_month=str(p),
            ending_subscribers=int(((h.start_date <= me) & (h.end_date.isna() | (h.end_date > me))).sum()),
            new_subscribers=int(((h.start_reason == "NEW") & in_month(h.start_date)).sum()),
            cancelled_subscribers=int(((h.status == "CANCELLED") & in_month(h.end_date)).sum()),
            billed_revenue=float(t.loc[in_month(t.transaction_date), "amount"].sum()),
        ))
    return pd.DataFrame(rows)


def run() -> bool:
    engine = get_engine()
    results: list[tuple[str, bool, str]] = []

    for name, sql in load_named_queries("05_validation_checks.sql").items():
        problems = int(run_query(engine, sql).iloc[0, 0])
        results.append((name, problems == 0, f"{problems} problem(s)"))

    q = load_named_queries("04_analytics_queries.sql")
    wh = run_query(engine, q["subscriber_rollforward"]).merge(
        run_query(engine, q["revenue_monthly"])[["year_month", "billed_revenue"]], on="year_month")
    ref = reference_metrics()
    merged = ref.merge(wh, on="year_month", suffixes=("_ref", "_wh"), how="outer", indicator=True)
    results.append(("months_match_between_pandas_and_warehouse", bool((merged["_merge"] == "both").all()),
                    f"{len(ref)} months in pandas vs {len(wh)} in warehouse"))
    for col in ("ending_subscribers", "new_subscribers", "cancelled_subscribers", "billed_revenue"):
        diff = (merged[f"{col}_ref"].astype(float) - merged[f"{col}_wh"].astype(float)).abs().fillna(1).max()
        results.append((f"pandas_vs_warehouse_{col}", bool(diff < 0.005), f"max abs difference = {diff:g}"))

    with engine.connect() as conn:
        for table, csv_name in (("customers", "customers"), ("subscriptions", "subscription_history"),
                                ("transactions", "transactions"), ("plans", "plans")):
            in_db = conn.exec_driver_sql(f"SELECT COUNT(*) FROM ops.{table}").scalar()
            in_csv = len(pd.read_csv(config.CLEAN_DIR / f"{csv_name}.csv"))
            results.append((f"row_count_ops_{table}_equals_clean_csv", in_db == in_csv, f"db={in_db}, csv={in_csv}"))

    lines = ["# Validation report", "", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {'PASS' if ok else 'FAIL'} | {d} |" for n, ok, d in results]
    all_ok = all(ok for _, ok, _ in results)
    lines += ["", f"**Overall: {'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}**"]
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT_DIR / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")

    for n, ok, d in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {n}: {d}")
    print("\nOverall:", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    return all_ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
