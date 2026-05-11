#!/usr/bin/env bash
# ============================================================
# FlowBridge Azure Pipeline — One-command deploy script
# ============================================================
# Prerequisites:
#   1. az login  (run once before this script)
#   2. func --version  (Azure Functions Core Tools installed)
#   3. Python 3.11+
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# ============================================================

set -euo pipefail

# ── config — edit these ───────────────────────────────────────────────────
RESOURCE_GROUP="rg-flowbridge-pipeline"
LOCATION="eastus"
STORAGE_ACCOUNT="stflowbridge$(shuf -i 1000-9999 -n 1)"   # unique suffix
FUNCTION_STORAGE="stflowbridgefn$(shuf -i 1000-9999 -n 1)"
FUNCTION_APP="fn-flowbridge-transform"
ADF_NAME="adf-flowbridge-pipeline"
SQL_SERVER="sql-flowbridge-$(shuf -i 100-999 -n 1)"
SQL_DB="db-contacts"
SQL_ADMIN="flowbridgeadmin"
SQL_PASSWORD="FlowBridge$(shuf -i 1000-9999 -n 1)Az!"
LAW_NAME="law-flowbridge"

# ── colours ───────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${BLUE}[FlowBridge]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   FlowBridge Azure Pipeline Deploy   ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. resource group ─────────────────────────────────────────────────────
log "Creating resource group: $RESOURCE_GROUP"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none
ok "Resource group ready"

# ── 2. data lake storage (ADLS Gen2) ──────────────────────────────────────
log "Creating Data Lake Storage: $STORAGE_ACCOUNT"
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --enable-hierarchical-namespace true \
  --output none

STORAGE_KEY=$(az storage account keys list \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query "[0].value" -o tsv)

for layer in bronze silver gold; do
  az storage container create \
    --name "$layer" \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY" \
    --output none
  ok "Container created: $layer"
done

# ── 3. upload sample data to bronze ───────────────────────────────────────
log "Uploading sample CRM data to bronze layer"
TODAY=$(date +%Y-%m-%d)
curl -s "https://jsonplaceholder.typicode.com/users" -o /tmp/raw_contacts.json
az storage blob upload \
  --account-name "$STORAGE_ACCOUNT" \
  --account-key "$STORAGE_KEY" \
  --container-name bronze \
  --name "contacts/$TODAY/raw_contacts.json" \
  --file /tmp/raw_contacts.json \
  --overwrite \
  --output none
ok "Sample data uploaded to bronze/contacts/$TODAY/raw_contacts.json"

# ── 4. azure function app ─────────────────────────────────────────────────
log "Creating Function App storage: $FUNCTION_STORAGE"
az storage account create \
  --name "$FUNCTION_STORAGE" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --output none

log "Creating Function App: $FUNCTION_APP"
az functionapp create \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-account "$FUNCTION_STORAGE" \
  --consumption-plan-location "$LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux \
  --output none

# Connect function to ADLS storage
CONN_STRING=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

az functionapp config appsettings set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --settings "AzureWebJobsStorage=$CONN_STRING" \
  --output none

ok "Function App ready: $FUNCTION_APP"

# ── 5. deploy function code ───────────────────────────────────────────────
log "Deploying Python transform function"
cd functions/transform_contacts
pip install -r requirements.txt --quiet
func azure functionapp publish "$FUNCTION_APP" --python
cd ../..
ok "Function deployed"

# ── 6. azure data factory ─────────────────────────────────────────────────
log "Creating Azure Data Factory: $ADF_NAME"
az datafactory create \
  --factory-name "$ADF_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none
ok "ADF created — open Studio to build pipelines"

# ── 7. azure sql database ─────────────────────────────────────────────────
log "Creating SQL Server: $SQL_SERVER"
az sql server create \
  --name "$SQL_SERVER" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --admin-user "$SQL_ADMIN" \
  --admin-password "$SQL_PASSWORD" \
  --output none

MY_IP=$(curl -s https://api.ipify.org)
az sql server firewall-rule create \
  --server "$SQL_SERVER" \
  --resource-group "$RESOURCE_GROUP" \
  --name "AllowMyIP" \
  --start-ip-address "$MY_IP" \
  --end-ip-address "$MY_IP" \
  --output none

az sql db create \
  --server "$SQL_SERVER" \
  --resource-group "$RESOURCE_GROUP" \
  --name "$SQL_DB" \
  --edition Basic \
  --output none
ok "SQL Database ready: $SQL_DB"

# ── 8. log analytics + monitor ────────────────────────────────────────────
log "Creating Log Analytics workspace"
az monitor log-analytics workspace create \
  --workspace-name "$LAW_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none
ok "Log Analytics ready"

# ── 9. set budget alert ───────────────────────────────────────────────────
warn "Set a budget alert manually: Portal → Cost Management → Budgets → \$20/month"

# ── done ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║           DEPLOYMENT COMPLETE ✓                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Resource group : $RESOURCE_GROUP"
echo "  Data Lake      : $STORAGE_ACCOUNT"
echo "  Function App   : $FUNCTION_APP"
echo "  Data Factory   : $ADF_NAME"
echo "  SQL Server     : $SQL_SERVER"
echo "  SQL Database   : $SQL_DB"
echo "  SQL Admin      : $SQL_ADMIN"
echo "  SQL Password   : $SQL_PASSWORD  ← SAVE THIS"
echo ""
echo "Next steps:"
echo "  1. Run sql/schema.sql against $SQL_DB in Azure Data Studio"
echo "  2. Open ADF Studio → build pipelines from pipelines/*.json"
echo "  3. Watch live logs: func azure functionapp logstream $FUNCTION_APP"
echo ""
