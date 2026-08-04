# System Overview

metrics-service is a Django-based telemetry service deployed as a 4-container stack. It connects read-only to the AWX/Automation Controller PostgreSQL database, aggregates and anonymizes usage metrics on a scheduled basis, and ships daily payloads to Segment.com for Red Hat telemetry. All external API access is brokered through AAP Gateway, which handles OAuth2/JWT authentication and resource registry synchronisation.

```mermaid
flowchart TB
    subgraph platform["AAP Platform"]
        GW["AAP Gateway\nOAuth2 + JWT\nService Router"]
        CTL["AWX / Automation Controller\nPostgreSQL (awx DB) — read-only"]
    end

    subgraph ms["metrics-service (4-container stack)"]
        direction LR
        INIT["init\nmigrations +\ninit-system-tasks"]
        WEB["web\nGunicorn + Nginx\nREST API :8080/:8443"]
        SCHED["scheduler\nAPScheduler\ncron dispatch"]
        DISP["dispatcherd\npg_notify workers\ntask execution"]
    end

    subgraph msdb["metrics-service PostgreSQL"]
        T["Task / TaskExecution\n(task queue)"]
        H["HourlyMetricsCollection\nDailyMetricsSummary\nAnonymizedMetricsPayload"]
        D["JobData / TemplateMetadata\nJobHostSummary\n(dashboard data)"]
        S["Setting\n(dynamic feature flags)"]
    end

    Client["Admin / BI Client"] -->|HTTPS| GW
    GW -->|"JWT auth\nresource sync"| WEB
    CTL -->|"direct SQL read-only\npsycopg3"| DISP
    WEB <-->|"Django ORM"| msdb
    SCHED -->|"INSERT Task rows\npoll every 60s"| msdb
    DISP -->|"pg_notify LISTEN/NOTIFY\nclaim + execute tasks"| msdb
    DISP -->|"anonymized daily payload\nSegment write key"| SEG["Segment.com\nRed Hat Telemetry"]
```
