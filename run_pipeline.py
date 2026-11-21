"""Run the whole project end to end:

    python run_pipeline.py                 # everything
    python run_pipeline.py --skip-generate # re-use the CSVs already in data/raw
    python run_pipeline.py --customers 2000
"""
import argparse
import sys

from src import config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--customers", type=int, default=config.N_CUSTOMERS)
    args = parser.parse_args()

    from src import build_warehouse, etl_clean, generate_data, load_operational, run_analytics, validate
    from src.db import ensure_database

    def step(title, fn):
        print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
        return fn()

    try:
        if not args.skip_generate:
            step("1. Generate raw CSV data", lambda: generate_data.generate_all(
                args.customers, config.RANDOM_SEED, config.RAW_DIR) and None)
        step("2-3. ETL: validate, clean, transform", etl_clean.run)
        step("4a. Create PostgreSQL database", ensure_database)
        step("4b. Load normalized operational tables", load_operational.run)
        step("5. Build star schema (dimensions + fact)", build_warehouse.run)
        step("6. Analytical SQL", run_analytics.run)
        ok = step("7. Validation", validate.run)
    except Exception as exc:  # friendly hint for the most common problem
        name = type(exc).__name__
        if "OperationalError" in name:
            print(f"\nCould not connect to PostgreSQL ({name}). Check that the PostgreSQL service is running "
                  "and that PG_HOST / PG_PORT / PG_USER / PG_PASSWORD in your .env file are correct.\n")
            print(exc)
            return 2
        raise
    print("\nDone. Results: outputs/ folder.  Dashboard: streamlit run dashboard/app.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
