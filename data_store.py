from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "incidents.csv"

COLUMNS = [
    "Year",
    "Incident Name",
    "Country/Region",
    "Sector",
    "Attack Type",
    "Attacker / Group",
    "Verified Impact Summary",
    "Source / Verification URL",
    "Verification Status",
    "URL1",
    "URL2",
    "URL3",
    "URL4",
]


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return the canonical 13-column incident dataset.

    Important: do not call df.fillna("") on the whole dataframe because
    the Year column uses pandas nullable Int64 and cannot accept an empty
    string. Handle Year separately and fill text columns only.
    """
    df = df.copy()

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[COLUMNS].copy()

    # Keep Year sortable as a nullable integer where possible.
    year_numeric = pd.to_numeric(df["Year"], errors="coerce")
    df["Year"] = year_numeric.astype("Int64")

    # Fill/clean only text columns.
    for col in COLUMNS[1:]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # Drop accidental blank separator rows only.
    df = df[df["Incident Name"].str.strip() != ""].reset_index(drop=True)
    return df


@st.cache_data(show_spinner=False)
def load_repository_dataset() -> pd.DataFrame:
    return normalize_dataframe(pd.read_csv(DATA_PATH))


def initialize_session_dataset(force: bool = False) -> None:
    if force or "incidents_df" not in st.session_state:
        st.session_state["incidents_df"] = load_repository_dataset().copy()
        st.session_state["dataset_dirty"] = False


def get_session_dataset() -> pd.DataFrame:
    initialize_session_dataset()
    return st.session_state["incidents_df"]


def set_session_dataset(df: pd.DataFrame) -> None:
    st.session_state["incidents_df"] = normalize_dataframe(df)
    st.session_state["dataset_dirty"] = True


def reset_session_dataset() -> None:
    load_repository_dataset.clear()
    initialize_session_dataset(force=True)


def csv_bytes(df: pd.DataFrame) -> bytes:
    clean = normalize_dataframe(df).copy()
    # Convert nullable integer Year to plain text only for CSV export.
    clean["Year"] = clean["Year"].astype("string").fillna("")
    return clean.to_csv(index=False).encode("utf-8-sig")


def unique_nonempty(df: pd.DataFrame, column: str) -> list[str]:
    values = (
        df[column]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(values, key=lambda x: x.lower()
