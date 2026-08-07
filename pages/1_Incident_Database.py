from __future__ import annotations

import pandas as pd
import streamlit as st

from data_store import (
    COLUMNS,
    csv_bytes,
    get_session_dataset,
    initialize_session_dataset,
    reset_session_dataset,
    set_session_dataset,
    unique_nonempty,
)


st.set_page_config(
    page_title="Incident Database",
    page_icon="🗂️",
    layout="wide",
)

initialize_session_dataset()
df = get_session_dataset().copy()

st.title("🗂️ Incident Database")
st.caption(
    "Browse, filter, add, edit, and delete CPS incident records. "
    "The canonical dataset keeps exactly the same 13 fields."
)

# Internal row id for selection only; it is never exported to CSV.
view = df.reset_index().rename(columns={"index": "_row_id"})

# -------------------------------------------------------------------
# Filters
# -------------------------------------------------------------------
st.markdown("### Filters")

f1, f2, f3, f4 = st.columns([1.3, 1.3, 1.4, 2.0])

with f1:
    all_sectors = unique_nonempty(df, "Sector")
    selected_sectors = st.multiselect(
        "Sector",
        all_sectors,
        placeholder="All sectors",
    )

with f2:
    years = sorted(
        pd.to_numeric(df["Year"], errors="coerce").dropna().astype(int).unique().tolist()
    )
    selected_years = st.multiselect(
        "Year",
        years,
        placeholder="All years",
    )

with f3:
    countries = unique_nonempty(df, "Country/Region")
    selected_countries = st.multiselect(
        "Country / Region",
        countries,
        placeholder="All countries",
    )

with f4:
    query = st.text_input(
        "Search",
        placeholder="Incident, attacker, attack type, impact, source...",
    ).strip()

filtered = view.copy()

if selected_sectors:
    filtered = filtered[filtered["Sector"].isin(selected_sectors)]

if selected_years:
    year_values = pd.to_numeric(filtered["Year"], errors="coerce")
    filtered = filtered[year_values.isin(selected_years)]

if selected_countries:
    filtered = filtered[filtered["Country/Region"].isin(selected_countries)]

if query:
    q = query.lower()
    search_columns = [
        "Incident Name",
        "Country/Region",
        "Sector",
        "Attack Type",
        "Attacker / Group",
        "Verified Impact Summary",
        "Source / Verification URL",
        "Verification Status",
    ]
    mask = pd.Series(False, index=filtered.index)
    for col in search_columns:
        mask = mask | filtered[col].astype(str).str.lower().str.contains(
            q, regex=False, na=False
        )
    filtered = filtered[mask]

m1, m2, m3 = st.columns(3)
m1.metric("Matching incidents", f"{len(filtered):,}")
m2.metric("All incidents", f"{len(df):,}")
m3.metric("Sectors in result", f"{filtered['Sector'].nunique():,}")

display_columns = [
    "Year",
    "Incident Name",
    "Country/Region",
    "Sector",
    "Attack Type",
    "Attacker / Group",
    "Verification Status",
    "URL1",
]

st.dataframe(
    filtered[display_columns],
    use_container_width=True,
    hide_index=True,
    height=480,
    column_config={
        "Year": st.column_config.NumberColumn("Year", format="%d"),
        "URL1": st.column_config.LinkColumn("URL1"),
    },
)

with st.expander("Show full filtered table"):
    full_display = filtered[COLUMNS].copy()
    st.dataframe(
        full_display,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "URL1": st.column_config.LinkColumn("URL1"),
            "URL2": st.column_config.LinkColumn("URL2"),
            "URL3": st.column_config.LinkColumn("URL3"),
            "URL4": st.column_config.LinkColumn("URL4"),
        },
    )

st.download_button(
    "⬇ Download filtered CSV",
    data=csv_bytes(filtered[COLUMNS]),
    file_name="cps_incidents_filtered.csv",
    mime="text/csv",
)

st.divider()

