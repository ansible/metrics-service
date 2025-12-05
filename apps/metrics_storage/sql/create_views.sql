-- ============================================================================
-- SQLite Views for Metrics Data
--
-- These views extract JSON data into queryable columns that BI tools can use.
-- Run this SQL against metricsStorage.sqlite to create the views.
-- ============================================================================

-- ============================================================================
-- 1. CONFIG METRICS VIEW
-- ============================================================================
-- Extracts configuration data into a flat, queryable structure

CREATE VIEW IF NOT EXISTS vw_config_metrics AS
SELECT
    md.id as metric_id,
    md.collected_at,
    cr.id as collection_run_id,
    cr.started_at as collection_started_at,
    cr.status as collection_status,

    -- Controller information
    json_extract(md.data, '$.controller_version') as controller_version,
    json_extract(md.data, '$.controller_url_base') as controller_url,
    json_extract(md.data, '$.install_uuid') as install_uuid,
    json_extract(md.data, '$.instance_uuid') as instance_uuid,

    -- Platform information
    json_extract(md.data, '$.platform.system') as platform_system,
    json_extract(md.data, '$.platform.release') as platform_release,
    json_extract(md.data, '$.platform.type') as platform_type,

    -- License information
    json_extract(md.data, '$.license_type') as license_type,
    json_extract(md.data, '$.license_date') as license_date,
    CAST(json_extract(md.data, '$.license_expiry') AS INTEGER) as license_expiry_days,
    CAST(json_extract(md.data, '$.total_licensed_instances') AS INTEGER) as total_licensed_instances,
    CAST(json_extract(md.data, '$.free_instances') AS INTEGER) as free_instances,
    CAST(json_extract(md.data, '$.current_instances') AS INTEGER) as current_instances,
    CAST(json_extract(md.data, '$.valid_key') AS INTEGER) as valid_license_key,

    -- Subscription information
    json_extract(md.data, '$.subscription_id') as subscription_id,
    json_extract(md.data, '$.subscription_name') as subscription_name,
    json_extract(md.data, '$.subscription_usage_model') as subscription_usage_model,
    json_extract(md.data, '$.sku') as sku,
    json_extract(md.data, '$.account_number') as account_number,

    -- Versions
    json_extract(md.data, '$.metrics_utility_version') as metrics_utility_version,

    -- Flags
    CAST(json_extract(md.data, '$.trial') AS INTEGER) as is_trial,
    CAST(json_extract(md.data, '$.compliant') AS INTEGER) as is_compliant

FROM metric_data md
JOIN metric_types mt ON md.metric_type_id = mt.id
JOIN collection_runs cr ON md.collection_run_id = cr.id
WHERE mt.name = 'config'
  AND md.was_successful = 1;


-- ============================================================================
-- 2. ANONYMIZED ROLLUPS STATISTICS VIEW
-- ============================================================================
-- Extracts aggregate statistics from anonymized rollups

CREATE VIEW IF NOT EXISTS vw_anonymized_stats AS
SELECT
    md.id as metric_id,
    md.collected_at,
    cr.id as collection_run_id,
    cr.started_at as collection_started_at,

    -- Core statistics
    CAST(json_extract(md.data, '$.statistics.modules_used_to_automate_total') AS INTEGER) as modules_used_total,
    CAST(json_extract(md.data, '$.statistics.avg_number_of_modules_used_in_a_playbooks') AS REAL) as avg_modules_per_playbook,
    CAST(json_extract(md.data, '$.statistics.hosts_automated_total') AS INTEGER) as hosts_automated_total,
    CAST(json_extract(md.data, '$.statistics.event_total') AS INTEGER) as event_total,
    CAST(json_extract(md.data, '$.statistics.jobs_total') AS INTEGER) as jobs_total,
    CAST(json_extract(md.data, '$.statistics.unique_hosts_total') AS INTEGER) as unique_hosts_total,
    CAST(json_extract(md.data, '$.statistics.jobhostsummary_total') AS INTEGER) as job_host_summary_total,

    -- Execution Environment stats
    CAST(json_extract(md.data, '$.statistics.EE_total') AS INTEGER) as ee_total,
    CAST(json_extract(md.data, '$.statistics.EE_default_total') AS INTEGER) as ee_default_total,
    CAST(json_extract(md.data, '$.statistics.EE_custom_total') AS INTEGER) as ee_custom_total

FROM metric_data md
JOIN metric_types mt ON md.metric_type_id = mt.id
JOIN collection_runs cr ON md.collection_run_id = cr.id
WHERE mt.name = 'anonymized_rollups'
  AND md.was_successful = 1;


-- ============================================================================
-- 3. MODULE USAGE VIEW
-- ============================================================================
-- Flattens the module_stats array into rows for analysis

CREATE VIEW IF NOT EXISTS vw_module_usage AS
SELECT
    md.id as metric_id,
    md.collected_at,
    cr.id as collection_run_id,

    -- Extract each module from the array
    json_extract(module.value, '$.module') as module_name,
    CAST(json_extract(module.value, '$.count') AS INTEGER) as usage_count

FROM metric_data md
JOIN metric_types mt ON md.metric_type_id = mt.id
JOIN collection_runs cr ON md.collection_run_id = cr.id
CROSS JOIN json_each(md.data, '$.module_stats') as module
WHERE mt.name = 'anonymized_rollups'
  AND md.was_successful = 1;


-- ============================================================================
-- 4. COLLECTION STATS VIEW
-- ============================================================================
-- Flattens the collection_name_stats array

