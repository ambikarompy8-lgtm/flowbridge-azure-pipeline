"""
FlowBridge — HubSpot Connector
================================
Real HubSpot CRM API v3 connector with:
  - API key + OAuth 2.0 support
  - Pagination (handles >100 contacts)
  - Rate limit respect (HubSpot: 100 req/10s)
  - Retry with exponential backoff
  - Delta sync (only changed since last run)

Usage:
  connector = HubSpotConnector(api_key=os.environ["HUBSPOT_API_KEY"])
  contacts  = connector.get_contacts(modified_since=last_run_dt)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)


# ── data models ───────────────────────────────────────────────────────────

@dataclass
class HubSpotContact:
    """Normalised contact record — FlowBridge canonical schema."""
    contact_id:   str
    full_name:    str
    first_name:   str
    last_name:    str
    email:        str
    phone:        str
    company:      str
    job_title:    str
    city:         str
    website:      str
    hs_object_id: str
    created_at:   str
    updated_at:   str
    raw:          dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, record: dict) -> "HubSpotContact":
        """Build a canonical contact from a raw HubSpot API record."""
        props = record.get("properties", {})
        full_name = " ".join(filter(None, [
            props.get("firstname", ""),
            props.get("lastname", ""),
        ])).strip()
        return cls(
            contact_id   = record["id"],
            full_name    = full_name or props.get("email", "unknown"),
            first_name   = props.get("firstname", ""),
            last_name    = props.get("lastname", ""),
            email        = props.get("email", ""),
            phone        = props.get("phone", ""),
            company      = props.get("company", ""),
            job_title    = props.get("jobtitle", ""),
            city         = props.get("city", ""),
            website      = props.get("website", ""),
            hs_object_id = record["id"],
            created_at   = props.get("createdate", ""),
            updated_at   = props.get("lastmodifieddate", ""),
            raw          = record,
        )


# ── connector ─────────────────────────────────────────────────────────────

class HubSpotConnector:
    """
    HubSpot CRM API v3 connector for FlowBridge.

    Supports:
      - Private App tokens (recommended) and legacy API keys
      - Full sync and delta sync (modified_since parameter)
      - Automatic pagination through all contacts
      - Rate limit handling (429 → exponential backoff)
    """

    BASE_URL    = "https://api.hubapi.com"
    PAGE_SIZE   = 100  # max allowed by HubSpot API
    MAX_RETRIES = 5
    BACKOFF_FACTOR = 1.0

    CONTACT_PROPERTIES = [
        "firstname", "lastname", "email", "phone",
        "company", "jobtitle", "city", "website",
        "createdate", "lastmodifieddate",
    ]

    def __init__(self, api_key: str | None = None, access_token: str | None = None):
        if not api_key and not access_token:
            raise ValueError("Provide either api_key (Private App token) or access_token (OAuth)")

        self._session = self._build_session()
        if access_token:
            self._session.headers["Authorization"] = f"Bearer {access_token}"
        else:
            # Legacy API key — still works but Private App tokens preferred
            self._session.headers["Authorization"] = f"Bearer {api_key}"

        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent":   "FlowBridge/1.0",
        })

    def _build_session(self) -> requests.Session:
        retry = Retry(
            total           = self.MAX_RETRIES,
            backoff_factor  = self.BACKOFF_FACTOR,
            status_forcelist= [429, 500, 502, 503, 504],
            allowed_methods = ["GET", "POST"],
        )
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=retry))
        return s

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning("HubSpot rate limit hit — sleeping %ds", retry_after)
            time.sleep(retry_after)
            resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_contacts(
        self,
        modified_since: datetime | None = None,
        limit: int | None = None,
    ) -> Iterator[HubSpotContact]:
        """
        Yield all contacts (or those modified since a given datetime).

        Args:
            modified_since: Only return contacts updated after this time.
                            None = full sync (all contacts).
            limit:          Stop after this many records (useful for testing).

        Yields:
            HubSpotContact — normalised contact records
        """
        params: dict[str, Any] = {
            "limit":      self.PAGE_SIZE,
            "properties": ",".join(self.CONTACT_PROPERTIES),
            "sorts":      "lastmodifieddate",
        }

        # delta sync filter
        if modified_since:
            ts_ms = int(modified_since.timestamp() * 1000)
            params["filterGroups"] = [{
                "filters": [{
                    "propertyName": "lastmodifieddate",
                    "operator":     "GTE",
                    "value":        str(ts_ms),
                }]
            }]
            logger.info("HubSpot delta sync from %s", modified_since.isoformat())
        else:
            logger.info("HubSpot full sync")

        total_yielded = 0
        after_cursor  = None

        while True:
            if after_cursor:
                params["after"] = after_cursor

            # Use search endpoint for filtered queries, list endpoint for full sync
            if modified_since:
                data = self._post(
                    "/crm/v3/objects/contacts/search",
                    payload={**params, "after": after_cursor or 0},
                )
            else:
                data = self._get("/crm/v3/objects/contacts", params)

            results = data.get("results", [])
            logger.debug("HubSpot page: %d records", len(results))

            for record in results:
                yield HubSpotContact.from_api(record)
                total_yielded += 1
                if limit and total_yielded >= limit:
                    logger.info("HubSpot: reached limit=%d, stopping", limit)
                    return

            # pagination
            paging = data.get("paging", {})
            after_cursor = paging.get("next", {}).get("after")
            if not after_cursor:
                break

        logger.info("HubSpot sync complete: %d contacts fetched", total_yielded)

    def _post(self, path: str, payload: dict) -> dict:
        url  = f"{self.BASE_URL}{path}"
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_deals(self, modified_since: datetime | None = None) -> Iterator[dict]:
        """Fetch deals — used to trigger Xero invoice creation on close."""
        params = {
            "limit":      self.PAGE_SIZE,
            "properties": "dealname,amount,closedate,dealstage,pipeline",
        }
        data = self._get("/crm/v3/objects/deals", params)
        for deal in data.get("results", []):
            props = deal.get("properties", {})
            if props.get("dealstage") == "closedwon":
                yield {
                    "deal_id":   deal["id"],
                    "name":      props.get("dealname", ""),
                    "amount":    float(props.get("amount") or 0),
                    "closed_at": props.get("closedate", ""),
                }
