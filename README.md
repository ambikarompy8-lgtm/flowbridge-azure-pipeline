FlowBridge — AI Workflow Automation Platform

AI-native workflow automation and cloud analytics platform designed for SMEs, built on Microsoft Azure.

## Live Demo

🌐 https://ambikarompy8-lgtm.github.io/flowbridge-azure-pipeline/

---

## Overview

FlowBridge is an AI-native workflow automation and cloud analytics platform designed for SMEs to streamline data synchronization, ETL processing, and operational reporting using Azure-native infrastructure.

This repository contains both:

1. **The product layer** — FlowBridge UI (dashboard, workflow builder, analytics interface)
2. **The cloud backend** — scalable ETL and analytics pipelines powering workflow orchestration and operational reporting

---

## Azure Service Mapping

| FlowBridge Component         | Azure Service                       |
| ---------------------------- | ----------------------------------- |
| Workflow scheduling          | Azure Data Factory (ADF)            |
| Raw data ingestion           | Azure Data Lake Gen2 (Bronze Layer) |
| Event-driven transformations | Azure Functions (Python 3.11)       |
| Analytics datastore          | Azure SQL Database (Gold Layer)     |
| Monitoring & observability   | Azure Monitor + Log Analytics + KQL |

---

## Architecture

```text id="z01vwx"
Source APIs (HubSpot / Sheets / Shopify)
                │
                ▼
Azure Data Factory (ADF)
Scheduled + Triggered Pipelines
                │
                ▼
Azure Data Lake Gen2
Bronze Layer (Raw Storage)
                │
                ▼
Azure Functions (Python 3.11)
Transformation + Field Mapping
                │
                ▼
Azure Data Lake Gen2
Silver Layer (Cleaned Data)
                │
                ▼
Azure SQL Database
Analytics + Reporting Layer
                │
                ▼
Power BI + Operational Dashboards
```

---

## Frontend Dashboard

The FlowBridge frontend includes:

* Pipeline activity monitoring
* AI-assisted workflow builder concepts
* Azure service visualization
* SQL-backed operational analytics
* Enterprise-style access management
* Cloud workflow orchestration dashboard

---

## Quick Deploy

```bash id="s91krm"
# Prerequisites: Azure CLI, Python 3.11, Azure Functions Core Tools

git clone https://github.com/ambikarompy8-lgtm/flowbridge-azure-pipeline
cd flowbridge-azure-pipeline

chmod +x infrastructure/setup.sh
./infrastructure/setup.sh
```

The deployment provisions Azure infrastructure including Azure SQL Database, Azure Data Factory, Azure Data Lake Gen2, Azure Functions, and monitoring services.

---

## Run Tests Locally

```bash id="d20qaz"
pip install pytest
pytest functions/tests/ -v
```

---

## Project Structure

```text id="n83xpe"
flowbridge-azure-pipeline/
│
├── index.html                     # Frontend dashboard UI
├── README.md
├── main.tf                        # Terraform infrastructure
├── outputs.tf
├── variables.tf
├── schema.sql                     # Azure SQL schema
├── powerbi_views.sql              # Analytics views
├── requirements.txt
├── setup.sh                       # Azure deployment script
│
├── function_app.py                # Azure Functions
├── event_hub_streaming.py
├── hubspot_connector.py
├── xero_connector.py
│
├── pl_ingest_contacts.json        # ADF pipeline
└── deploy.yml                     # CI/CD workflow
```

---

## Business Context

Disconnected systems and manual workflows remain major operational challenges for SMEs. FlowBridge demonstrates how Azure-native automation pipelines can streamline integrations, analytics, and operational reporting using scalable cloud infrastructure.

---

## Future Enhancements

* Real-time streaming analytics
* OAuth connector integrations
* Embedded Power BI dashboards
* Role-based authentication
* AI-powered sync recommendations
* Advanced monitoring dashboards
* Automated anomaly detection
* Live Azure Functions API layer

```
```


