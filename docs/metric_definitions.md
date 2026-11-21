# Metric definitions and modelling assumptions

All numbers in the warehouse follow these simplified, documented rules.

## Business rules (simplified monthly billing model)

| Topic | Rule used |
|---|---|
| Billing | Calendar-month billing, **full plan price, no proration**. |
| When a customer is charged | On `start_date` (types NEW / UPGRADE / DOWNGRADE), then on the **1st of every following month** while the subscription is still running (RENEWAL). |
| Plan changes (upgrade / downgrade) | Take effect on the **1st of a month**. The old subscription closes (status UPGRADED / DOWNGRADED), a new subscription starts the same day. No extra or refunded money: the customer simply pays the new plan price from that 1st. |
| Cancellation | Happens on a day between the 2nd and 28th, always in a month **after** the start month. The customer has already paid for that month; there is **no refund**. |
| `end_date` | First day **without** service. A subscription is active on day D when `start_date <= D < end_date` (or `end_date` is NULL). |
| One active subscription | A customer has at most one ACTIVE subscription at a time (enforced by a unique index). |
| Failed payments, refunds, re-activations | **Not modelled** in this first version. Cancelled customers do not return. |

## Fact table: `dw.fact_subscription_monthly`

Grain: **one row per subscription per calendar month** in which the subscription is relevant.

| Column | Definition |
|---|---|
| `monthly_revenue` | Amount billed in that month = plan price if the subscription started in the month, or is still running on the 1st; otherwise 0. Sums to exactly the transaction amounts of that month. |
| `active_flag` | 1 if active on the **last day** of the month. |
| `churn_flag` | 1 if the subscription was **CANCELLED** during the month (plan changes are not churn). |
| `new_flag` | 1 if a brand-new customer subscription (`start_reason = NEW`) started in the month. |
| `upgrade_flag` / `downgrade_flag` | 1 if the subscription began that month as an upgrade / downgrade. |

## Business metrics

| Metric | Definition in this project | Where |
|---|---|---|
| Active subscribers | Distinct subscriptions with `active_flag = 1` at the month end. | `active_subscribers_monthly` |
| MRR | Sum of the plan price of subscriptions active at month end (`mrr_month_end`). Billed revenue (`billed_revenue`) is the cash billed in the month. They differ slightly because customers who cancel mid-month paid for the month but are not active at its end. | `revenue_monthly` |
| New subscriptions | Subscriptions with `new_flag = 1` in the month (a plan change is **not** a new customer). | `new_customers_monthly` |
| Cancellations | Subscriptions with `churn_flag = 1`. | `subscriber_rollforward` |
| Customer churn rate | cancellations in month / active subscribers at the **end of the previous month**, times 100. | `subscriber_rollforward` |
| Subscription churn rate (gross) | (cancellations + upgrades + downgrades) / beginning subscribers. Every plan change closes one subscription, so this is always higher than customer churn. | `churn_customer_vs_subscription` |
| Retention rate | Cohort = month of first subscription. Retention at month N = customers active at the end of month N after sign-up / cohort size. | `cohort_retention` |
| Plan revenue | Sum of `monthly_revenue` per plan. | `revenue_by_plan_total`, `revenue_by_plan_monthly` |

Worked example (matches the project brief): 1,000 subscribers at the start of a month, 100 cancel, 150 join:
ending = 1,000 - 100 + 150 = 1,050 and churn = 100 / 1,000 = 10 percent.
The validation step proves `ending = beginning + new - cancelled` in **every** month of the warehouse.

## Why customer churn equals subscription churn here
Because a customer can only hold one active subscription and cancelled customers do not return, a cancelled subscription is always a lost customer. The two churn measures are still reported separately (gross subscription churn counts plan switches) so the distinction is visible and the model is ready for multiple subscriptions per customer later.
