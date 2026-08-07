from __future__ import annotations

import pandas as pd
import streamlit as st

from data_store import get_session_dataset, initialize_session_dataset


st.set_page_config(
    page_title="CPS Security Incident Database",
    page_icon="🛡️",
    layout="wide",
)

initialize_session_dataset()
df = get_session_dataset()

st.title("🛡️ CPS Security Incident Database")
st.caption(
    "Browse and maintain the consolidated CPS security-incident dataset, "
    "then use the taxonomy classifier for evidence-based property mapping."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Incidents", f"{len(df):,}")
c2.metric("Sectors", f"{df['Sector'].nunique():,}")
c3.metric("Countries / regions", f"{df['Country/Region'].nunique():,}")
valid_years = pd.to_numeric(df["Year"], errors="coerce").dropna()
year_label = (
    f"{int(valid_years.min())}–{int(valid_years.max())}"
    if not valid_years.empty else "—"
)
c4.metric("Years", year_label)

st.markdown("### Dataset at a glance")

left, right = st.columns(2)
with left:
    sector_counts = (
        df["Sector"]
        .replace("", "Unknown")
        .value_counts()
        .sort_values(ascending=False)
    )
    st.markdown("**Incidents by sector**")
    st.bar_chart(sector_counts)

with right:
    year_counts = (
        pd.to_numeric(df["Year"], errors="coerce")
        .dropna()
        .astype(int)
        .value_counts()
        .sort_index()
    )
    st.markdown("**Incidents by year**")
    st.line_chart(year_counts)

st.markdown("### Pages")
st.markdown(
    """
- **Incident Database** — search/filter incidents and add, edit, or delete records.
- **Taxonomy Classifier** — the existing classification prototype, now pointed at the full dataset.
"""
)

st.info(
    "Data-management changes made in the web interface are kept in the current Streamlit session. "
    "Use **Download current CSV** on the Incident Database page, then replace "
    "`data/incidents.csv` in GitHub to make those changes permanent. "
    "Direct GitHub saving can be added later with a repository token."
)

if st.session_state.get("dataset_dirty", False):
    st.warning(
        "This session contains unsaved dataset changes. "
        "Download the current CSV from the Incident Database page before closing the session."
    )
