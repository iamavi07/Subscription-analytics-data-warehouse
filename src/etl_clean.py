"""Step 2/3 - Extract, validate, clean and transform the raw CSV files.

Reads  data/raw/*.csv
Writes data/clean/*.csv            (validated rows, ISO dates, standard formats)
       data/rejects/*_rejected.csv (every removed row with a reject_reason)
       outputs/etl_report.json     (row counts and reasons)
"""
from __future__ import annotations

import json

import pandas as pd

from src import config

REQUIRED = {
    "customers": ["customer_id", "customer_name", "region", "signup_date"],
    "plans": ["plan_id", "plan_name", "monthly_price", "billing_cycle"],
    "transactions": ["transaction_id", "customer_id", "plan_id", "transaction_date", "amount", "transaction_type"],
    "subscription_history": ["subscription_id", "customer_id", "plan_id", "start_date", "end_date",
                             "status", "start_reason"],
}
NULL_TOKENS = ["", "NULL", "null", "Null", "NaN", "nan", "None", "N/A", "NA"]
REGION_MAP = {"india": "India", "usa": "USA", "us": "USA", "uk": "UK", "uae": "UAE", "singapore": "Singapore"}
STATUSES = {"ACTIVE", "CANCELLED", "UPGRADED", "DOWNGRADED"}
START_REASONS = {"NEW", "UPGRADE", "DOWNGRADE"}
TXN_TYPES = {"NEW", "RENEWAL", "UPGRADE", "DOWNGRADE"}


class Rejects:
    """Collects rejected rows together with the reason they were removed."""

    def __init__(self) -> None:
        self.parts: list[pd.DataFrame] = []
        self.reasons: dict[str, int] = {}

    def drop(self, df: pd.DataFrame, bad: pd.Series, reason: str) -> pd.DataFrame:
        bad = bad.fillna(False).astype(bool)
        if bad.any():
            self.parts.append(df[bad].assign(reject_reason=reason).astype(str))
            self.reasons[reason] = self.reasons.get(reason, 0) + int(bad.sum())
        return df[~bad].copy()

    def frame(self) -> pd.DataFrame:
        return pd.concat(self.parts, ignore_index=True) if self.parts else pd.DataFrame()


def read_raw(name: str) -> pd.DataFrame:
    path = config.RAW_DIR / f"{name}.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=NULL_TOKENS)
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:  # mandatory-column check
        raise ValueError(f"{path.name}: missing mandatory column(s) {missing}")
    df = df[REQUIRED[name]].copy()
    for col in df.columns:
        df[col] = df[col].str.strip()
    return df


def _parse_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")


# ------------------------------------------------------------------ per-table cleaning
def clean_plans(df: pd.DataFrame, rej: Rejects) -> pd.DataFrame:
    df = rej.drop(df, df[["plan_id", "plan_name", "monthly_price"]].isna().any(axis=1), "missing mandatory value")
    df["monthly_price"] = pd.to_numeric(df["monthly_price"], errors="coerce")
    df = rej.drop(df, df["monthly_price"].isna() | (df["monthly_price"] <= 0), "invalid monthly_price")
    df["billing_cycle"] = df["billing_cycle"].fillna("Monthly").str.title()
    df = rej.drop(df, df.duplicated("plan_id"), "duplicate plan_id")
    return df.sort_values("plan_id").reset_index(drop=True)


def clean_customers(df: pd.DataFrame, rej: Rejects, fixes: dict) -> pd.DataFrame:
    df = rej.drop(df, df[["customer_id", "signup_date"]].isna().any(axis=1), "missing mandatory value")
    df["signup_date"] = _parse_date(df["signup_date"])
    df = rej.drop(df, df["signup_date"].isna(), "invalid signup_date")
    df = rej.drop(df, df.duplicated("customer_id"), "duplicate customer_id")
    before = df["region"].copy()
    key = df["region"].fillna("").str.strip().str.lower()
    df["region"] = key.map(lambda k: REGION_MAP.get(k, k.title() if k else "Unknown"))
    fixes["region_blank_set_to_Unknown"] = int((key == "").sum())
    fixes["region_standardised"] = int(((key != "") & (before.fillna("") != df["region"])).sum())
    df["customer_name"] = df["customer_name"].fillna("Unknown")
    return df.sort_values("customer_id").reset_index(drop=True)


