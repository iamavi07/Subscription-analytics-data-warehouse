"""Central configuration. Values can be overridden in the .env file."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---- folders -------------------------------------------------------------
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
REJECT_DIR = ROOT / "data" / "rejects"
OUTPUT_DIR = ROOT / "outputs"
SQL_DIR = ROOT / "sql"

# ---- PostgreSQL ----------------------------------------------------------
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DATABASE = os.getenv("PG_DATABASE", "subscription_dwh")

# ---- synthetic data settings --------------------------------------------
N_CUSTOMERS = int(os.getenv("N_CUSTOMERS", "5000"))
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))
DATA_START = date(2025, 1, 1)
AS_OF_DATE = date(2026, 10, 31)  # must be a month-end; data is generated up to this day

PLANS = [
    # plan_id, plan_name, monthly_price (INR), billing_cycle
    ("P001", "Basic", 199, "Monthly"),
    ("P002", "Standard", 399, "Monthly"),
    ("P003", "Premium", 599, "Monthly"),
]