# -------------------------------------------------------------------
# Record management
# -------------------------------------------------------------------
st.markdown("## Manage records")
tab_add, tab_edit, tab_delete, tab_export = st.tabs(
    ["➕ Add incident", "✏️ Edit incident", "🗑️ Delete incident", "💾 Export / Reset"]
)

sector_options = unique_nonempty(df, "Sector")

with tab_add:
    st.markdown("### Add a new incident")
    with st.form("add_incident_form", clear_on_submit=True):
        a1, a2, a3 = st.columns(3)
        with a1:
            new_year = st.number_input(
                "Year",
                min_value=1900,
                max_value=2100,
                value=2026,
                step=1,
            )
            new_country = st.text_input("Country/Region")
        with a2:
            new_name = st.text_input("Incident Name *")
            new_sector = st.selectbox(
                "Sector",
                options=sector_options,
                index=0 if sector_options else None,
            )
        with a3:
            new_attack_type = st.text_input("Attack Type")
            new_attacker = st.text_input("Attacker / Group")

        new_impact = st.text_area("Verified Impact Summary", height=130)
        new_source = st.text_input("Source / Verification URL")
        new_status = st.text_input("Verification Status")

        u1, u2 = st.columns(2)
        with u1:
            new_url1 = st.text_input("URL1")
            new_url2 = st.text_input("URL2")
        with u2:
            new_url3 = st.text_input("URL3")
            new_url4 = st.text_input("URL4")

        add_submit = st.form_submit_button("Add incident", type="primary")

    if add_submit:
        if not new_name.strip():
            st.error("Incident Name is required.")
        else:
            new_row = pd.DataFrame([{
                "Year": int(new_year),
                "Incident Name": new_name.strip(),
                "Country/Region": new_country.strip(),
                "Sector": new_sector.strip() if new_sector else "",
                "Attack Type": new_attack_type.strip(),
                "Attacker / Group": new_attacker.strip(),
                "Verified Impact Summary": new_impact.strip(),
                "Source / Verification URL": new_source.strip(),
                "Verification Status": new_status.strip(),
                "URL1": new_url1.strip(),
                "URL2": new_url2.strip(),
                "URL3": new_url3.strip(),
                "URL4": new_url4.strip(),
            }])
            updated = pd.concat([df, new_row], ignore_index=True)
            set_session_dataset(updated)
            st.success(f"Added: {new_name.strip()}")
            st.rerun()

