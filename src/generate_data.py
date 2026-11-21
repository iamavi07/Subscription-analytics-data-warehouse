"""Step 1 - Generate synthetic subscription data (raw CSV files).

Outputs (data/raw/):
    customers.csv, plans.csv, transactions.csv, subscription_history.csv

The simulation follows these rules (see docs/metric_definitions.md):
  * A customer signs up on a random day and starts one subscription (start_reason = NEW).
  * Every following calendar month the customer may cancel, upgrade or downgrade.
  * Plan changes take effect on the 1st of a month (old subscription closes, new one starts).
  * Cancellations happen on a day between the 2nd and 28th, always in a month AFTER the start month.
  * Billing is calendar-month based, full price, no proration:
        - charged on start_date (NEW / UPGRADE / DOWNGRADE)
        - charged again on the 1st of every following month while still subscribed (RENEWAL)
  * After the clean data is created, a few deliberately bad rows are injected
    (duplicates, orphans, bad dates, missing values) so the ETL step has real work to do.
"""
from __future__ import annotations

import argparse
import calendar
import random
from datetime import date
from pathlib import Path

import pandas as pd

from src import config

PLAN_NAMES = ["Basic", "Standard", "Premium"]  # ascending price order
PLAN_ID = {name: pid for pid, name, _, _ in config.PLANS}
PLAN_PRICE = {name: price for _, name, price, _ in config.PLANS}

CANCEL_P = {"Basic": 0.07, "Standard": 0.045, "Premium": 0.03}     # monthly cancel probability
UPGRADE_P = {"Basic": 0.04, "Standard": 0.025, "Premium": 0.0}
DOWNGRADE_P = {"Basic": 0.0, "Standard": 0.015, "Premium": 0.02}
EARLY_CHURN_MULTIPLIER = 2.0   # cancel risk doubles in the first 2 months after the start month

REGIONS = ["India", "USA", "UK", "UAE", "Singapore"]
REGION_WEIGHTS = [70, 12, 8, 6, 4]


# ---------------------------------------------------------------- date helpers
def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    """First day of the month that is n months after d's month."""
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def month_list(start: date, end: date) -> list[date]:
    months, m = [], month_start(start)
    while m <= end:
        months.append(m)
        m = add_months(m, 1)
    return months


# ---------------------------------------------------------------- simulation
def simulate_customer(rng: random.Random, customer_id: str, signup: date, plan: str, as_of: date) -> list[dict]:
    """Return the chain of subscription records for one customer."""
    cur = dict(customer_id=customer_id, plan=plan, start=signup, end=None,
               status="ACTIVE", start_reason="NEW")
    subs: list[dict] = []
    first_month = month_start(signup)
    m = add_months(first_month, 1)
    while m <= as_of:
        plan = cur["plan"]
        mult = EARLY_CHURN_MULTIPLIER if months_between(first_month, m) <= 2 else 1.0
        p_cancel = CANCEL_P[plan] * mult
        p_up, p_down = UPGRADE_P[plan], DOWNGRADE_P[plan]
        u = rng.random()
        if u < p_cancel:
            cur["end"] = date(m.year, m.month, rng.randint(2, 28))
            cur["status"] = "CANCELLED"
            subs.append(cur)
            return subs
        if u < p_cancel + p_up or u < p_cancel + p_up + p_down:
            idx = PLAN_NAMES.index(plan)
            if u < p_cancel + p_up:
                new_plan, status, reason = rng.choice(PLAN_NAMES[idx + 1:]), "UPGRADED", "UPGRADE"
            else:
                new_plan, status, reason = rng.choice(PLAN_NAMES[:idx]), "DOWNGRADED", "DOWNGRADE"
            cur["end"], cur["status"] = m, status
            subs.append(cur)
            cur = dict(customer_id=customer_id, plan=new_plan, start=m, end=None,
                       status="ACTIVE", start_reason=reason)
        m = add_months(m, 1)
    subs.append(cur)
    return subs


def build_transactions(subs: list[dict], as_of: date) -> list[dict]:
    rows = []
    for s in subs:
        price = PLAN_PRICE[s["plan"]]
        rows.append(dict(customer_id=s["customer_id"], plan_id=PLAN_ID[s["plan"]],
                         transaction_date=s["start"], amount=price, transaction_type=s["start_reason"]))
        m = add_months(month_start(s["start"]), 1)
        while m <= as_of and (s["end"] is None or s["end"] > m):
            rows.append(dict(customer_id=s["customer_id"], plan_id=PLAN_ID[s["plan"]],
                             transaction_date=m, amount=price, transaction_type="RENEWAL"))
            m = add_months(m, 1)
    return rows


