-- ============================================================
-- FlowBridge Sync Engine — Azure SQL Gold Layer Schema
-- ============================================================
-- Run this once after creating your Azure SQL Database.
-- Connect with VS Code SQL extension or Azure Data Studio.
-- ============================================================

-- ── contacts (gold layer) ─────────────────────────────────────────────────
CREATE TABLE dbo.contacts (
    contact_id    INT              NOT NULL,
    full_name     NVARCHAR(255)    NOT NULL,
    display_name  NVARCHAR(100)    NULL,
    email         NVARCHAR(255)    NULL,
    phone         VARCHAR(50)      NULL,
    company       NVARCHAR(255)    NULL,
    city          NVARCHAR(100)    NULL,
    postcode      VARCHAR(20)      NULL,
    website       NVARCHAR(255)    NULL,
    synced_at     DATETIMEOFFSET   NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    pipeline_ver  VARCHAR(20)      NULL,
    source        VARCHAR(100)     NULL,
    created_at    DATETIMEOFFSET   NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    updated_at    DATETIMEOFFSET   NOT NULL DEFAULT SYSDATETIMEOFFSET(),

    CONSTRAINT PK_contacts PRIMARY KEY (contact_id)
);
GO

-- ── indexes ───────────────────────────────────────────────────────────────
-- Fast email deduplication lookup (used by ADF upsert)
CREATE UNIQUE INDEX idx_contacts_email
    ON dbo.contacts (email)
    WHERE email IS NOT NULL AND email != '';
GO

-- Fast query by sync time (used by Azure Monitor KQL dashboard)
CREATE INDEX idx_contacts_synced_at
    ON dbo.contacts (synced_at DESC);
GO

-- Full-text search on name + company (used by FlowBridge dashboard)
CREATE INDEX idx_contacts_name
    ON dbo.contacts (full_name, company);
GO

-- ── pipeline_runs audit log ───────────────────────────────────────────────
-- Tracks every ADF pipeline execution for observability
CREATE TABLE dbo.pipeline_runs (
    run_id         UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    pipeline_name  VARCHAR(100)     NOT NULL,
    status         VARCHAR(20)      NOT NULL,  -- 'success' | 'failed' | 'healing'
    records_in     INT              NULL,
    records_out    INT              NULL,
    records_skip   INT              NULL,
    error_msg      NVARCHAR(MAX)    NULL,
    started_at     DATETIMEOFFSET   NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    finished_at    DATETIMEOFFSET   NULL,
    duration_ms    INT              NULL,
    pipeline_ver   VARCHAR(20)      NULL,

    CONSTRAINT PK_pipeline_runs PRIMARY KEY (run_id)
);
GO

CREATE INDEX idx_runs_started ON dbo.pipeline_runs (started_at DESC);
CREATE INDEX idx_runs_status  ON dbo.pipeline_runs (status, started_at DESC);
GO

-- ── stored procedure: upsert contact ─────────────────────────────────────
-- Called by ADF sink with write behaviour = Stored Procedure
CREATE OR ALTER PROCEDURE dbo.usp_upsert_contact
    @contact_id    INT,
    @full_name     NVARCHAR(255),
    @display_name  NVARCHAR(100)  = NULL,
    @email         NVARCHAR(255)  = NULL,
    @phone         VARCHAR(50)    = NULL,
    @company       NVARCHAR(255)  = NULL,
    @city          NVARCHAR(100)  = NULL,
    @postcode      VARCHAR(20)    = NULL,
    @website       NVARCHAR(255)  = NULL,
    @synced_at     DATETIMEOFFSET = NULL,
    @pipeline_ver  VARCHAR(20)    = NULL,
    @source        VARCHAR(100)   = NULL
AS
BEGIN
    SET NOCOUNT ON;

    MERGE dbo.contacts AS target
    USING (SELECT
        @contact_id   AS contact_id,
        @full_name    AS full_name,
        @display_name AS display_name,
        @email        AS email,
        @phone        AS phone,
        @company      AS company,
        @city         AS city,
        @postcode     AS postcode,
        @website      AS website,
        @synced_at    AS synced_at,
        @pipeline_ver AS pipeline_ver,
        @source       AS source
    ) AS source
    ON target.contact_id = source.contact_id

    WHEN MATCHED THEN UPDATE SET
        full_name    = source.full_name,
        display_name = source.display_name,
        email        = source.email,
        phone        = source.phone,
        company      = source.company,
        city         = source.city,
        postcode     = source.postcode,
        website      = source.website,
        synced_at    = source.synced_at,
        pipeline_ver = source.pipeline_ver,
        updated_at   = SYSDATETIMEOFFSET()

    WHEN NOT MATCHED THEN INSERT (
        contact_id, full_name, display_name, email, phone,
        company, city, postcode, website, synced_at,
        pipeline_ver, source
    ) VALUES (
        source.contact_id, source.full_name, source.display_name,
        source.email, source.phone, source.company, source.city,
        source.postcode, source.website, source.synced_at,
        source.pipeline_ver, source.source
    );
END;
GO

-- ── useful queries ────────────────────────────────────────────────────────
-- Run these in Azure Data Studio to verify the pipeline is working:

-- 1. Check latest synced contacts
-- SELECT TOP 20 * FROM dbo.contacts ORDER BY synced_at DESC;

-- 2. Count records by company
-- SELECT company, COUNT(*) AS cnt FROM dbo.contacts GROUP BY company ORDER BY cnt DESC;

-- 3. Check pipeline run history
-- SELECT * FROM dbo.pipeline_runs ORDER BY started_at DESC;

-- 4. Find duplicates (should be 0 with upsert)
-- SELECT email, COUNT(*) FROM dbo.contacts GROUP BY email HAVING COUNT(*) > 1;
