-- =====================================================================
-- 01_operational_schema.sql
-- Normalized operational (OLTP-style) database, schema "ops".
-- Run order: this file is executed first by src/load_operational.py
-- =====================================================================
DROP SCHEMA IF EXISTS dw CASCADE;
DROP SCHEMA IF EXISTS ops CASCADE;
CREATE SCHEMA ops;

-- Plans: one row per subscription plan (price lives here ONLY -> 2NF/3NF)
CREATE TABLE ops.plans (
    plan_id        VARCHAR(10)   PRIMARY KEY,
    plan_name      VARCHAR(50)   NOT NULL UNIQUE,
    monthly_price  NUMERIC(10,2) NOT NULL CHECK (monthly_price > 0),
    billing_cycle  VARCHAR(20)   NOT NULL CHECK (billing_cycle IN ('Monthly'))
);

-- Customers: one row per customer (region lives here ONLY)
CREATE TABLE ops.customers (
    customer_id    VARCHAR(20)  PRIMARY KEY,
    customer_name  VARCHAR(100) NOT NULL,
    region         VARCHAR(50)  NOT NULL,
    signup_date    DATE         NOT NULL
);

-- Subscriptions: one row per period a customer holds one plan.
-- end_date is the first day WITHOUT service (NULL while still active).
CREATE TABLE ops.subscriptions (
    subscription_id VARCHAR(20) PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL REFERENCES ops.customers (customer_id),
    plan_id         VARCHAR(10) NOT NULL REFERENCES ops.plans (plan_id),
    start_date      DATE        NOT NULL,
    end_date        DATE,
    status          VARCHAR(12) NOT NULL
                    CHECK (status IN ('ACTIVE', 'CANCELLED', 'UPGRADED', 'DOWNGRADED')),
    start_reason    VARCHAR(12) NOT NULL
                    CHECK (start_reason IN ('NEW', 'UPGRADE', 'DOWNGRADE')),
    CONSTRAINT ck_sub_dates CHECK (end_date IS NULL OR end_date > start_date),
    CONSTRAINT ck_sub_status_end CHECK (
        (status = 'ACTIVE' AND end_date IS NULL) OR
        (status <> 'ACTIVE' AND end_date IS NOT NULL))
);
-- Business rule: a customer has at most ONE active subscription at a time.
CREATE UNIQUE INDEX ux_one_active_subscription
    ON ops.subscriptions (customer_id) WHERE status = 'ACTIVE';
CREATE INDEX ix_subscriptions_customer ON ops.subscriptions (customer_id);
CREATE INDEX ix_subscriptions_plan     ON ops.subscriptions (plan_id);

-- Transactions: one row per payment. "amount" is kept on purpose (price history snapshot).
CREATE TABLE ops.transactions (
    transaction_id   VARCHAR(20)   PRIMARY KEY,
    customer_id      VARCHAR(20)   NOT NULL REFERENCES ops.customers (customer_id),
    plan_id          VARCHAR(10)   NOT NULL REFERENCES ops.plans (plan_id),
    transaction_date DATE          NOT NULL,
    amount           NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    transaction_type VARCHAR(12)   NOT NULL
                     CHECK (transaction_type IN ('NEW', 'RENEWAL', 'UPGRADE', 'DOWNGRADE'))
);
CREATE INDEX ix_transactions_customer ON ops.transactions (customer_id);
CREATE INDEX ix_transactions_date     ON ops.transactions (transaction_date);