def clean_history(df: pd.DataFrame, rej: Rejects, customers: pd.DataFrame, plans: pd.DataFrame) -> pd.DataFrame:
    mandatory = ["subscription_id", "customer_id", "plan_id", "start_date", "status", "start_reason"]
    df = rej.drop(df, df[mandatory].isna().any(axis=1), "missing mandatory value")
    df["status"], df["start_reason"] = df["status"].str.upper(), df["start_reason"].str.upper()
    df = rej.drop(df, ~df["status"].isin(STATUSES), "invalid status")
    df = rej.drop(df, ~df["start_reason"].isin(START_REASONS), "invalid start_reason")
    end_raw = df["end_date"]
    df["start_date"], df["end_date"] = _parse_date(df["start_date"]), _parse_date(df["end_date"])
    df = rej.drop(df, df["start_date"].isna() | (end_raw.notna() & df["end_date"].isna()), "invalid date format")
    df = rej.drop(df, df.duplicated("subscription_id"), "duplicate subscription_id")
    df = rej.drop(df, ~df["customer_id"].isin(customers["customer_id"]), "customer_id not in customers")
    df = rej.drop(df, ~df["plan_id"].isin(plans["plan_id"]), "plan_id not in plans")
    df = rej.drop(df, df["end_date"].notna() & (df["end_date"] <= df["start_date"]), "end_date not after start_date")
    active = df["status"] == "ACTIVE"
    df = rej.drop(df, (active & df["end_date"].notna()) | (~active & df["end_date"].isna()),
                  "status inconsistent with end_date")
    signup = df["customer_id"].map(customers.set_index("customer_id")["signup_date"])
    df = rej.drop(df, df["start_date"] < signup, "subscription starts before customer signup")
    return df.sort_values("subscription_id").reset_index(drop=True)


def clean_transactions(df: pd.DataFrame, rej: Rejects, customers: pd.DataFrame, plans: pd.DataFrame) -> pd.DataFrame:
    df = rej.drop(df, df.isna().any(axis=1), "missing mandatory value")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["transaction_date"] = _parse_date(df["transaction_date"])
    df = rej.drop(df, df["amount"].isna() | df["transaction_date"].isna(), "invalid amount or date")
    df = rej.drop(df, df["amount"] <= 0, "amount must be positive")
    df["transaction_type"] = df["transaction_type"].str.upper()
    df = rej.drop(df, ~df["transaction_type"].isin(TXN_TYPES), "invalid transaction_type")
    df = rej.drop(df, df.duplicated("transaction_id", keep="first"), "duplicate transaction_id")
    df = rej.drop(df, ~df["customer_id"].isin(customers["customer_id"]), "customer_id not in customers")
    df = rej.drop(df, ~df["plan_id"].isin(plans["plan_id"]), "plan_id not in plans")
    price = df["plan_id"].map(plans.set_index("plan_id")["monthly_price"])
    df = rej.drop(df, (df["amount"] - price).abs() > 0.005, "amount differs from plan price")
    return df.sort_values("transaction_id").reset_index(drop=True)


# ------------------------------------------------------------------ driver
def _write(df: pd.DataFrame, name: str, date_cols: list[str]) -> None:
    out = df.copy()
    for c in date_cols:
        out[c] = out[c].dt.strftime("%Y-%m-%d")
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(config.CLEAN_DIR / f"{name}.csv", index=False)


def run() -> dict:
    config.REJECT_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = {name: read_raw(name) for name in REQUIRED}
    rej = {name: Rejects() for name in REQUIRED}
    fixes: dict = {}

    plans = clean_plans(raw["plans"], rej["plans"])
    customers = clean_customers(raw["customers"], rej["customers"], fixes)
    history = clean_history(raw["subscription_history"], rej["subscription_history"], customers, plans)
    txns = clean_transactions(raw["transactions"], rej["transactions"], customers, plans)
    clean = {"plans": plans, "customers": customers, "subscription_history": history, "transactions": txns}

    _write(plans, "plans", [])
    _write(customers, "customers", ["signup_date"])
    _write(history, "subscription_history", ["start_date", "end_date"])
    _write(txns, "transactions", ["transaction_date"])

    report = {"fixes": fixes, "tables": {}}
    for name in REQUIRED:
        frame = rej[name].frame()
        if len(frame):
            frame.to_csv(config.REJECT_DIR / f"{name}_rejected.csv", index=False)
        else:
            (config.REJECT_DIR / f"{name}_rejected.csv").unlink(missing_ok=True)
        report["tables"][name] = {"rows_in": len(raw[name]), "rows_clean": len(clean[name]),
                                  "rows_rejected": int(sum(rej[name].reasons.values())),
                                  "reject_reasons": rej[name].reasons}
    (config.OUTPUT_DIR / "etl_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("ETL summary (rows in -> clean / rejected)")
    for name, t in report["tables"].items():
        print(f"  {name:22s} {t['rows_in']:>8,d} -> {t['rows_clean']:>8,d} / {t['rows_rejected']:>4d}")
        for reason, count in t["reject_reasons"].items():
            print(f"      - {reason}: {count}")
    print(f"  fixes applied: {fixes}")
    return report


if __name__ == "__main__":
    run()
