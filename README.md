# FlowBridge — Azure Sync Engine

> **AI-native SME data integration platform** | Product UI + Azure cloud backend

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com)
[![Tests](https://img.shields.io/badge/tests-14%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11-blue)]()
[![Azure](https://img.shields.io/badge/azure-data%20factory%20%7C%20functions%20%7C%20sql-0078d4)]()

## What is this?

FlowBridge is an AI-native data sync platform for SMEs — think Zapier but powered by Azure.
This repo contains both:

1. **The product** — FlowBridge UI (dashboard, AI sync builder, competitor analysis)
2. **The Azure backend** — the ETL pipeline that actually runs every sync

**Every FlowBridge feature maps to an Azure service:**

| FlowBridge feature | Azure service |
|---|---|
| Sync scheduler | Azure Data Factory (ADF) — schedule triggers |
| Raw sync buffer | Azure Data Lake Gen2 — bronze layer |
| AI field mapper | Azure Functions (Python 3.11) — blob-triggered |
| Production datastore | Azure SQL Database — gold layer (upsert) |
| Self-healing monitor | Azure Monitor + Log Analytics + KQL |

## Architecture

```
Source API (HubSpot / Sheets / Shopify)
    │
    ▼
Azure Data Factory ──── schedule trigger (hourly / daily / on-event)
    │
    ▼
ADLS Gen2: bronze/contacts/YYYY-MM-DD/raw.json   ← immutable raw data
    │ (blob trigger)
    ▼
Azure Functions: transform_contacts.py            ← field mapping + cleanse
    │
    ▼
ADLS Gen2: silver/contacts/YYYY-MM-DD/clean_*.json
    │
    ▼
Azure SQL Database: dbo.contacts                  ← gold layer (upsert)
    │
    ▼
Azure Monitor + Log Analytics                     ← KQL alerts + self-heal
```

## Quick deploy

```bash
# Prerequisites: az login, func --version, Python 3.11
git clone https://github.com/YOUR_USERNAME/flowbridge-azure-pipeline
cd flowbridge-azure-pipeline
chmod +x infrastructure/setup.sh
./infrastructure/setup.sh
```

The script creates all Azure resources (~5 min). Total cost: ~$0–5/month on free tier.

## Run tests locally

```bash
pip install pytest
pytest functions/tests/ -v
# 14 tests, 0 failures
```

## Project structure

```
flowbridge-azure-pipeline/
├── README.md
├── infrastructure/
│   └── setup.sh              # one-command Azure deploy
├── functions/
│   ├── transform_contacts/
│   │   ├── function_app.py   # Python blob-trigger transform
│   │   └── requirements.txt
│   └── tests/
│       └── test_transform.py # 14 unit tests
├── pipelines/
│   └── pl_ingest_contacts.json  # ADF pipeline JSON
├── sql/
│   └── schema.sql            # contacts table + upsert SP + indexes
└── .github/
    └── workflows/
        └── deploy.yml        # CI/CD: test → deploy Function → publish ADF
```



## Market context

- $26B workflow automation market in 2026 (Mordor Intelligence)
- 96 min/day wasted per SME owner on manual data work (Slack, 2024)
- 57% of SMBs cite disconnected systems as #1 blocker (HubSpot, 2025)
- Only 4% of businesses have fully automated any workflow (2026)

