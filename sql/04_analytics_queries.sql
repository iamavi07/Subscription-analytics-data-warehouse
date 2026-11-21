-- =====================================================================
-- 04_analytics_queries.sql
-- Analytical SQL on the star schema. Each query starts with "-- name: <id>"
-- so Python (and the dashboard) can run them one by one.
-- (No percent signs and no double-colon casts: keeps them portable.)
-- =====================================================================

-- name: active_subscribers_monthly
-- Q1: active subscriptions / customers at the END of every month
SELECT d.year_month,
       d.month_start_date,
       SUM(f.active_flag) AS active_subscriptions,
       COUNT(DISTINCT CASE WHEN f.active_flag = 1 THEN f.customer_key END) AS active_customers
FROM dw.fact_subscription_monthly f
JOIN dw.dim_date d ON d.date_key = f.date_key
GROUP BY d.year_month, d.month_start_date
ORDER BY d.month_start_date;

-- name: revenue_monthly
-- Q2: revenue per month. billed_revenue = cash billed in the month (ties to transactions);
--     mrr_month_end = recurring revenue run-rate of subscriptions active at month end.
SELECT d.year_month,
       d.month_start_date,
       SUM(f.monthly_revenue) AS billed_revenue,
       SUM(CASE WHEN f.active_flag = 1 THEN p.monthly_price ELSE 0 END) AS mrr_month_end
FROM dw.fact_subscription_monthly f
JOIN dw.dim_date d ON d.date_key = f.date_key
JOIN dw.dim_plan p ON p.plan_key = f.plan_key
GROUP BY d.year_month, d.month_start_date
ORDER BY d.month_start_date;

-- name: new_customers_monthly
-- Q5: new customers subscribing each month
SELECT d.year_month,
       d.month_start_date,
       SUM(f.new_flag) AS new_customers
FROM dw.fact_subscription_monthly f
JOIN dw.dim_date d ON d.date_key = f.date_key
GROUP BY d.year_month, d.month_start_date
ORDER BY d.month_start_date;

-- name: subscriber_rollforward
-- Q1/Q3/Q5/Q6: beginning + new - cancelled = ending, plus churn rate and growth
WITH monthly AS (
    SELECT d.year_month,
           d.month_start_date,
           SUM(f.active_flag) AS ending_subscribers,
           SUM(f.new_flag)    AS new_subscribers,
           SUM(f.churn_flag)  AS cancelled_subscribers,
           SUM(f.upgrade_flag + f.downgrade_flag) AS plan_changes
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    GROUP BY d.year_month, d.month_start_date
),
with_begin AS (
    SELECT m.*,
           LAG(ending_subscribers, 1, 0) OVER (ORDER BY month_start_date) AS beginning_subscribers
    FROM monthly m
)
SELECT year_month,
       month_start_date,
       beginning_subscribers,
       new_subscribers,
       cancelled_subscribers,
       ending_subscribers,
       plan_changes,
       ROUND(100.0 * cancelled_subscribers / NULLIF(beginning_subscribers, 0), 2) AS churn_rate_pct,
       ROUND(100.0 * (ending_subscribers - beginning_subscribers) / NULLIF(beginning_subscribers, 0), 2) AS net_growth_pct
FROM with_begin
ORDER BY month_start_date;

-- name: churn_customer_vs_subscription
-- Customer churn (real cancellations) vs gross subscription churn
-- (every subscription that CLOSED, including upgrades/downgrades that immediately re-open).
WITH monthly AS (
    SELECT d.year_month,
           d.month_start_date,
           SUM(f.active_flag)  AS ending_subscribers,
           SUM(f.churn_flag)   AS customers_lost,
           SUM(f.churn_flag + f.upgrade_flag + f.downgrade_flag) AS subscriptions_closed
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    GROUP BY d.year_month, d.month_start_date
),
with_begin AS (
    SELECT m.*,
           LAG(ending_subscribers, 1, 0) OVER (ORDER BY month_start_date) AS beginning_subscribers
    FROM monthly m
)
SELECT year_month,
       month_start_date,
       beginning_subscribers,
       customers_lost,
       subscriptions_closed,
       ROUND(100.0 * customers_lost / NULLIF(beginning_subscribers, 0), 2)       AS customer_churn_pct,
       ROUND(100.0 * subscriptions_closed / NULLIF(beginning_subscribers, 0), 2) AS subscription_churn_pct
