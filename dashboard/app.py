"""Step 6b - Streamlit dashboard.   Run:  streamlit run dashboard/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from src.db import get_engine, load_named_queries, run_query  # noqa: E402

st.set_page_config(page_title="Subscription Analytics", layout="wide")
st.title("Subscription Analytics Dashboard")
st.caption("Fictional streaming platform | Basic 199, Standard 399, Premium 599 INR per month | source: PostgreSQL star schema")


@st.cache_data(ttl=300, show_spinner="Running warehouse queries...")
def load_all() -> dict:
    engine = get_engine()
    return {name: run_query(engine, sql) for name, sql in load_named_queries("04_analytics_queries.sql").items()}


try:
    data = load_all()
except Exception as exc:  # pragma: no cover
    st.error("Could not read the warehouse. Run `python run_pipeline.py` first and check your .env file.")
    st.exception(exc)
    st.stop()

roll = data["subscriber_rollforward"].copy()
rev = data["revenue_monthly"].copy()
for df in (roll, rev):
    df["month_start_date"] = pd.to_datetime(df["month_start_date"])

months = list(roll["year_month"])
start, end = st.select_slider("Month range", options=months, value=(months[0], months[-1]))
in_range = lambda df: df[(df["year_month"] >= start) & (df["year_month"] <= end)]  # noqa: E731
roll_f, rev_f = in_range(roll), in_range(rev)

latest, latest_rev = roll_f.iloc[-1], rev_f.iloc[-1]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Active subscribers", f"{int(latest['ending_subscribers']):,}")
c2.metric("MRR (month end, INR)", f"{float(latest_rev['mrr_month_end']):,.0f}")
c3.metric("Billed revenue (INR)", f"{float(latest_rev['billed_revenue']):,.0f}")
c4.metric("Churn rate", f"{float(latest['churn_rate_pct'] or 0):.2f}%")
c5.metric("New customers", f"{int(latest['new_subscribers']):,}")
st.caption(f"KPI tiles show the last month in the selected range: {latest['year_month']}")

left, right = st.columns(2)
left.plotly_chart(px.line(roll_f, x="month_start_date", y="ending_subscribers", markers=True,
                          title="Active subscribers (month end)"), use_container_width=True)
right.plotly_chart(px.bar(rev_f, x="month_start_date", y="billed_revenue",
                          title="Monthly billed revenue (INR)"), use_container_width=True)

left, right = st.columns(2)
left.plotly_chart(px.line(roll_f, x="month_start_date", y="churn_rate_pct", markers=True,
                          title="Monthly customer churn rate (percent)"), use_container_width=True)
new_vs_lost = roll_f.melt(id_vars=["month_start_date"], value_vars=["new_subscribers", "cancelled_subscribers"],
                          var_name="measure", value_name="customers")
right.plotly_chart(px.bar(new_vs_lost, x="month_start_date", y="customers", color="measure", barmode="group",
                          title="New customers vs cancellations"), use_container_width=True)

plan_m = data["revenue_by_plan_monthly"].copy()
plan_m = in_range(plan_m)
left, right = st.columns(2)
left.plotly_chart(px.area(plan_m, x="month_start_date", y="billed_revenue", color="plan_name",
                          title="Revenue by plan over time"), use_container_width=True)
right.plotly_chart(px.pie(data["revenue_by_plan_total"], names="plan_name", values="total_revenue",
                          title="Share of all-time revenue by plan"), use_container_width=True)

st.subheader("Cohort retention")
coh = data["cohort_retention"]
heat = coh.pivot(index="cohort_month", columns="months_since_signup", values="retention_pct")
st.plotly_chart(px.imshow(heat, aspect="auto", color_continuous_scale="Blues",
                          labels=dict(x="Months since sign-up", y="Cohort month", color="Retained (percent)")),
                use_container_width=True)

left, right = st.columns(2)
left.subheader("Months with the most cancellations")
left.dataframe(data["top_cancellation_months"], hide_index=True, use_container_width=True)
right.subheader("Customer churn vs subscription churn")
right.dataframe(in_range(data["churn_customer_vs_subscription"]).drop(columns=["month_start_date"]),
                hide_index=True, use_container_width=True)

with st.expander("Subscriber roll-forward table"):
    st.dataframe(roll_f.drop(columns=["month_start_date"]), hide_index=True, use_container_width=True)
