-- =====================================================================
-- 03_load_warehouse.sql
-- Populate dimensions first, then the fact table (dim_date is filled by
-- src/build_warehouse.py before this file runs).
-- =====================================================================
INSERT INTO dw.dim_customer (customer_id, customer_name, region, signup_date)
SELECT customer_id, customer_name, region, signup_date
FROM ops.customers
ORDER BY customer_id;

INSERT INTO dw.dim_plan (plan_id, plan_name, monthly_price, billing_cycle)
SELECT plan_id, plan_name, monthly_price, billing_cycle
FROM ops.plans
ORDER BY plan_id;

-- Fact table: a subscription gets a row for every month it is "relevant":
--   it started on/before the month end AND it still existed after the month start
--   (a subscription closed on the 1st by a plan change belongs to the previous month only;
--    a cancellation exactly on the 1st still gets its churn row).
INSERT INTO dw.fact_subscription_monthly
    (customer_key, plan_key, date_key, subscription_id,
     monthly_revenue, active_flag, churn_flag, new_flag, upgrade_flag, downgrade_flag)
SELECT
    dc.customer_key,
    dp.plan_key,
    dd.date_key,
    s.subscription_id,
    -- billed in the start month, and in every later month in which it is still running on the 1st
    CASE WHEN s.start_date >= dd.month_start_date
              OR s.end_date IS NULL
              OR s.end_date > dd.month_start_date
         THEN dp.monthly_price ELSE 0 END AS monthly_revenue,
    -- active on the last day of the month
    CASE WHEN s.start_date <= dd.month_end_date
              AND (s.end_date IS NULL OR s.end_date > dd.month_end_date)
         THEN 1 ELSE 0 END AS active_flag,
    CASE WHEN s.status = 'CANCELLED'
              AND s.end_date >= dd.month_start_date
              AND s.end_date <= dd.month_end_date
         THEN 1 ELSE 0 END AS churn_flag,
    CASE WHEN s.start_reason = 'NEW'
              AND s.start_date >= dd.month_start_date
              AND s.start_date <= dd.month_end_date
         THEN 1 ELSE 0 END AS new_flag,
    CASE WHEN s.start_reason = 'UPGRADE'
              AND s.start_date >= dd.month_start_date
              AND s.start_date <= dd.month_end_date
         THEN 1 ELSE 0 END AS upgrade_flag,
    CASE WHEN s.start_reason = 'DOWNGRADE'
              AND s.start_date >= dd.month_start_date
              AND s.start_date <= dd.month_end_date
         THEN 1 ELSE 0 END AS downgrade_flag
FROM ops.subscriptions s
JOIN dw.dim_customer dc ON dc.customer_id = s.customer_id
JOIN dw.dim_plan     dp ON dp.plan_id     = s.plan_id
JOIN dw.dim_date     dd ON s.start_date <= dd.month_end_date
                       AND (s.end_date IS NULL
                            OR s.end_date > dd.month_start_date
                            OR (s.status = 'CANCELLED' AND s.end_date = dd.month_start_date));
