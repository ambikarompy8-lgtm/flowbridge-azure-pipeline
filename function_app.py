"""
FlowBridge Sync Engine — Azure Function: transform_contacts
============================================================
Blob trigger: fires when ADF drops raw JSON into bronze/contacts/{date}/{filename}
Reads raw CRM data → cleanses & normalises → writes to silver layer
Mirrors FlowBridge's AI field mapping step

Architecture:
  ADF Schedule Trigger
    → Copy Data: source API → ADLS bronze/contacts/YYYY-MM-DD/raw.json
    → This Function triggers automatically
    → Writes clean JSON to silver/contacts/YYYY-MM-DD/clean_raw.json
    → ADF Copy Data: silver → Azure SQL (upsert on contact_id)
"""

import azure.functions as func
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ── helpers ──────────────────────────────────────────────────────────────────

def clean_phone(raw: str) -> str:
    """Strip non-numeric chars, keep leading +."""
    return re.sub(r"[^\d+]", "", raw or "")


def clean_email(raw: str) -> str:
    """Lowercase, strip whitespace, basic validation."""
    email = (raw or "").lower().strip()
    return email if "@" in email else ""


def clean_name(raw: str) -> str:
    """Title-case, collapse whitespace."""
    return " ".join((raw or "").split()).title()


def safe_get(obj: dict, *keys, default="") -> Any:
    """Safe nested dict getter."""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
    return obj


# ── main transform ────────────────────────────────────────────────────────────

def transform_record(record: dict) -> dict:
    """
    Normalise a single raw CRM contact record.
    Maps raw API field names → FlowBridge canonical schema.

    Raw (JSONPlaceholder / HubSpot-style) → Clean (FlowBridge gold schema)
    -----------------------------------------------------------------------
    id             → contact_id
    name           → full_name        (title-cased, whitespace collapsed)
    username       → display_name
    email          → email            (lowercased, validated)
    phone          → phone            (digits + + only)
    company.name   → company
    address.city   → city
    address.zipcode→ postcode
    website        → website
    """
    return {
        "contact_id":   record.get("id"),
        "full_name":    clean_name(record.get("name", "")),
        "display_name": record.get("username", ""),
        "email":        clean_email(record.get("email", "")),
        "phone":        clean_phone(record.get("phone", "")),
        "company":      safe_get(record, "company", "name"),
        "city":         safe_get(record, "address", "city"),
        "postcode":     safe_get(record, "address", "zipcode"),
        "website":      record.get("website", ""),
        "synced_at":    datetime.now(timezone.utc).isoformat(),
        "pipeline_ver": "1.0.0",
        "source":       "flowbridge-azure-pipeline",
    }


def validate_record(record: dict) -> tuple[bool, str]:
    """Basic data quality check — returns (is_valid, reason)."""
    if not record.get("contact_id"):
        return False, "missing contact_id"
    if not record.get("full_name"):
        return False, "missing full_name"
    if not record.get("email"):
        return False, "missing or invalid email"
    return True, "ok"


# ── azure function entry point ────────────────────────────────────────────────

@app.blob_trigger(
    arg_name="myblob",
    path="bronze/contacts/{date}/{filename}",
    connection="AzureWebJobsStorage",
)
@app.blob_output(
    arg_name="outputblob",
    path="silver/contacts/{date}/clean_{filename}",
    connection="AzureWebJobsStorage",
)
def transform_contacts(
    myblob: func.InputStream,
    outputblob: func.Out[str],
) -> None:
    """
    Entry point.  Triggered by new blob in bronze/contacts/.
    Transforms raw records and writes to silver/contacts/.
    """
    logging.info(
        "FlowBridge transform started | blob=%s | size=%d bytes",
        myblob.name,
        myblob.length,
    )

    # ── read raw data ──────────────────────────────────────────────────────
    try:
        raw_content = myblob.read()
        raw_data = json.loads(raw_content)
    except (json.JSONDecodeError, Exception) as e:
        logging.error("Failed to parse blob: %s", e)
        raise

    # normalise: handle both list and single-record payloads
    records = raw_data if isinstance(raw_data, list) else [raw_data]
    logging.info("Records to process: %d", len(records))

    # ── transform ──────────────────────────────────────────────────────────
    clean = []
    skipped = []

    for record in records:
        try:
            transformed = transform_record(record)
            valid, reason = validate_record(transformed)
            if valid:
                clean.append(transformed)
            else:
                skipped.append({"record_id": record.get("id"), "reason": reason})
        except Exception as e:
            logging.warning("Failed to transform record %s: %s", record.get("id"), e)
            skipped.append({"record_id": record.get("id"), "reason": str(e)})

    # ── write output ───────────────────────────────────────────────────────
    output = {
        "metadata": {
            "source_blob":   myblob.name,
            "processed_at":  datetime.now(timezone.utc).isoformat(),
            "total_raw":     len(records),
            "total_clean":   len(clean),
            "total_skipped": len(skipped),
            "pipeline_ver":  "1.0.0",
        },
        "contacts": clean,
        "skipped":  skipped,
    }

    outputblob.set(json.dumps(output, indent=2, ensure_ascii=False))

    logging.info(
        "FlowBridge transform complete | clean=%d | skipped=%d",
        len(clean),
        len(skipped),
    )
