"""Database helpers: engine creation, SQL-file execution and named-query loading."""
from __future__ import annotations

import re

import pandas as pd
import psycopg2
from psycopg2 import sql as pg_sql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from src import config


def get_engine(database: str | None = None) -> Engine:
    url = URL.create(
        "postgresql+psycopg2",
        username=config.PG_USER,
        password=config.PG_PASSWORD,
        host=config.PG_HOST,
        port=config.PG_PORT,
        database=database or config.PG_DATABASE,
    )
    return create_engine(url, future=True)


def ensure_database() -> None:
    """Create the project database if it does not exist yet."""
    conn = psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT, user=config.PG_USER,
        password=config.PG_PASSWORD, dbname="postgres",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.PG_DATABASE,))
            if cur.fetchone() is None:
                cur.execute(
                    pg_sql.SQL("CREATE DATABASE {}").format(pg_sql.Identifier(config.PG_DATABASE))
                )
                print(f"Created database '{config.PG_DATABASE}'.")
            else:
                print(f"Database '{config.PG_DATABASE}' already exists.")
    finally:
        conn.close()


def execute_sql_file(engine: Engine, filename: str) -> None:
    """Run a whole .sql file (many statements) in a single transaction.
    NOTE: the SQL files must not contain a percent sign (psycopg2 treats it specially)."""
    text = (config.SQL_DIR / filename).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(text)


def load_named_queries(filename: str) -> dict[str, str]:
    """Parse a .sql file where each query starts with a line '-- name: <query_name>'."""
    text = (config.SQL_DIR / filename).read_text(encoding="utf-8")
    queries: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^--\s*name:\s*(\w+)\s*$", line)
        if match:
            if current:
                queries[current] = "\n".join(buffer).strip().rstrip(";")
            current, buffer = match.group(1), []
        elif current:
            buffer.append(line)
    if current:
        queries[current] = "\n".join(buffer).strip().rstrip(";")
    return queries


def run_query(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)
