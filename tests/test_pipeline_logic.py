"""Database-free tests of the generator, the ETL cleaning and the metric definitions.
Run with:  pytest -q"""
import pandas as pd
import pytest

from src import config, etl_clean, generate_data, validate


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("proj")
    patch = {"RAW_DIR": root / "raw", "CLEAN_DIR": root / "clean", "REJECT_DIR": root / "rej", "OUTPUT_DIR": root / "out"}
    saved = {k: getattr(config, k) for k in patch}
    for k, v in patch.items():
        setattr(config, k, v)
    truth = generate_data.generate_all(400, 7, config.RAW_DIR, dirty=False)
    generate_data.generate_all(400, 7, config.RAW_DIR, dirty=True)
    report = etl_clean.run()
    yield truth, report
    for k, v in saved.items():
        setattr(config, k, v)


def test_generator_rules(workspace):
    truth, _ = workspace
    h = truth["subscription_history"]
    assert (h[h.status == "ACTIVE"].groupby("customer_id").size() <= 1).all()
    assert (h["end_date"].isna() == (h["status"] == "ACTIVE")).all()
    cancelled = h[h.status == "CANCELLED"]
    assert (pd.to_datetime(cancelled.end_date).dt.to_period("M") > pd.to_datetime(cancelled.start_date).dt.to_period("M")).all()


def test_etl_rejects_bad_rows_and_recovers_truth(workspace):
    truth, report = workspace
    assert all(t["rows_rejected"] > 0 for n, t in report["tables"].items() if n in ("transactions", "subscription_history"))
    clean_txn = pd.read_csv(config.CLEAN_DIR / "transactions.csv")
    assert clean_txn["transaction_id"].is_unique
    assert len(clean_txn) == len(truth["transactions"])
    clean_hist = pd.read_csv(config.CLEAN_DIR / "subscription_history.csv")
    assert len(clean_hist) == len(truth["subscription_history"])
    cust = pd.read_csv(config.CLEAN_DIR / "customers.csv")
    assert set(clean_txn.customer_id) <= set(cust.customer_id)
    assert (cust.region != "").all() and cust.region.notna().all()


def test_rollforward_identity(workspace):
    ref = validate.reference_metrics()
    beginning = ref["ending_subscribers"].shift(1, fill_value=0)
    assert (ref["ending_subscribers"] == beginning + ref["new_subscribers"] - ref["cancelled_subscribers"]).all()


def test_revenue_equals_active_billing(workspace):
    ref = validate.reference_metrics()
    assert (ref["billed_revenue"] > 0).all()
