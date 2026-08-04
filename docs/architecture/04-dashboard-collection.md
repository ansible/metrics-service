# Dashboard Collection System

The dashboard collection system mirrors AWX job execution data into metrics-service so that the Automation Dashboard can produce ROI, cost, and trend reports. Data arrives through two routes: an hourly incremental pipeline (query AWX DB → post_collect_hook → dispatcherd sync tasks → metrics-service DB) and a one-shot initial backfill that cursor-paginates through AWX's entire job history using the retention window from `awx_cleanupsched`. Report endpoints then serve annotated `JobData` querysets directly from the metrics-service DB, while filter-dropdown endpoints hit the live AWX DB on each request.

```mermaid
flowchart TB
    subgraph awx["AWX PostgreSQL DB"]
        direction LR
        UJ["main_unifiedjob\n(jobs, status, timing)"]
        JHS["main_jobhostsummary\n(host per job)"]
        JL["main_job_labels"]
        CS["awx_cleanupsched\n(retention window)"]
        ORG["main_organization\nmain_jobtemplate\nmain_project · main_label\n(filter dropdowns)"]
    end

    subgraph collect["Hourly Collection (dispatcherd)"]
        UC["unified_jobs_dashboard\ncollector — every :05"]
        HC["job_host_summary_service\ncollector — every :10"]
    end

    subgraph hooks["post_collect_hooks → new Tasks"]
        DH["_build_dashboard_sync_hook\ncreate sync_dashboard_jobs tasks"]
        HH["_build_dashboard_host_summary_sync_hook\ncreate sync_dashboard_host_summaries tasks"]
    end

    INIT_C["initial_dashboard_collection\none-shot on first enable\nbatch backfill 5000/batch\nderives window from awx_cleanupsched"]

    subgraph store["metrics-service DB — dashboard_reports app"]
        JD["JobData\njob_id unique\nstatus · elapsed · num_hosts\ntemplate/org/project refs"]
        TM2["TemplateMetadata\nper-template time estimates\n(user-maintained)"]
        JL2["JobLabel\nM2M: JobData ↔ label_id"]
        JH2["JobHostSummary\nhost_id · host_name per job"]
        SC["SubscriptionCost\n(singleton pk=1)\nmonthly cost + hourly rate"]
        FS["FilterSet\nuser-saved filter views"]
    end

    subgraph api["Dashboard REST API"]
        FILT["/api/v1/dashboard_reports/\norganizations/ · templates/\nprojects/ · labels/\n(live AWX DB queries)"]
        RPT["/api/v1/dashboard_reports/report/\nROI · cost · trends\nAnnotated JobData queryset"]
        EXP["/api/v1/dashboard_reports/report/export/\nCSV download"]
    end

    UJ --> UC
    JHS --> HC
    CS --> INIT_C
    UC --> DH
    HC --> HH
    DH --> JD
    HH --> JH2
    INIT_C --> JD
    INIT_C --> JH2
    JD --- TM2
    JD --- JL2
    ORG --> FILT
    JD --> RPT
    SC --> RPT
    RPT --> EXP
```
