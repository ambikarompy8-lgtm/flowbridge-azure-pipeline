"""
FlowBridge — Azure Event Hubs Streaming
=========================================
Two parts:
  1. EventProducer  — sends contact/deal events to Event Hub (real-time path)
  2. stream_processor (Azure Function) — consumes events, processes immediately

Architecture:
  HubSpot webhook → EventProducer → Event Hub → stream_processor Function
                                                      ↓
                                              ADLS silver + Azure SQL
                                              (seconds, not hours)

vs. batch path:
  ADF schedule → REST API → ADLS bronze → transform Function → SQL
  (hourly — catches anything the webhook missed)

Both paths write to the same Azure SQL table — the streaming path wins on
recency, the batch path wins on completeness. Together = no missed records.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import azure.functions as func
from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient, EventHubConsumerClient

logger = logging.getLogger(__name__)


# ── producer (called by webhook handler / HubSpot connector) ─────────────

class FlowBridgeEventProducer:
    """
    Sends FlowBridge sync events to Azure Event Hub.
    Use this when a HubSpot/Xero webhook arrives for real-time processing.
    """

    def __init__(self, connection_str: str, hub_name: str):
        self._conn_str = connection_str
        self._hub_name = hub_name

    async def send_contact_event(self, contact: dict, event_type: str = "contact.updated") -> None:
        """Send a single contact event to the Event Hub."""
        envelope = {
            "event_type":  event_type,                          # contact.created | contact.updated
            "source":      "hubspot",
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "pipeline_ver": "1.0.0",
            "data":         contact,
        }
        async with EventHubProducerClient.from_connection_string(
            conn_str   = self._conn_str,
            eventhub_name = self._hub_name,
        ) as producer:
            batch = await producer.create_batch()
            batch.add(EventData(json.dumps(envelope)))
            await producer.send_batch(batch)
            logger.info("Event sent: %s | contact_id=%s", event_type, contact.get("id"))

    async def send_deal_event(self, deal: dict) -> None:
        """Send a closed-won deal event (triggers Xero invoice creation)."""
        await self.send_contact_event(deal, event_type="deal.closed_won")

    async def send_batch(self, events: list[dict], event_type: str) -> None:
        """Send multiple events in one batch (more efficient for >10 records)."""
        async with EventHubProducerClient.from_connection_string(
            conn_str      = self._conn_str,
            eventhub_name = self._hub_name,
        ) as producer:
            batch = await producer.create_batch()
            for item in events:
                envelope = {
                    "event_type":  event_type,
                    "source":      "flowbridge-batch",
                    "timestamp":   datetime.now(timezone.utc).isoformat(),
                    "pipeline_ver": "1.0.0",
                    "data":         item,
                }
                try:
                    batch.add(EventData(json.dumps(envelope)))
                except ValueError:
                    # batch full — send current and start a new one
                    await producer.send_batch(batch)
                    batch = await producer.create_batch()
                    batch.add(EventData(json.dumps(envelope)))

            await producer.send_batch(batch)
            logger.info("Batch sent: %d events (type=%s)", len(events), event_type)


# ── consumer (Azure Function — Event Hub trigger) ─────────────────────────

app = func.FunctionApp()


@app.event_hub_message_trigger(
    arg_name="events",
    event_hub_name="%EVENT_HUB_NAME%",         # set in Function App settings
    connection="EVENT_HUB_CONN_STR",
    cardinality="many",                         # batch processing
    consumer_group="$Default",
)
def stream_processor(events: list[func.EventHubEvent]) -> None:
    """
    Azure Function: processes real-time contact/deal events from Event Hub.

    Triggered immediately when events arrive (seconds, not hours).
    Writes directly to ADLS silver layer + Azure SQL gold layer.

    This is the real-time complement to the ADF batch pipeline.
    """
    logger.info("stream_processor triggered: %d events", len(events))

    contacts_to_upsert = []
    invoices_to_create = []

    for event in events:
        try:
            envelope: dict[str, Any] = json.loads(event.get_body().decode("utf-8"))
            event_type = envelope.get("event_type", "")
            data       = envelope.get("data", {})

            if event_type in ("contact.created", "contact.updated"):
                clean = _clean_contact(data)
                if clean:
                    contacts_to_upsert.append(clean)

            elif event_type == "deal.closed_won":
                invoices_to_create.append(data)

            else:
                logger.warning("Unknown event type: %s", event_type)

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse event: %s", e)

    # batch write to reduce DB round-trips
    if contacts_to_upsert:
        _write_contacts_to_sql(contacts_to_upsert)

    if invoices_to_create:
        for deal in invoices_to_create:
            _create_xero_invoice_async(deal)

    logger.info(
        "stream_processor complete | contacts=%d | invoices=%d",
        len(contacts_to_upsert),
        len(invoices_to_create),
    )


def _clean_contact(raw: dict) -> dict | None:
    """Minimal transform for real-time path (mirrors function_app.py logic)."""
    props = raw.get("properties", raw)  # handle both HubSpot API and raw dict
    contact_id = raw.get("id") or props.get("contact_id")
    if not contact_id:
        return None

    return {
        "contact_id":   contact_id,
        "full_name":    f"{props.get('firstname','')} {props.get('lastname','')}".strip(),
        "email":        (props.get("email") or "").lower().strip(),
        "phone":        props.get("phone", ""),
        "company":      props.get("company", ""),
        "synced_at":    datetime.now(timezone.utc).isoformat(),
        "pipeline_ver": "1.0.0",
        "sync_path":    "streaming",           # ← tag so you know which path wrote this
    }


def _write_contacts_to_sql(contacts: list[dict]) -> None:
    """
    Bulk upsert contacts to Azure SQL gold layer.
    In production: use pyodbc + Azure AD managed identity (no passwords).
    """
    import os, pyodbc  # pyodbc installed via requirements.txt

    server   = os.environ.get("SQL_SERVER", "")
    database = os.environ.get("SQL_DATABASE", "db-contacts")

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};DATABASE={database};"
        f"Authentication=ActiveDirectoryMsi"     # managed identity — no password!
    )

    with pyodbc.connect(conn_str, timeout=10) as conn:
        cursor = conn.cursor()
        for c in contacts:
            cursor.execute(
                "EXEC dbo.usp_upsert_contact ?,?,?,?,?,?",
                c["contact_id"], c["full_name"], c["email"],
                c["phone"], c["company"], c["synced_at"],
            )
        conn.commit()
    logger.info("SQL upsert: %d contacts written (streaming path)", len(contacts))


def _create_xero_invoice_async(deal: dict) -> None:
    """Trigger Xero invoice creation for a closed deal."""
    import os
    from connectors.xero_connector import XeroConnector

    xero = XeroConnector(
        client_id     = os.environ.get("XERO_CLIENT_ID", ""),
        client_secret = os.environ.get("XERO_CLIENT_SECRET", ""),
        tenant_id     = os.environ.get("XERO_TENANT_ID", ""),
    )
    invoice = xero.create_invoice(deal, contact_name=deal.get("name", ""))
    logger.info("Xero invoice created: %s for deal %s", invoice.invoice_number, deal.get("deal_id"))
