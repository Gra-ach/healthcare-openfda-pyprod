# openfda-healthcare-pyprod

A pure Python InterSystems IRIS Interoperability production built with the **PyProd** package.

This project demonstrates an end-to-end healthcare interoperability flow that calls the public **openFDA Drug Adverse Event API**, rotates through a configured list of common medications, analyzes each returned batch of adverse-event reports, and stores batch-level healthcare analytics in an IRIS SQL table.

The production is implemented entirely in Python using PyProd business hosts.

> Important: FAERS/openFDA adverse-event reports are surveillance reports. They are not proof that a drug caused a reported event.

This project builds on the concepts demonstrated in the Electric Utility PyProd example [smart-grid-pyprod](https://openexchange.intersystems.com/package/smart-grid-pyprod) by introducing integration with an external REST API, making it a more advanced interoperability production that combines online data retrieval, batch analytics, and persistent storage.

---

## What the production does

```text
openFDA Drug Event API
        |
        v
OpenFDAInboundAdapter
        |
        v
OpenFDAEventService
        |
        v
OpenFDAAnalysisProcess
        |
        v
OpenFDADBOperation
        |
        v
HealthOps.OpenFDAAdverseEvents
```

The production:

1. Rotates through a configured list of medication names.
2. Calls the openFDA Drug Adverse Event API for the selected medication.
3. Saves the raw API response as a JSON payload file.
4. Sends only lightweight metadata through the production message flow.
5. Analyzes the full JSON payload from disk.
6. Calculates batch-level healthcare metrics:
   - record count
   - serious adverse-event count
   - serious adverse-event rate
   - death count
   - hospitalization count
   - average patient age
   - most frequent reaction term
7. Sends one `AdverseEventAnalysisMessage` for the whole batch.
8. Creates the SQL table automatically if it does not exist.
9. Inserts one summary row per API batch.
10. Archives the processed JSON payload file.

---

## Project structure

```text
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── merge.cpf
├── iris.script
├── module.xml
├── README.md
└── src/
    └── healthcare-openfda-pyprod/
        ├── controls.py
        └── openfda_adverse_events.py
```

---

## Main production class

```text
HealthOps.OpenFDAHealthcareProduction
```

---

## Interoperability components

| Component | Class | Purpose |
|---|---|---|
| Inbound adapter | `HealthOps.OpenFDAInboundAdapter` | Selects the next medication, calls the openFDA API, and saves the response to a JSON file |
| Business service | `HealthOps.OpenFDAEventService` | Forwards the file metadata message to the business process |
| Business process | `HealthOps.OpenFDAAnalysisProcess` | Reads the JSON file and calculates batch-level healthcare analytics |
| Business operation | `HealthOps.OpenFDADBOperation` | Creates the SQL table, inserts one batch summary row, and archives the payload file |

---

## Default medication rotation

The production rotates through these medication names by default:

```text
ASPIRIN, IBUPROFEN, ACETAMINOPHEN, NAPROXEN, LORATADINE
```

The current index is stored in:

```text
/home/irisowner/dev/Data/last_med_index.txt
```

On each adapter poll, the next medication is selected and used to build an openFDA query like:

```text
patient.drug.medicinalproduct:"ASPIRIN"
```

You can change the medication list in the Production Configuration page by editing the adapter setting:

```text
medication_names
```

Example value:

```text
ASPIRIN,IBUPROFEN,CETIRIZINE,LORATADINE,DIPHENHYDRAMINE
```

---

## File-based payload handling

To avoid IRIS `<MAXSTRING>` issues with large JSON payloads, this production does **not** pass the full API response through a PyProd message.

Instead:

1. The inbound adapter writes the raw API response to disk.
2. The message contains only:
   - API URL
   - search query
   - selected medication
   - pull timestamp
   - payload file path
3. The business process and operation read the JSON payload from the file path.

Payload files are written to:

```text
/home/irisowner/dev/Data/payloads
```

After successful database insertion, they are moved to:

```text
/home/irisowner/dev/Data/archive
```

---

## SQL table

The table is created automatically by the business operation:

```text
HealthOps.OpenFDAAdverseEvents
```

This version stores **one row per API batch**, not one row per individual adverse-event report.

| Column | Description |
|---|---|
| `id` | Auto-generated primary key |
| `payload_file_path` | Path to the JSON payload file that was processed |
| `api_url` | Full openFDA API URL used for the request |
| `search_query` | openFDA search query used for the selected medication |
| `pulled_at` | Timestamp when the API call was made |
| `batch_record_count` | Number of records returned in the API batch |
| `batch_serious_count` | Number of records marked serious |
| `batch_serious_rate_pct` | Percentage of records marked serious |
| `batch_death_count` | Number of records with death seriousness flag |
| `batch_hospitalization_count` | Number of records with hospitalization seriousness flag |
| `batch_avg_patient_age_years` | Average patient age normalized to years when available |
| `batch_top_reaction` | Most frequently reported reaction term in the batch |
| `batch_top_reaction_count` | Number of occurrences for the top reaction |
| `medicine` | Medication selected for this batch |
| `inserted_at` | Row insert timestamp |

---

## Query the results

```sql
SELECT TOP 25
    id,
    medicine,
    pulled_at,
    batch_record_count,
    batch_serious_count,
    batch_serious_rate_pct,
    batch_death_count,
    batch_hospitalization_count,
    batch_avg_patient_age_years,
    batch_top_reaction,
    batch_top_reaction_count
FROM HealthOps.OpenFDAAdverseEvents
ORDER BY id DESC;
```

---

## Build with Docker

```bash
git clone https://github.com/Gra-ach/healthcare-openfda-pyprod.git
cd healthcare-openfda-pyprod
docker-compose up --build -d
```

---

## Open the IRIS Management Portal

```text
http://localhost:62773/csp/sys/UtilHome.csp
```

Default development credentials in this project:

```text
Username: _SYSTEM
Password: SYS
Namespace: ENSEMBLE
```

---

## Start the production

```bash
python controls.py start HealthOps.OpenFDAHealthcareProduction
```

Or from the IRIS terminal:

```objectscript
zn "ENSEMBLE"
do ##class(Ens.Director).StartProduction("HealthOps.OpenFDAHealthcareProduction")
```

---

## Stop the production

```bash
python controls.py stop
```

---

## Check production status

```bash
python controls.py status
```

---

## View production messages

```bash
python controls.py messages OpenFDAEventService
python controls.py messages OpenFDAAnalysisProcess
python controls.py messages OpenFDADBOperation
```

---

## Run without Docker

Install dependencies into the Python environment that can connect to IRIS:

```bash
python -m pip install intersystems-pyprod
```

Set the expected environment variables:

```bash
export IRISINSTALLDIR=/usr/irissys
export IRISUSERNAME=SuperUser
export IRISPASSWORD=SYS
export IRISNAMESPACE=ENSEMBLE
export PYTHONPATH=$IRISINSTALLDIR/lib/python:$IRISINSTALLDIR/mgr/python
export PATH=$IRISINSTALLDIR/mgr/python/bin:$IRISINSTALLDIR/bin:$PATH
```

Load the production classes:

```bash
intersystems_pyprod src/healthcare-openfda-pyprod/openfda_adverse_events.py
```

Start the production:

```bash
python controls.py start HealthOps.OpenFDAHealthcareProduction
```

---

## Default adapter settings

```python
adapter_settings={
    "api_base_url": "https://api.fda.gov/drug/event.json",
    "medication_names": "ASPIRIN,IBUPROFEN,ACETAMINOPHEN,NAPROXEN,LORATADINE",
    "result_limit": 30,
    "api_key": "",
    "payload_dir": "/home/irisowner/dev/Data/payloads"
}
```

`api_key` is optional. openFDA allows unauthenticated access for lower-volume use, but an API key may be useful for higher request limits.

---

## Files generated by PyProd

Running `intersystems_pyprod` loads the Python production components into IRIS as interoperability classes under the `HealthOps` package.

---

## Development notes

This production intentionally stores only batch-level analytics in SQL. The raw source data is preserved as archived JSON payload files instead of being inserted as large JSON strings. This avoids large string limits and keeps the interoperability message flow lightweight.

---

## License

MIT