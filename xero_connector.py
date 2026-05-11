"""
FlowBridge — Xero Connector
==============================
Real Xero Accounting API v2 connector with:
  - OAuth 2.0 (Client Credentials flow for machine-to-machine)
  - Invoice creation from HubSpot closed deals
  - Contact sync (Xero contacts ↔ FlowBridge contacts)
  - Token refresh handling

Usage:
  connector = XeroConnector(
      client_id     = os.environ["XERO_CLIENT_ID"],
      client_secret = os.environ["XERO_CLIENT_SECRET"],
      tenant_id     = os.environ["XERO_TENANT_ID"],
  )
  invoice_id = connector.create_invoice(deal)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class XeroInvoice:
    """Represents a Xero invoice created from a FlowBridge deal."""
    invoice_id:    str
    invoice_number:str
    contact_name:  str
    amount:        float
    currency:      str
    due_date:      str
    status:        str
    xero_url:      str


class XeroConnector:
    """
    Xero Accounting API v2 connector for FlowBridge.

    Handles:
      - OAuth 2.0 token management (auto-refresh)
      - Invoice creation from HubSpot closed deals
      - Contact lookup / creation in Xero
    """

    AUTH_URL    = "https://identity.xero.com/connect/token"
    BASE_URL    = "https://api.xero.com/api.xro/2.0"
    SCOPE       = "accounting.transactions accounting.contacts"

    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self._client_id     = client_id
        self._client_secret = client_secret
        self._tenant_id     = tenant_id
        self._token: dict   = {}
        self._session       = requests.Session()
        self._session.headers["Accept"] = "application/json"

    # ── auth ──────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if expired."""
        now = datetime.now(timezone.utc)
        expires_at = self._token.get("expires_at", now)
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if self._token and expires_at > now + timedelta(seconds=60):
            return self._token["access_token"]

        logger.info("Requesting Xero access token")
        resp = requests.post(
            self.AUTH_URL,
            data={
                "grant_type":    "client_credentials",
                "scope":         self.SCOPE,
            },
            auth=(self._client_id, self._client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        tok = resp.json()
        self._token = {
            "access_token": tok["access_token"],
            "expires_at":   datetime.now(timezone.utc) + timedelta(seconds=tok["expires_in"] - 60),
        }
        return self._token["access_token"]

    def _headers(self) -> dict:
        return {
            "Authorization":  f"Bearer {self._get_token()}",
            "Xero-tenant-id": self._tenant_id,
            "Content-Type":   "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._session.get(
            f"{self.BASE_URL}/{path}",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._session.post(
            f"{self.BASE_URL}/{path}",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ── contacts ─────────────────────────────────────────────────────────

    def find_or_create_contact(self, name: str, email: str = "") -> str:
        """Find an existing Xero contact by name, or create a new one."""
        # search first
        results = self._get("Contacts", params={"where": f'Name="{name}"'})
        contacts = results.get("Contacts", [])
        if contacts:
            cid = contacts[0]["ContactID"]
            logger.debug("Found existing Xero contact: %s → %s", name, cid)
            return cid

        # create new
        logger.info("Creating Xero contact: %s", name)
        data = self._post("Contacts", {
            "Contacts": [{
                "Name":         name,
                "EmailAddress": email,
            }]
        })
        return data["Contacts"][0]["ContactID"]

    # ── invoices ──────────────────────────────────────────────────────────

    def create_invoice(
        self,
        deal: dict,
        contact_name: str = "",
        contact_email: str = "",
        currency: str = "GBP",
    ) -> XeroInvoice:
        """
        Create a Xero invoice from a FlowBridge / HubSpot deal.

        Args:
            deal:          Dict with keys: deal_id, name, amount, closed_at
            contact_name:  Name of the Xero contact (company or person)
            contact_email: Email for new contact creation
            currency:      ISO currency code (default GBP)

        Returns:
            XeroInvoice dataclass with invoice_id, number, URL etc.
        """
        contact_id = self.find_or_create_contact(
            name  = contact_name or deal.get("name", "Unknown"),
            email = contact_email,
        )

        due_date = (date.today() + timedelta(days=30)).isoformat()
        amount   = deal.get("amount", 0)

        payload = {
            "Invoices": [{
                "Type":        "ACCREC",        # accounts receivable
                "Contact":     {"ContactID": contact_id},
                "Date":        date.today().isoformat(),
                "DueDate":     due_date,
                "CurrencyCode": currency,
                "Status":      "AUTHORISED",
                "Reference":   f"FlowBridge-{deal.get('deal_id', '')}",
                "LineItems":   [{
                    "Description": deal.get("name", "Services"),
                    "Quantity":    1.0,
                    "UnitAmount":  float(amount),
                    "AccountCode": "200",       # sales account — change to match your chart of accounts
                    "TaxType":     "OUTPUT2",   # 20% VAT (UK) — adjust for your region
                }],
            }]
        }

        data    = self._post("Invoices", payload)
        invoice = data["Invoices"][0]

        result = XeroInvoice(
            invoice_id    = invoice["InvoiceID"],
            invoice_number= invoice.get("InvoiceNumber", ""),
            contact_name  = contact_name,
            amount        = amount,
            currency      = currency,
            due_date      = due_date,
            status        = invoice["Status"],
            xero_url      = f"https://go.xero.com/AccountsReceivable/View.aspx?invoiceID={invoice['InvoiceID']}",
        )

        logger.info(
            "Xero invoice created: %s | %s %.2f | %s",
            result.invoice_number, currency, amount, result.xero_url,
        )
        return result

    def get_unpaid_invoices(self) -> list[dict]:
        """Return all unpaid invoices (for dashboard display)."""
        data = self._get("Invoices", params={"where": 'Status="AUTHORISED"'})
        return [
            {
                "invoice_id":  inv["InvoiceID"],
                "number":      inv.get("InvoiceNumber"),
                "contact":     inv.get("Contact", {}).get("Name"),
                "amount_due":  inv.get("AmountDue", 0),
                "due_date":    inv.get("DueDateString"),
                "currency":    inv.get("CurrencyCode"),
            }
            for inv in data.get("Invoices", [])
        ]
