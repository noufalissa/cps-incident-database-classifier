# CPS Security Incident Database + Taxonomy Classifier

This Streamlit project contains the consolidated CPS incident dataset and two working pages:

1. **Incident Database**
   - 1,207 incidents
   - filter by sector, year, country/region
   - free-text search
   - add a new incident
   - edit an existing incident
   - delete an incident
   - download the filtered dataset
   - download the current edited dataset

2. **Taxonomy Classifier**
   - preserves the existing evidence-aware classifier prototype
   - now reads the full consolidated CPS dataset

## Dataset

`data/incidents.csv`

Canonical columns:

- Year
- Incident Name
- Country/Region
- Sector
- Attack Type
- Attacker / Group
- Verified Impact Summary
- Source / Verification URL
- Verification Status
- URL1
- URL2
- URL3
- URL4

## Important: Streamlit Community Cloud persistence

The Incident Database page supports add/edit/delete in the active Streamlit session.

Streamlit Community Cloud should **not** be treated as a persistent database. The local
filesystem of a deployed app can be replaced when the app restarts/redeploys.

Therefore the safe workflow in this version is:

1. Add/edit/delete records in the web UI.
2. Click **Download current CSV**.
3. Replace `data/incidents.csv` in the GitHub repository with the downloaded file.
4. Commit the change.
5. Streamlit redeploys using the updated dataset.

A later version can write directly back to GitHub by using a GitHub token stored in
Streamlit Secrets, or use an external database.

## GitHub update

Replace/upload these project files to your repository:

```text
app.py
data_store.py
taxonomy.py
classifier.py
fetcher.py
batch_processor.py
batch_run.py
requirements.txt
data/incidents.csv
pages/1_Incident_Database.py
pages/2_Taxonomy_Classifier.py
.streamlit/config.toml
```

The Streamlit entrypoint remains:

```text
app.py
```

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```
