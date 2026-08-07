"""Batch processing for the CPS incident taxonomy classifier."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from classifier import SourceText, classify_sources
from fetcher import fetch_public_document


INCIDENT_NAME_ALIASES = ["Incident Name", "Incident", "Event", "Event Name"]
COUNTRY_ALIASES = ["Country", "Country/Region", "Country / Region", "Region"]
SECTOR_ALIASES = ["Sector", "CI Sector", "Critical Infrastructure Sector"]
DESCRIPTION_ALIASES = [
    "Verified Impact Summary",
    "Impact Summary",
    "Description",
    "Incident Description",
    "Summary",
]
MANUAL_TEXT_ALIASES = ["Manual Source Text", "Manual Text", "Pasted Source Text"]


@dataclass
class BatchResult:
    visualization_rows: list[dict]
    incident_qc_rows: list[dict]
    url_fetch_rows: list[dict]
    manual_review_rows: list[dict]


def _first_existing_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lookup = {str(col).strip().lower(): col for col in df.columns}
    for alias in aliases:
        found = lookup.get(alias.lower())
        if found is not None:
            return found
    return None


def _get_value(row: pd.Series, column: str | None) -> str:
    if not column:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def detect_schema(df: pd.DataFrame) -> dict:
    schema = {
        "incident": _first_existing_column(df, INCIDENT_NAME_ALIASES),
        "country": _first_existing_column(df, COUNTRY_ALIASES),
        "sector": _first_existing_column(df, SECTOR_ALIASES),
        "description": _first_existing_column(df, DESCRIPTION_ALIASES),
        "manual_text": _first_existing_column(df, MANUAL_TEXT_ALIASES),
        "urls": [
            col for col in df.columns
            if str(col).strip().upper().startswith("URL")
        ],
    }
    if not schema["incident"]:
        raise ValueError(
            "Dataset needs an incident-name column, e.g. 'Incident Name'."
        )
    if not schema["description"]:
        raise ValueError(
            "Dataset needs a description column, e.g. 'Verified Impact Summary'."
        )
    return schema


def _aggregate_fetch_state(
    url_rows: list[dict],
    fetch_enabled: bool,
    manual_text: str,
) -> tuple[str, str, int, int]:
    if not fetch_enabled:
        return "FETCH_DISABLED", "FETCH_DISABLED", 0, 0

    if not url_rows:
        if manual_text:
            return "NO_URL", "MANUAL_TEXT_AVAILABLE", 0, 0
        return "NO_URL", "NO_URL_REVIEW", 0, 0

    fetched = sum(1 for r in url_rows if r["Fetch Status"] == "FETCHED")
    failed = sum(1 for r in url_rows if r["Fetch Status"] == "FAILED")

    if failed == 0:
        status = "ALL_FETCHED"
        flag = "NO"
    elif fetched == 0:
        status = "ALL_FAILED"
        flag = "MANUAL_TEXT_USED" if manual_text else "YES_ADD_MANUAL_TEXT"
    else:
        status = "PARTIAL"
        flag = "MANUAL_TEXT_USED" if manual_text else "REVIEW_FAILED_URLS"

    return status, flag, fetched, failed


def _fetch_one(incident_index: int, incident_name: str, url_number: int, url: str) -> dict:
    result = fetch_public_document(url, timeout=12)
    return {
        "Incident Row": incident_index,
        "Incident Name": incident_name,
        "URL Number": url_number,
        "URL": url,
        "Fetch Status": "FETCHED" if result.ok else "FAILED",
        "Fetch Message": result.message,
        "Extracted Characters": len(result.text or ""),
        "_text": result.text if result.ok else "",
        "_resolved_url": result.url if result.ok else url,
    }


def batch_classify(
    df: pd.DataFrame,
    *,
    fetch_urls: bool = True,
    max_urls_per_incident: int = 1,
    max_workers: int = 8,
    max_properties: int = 3,
    row_start: int = 0,
    row_end: int | None = None,
) -> BatchResult:
    """
    Classify a dataframe and keep only CONFIRMED properties.

    Selection rule:
      1. Final Status must be CONFIRMED.
      2. Sort by Evidence Score descending.
      3. Keep at most max_properties (default 3).
      4. If only 1 or 2 confirmed properties exist, keep only those 1 or 2.
    """
    schema = detect_schema(df)
    work = df.iloc[row_start:row_end].copy()

    # Build URL jobs first so retrieval can run concurrently.
    fetch_rows_by_index: dict[int, list[dict]] = {idx: [] for idx in work.index}
    jobs = []

    if fetch_urls:
        with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as executor:
            for idx, row in work.iterrows():
                incident_name = _get_value(row, schema["incident"])
                urls = []
                for col in schema["urls"]:
                    value = _get_value(row, col)
                    if value.startswith(("http://", "https://")):
                        urls.append(value)
                urls = list(dict.fromkeys(urls))[:max_urls_per_incident]

                for url_number, url in enumerate(urls, start=1):
                    future = executor.submit(
                        _fetch_one, int(idx), incident_name, url_number, url
                    )
                    jobs.append(future)

            for future in as_completed(jobs):
                result = future.result()
                fetch_rows_by_index[result["Incident Row"]].append(result)

    visualization_rows: list[dict] = []
    incident_qc_rows: list[dict] = []
    public_fetch_rows: list[dict] = []
    manual_review_rows: list[dict] = []

    for idx, row in work.iterrows():
        incident_name = _get_value(row, schema["incident"])
        country = _get_value(row, schema["country"]) or "Unknown"
        sector = _get_value(row, schema["sector"]) or "Unknown"
        description = _get_value(row, schema["description"])
        manual_text = _get_value(row, schema["manual_text"])

        sources = []
        if description:
            sources.append(
                SourceText(
                    source="Dataset description",
                    url="",
                    text=description,
                )
            )
        if manual_text:
            sources.append(
                SourceText(
                    source="Manual source text",
                    url="",
                    text=manual_text,
                )
            )

        incident_fetch_rows = sorted(
            fetch_rows_by_index.get(idx, []),
            key=lambda r: r["URL Number"],
        )
        for fetch_row in incident_fetch_rows:
            public_fetch_rows.append(
                {k: v for k, v in fetch_row.items() if not k.startswith("_")}
            )
            if fetch_row["Fetch Status"] == "FETCHED" and fetch_row["_text"]:
                sources.append(
                    SourceText(
                        source=f"Fetched URL {fetch_row['URL Number']}",
                        url=fetch_row["_resolved_url"],
                        text=fetch_row["_text"],
                    )
                )

        fetch_status, manual_flag, fetched_count, failed_count = _aggregate_fetch_state(
            incident_fetch_rows, fetch_urls, manual_text
        )

        evidence_rows, summaries = classify_sources(sources)

        confirmed = [
            summary for summary in summaries
            if summary.get("Final Status") == "CONFIRMED"
        ]
        confirmed.sort(
            key=lambda r: (
                -float(r.get("Evidence Score", 0) or 0),
                str(r.get("Property", "")),
            )
        )

        selected = confirmed[: max(1, min(int(max_properties), 3))]

        for rank, item in enumerate(selected, start=1):
            visualization_rows.append(
                {
                    "Incident Name": incident_name,
                    "Country": country,
                    "Sector": sector,
                    "Property": item.get("Property", ""),
                    "Parent Category": item.get("Parent Category", ""),
                    "Evidence Score": item.get("Evidence Score", 0),
                    "Property Rank": rank,
                    "Final Status": "CONFIRMED",
                    "Best Evidence": item.get("Best Evidence", ""),
                    "Evidence Source": item.get("Source", ""),
                    "Evidence URL": item.get("URL", ""),
                    "URL Fetch Status": fetch_status,
                    "Manual Text Flag": manual_flag,
                }
            )

        qc = {
            "Incident Name": incident_name,
            "Country": country,
            "Sector": sector,
            "Confirmed Property Count": len(confirmed),
            "Selected Property Count": len(selected),
            "URL Fetch Status": fetch_status,
            "Fetched URL Count": fetched_count,
            "Failed URL Count": failed_count,
            "Manual Text Flag": manual_flag,
            "Manual Source Text Used": "YES" if manual_text else "NO",
            "No Confirmed Property Flag": "YES" if not selected else "NO",
        }
        for position in range(1, 4):
            if position <= len(selected):
                item = selected[position - 1]
                qc[f"Property {position}"] = item.get("Property", "")
                qc[f"Score {position}"] = item.get("Evidence Score", 0)
            else:
                qc[f"Property {position}"] = ""
                qc[f"Score {position}"] = ""
        incident_qc_rows.append(qc)

        failed_urls = [
            r["URL"] for r in incident_fetch_rows
            if r["Fetch Status"] == "FAILED"
        ]
        if (
            manual_flag in {"YES_ADD_MANUAL_TEXT", "REVIEW_FAILED_URLS", "NO_URL_REVIEW"}
            or not selected
        ):
            manual_review_rows.append(
                {
                    "Incident Name": incident_name,
                    "Country": country,
                    "Sector": sector,
                    "Verified Impact Summary": description,
                    "Failed URLs": " | ".join(failed_urls),
                    "URL Fetch Status": fetch_status,
                    "Manual Text Flag": manual_flag,
                    "No Confirmed Property Flag": "YES" if not selected else "NO",
                    "Manual Source Text": manual_text,
                }
            )

    return BatchResult(
        visualization_rows=visualization_rows,
        incident_qc_rows=incident_qc_rows,
        url_fetch_rows=public_fetch_rows,
        manual_review_rows=manual_review_rows,
    )
