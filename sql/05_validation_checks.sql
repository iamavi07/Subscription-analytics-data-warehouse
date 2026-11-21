-- =====================================================================
-- 05_validation_checks.sql
-- Every query returns ONE number: how many problems were found. 0 = PASS.
-- =====================================================================

-- name: ops_orphan_subscriptions
SELECT COUNT(*) AS problems
FROM ops.subscriptions s
LEFT JOIN ops.customers c ON c.customer_id = s.customer_id
LEFT JOIN ops.plans p     ON p.plan_id     = s.plan_id
WHERE c.customer_id IS NULL OR p.plan_id IS NULL;

-- name: ops_orphan_transactions
SELECT COUNT(*) AS problems
FROM ops.transactions t
LEFT JOIN ops.customers c ON c.customer_id = t.customer_id
LEFT JOIN ops.plans p     ON p.plan_id     = t.plan_id
WHERE c.customer_id IS NULL OR p.plan_id IS NULL;

-- name: ops_duplicate_transaction_ids
SELECT COUNT(*) AS problems
FROM (SELECT transaction_id FROM ops.transactions GROUP BY transaction_id HAVING COUNT(*) > 1) x;

-- name: ops_customers_with_multiple_active_subscriptions
SELECT COUNT(*) AS problems
FROM (SELECT customer_id FROM ops.subscriptions WHERE status = 'ACTIVE'
      GROUP BY customer_id HAVING COUNT(*) > 1) x;

-- name: ops_invalid_subscription_dates
SELECT COUNT(*) AS problems
FROM ops.subscriptions
WHERE end_date IS NOT NULL AND end_date <= start_date;

-- name: dw_orphan_fact_keys
SELECT COUNT(*) AS problems
FROM dw.fact_subscription_monthly f
LEFT JOIN dw.dim_customer c ON c.customer_key = f.customer_key
LEFT JOIN dw.dim_plan p     ON p.plan_key     = f.plan_key
LEFT JOIN dw.dim_date d     ON d.date_key     = f.date_key
WHERE c.customer_key IS NULL OR p.plan_key IS NULL OR d.date_key IS NULL;

-- name: dw_fact_grain_duplicates
SELECT COUNT(*) AS problems
FROM (SELECT subscription_id, date_key FROM dw.fact_subscription_monthly
      GROUP BY subscription_id, date_key HAVING COUNT(*) > 1) x;

-- name: dw_every_subscription_in_fact
SELECT COUNT(*) AS problems
FROM ops.subscriptions s
WHERE NOT EXISTS (SELECT 1 FROM dw.fact_subscription_monthly f WHERE f.subscription_id = s.subscription_id);

-- name: dw_revenue_matches_transactions
-- months where fact revenue differs from the sum of raw transaction amounts
SELECT COUNT(*) AS problems
FROM (
    SELECT d.date_key,
           COALESCE((SELECT SUM(f.monthly_revenue) FROM dw.fact_subscription_monthly f
                     WHERE f.date_key = d.date_key), 0) AS fact_revenue,
           COALESCE((SELECT SUM(t.amount) FROM ops.transactions t
                     WHERE t.transaction_date >= d.month_start_date
                       AND t.transaction_date <= d.month_end_date), 0) AS txn_revenue
    FROM dw.dim_date d
) x
WHERE fact_revenue <> txn_revenue;

-- name: dw_active_count_matches_source
-- months where fact active count differs from active subscriptions counted directly in ops
SELECT COUNT(*) AS problems
FROM (
    SELECT d.date_key,
           COALESCE((SELECT SUM(f.active_flag) FROM dw.fact_subscription_monthly f
                     WHERE f.date_key = d.date_key), 0) AS fact_active,
           (SELECT COUNT(*) FROM ops.subscriptions s
            WHERE s.start_date <= d.month_end_date
              AND (s.end_date IS NULL OR s.end_date > d.month_end_date)) AS source_active
    FROM dw.dim_date d
) x
WHERE fact_active <> source_active;

-- name: dw_cancellations_match_source
SELECT COUNT(*) AS problems
FROM (
    SELECT d.date_key,
           COALESCE((SELECT SUM(f.churn_flag) FROM dw.fact_subscription_monthly f
                     WHERE f.date_key = d.date_key), 0) AS fact_cancel,
           (SELECT COUNT(*) FROM ops.subscriptions s
            WHERE s.status = 'CANCELLED'
              AND s.end_date >= d.month_start_date
              AND s.end_date <= d.month_end_date) AS source_cancel
    FROM dw.dim_date d
) x
WHERE fact_cancel <> source_cancel;

-- name: dw_rollforward_identity
-- ending = beginning + new - cancelled must hold in every month
WITH m AS (
    SELECT d.month_index,
           SUM(f.active_flag) AS ending_subs,
           SUM(f.new_flag)    AS new_subs,
           SUM(f.churn_flag)  AS churned
    FROM dw.fact_subscription_monthly f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    GROUP BY d.month_index
),
r AS (
    SELECT month_index, ending_subs, new_subs, churned,
           LAG(ending_subs, 1, 0) OVER (ORDER BY month_index) AS beginning_subs
    FROM m
)
SELECT COUNT(*) AS problems
FROM r
WHERE ending_subs <> beginning_subs + new_subs - churned;

-- name: dw_fact_table_not_empty
-- guards against "all checks pass because there is no data": 1 problem if the fact table is empty
SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END AS problems
FROM dw.fact_subscription_monthly;

-- name: dw_dimensions_not_empty
SELECT (CASE WHEN (SELECT COUNT(*) FROM dw.dim_customer) = 0 THEN 1 ELSE 0 END
      + CASE WHEN (SELECT COUNT(*) FROM dw.dim_plan) = 0 THEN 1 ELSE 0 END
      + CASE WHEN (SELECT COUNT(*) FROM dw.dim_date) = 0 THEN 1 ELSE 0 END) AS problems;
