-- ============================================================
-- FlowBridge — Power BI Optimised SQL Views
-- ============================================================
-- Run these after schema.sql.
-- In Power BI Desktop: Get Data → SQL Server →
--   Server: sql-flowbridge-xxx.database.windows.net
--   Database: db-contacts
--   Then import these views.
-- ============================================================

-- ── vw_contacts_enriched ──────────────────────────────────────────────────
-- Main contacts view with calculated columns for Power BI metrics
CREATE OR ALTER VIEW dbo.vw_contacts_enriched AS
SELECT
    c.contact_id,
    c.full_name,
    c.email,
    c.phone,
    c.company,
    c.city,
    c.synced_at,
    c.pipeline_ver,
    c.sync_path,                                     -- 'batch' or 'streaming'

    -- Completeness score (0–100) — use in Power BI gauge
    CAST(
        (CASE WHEN c.email   != '' AND c.email   IS NOT NULL THEN 25 ELSE 0 END +
         CASE WHEN c.phone   != '' AND c.phone   IS NOT NULL THEN 20 ELSE 0 END +
         CASE WHEN c.company != '' AND c.company IS NOT NULL THEN 25 ELSE 0 END +
         CASE WHEN c.city    != '' AND c.city    IS NOT NULL THEN 15 ELSE 0 END +
         CASE WHEN c.full_name NOT LIKE '% %'               THEN  0 ELSE 15 END)
    AS FLOAT) AS completeness_pct,

    -- Days since last sync
    DATEDIFF(day, c.synced_at, SYSDATETIMEOFFSET()) AS days_since_sync,

    -- Sync date parts for Power BI time intelligence
    CAST(c.synced_at AS DATE)  AS sync_date,
    YEAR(c.synced_at)          AS sync_year,
    MONTH(c.synced_at)         AS sync_month,
    DAY(c.synced_at)           AS sync_day,
    DATENAME(WEEKDAY, c.synced_at) AS sync_weekday

FROM dbo.contacts c;
GO

-- ── vw_sync_summary ───────────────────────────────────────────────────────
-- Daily sync summary — drives the "Records synced over time" line chart
CREATE OR ALTER VIEW dbo.vw_sync_summary AS
SELECT
    CAST(synced_at AS DATE)          AS sync_date,
    COUNT(*)                         AS total_contacts,
    COUNT(CASE WHEN email != ''  AND email  IS NOT NULL THEN 1 END) AS with_email,
    COUNT(CASE WHEN phone != ''  AND phone  IS NOT NULL THEN 1 END) AS with_phone,
    COUNT(CASE WHEN company != '' AND company IS NOT NULL THEN 1 END) AS with_company,
    AVG(CAST(
        (CASE WHEN email   != '' THEN 25 ELSE 0 END +
         CASE WHEN phone   != '' THEN 20 ELSE 0 END +
         CASE WHEN company != '' THEN 25 ELSE 0 END)
    AS FLOAT))                        AS avg_completeness_pct,
    COUNT(CASE WHEN sync_path = 'streaming' THEN 1 END) AS streaming_count,
    COUNT(CASE WHEN sync_path = 'batch'     THEN 1 END) AS batch_count
FROM dbo.contacts
GROUP BY CAST(synced_at AS DATE);
GO

-- ── vw_company_breakdown ─────────────────────────────────────────────────
-- Company-level rollup — drives the bar chart in Power BI
CREATE OR ALTER VIEW dbo.vw_company_breakdown AS
SELECT
    ISNULL(NULLIF(company, ''), 'Unknown') AS company,
    COUNT(*)                               AS contact_count,
    COUNT(DISTINCT city)                   AS city_count,
    COUNT(CASE WHEN email != '' THEN 1 END) AS contacts_with_email,
    MAX(synced_at)                         AS last_synced
FROM dbo.contacts
GROUP BY company;
GO

-- ── vw_pipeline_health ────────────────────────────────────────────────────
-- Pipeline run stats — drives the "Pipeline health" KPI cards
CREATE OR ALTER VIEW dbo.vw_pipeline_health AS
SELECT
    CAST(started_at AS DATE)              AS run_date,
    COUNT(*)                              AS total_runs,
    COUNT(CASE WHEN status='success' THEN 1 END) AS successful_runs,
    COUNT(CASE WHEN status='failed'  THEN 1 END) AS failed_runs,
    COUNT(CASE WHEN status='healing' THEN 1 END) AS healing_runs,
    SUM(records_out)                      AS total_records_synced,
    AVG(duration_ms)                      AS avg_duration_ms,
    CAST(
        100.0 * COUNT(CASE WHEN status='success' THEN 1 END) / NULLIF(COUNT(*),0)
    AS DECIMAL(5,2))                      AS success_rate_pct
FROM dbo.pipeline_runs
GROUP BY CAST(started_at AS DATE);
GO

-- ── vw_data_quality ───────────────────────────────────────────────────────
-- Data quality metrics — main FlowBridge selling point vs manual entry
CREATE OR ALTER VIEW dbo.vw_data_quality AS
SELECT
    'Total contacts'          AS metric, CAST(COUNT(*) AS VARCHAR)          AS value FROM dbo.contacts
UNION ALL SELECT 'With email',    CAST(COUNT(CASE WHEN email   !='' AND email   IS NOT NULL THEN 1 END) AS VARCHAR) FROM dbo.contacts
UNION ALL SELECT 'With phone',    CAST(COUNT(CASE WHEN phone   !='' AND phone   IS NOT NULL THEN 1 END) AS VARCHAR) FROM dbo.contacts
UNION ALL SELECT 'With company',  CAST(COUNT(CASE WHEN company !='' AND company IS NOT NULL THEN 1 END) AS VARCHAR) FROM dbo.contacts
UNION ALL SELECT 'Avg completeness %', CAST(AVG(CAST(
    (CASE WHEN email!='' THEN 25 ELSE 0 END+CASE WHEN phone!='' THEN 20 ELSE 0 END+
     CASE WHEN company!='' THEN 25 ELSE 0 END) AS FLOAT)) AS VARCHAR) FROM dbo.contacts;
GO

-- ── Power BI connection instructions ─────────────────────────────────────
-- 1. Open Power BI Desktop (free download from powerbi.microsoft.com)
-- 2. Get Data → SQL Server
-- 3. Server: <your-sql-server>.database.windows.net
-- 4. Database: db-contacts
-- 5. Data Connectivity: Import
-- 6. Select views: vw_contacts_enriched, vw_sync_summary, vw_company_breakdown,
--                  vw_pipeline_health, vw_data_quality
-- 7. Suggested visuals:
--    - Card: COUNT of contact_id from vw_contacts_enriched
--    - Line chart: sync_date vs total_contacts from vw_sync_summary
--    - Bar chart: company vs contact_count from vw_company_breakdown
--    - Gauge: avg_completeness_pct from vw_contacts_enriched
--    - Pie: batch_count vs streaming_count from vw_sync_summary
--    - Table: vw_pipeline_health with conditional formatting on success_rate_pct
