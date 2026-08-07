from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from batch_processor import batch_classify, detect_schema
from classifier import SourceText, classify_sources, evidence_to_dicts
from fetcher import fetch_public_document
from taxonomy import TAXONOMY
from data_store import get_session_dataset, initialize_session_dataset


st.set_page_config(
    page_title="CPS Incident Taxonomy Classifier",
    page_icon="🛡️",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "incidents.csv"


def load_default_data() -> pd.DataFrame:
    initialize_session_dataset()
    return get_session_dataset().copy()


def read_uploaded_table(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(uploaded_file).fillna("")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file).fillna("")
    raise ValueError("Upload CSV, XLSX, or XLS.")


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def taxonomy_panel():
    cols = st.columns(3)
    for col, (parent, properties) in zip(cols, TAXONOMY.items()):
        with col:
            st.markdown(f"#### {parent}")
            for prop in properties:
                st.markdown(f"- {prop}")


st.title("🛡️ CPS Incident Taxonomy Classifier")
st.caption(
    "Evidence-aware, rule-guided multi-label classification. "
    "The visualization output contains only CONFIRMED properties, "
    "ranked by Evidence Score, with a maximum of three properties per incident."
)

with st.expander("Taxonomy used by the classifier"):
    taxonomy_panel()

st.info(
    "Important: 'Sec. Property Target' and 'Keywords' columns in the original dataset "
    "are NOT used as classifier input. This avoids label leakage."
)

with st.sidebar:
    st.header("Dataset")
    data_source = st.radio(
        "Source",
        ["Current CPS dataset (repository + session edits)", "Upload CSV/XLSX"],
    )

    if data_source == "Upload CSV/XLSX":
        uploaded = st.file_uploader("Upload dataset", type=["csv", "xlsx", "xls"])
        if uploaded is None:
            st.stop()
        df = read_uploaded_table(uploaded)
    else:
        df = load_default_data()

    st.success(f"Loaded {len(df):,} incidents")

    st.header("Batch settings")
    fetch_urls = st.checkbox(
        "Fetch source URLs",
        value=True,
        help="Fetching improves evidence but is slower. Description text is always used.",
    )
    max_urls = st.slider(
        "Maximum URLs per incident",
        1, 4, 1,
        help="For the full dataset start with 1. Increase later if needed.",
    )
    max_workers = st.slider("Parallel fetch workers", 2, 12, 8)
    top_properties = st.slider(
        "Maximum confirmed properties per incident",
        1, 3, 3,
    )

    total = len(df)
    start_row = st.number_input(
        "Start row (0-based)",
        min_value=0,
        max_value=max(0, total - 1),
        value=0,
        step=1,
    )
    end_default = min(total, int(start_row) + 50)
    end_row = st.number_input(
        "End row (exclusive)",
        min_value=1,
        max_value=max(1, total),
        value=end_default,
        step=1,
    )

schema = detect_schema(df)

tab_batch, tab_single, tab_data = st.tabs(
    ["Batch classify", "Inspect one incident", "Dataset preview"]
)

with tab_batch:
    st.subheader("Batch classification")
    st.write(
        "Selection rule: keep only `Final Status = CONFIRMED`, sort by "
        "`Evidence Score` descending, and keep at most the top 3 properties."
    )

    if int(end_row) <= int(start_row):
        st.error("End row must be greater than start row.")
    elif st.button("▶ Run batch classification", type="primary", use_container_width=True):
        with st.spinner("Retrieving evidence and classifying incidents..."):
            result = batch_classify(
                df,
                fetch_urls=fetch_urls,
                max_urls_per_incident=max_urls,
                max_workers=max_workers,
                max_properties=top_properties,
                row_start=int(start_row),
                row_end=int(end_row),
            )

        viz_df = pd.DataFrame(result.visualization_rows)
        qc_df = pd.DataFrame(result.incident_qc_rows)
        fetch_df = pd.DataFrame(result.url_fetch_rows)
        review_df = pd.DataFrame(result.manual_review_rows)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Incidents processed", len(qc_df))
        c2.metric("Visualization rows", len(viz_df))
        c3.metric(
            "Incidents with no confirmed property",
            int((qc_df["No Confirmed Property Flag"] == "YES").sum()) if not qc_df.empty else 0,
        )
        c4.metric(
            "Incidents needing URL/manual review",
            len(review_df),
        )

        st.markdown("### Visualization-ready output")
        if viz_df.empty:
            st.warning("No confirmed properties were selected in this batch.")
        else:
            st.dataframe(
                viz_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Evidence Score": st.column_config.ProgressColumn(
                        "Evidence Score", min_value=0, max_value=100, format="%.1f"
                    ),
                    "Evidence URL": st.column_config.LinkColumn("Evidence URL"),
                },
            )

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇ Download visualization_properties.csv",
                data=to_csv_bytes(viz_df),
                file_name="visualization_properties.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                "⬇ Download incident_classification_qc.csv",
                data=to_csv_bytes(qc_df),
                file_name="incident_classification_qc.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("### URL fetch audit")
        if fetch_df.empty:
            st.info("No URL fetch records: fetching may be disabled or the selected rows have no URLs.")
        else:
            st.dataframe(
                fetch_df,
                use_container_width=True,
                hide_index=True,
                column_config={"URL": st.column_config.LinkColumn("URL")},
            )
        st.download_button(
            "⬇ Download url_fetch_status.csv",
            data=to_csv_bytes(fetch_df),
            file_name="url_fetch_status.csv",
            mime="text/csv",
        )

        st.markdown("### Manual review / failed URL queue")
        st.write(
            "If a URL cannot be fetched, copy the relevant article/report text into the "
            "`Manual Source Text` column of the dataset and rerun the classifier. "
            "This is cleaner than overwriting the verified summary."
        )
        if review_df.empty:
            st.success("No manual-review rows were generated in this batch.")
        else:
            st.dataframe(review_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ Download manual_review_queue.csv",
            data=to_csv_bytes(review_df),
            file_name="manual_review_queue.csv",
            mime="text/csv",
        )

