-- =====================================================================
-- 02_warehouse_schema.sql
-- Star schema, schema "dw".  Grain of the fact table:
--     ONE ROW PER SUBSCRIPTION PER CALENDAR MONTH
-- =====================================================================
DROP SCHEMA IF EXISTS dw CASCADE;
CREATE SCHEMA dw;

CREATE TABLE dw.dim_customer (
    customer_key   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,   -- surrogate key
    customer_id    VARCHAR(20)  NOT NULL UNIQUE,                       -- business key
    customer_name  VARCHAR(100) NOT NULL,
    region         VARCHAR(50)  NOT NULL,
    signup_date    DATE         NOT NULL
);

CREATE TABLE dw.dim_plan (
    plan_key       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id        VARCHAR(10)   NOT NULL UNIQUE,
    plan_name      VARCHAR(50)   NOT NULL,
    monthly_price  NUMERIC(10,2) NOT NULL,
    billing_cycle  VARCHAR(20)   NOT NULL
);

-- DIM_DATE is a MONTH dimension (one row per calendar month)
CREATE TABLE dw.dim_date (
    date_key          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    month_start_date  DATE        NOT NULL UNIQUE,
    month_end_date    DATE        NOT NULL,
    month_number      SMALLINT    NOT NULL,
    month_name        VARCHAR(10) NOT NULL,
    calendar_quarter  SMALLINT    NOT NULL,
    calendar_year     SMALLINT    NOT NULL,
    year_month        VARCHAR(7)  NOT NULL,      -- e.g. 2026-03
    month_index       INTEGER     NOT NULL UNIQUE  -- 1,2,3... handy for cohort arithmetic
);

CREATE TABLE dw.fact_subscription_monthly (
    customer_key     INTEGER       NOT NULL REFERENCES dw.dim_customer (customer_key),
    plan_key         INTEGER       NOT NULL REFERENCES dw.dim_plan (plan_key),
    date_key         INTEGER       NOT NULL REFERENCES dw.dim_date (date_key),
    subscription_id  VARCHAR(20)   NOT NULL,              -- degenerate dimension
    monthly_revenue  NUMERIC(10,2) NOT NULL DEFAULT 0,    -- amount billed in that month
    active_flag      SMALLINT      NOT NULL CHECK (active_flag    IN (0, 1)),  -- active on the last day of month
    churn_flag       SMALLINT      NOT NULL CHECK (churn_flag     IN (0, 1)),  -- cancelled during the month
    new_flag         SMALLINT      NOT NULL CHECK (new_flag       IN (0, 1)),  -- brand-new customer subscription started
    upgrade_flag     SMALLINT      NOT NULL CHECK (upgrade_flag   IN (0, 1)),  -- subscription began as an upgrade
    downgrade_flag   SMALLINT      NOT NULL CHECK (downgrade_flag IN (0, 1)),  -- subscription began as a downgrade
    PRIMARY KEY (subscription_id, date_key)
);
CREATE INDEX ix_fact_date     ON dw.fact_subscription_monthly (date_key);
CREATE INDEX ix_fact_customer ON dw.fact_subscription_monthly (customer_key);
CREATE INDEX ix_fact_plan     ON dw.fact_subscription_monthly (plan_key);
