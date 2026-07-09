import json
import os
import shutil
import csv
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

import iris
from intersystems_pyprod import (    
    BusinessProcess,
    BusinessService,
    Column,
    InboundAdapter,
    BusinessOperation,
    IRISLog,
    IRISParameter,
    IRISProperty,
    JsonSerialize,
    OperationItem,
    ProcessItem,
    Production,
    ServiceItem,
    Status
)

iris_package_name = "HealthOps"

OPENFDA_ROOT = "/home/irisowner/dev/Data"


class AdverseEventFileMessage(JsonSerialize):
    api_url: str = Column()
    search_query: str = Column()
    pulled_at: str = Column()
    payload_file_path: str = Column()
    medicine: str = Column()


class AdverseEventAnalysisMessage(JsonSerialize):
    api_url: str = Column()
    search_query: str = Column()
    pulled_at: str = Column()
    payload_file_path: str = Column()
    record_count: int = Column()
    serious_count: int = Column()
    serious_rate_pct: float = Column()
    death_count: int = Column()
    hospitalization_count: int = Column()
    avg_patient_age_years: float = Column()
    top_reaction: str = Column()
    top_reaction_count: int = Column()
    medicine: str = Column()


class OpenFDAInboundAdapter(InboundAdapter):
    api_base_url: str = IRISProperty(
        description="openFDA Drug Adverse Event API URL",
        settings="API Settings",
    )
    result_limit: int = IRISProperty(
        description="Number of records to retrieve per poll",
        settings="API Settings",
    )
    api_key: str = IRISProperty(
        description="Optional openFDA API key",
        settings="API Settings",
    )
    payload_dir: str = IRISProperty(
        description="Directory where raw openFDA JSON payloads are saved",
        settings="File Settings",
    )
    medication_names: str = IRISProperty(
        description="Comma-separated medication names to rotate through",
        settings="API Settings"
    )  

    def on_task(self):
        os.makedirs(self.payload_dir, exist_ok=True)

        meds = [
            med.strip().upper()
            for med in str(self.medication_names or "").split(",")
                if med.strip()
        ]

        if not meds:
            meds = ["ASPIRIN", "IBUPROFEN", "ACETAMINOPHEN", "NAPROXEN", "LORATADINE"]

        state_file = f"{OPENFDA_ROOT}/last_med_index.txt"
        os.makedirs(OPENFDA_ROOT, exist_ok=True)

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                last_index = int(f.read().strip())
        except Exception:
            last_index = -1

        next_index = (last_index + 1) % len(meds)
        selected_med = meds[next_index]

        with open(state_file, "w", encoding="utf-8") as f:
            f.write(str(next_index))

        search_query = f'patient.drug.medicinalproduct:"{selected_med}"'

        params = {
            "search": search_query,
            "limit": int(self.result_limit or 50),
            "sort": "receiptdate:desc",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.api_base_url}?{urllib.parse.urlencode(params)}"
        pulled_at = datetime.utcnow().isoformat(timespec="seconds")
        safe_timestamp = pulled_at.replace(":", "").replace("-", "")
        pulled_at = pulled_at.replace("T", " ")
        payload_file_path = os.path.join(
            self.payload_dir,
            f"openfda_adverse_events_{safe_timestamp}.json",
        )

        IRISLog.Info(f"Calling openFDA API: {url}")

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload_bytes = response.read()

            with open(payload_file_path, "wb") as payload_file:
                payload_file.write(payload_bytes)
        except Exception as ex:
            IRISLog.Error(f"openFDA API call or payload write failed: {ex}")
            return Status.Error()

        msg = AdverseEventFileMessage(
            api_url=url,
            search_query=search_query,
            pulled_at=pulled_at,
            payload_file_path=payload_file_path,
            medicine = selected_med
        )
        self.business_host_process_input(msg)
        return Status.OK()


class OpenFDAEventService(BusinessService):
    ADAPTER: str = IRISParameter(
        value="HealthOps.OpenFDAInboundAdapter",
        description="Pure Python CSV polling adapter"
    )
    process_target: str = IRISProperty(
        description="Business process target",
        settings="Target Settings"
    )

    def on_process_input(self, input):
        return self.send_request_async(self.process_target, input)