CREATE VIEW IF NOT EXISTS vw_collection_usage AS
SELECT
    md.id as metric_id,
    md.collected_at,
    cr.id as collection_run_id,

    -- Extract collection stats
    json_extract(coll.value, '$.collection_name') as collection_name,
    CAST(json_extract(coll.value, '$.count') AS INTEGER) as usage_count

FROM metric_data md
JOIN metric_types mt ON md.metric_type_id = mt.id
JOIN collection_runs cr ON md.collection_run_id = cr.id
CROSS JOIN json_each(md.data, '$.collection_name_stats') as coll
WHERE mt.name = 'anonymized_rollups'
  AND md.was_successful = 1;


-- ============================================================================
-- 5. COMBINED METRICS VIEW (for BI dashboards)
-- ============================================================================
-- Joins config and anonymized stats for comprehensive reporting

CREATE VIEW IF NOT EXISTS vw_metrics_combined AS
SELECT
    config.collection_run_id,
    config.collected_at,

    -- Controller info
    config.controller_version,
    config.install_uuid,
    config.platform_system,

    -- License info
    config.license_type,
    config.total_licensed_instances,
    config.free_instances,
    config.valid_license_key,

    -- Usage stats (from anonymized rollups collected in same run)
    stats.hosts_automated_total,
    stats.jobs_total,
    stats.modules_used_total,
    stats.unique_hosts_total,
    stats.ee_total,
    stats.ee_custom_total,

    -- Calculated fields
    CASE
        WHEN config.total_licensed_instances > 0
        THEN ROUND(CAST(stats.hosts_automated_total AS REAL) / config.total_licensed_instances * 100, 2)
        ELSE NULL
    END as license_utilization_percent

FROM vw_config_metrics config
LEFT JOIN vw_anonymized_stats stats
    ON config.collection_run_id = stats.collection_run_id
    AND DATE(config.collected_at) = DATE(stats.collected_at);


-- ============================================================================
-- 6. TIME SERIES AGGREGATION VIEW
-- ============================================================================
-- Daily aggregates for trending analysis

CREATE VIEW IF NOT EXISTS vw_metrics_daily_trends AS
SELECT
    DATE(collected_at) as date,
    COUNT(DISTINCT collection_run_id) as collections_count,

    -- Averages
    AVG(hosts_automated_total) as avg_hosts_automated,
    AVG(jobs_total) as avg_jobs_total,
    AVG(total_licensed_instances) as avg_licensed_instances,

    -- Totals
    SUM(hosts_automated_total) as total_hosts_automated,
    SUM(jobs_total) as total_jobs,

    -- License compliance
    SUM(CASE WHEN valid_license_key = 1 THEN 1 ELSE 0 END) as valid_licenses_count,
    SUM(CASE WHEN valid_license_key = 0 THEN 1 ELSE 0 END) as invalid_licenses_count

FROM vw_metrics_combined
GROUP BY DATE(collected_at)
ORDER BY date DESC;


-- ============================================================================
-- 7. TOP MODULES VIEW (Most used modules across all collections)
-- ============================================================================

CREATE VIEW IF NOT EXISTS vw_top_modules AS
SELECT
    module_name,
    SUM(usage_count) as total_usage,
    COUNT(DISTINCT metric_id) as collections_count,
    AVG(usage_count) as avg_usage_per_collection,
    MAX(usage_count) as max_usage,
    MAX(collected_at) as last_seen
FROM vw_module_usage
GROUP BY module_name
ORDER BY total_usage DESC;


-- ============================================================================
-- INDEXES ON BASE TABLES (for view performance)
-- ============================================================================
-- These help views perform better by indexing the JSON extract paths

-- Index on config metrics controller_version
CREATE INDEX IF NOT EXISTS idx_config_version
ON metric_data(json_extract(data, '$.controller_version'))
WHERE json_extract(data, '$.controller_version') IS NOT NULL;

-- Index on anonymized stats hosts_total
CREATE INDEX IF NOT EXISTS idx_hosts_automated
ON metric_data(json_extract(data, '$.statistics.hosts_automated_total'))
WHERE json_extract(data, '$.statistics.hosts_automated_total') IS NOT NULL;

-- Index on anonymized stats jobs_total
CREATE INDEX IF NOT EXISTS idx_jobs_total
ON metric_data(json_extract(data, '$.statistics.jobs_total'))
WHERE json_extract(data, '$.statistics.jobs_total') IS NOT NULL;


-- ============================================================================
-- USAGE EXAMPLES
-- ============================================================================

/*
-- List all available views
SELECT name FROM sqlite_master WHERE type='view' ORDER BY name;

-- Query config metrics
SELECT
    controller_version,
    COUNT(*) as count
FROM vw_config_metrics
GROUP BY controller_version
ORDER BY count DESC;

-- Find invalid licenses
SELECT
    install_uuid,
    controller_version,
    license_type,
    collected_at
FROM vw_config_metrics
WHERE valid_license_key = 0
ORDER BY collected_at DESC;

-- Get usage trends
SELECT * FROM vw_metrics_daily_trends
WHERE date >= date('now', '-30 days')
ORDER BY date DESC;

-- Top 10 most used modules
SELECT
    module_name,
    total_usage,
    collections_count
FROM vw_top_modules
LIMIT 10;

-- Combined metrics with license utilization
SELECT
    controller_version,
    AVG(license_utilization_percent) as avg_utilization,
    AVG(hosts_automated_total) as avg_hosts,
    COUNT(*) as collections
FROM vw_metrics_combined
WHERE license_utilization_percent IS NOT NULL
GROUP BY controller_version
ORDER BY avg_utilization DESC;
*/