FROM with_begin
ORDER BY month_start_date;

-- name: revenue_by_plan_total
-- Q4: which plan generates the most revenue (all time) + share of total
WITH plan_rev AS (
    SELECT p.plan_name,
           p.monthly_price,
           SUM(f.monthly_revenue) AS total_revenue,
           SUM(f.active_flag)     AS active_subscription_months
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_plan p ON p.plan_key = f.plan_key
    GROUP BY p.plan_name, p.monthly_price
)
SELECT plan_name,
       monthly_price,
       total_revenue,
       ROUND(100.0 * total_revenue / SUM(total_revenue) OVER (), 2) AS revenue_share_pct,
       RANK() OVER (ORDER BY total_revenue DESC) AS revenue_rank
FROM plan_rev
ORDER BY total_revenue DESC;

-- name: revenue_by_plan_monthly
-- Q4 (trend): billed revenue per plan per month
SELECT d.year_month,
       d.month_start_date,
       p.plan_name,
       SUM(f.monthly_revenue) AS billed_revenue
FROM dw.fact_subscription_monthly f
JOIN dw.dim_date d ON d.date_key = f.date_key
JOIN dw.dim_plan p ON p.plan_key = f.plan_key
GROUP BY d.year_month, d.month_start_date, p.plan_name
ORDER BY d.month_start_date, p.plan_name;

-- name: top_cancellation_months
-- Q7: months with the highest cancellations
WITH monthly AS (
    SELECT d.year_month, d.month_start_date, SUM(f.churn_flag) AS cancellations
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    GROUP BY d.year_month, d.month_start_date
)
SELECT year_month,
       cancellations,
       RANK() OVER (ORDER BY cancellations DESC) AS cancellation_rank
FROM monthly
ORDER BY cancellation_rank, year_month
LIMIT 5;

-- name: cohort_retention
-- Q6: cohort retention. Cohort = month the customer first subscribed.
-- retained = customers whose subscription is active at the end of month N after sign-up.
WITH cohort AS (
    SELECT f.customer_key, MIN(d.month_index) AS cohort_index
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    WHERE f.new_flag = 1
    GROUP BY f.customer_key
),
cohort_size AS (
    SELECT cohort_index, COUNT(*) AS cohort_customers
    FROM cohort
    GROUP BY cohort_index
),
activity AS (
    SELECT c.cohort_index,
           d.month_index - c.cohort_index AS months_since_signup,
           COUNT(DISTINCT f.customer_key) AS retained_customers
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    JOIN cohort c      ON c.customer_key = f.customer_key
    WHERE f.active_flag = 1
      AND d.month_index >= c.cohort_index
    GROUP BY c.cohort_index, d.month_index - c.cohort_index
)
SELECT cd.year_month AS cohort_month,
       a.months_since_signup,
       cs.cohort_customers,
       a.retained_customers,
       ROUND(100.0 * a.retained_customers / cs.cohort_customers, 2) AS retention_pct
FROM activity a
JOIN cohort_size cs ON cs.cohort_index = a.cohort_index
JOIN dw.dim_date cd ON cd.month_index  = a.cohort_index
ORDER BY cd.month_start_date, a.months_since_signup;

-- name: plan_changes_monthly
-- Upgrades and downgrades per month
SELECT d.year_month,
       d.month_start_date,
       SUM(f.upgrade_flag)   AS upgrades,
       SUM(f.downgrade_flag) AS downgrades
FROM dw.fact_subscription_monthly f
JOIN dw.dim_date d ON d.date_key = f.date_key
GROUP BY d.year_month, d.month_start_date
ORDER BY d.month_start_date;

-- name: active_by_plan_region_latest
-- Q1: active subscribers split by plan and region in the latest month
SELECT p.plan_name,
       c.region,
       SUM(f.active_flag) AS active_subscribers
FROM dw.fact_subscription_monthly f
JOIN dw.dim_date d     ON d.date_key     = f.date_key
JOIN dw.dim_plan p     ON p.plan_key     = f.plan_key
JOIN dw.dim_customer c ON c.customer_key = f.customer_key
WHERE d.month_index = (SELECT MAX(month_index) FROM dw.dim_date)
GROUP BY p.plan_name, c.region
ORDER BY p.plan_name, active_subscribers DESC;