def generate_clean(n_customers: int, seed: int, start: date, as_of: date) -> dict[str, pd.DataFrame]:
    assert as_of.day == calendar.monthrange(as_of.year, as_of.month)[1], "as_of must be a month-end"
    rng = random.Random(seed)
    months = month_list(start, as_of)
    weights = [1 + 0.06 * i for i in range(len(months))]  # sign-ups grow over time

    customers, all_subs = [], []
    for i in range(1, n_customers + 1):
        cid = f"C{i:05d}"
        month = rng.choices(months, weights)[0]
        signup = date(month.year, month.month, rng.randint(1, calendar.monthrange(month.year, month.month)[1]))
        customers.append(dict(customer_id=cid, customer_name=f"User {i:05d}",
                              region=rng.choices(REGIONS, REGION_WEIGHTS)[0], signup_date=signup))
        first_plan = rng.choices(PLAN_NAMES, [45, 35, 20])[0]
        all_subs.extend(simulate_customer(rng, cid, signup, first_plan, as_of))

    for n, s in enumerate(all_subs, start=1):
        s["subscription_id"] = f"S{n:05d}"
    history = pd.DataFrame([dict(subscription_id=s["subscription_id"], customer_id=s["customer_id"],
                                 plan_id=PLAN_ID[s["plan"]], start_date=s["start"], end_date=s["end"],
                                 status=s["status"], start_reason=s["start_reason"]) for s in all_subs])

    txn = pd.DataFrame(build_transactions(all_subs, as_of))
    txn = txn.sort_values(["transaction_date", "customer_id"]).reset_index(drop=True)
    txn.insert(0, "transaction_id", [f"T{n:06d}" for n in range(1, len(txn) + 1)])

    plans = pd.DataFrame(config.PLANS, columns=["plan_id", "plan_name", "monthly_price", "billing_cycle"])
    return dict(customers=pd.DataFrame(customers), plans=plans, transactions=txn, subscription_history=history)


# ---------------------------------------------------------------- dirty data
def inject_quality_issues(data: dict[str, pd.DataFrame], seed: int) -> dict[str, pd.DataFrame]:
    """Add realistic bad rows. Every bad row is an EXTRA row (or a harmless formatting
    change), so a correct ETL recovers exactly the original clean data."""
    rng = random.Random(seed + 1)
    cust, txn, hist = (data[k].copy() for k in ("customers", "transactions", "subscription_history"))
    n = len(cust)
    k = max(5, n // 500)

    # customers: blank / badly formatted region (cleaned, not rejected)
    cust["region"] = cust["region"].astype(object)
    for idx in rng.sample(range(n), max(3, int(n * 0.02))):
        cust.at[idx, "region"] = ""
    for idx in rng.sample(range(n), max(3, int(n * 0.015))):
        cust.at[idx, "region"] = f"  {str(cust.at[idx, 'region']).lower()} "

    ts = pd.to_datetime(txn["transaction_date"])
    template = txn.iloc[len(txn) // 2]
    extras = []
    for j in range(k):  # orphan customers / plans
        extras.append(dict(transaction_id=f"T9{j:05d}", customer_id=f"C9{j:04d}", plan_id=template["plan_id"],
                           transaction_date=template["transaction_date"], amount=template["amount"],
                           transaction_type="NEW"))
    for j in range(k):
        extras.append(dict(transaction_id=f"T91{j:04d}", customer_id=template["customer_id"], plan_id="P999",
                           transaction_date=template["transaction_date"], amount=199, transaction_type="NEW"))
    for j in range(k):  # missing amount
        extras.append(dict(transaction_id=f"T92{j:04d}", customer_id=template["customer_id"],
                           plan_id=template["plan_id"], transaction_date=template["transaction_date"],
                           amount=None, transaction_type="RENEWAL"))
    for j in range(k):  # negative amount
        extras.append(dict(transaction_id=f"T93{j:04d}", customer_id=template["customer_id"],
                           plan_id=template["plan_id"], transaction_date=template["transaction_date"],
                           amount=-199, transaction_type="RENEWAL"))
    dups = txn.sample(n=max(5, int(len(txn) * 0.004)), random_state=seed)  # exact duplicate rows
    txn = pd.concat([txn, pd.DataFrame(extras), dups], ignore_index=True)
    txn = txn.sample(frac=1, random_state=seed).reset_index(drop=True)
    del ts

    bad_hist = []
    for j in range(k):  # end date before start date
        c = cust.at[rng.randrange(n), "customer_id"]
        st = date(2026, 3, rng.randint(5, 25))
        bad_hist.append(dict(subscription_id=f"S9{j:04d}", customer_id=c, plan_id="P001", start_date=st,
                             end_date=date(2026, 2, rng.randint(1, 20)), status="CANCELLED", start_reason="NEW"))
    for j in range(max(3, k // 2)):  # missing customer_id
        bad_hist.append(dict(subscription_id=f"S98{j:03d}", customer_id=None, plan_id="P002",
                             start_date=date(2026, 4, 10), end_date=None, status="ACTIVE", start_reason="NEW"))
    hist = pd.concat([hist, pd.DataFrame(bad_hist)], ignore_index=True)
    return dict(customers=cust, plans=data["plans"], transactions=txn, subscription_history=hist)


# ---------------------------------------------------------------- entry points
def generate_all(n_customers: int, seed: int, out_dir: Path | None = None, dirty: bool = True) -> dict[str, pd.DataFrame]:
    data = generate_clean(n_customers, seed, config.DATA_START, config.AS_OF_DATE)
    if dirty:
        data = inject_quality_issues(data, seed)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, df in data.items():
            df.to_csv(out_dir / f"{name}.csv", index=False)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate raw subscription CSV files")
    parser.add_argument("--customers", type=int, default=config.N_CUSTOMERS)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument("--clean-only", action="store_true", help="do not inject bad rows")
    args = parser.parse_args()
    data = generate_all(args.customers, args.seed, config.RAW_DIR, dirty=not args.clean_only)
    print(f"Raw files written to {config.RAW_DIR}")
    for name, df in data.items():
        print(f"  {name:22s} {len(df):>8,d} rows")


if __name__ == "__main__":
    main()