class OpenFDAAnalysisProcess(BusinessProcess):
    operation_target: str = IRISProperty(
        description="Operation that persists rows and analysis results",
        settings="Target Settings"
    )

    def _age_to_years(self, age_value, age_unit) -> Optional[float]:
        if age_value in ("", None):
            return None
        try:
            age = float(age_value)
        except Exception:
            return None
        unit = str(age_unit or "")
        if unit == "801":
            return age
        if unit == "802":
            return age / 12.0
        if unit == "803":
            return age / 52.0
        if unit == "804":
            return age / 365.0
        if unit == "805":
            return age / 8760.0
        return age

    def _load_records(self, payload_file_path: str):
        with open(payload_file_path, "r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload.get("results", [])

    def on_request(self, request):
        try:
            records = self._load_records(request.payload_file_path)
        except Exception as ex:
            IRISLog.Error(f"Failed to read openFDA payload file {request.payload_file_path}: {ex}")
            return Status.Error()

        record_count = len(records)
        serious_count = 0
        death_count = 0
        hospitalization_count = 0
        ages: List[float] = []
        reaction_counts: Dict[str, int] = {}

        for record in records:
            if str(record.get("serious", "")) == "1":
                serious_count += 1
            if str(record.get("seriousnessdeath", "")) == "1":
                death_count += 1
            if str(record.get("seriousnesshospitalization", "")) == "1":
                hospitalization_count += 1

            patient = record.get("patient", {}) or {}

            age_years = self._age_to_years(
                patient.get("patientonsetage"),
                patient.get("patientonsetageunit"),
            )
            if age_years is not None:
                ages.append(age_years)

            for reaction in patient.get("reaction", []) or []:
                term = reaction.get("reactionmeddrapt")
                if term:
                    reaction_counts[term] = reaction_counts.get(term, 0) + 1

        serious_rate_pct = round((serious_count / record_count) * 100, 2) if record_count else 0.0
        avg_patient_age_years = round(sum(ages) / len(ages), 2) if ages else 0.0

        top_reaction = ""
        top_reaction_count = 0
        if reaction_counts:
            top_reaction, top_reaction_count = max(reaction_counts.items(), key=lambda item: item[1])

        analysis = AdverseEventAnalysisMessage(
            api_url=request.api_url,
            search_query=request.search_query,
            pulled_at=request.pulled_at,
            payload_file_path=request.payload_file_path,
            record_count=record_count,
            serious_count=serious_count,
            serious_rate_pct=serious_rate_pct,
            death_count=death_count,
            hospitalization_count=hospitalization_count,
            avg_patient_age_years=avg_patient_age_years,
            top_reaction=top_reaction,
            top_reaction_count=top_reaction_count,
            medicine = request.medicine
        )

        IRISLog.Info(
            f"Batch analysis complete: "
            f"medicine={request.medicine}, "
            f"records={record_count}, "
            f"serious={serious_count}, "
            f"serious_rate={serious_rate_pct}%, "
            f"deaths={death_count}, "
            f"hospitalizations={hospitalization_count}, "
            f"avg_age={avg_patient_age_years}, "
            f"top_reaction={top_reaction}"
        )

        return self.send_request_async(self.operation_target, analysis, response_required=0)


class OpenFDADBOperation(BusinessOperation):
    archive_payload_dir: str = IRISProperty(
        description="Directory where successfully processed JSON payloads are archived",
        settings="Operation Settings"
    )

    message_map = {
        f"{iris_package_name}.AdverseEventAnalysisMessage": "save_events"
    }

    def _ensure_table(self):
        ddl = """
        CREATE TABLE IF NOT EXISTS HealthOps.OpenFDAAdverseEvents (
            id INTEGER IDENTITY PRIMARY KEY,            
            payload_file_path VARCHAR(1000),
            api_url LONGVARCHAR,
            search_query VARCHAR(1000),
            pulled_at TIMESTAMP,
            batch_record_count INTEGER,
            batch_serious_count INTEGER,
            batch_serious_rate_pct NUMERIC(6,2),
            batch_death_count INTEGER,
            batch_hospitalization_count INTEGER,
            batch_avg_patient_age_years NUMERIC(10,2),
            batch_top_reaction VARCHAR(255),
            batch_top_reaction_count INTEGER,
            medicine VARCHAR(60),
            inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        iris.sql.prepare(ddl).execute()    
    
    def save_events(self, request):
        self._ensure_table()       

        insert_sql = """
        INSERT INTO HealthOps.OpenFDAAdverseEvents (
            payload_file_path,
            api_url, search_query, pulled_at, batch_record_count,
            batch_serious_count, batch_serious_rate_pct, batch_death_count,
            batch_hospitalization_count, batch_avg_patient_age_years,
            batch_top_reaction, batch_top_reaction_count, medicine
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        stmt = iris.sql.prepare(insert_sql)
       
        stmt.execute(
            request.payload_file_path,
            request.api_url,
            request.search_query,
            request.pulled_at,
            int(request.record_count),
            int(request.serious_count),
            float(request.serious_rate_pct),
            int(request.death_count),
            int(request.hospitalization_count),
            float(request.avg_patient_age_years),
            request.top_reaction,
            int(request.top_reaction_count),
            request.medicine
        )
        
        os.makedirs(self.archive_payload_dir, exist_ok=True)
        archive_path = os.path.join(self.archive_payload_dir, os.path.basename(request.payload_file_path))
        try:
            os.replace(request.payload_file_path, archive_path)
        except Exception as ex:
            IRISLog.Warning(
                f"Inserted records but could not archive payload file {request.payload_file_path}: {ex}"
            )

        IRISLog.Info(
            f"Inserted info about {request.medicine}: "
            f"serious_rate={request.serious_rate_pct}%, "
            f"death_count={request.death_count}, "
            f"hospitalization_count={request.hospitalization_count}, "
            f"avg_age={request.avg_patient_age_years}, "
            f"top_reaction={request.top_reaction}"
        )
        return Status.OK()


class OpenFDAHealthcareProduction(Production):
    services = [
        ServiceItem(
            "OpenFDAEventService",
            "HealthOps.OpenFDAEventService",
            host_settings={"process_target": "OpenFDAAnalysisProcess"},
            adapter_settings={
                "api_base_url": "https://api.fda.gov/drug/event.json",
                "medication_names": "ASPIRIN,IBUPROFEN,ACETAMINOPHEN,NAPROXEN,LORATADINE",
                "result_limit": 30,
                "api_key": "",
                "payload_dir": f"{OPENFDA_ROOT}/payloads"
            }
        )
    ]
    processes = [
        ProcessItem(
            "OpenFDAAnalysisProcess",
            "HealthOps.OpenFDAAnalysisProcess",
            host_settings={"operation_target": "OpenFDADBOperation"}
        )
    ]
    operations = [
        OperationItem(
            "OpenFDADBOperation",
            "HealthOps.OpenFDADBOperation",
            host_settings={"archive_payload_dir": f"{OPENFDA_ROOT}/archive"}
        )
    ]