with tab_edit:
    st.markdown("### Edit an existing incident")

    if filtered.empty:
        st.info("No records match the current filters.")
    else:
        edit_options = filtered["_row_id"].tolist()

        def edit_label(row_id: int) -> str:
            row = df.loc[row_id]
            year = row["Year"]
            return (
                f"#{row_id + 1} — {row['Incident Name']} "
                f"({year}, {row['Sector']})"
            )

        edit_id = st.selectbox(
            "Select incident",
            options=edit_options,
            format_func=edit_label,
            key="edit_record_id",
        )
        current = df.loc[edit_id]

        with st.form("edit_incident_form"):
            e1, e2, e3 = st.columns(3)
            with e1:
                current_year = pd.to_numeric(current["Year"], errors="coerce")
                current_year = int(current_year) if pd.notna(current_year) else 2026
                edit_year = st.number_input(
                    "Year",
                    min_value=1900,
                    max_value=2100,
                    value=current_year,
                    step=1,
                )
                edit_country = st.text_input(
                    "Country/Region",
                    value=str(current["Country/Region"]),
                )
            with e2:
                edit_name = st.text_input(
                    "Incident Name *",
                    value=str(current["Incident Name"]),
                )
                current_sector = str(current["Sector"])
                sector_edit_options = sector_options.copy()
                if current_sector and current_sector not in sector_edit_options:
                    sector_edit_options.append(current_sector)
                    sector_edit_options = sorted(sector_edit_options)
                edit_sector = st.selectbox(
                    "Sector",
                    sector_edit_options,
                    index=sector_edit_options.index(current_sector)
                    if current_sector in sector_edit_options else 0,
                )
            with e3:
                edit_attack_type = st.text_input(
                    "Attack Type",
                    value=str(current["Attack Type"]),
                )
                edit_attacker = st.text_input(
                    "Attacker / Group",
                    value=str(current["Attacker / Group"]),
                )

            edit_impact = st.text_area(
                "Verified Impact Summary",
                value=str(current["Verified Impact Summary"]),
                height=150,
            )
            edit_source = st.text_input(
                "Source / Verification URL",
                value=str(current["Source / Verification URL"]),
            )
            edit_status = st.text_input(
                "Verification Status",
                value=str(current["Verification Status"]),
            )

            eu1, eu2 = st.columns(2)
            with eu1:
                edit_url1 = st.text_input("URL1", value=str(current["URL1"]))
                edit_url2 = st.text_input("URL2", value=str(current["URL2"]))
            with eu2:
                edit_url3 = st.text_input("URL3", value=str(current["URL3"]))
                edit_url4 = st.text_input("URL4", value=str(current["URL4"]))

            edit_submit = st.form_submit_button("Save changes", type="primary")

        if edit_submit:
            if not edit_name.strip():
                st.error("Incident Name is required.")
            else:
                updated = df.copy()
                updated.loc[edit_id, COLUMNS] = [
                    int(edit_year),
                    edit_name.strip(),
                    edit_country.strip(),
                    edit_sector.strip(),
                    edit_attack_type.strip(),
                    edit_attacker.strip(),
                    edit_impact.strip(),
                    edit_source.strip(),
                    edit_status.strip(),
                    edit_url1.strip(),
                    edit_url2.strip(),
                    edit_url3.strip(),
                    edit_url4.strip(),
                ]
                set_session_dataset(updated)
                st.success(f"Updated: {edit_name.strip()}")
                st.rerun()

with tab_delete:
    st.markdown("### Delete an incident")

    if filtered.empty:
        st.info("No records match the current filters.")
    else:
        delete_options = filtered["_row_id"].tolist()

        def delete_label(row_id: int) -> str:
            row = df.loc[row_id]
            return f"#{row_id + 1} — {row['Incident Name']} ({row['Year']}, {row['Sector']})"

        delete_id = st.selectbox(
            "Select incident to delete",
            options=delete_options,
            format_func=delete_label,
            key="delete_record_id",
        )
        target = df.loc[delete_id]

        st.warning(
            f"You are about to delete **{target['Incident Name']}**. "
            "This deletion affects the current session dataset."
        )
        confirm_delete = st.checkbox(
            "I confirm that I want to delete this incident",
            key="confirm_delete",
        )

        if st.button(
            "Delete incident",
            type="primary",
            disabled=not confirm_delete,
        ):
            updated = df.drop(index=delete_id).reset_index(drop=True)
            set_session_dataset(updated)
            st.success(f"Deleted: {target['Incident Name']}")
            st.rerun()

with tab_export:
    st.markdown("### Export current dataset")
    current_df = get_session_dataset()

    if st.session_state.get("dataset_dirty", False):
        st.warning(
            "The current session has changes that are not yet in GitHub. "
            "Download this CSV and replace `data/incidents.csv` in the repository."
        )
    else:
        st.success("The current session matches the repository dataset.")

    st.download_button(
        "⬇ Download current CSV",
        data=csv_bytes(current_df),
        file_name="incidents.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.markdown("### Reset")
    st.write(
        "Reset discards all add/edit/delete changes made in this Streamlit session "
        "and reloads the CSV bundled with the GitHub deployment."
    )
    if st.button("Reset to repository CSV"):
        reset_session_dataset()
        st.success("Dataset reset.")
        st.rerun()

st.caption(
    "Persistence note: Streamlit Community Cloud is not a database. "
    "For now, CRUD changes live in the session and become permanent only after "
    "you download the updated CSV and commit it to GitHub."
)