with tab_single:
    st.subheader("Inspect one incident")
    incident_col = schema["incident"]
    selected_idx = st.selectbox(
        "Incident",
        options=list(df.index),
        format_func=lambda idx: str(df.loc[idx, incident_col]),
    )
    row = df.loc[selected_idx]

    incident_name = str(row.get(incident_col, ""))
    description = str(row.get(schema["description"], ""))
    manual_text = str(row.get(schema["manual_text"], "")) if schema["manual_text"] else ""

    urls = []
    for col in schema["urls"]:
        value = str(row.get(col, "")).strip()
        if value.startswith(("http://", "https://")):
            urls.append(value)

    st.json(
        {
            "Incident Name": incident_name,
            "Country": str(row.get(schema["country"], "")) if schema["country"] else "",
            "Sector": str(row.get(schema["sector"], "")) if schema["sector"] else "",
            "Description": description,
            "URLs": urls,
            "Manual Source Text Present": bool(manual_text.strip()),
        },
        expanded=False,
    )

    if st.button("🔎 Inspect and classify this incident"):
        sources = []
        if description.strip():
            sources.append(SourceText("Dataset description", "", description))
        if manual_text.strip():
            sources.append(SourceText("Manual source text", "", manual_text))

        fetch_log = []
        for number, url in enumerate(urls[:max_urls], start=1):
            result = fetch_public_document(url, timeout=12)
            fetch_log.append(
                {
                    "URL": url,
                    "Fetch Status": "FETCHED" if result.ok else "FAILED",
                    "Message": result.message,
                    "Extracted Characters": len(result.text or ""),
                }
            )
            if result.ok:
                sources.append(
                    SourceText(f"Fetched URL {number}", result.url, result.text)
                )

        evidence, summaries = classify_sources(sources)
        summary_df = pd.DataFrame(summaries)
        evidence_df = pd.DataFrame(evidence_to_dicts(evidence))

        confirmed = summary_df[
            summary_df["Final Status"] == "CONFIRMED"
        ].sort_values("Evidence Score", ascending=False).head(3) if not summary_df.empty else summary_df

        st.markdown("#### Top confirmed properties")
        st.dataframe(confirmed, use_container_width=True, hide_index=True)

        st.markdown("#### All evidence")
        st.dataframe(evidence_df, use_container_width=True, hide_index=True)

        st.markdown("#### URL status")
        st.dataframe(pd.DataFrame(fetch_log), use_container_width=True, hide_index=True)

with tab_data:
    st.subheader("Dataset preview")
    st.write(f"Rows: **{len(df):,}**")
    st.dataframe(df.head(100), use_container_width=True, hide_index=True)
    st.caption(
        "The bundled dataset contains the full Energy & Power Grid incident file. "
        "You can later replace data/incidents.csv or upload another sector/all-sector dataset."
    )
