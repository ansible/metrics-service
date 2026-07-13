# Segment Send Architecture

Comparison of the old dispatcherd-based send path and the new APScheduler-native path introduced on `feat/segment-web-container-batch-send`.

---

## Old flow — dispatcherd (sync_mode=True, no gzip)

```mermaid
sequenceDiagram
    participant C as Cron (3 AM)
    participant D as dispatcherd
    participant A as APScheduler
    participant DB as Postgres
    participant SS as StorageSegment
    participant SEG as Segment API

    C->>D: daily_anonymize_and_prepare
    D->>DB: create AnonymizedMetricsPayload (pending)
    D->>DB: create Task record (send_anonymized_to_segment)<br/>scheduled_time = now + random(1–240 min)
    DB-->>A: _periodic_database_sync picks up Task
    A->>D: submit_task_to_dispatcher(task)
    D->>D: execute send_anonymized_to_segment()
    D->>SS: StorageSegment.put()
    note over SS: sync_mode=True<br/>no gzip
    loop for each chunk (24 KB limit)
        SS->>SEG: POST /v1/track (uncompressed)
        SEG-->>SS: 200 OK
    end
    D->>DB: payload.status = "sent"
```

---

## New flow — APScheduler-native (sync_mode=False, gzip=True)

```mermaid
sequenceDiagram
    participant C as Cron (3 AM)
    participant D as dispatcherd
    participant A as APScheduler<br/>(web process)
    participant DB as Postgres
    participant CL as analytics.Client<br/>(persistent, module-level)
    participant SEG as Segment API

    C->>D: daily_anonymize_and_prepare
    D->>DB: create AnonymizedMetricsPayload (pending)<br/>no Task record created

    loop every 5 minutes
        A->>DB: poll AnonymizedMetricsPayload<br/>status=pending/retry
        note over A: skip if created + jitter(segment_user_id) > now
        A->>CL: track() × N chunks
        note over CL: chunks queued in SDK<br/>background thread
        A->>CL: flush()
        CL->>SEG: POST /v1/batch (gzip compressed)<br/>all N chunks in one request
        SEG-->>CL: 200 OK
        A->>DB: payload.status = "sent"
    end
```

---

## Jitter distribution — 4000 customers over 24 hours

```mermaid
xychart-beta
    title "Expected sends per minute (4000 customers, 1440-minute window)"
    x-axis "Time after 3 AM cron (hours)" [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
    y-axis "Sends per hour" 0 --> 200
    bar [167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167, 167]
```

SHA-256 of `segment_user_id` gives a uniform distribution across the 1440-minute window.

| Customers | Window | Avg sends/min | Avg sends/hour |
|----------:|-------:|--------------:|---------------:|
| 200 | 240 min (old) | 0.8 | 50 |
| 4 000 | 240 min (old) | **16.7** | **1 000** |
| 4 000 | 1 440 min (new) | **2.8** | **167** |
| 10 000 | 1 440 min (new) | 6.9 | 417 |

---

## Wire size impact per payload

Each payload is split into chunks at the `StorageSegment.REGULAR_MESSAGE_LIMIT` boundary (24 KB of JSON).

```mermaid
block-beta
    columns 3

    block:old["Old path"]:1
        O1["Chunk 1\n24 KB\nPOST /v1/track"]
        O2["Chunk 2\n24 KB\nPOST /v1/track"]
        O3["Chunk N\n24 KB\nPOST /v1/track"]
    end

    space

    block:new["New path"]:1
        N1["Chunk 1 + 2 + … + N\nbatched → gzip\nPOST /v1/batch"]
    end
```

| Metric | Old (sync_mode=True) | New (batch + gzip) |
|---|---|---|
| HTTP requests per payload | N (one per chunk) | **1** |
| Encoding | None (plain JSON) | **gzip** |
| Typical uncompressed size (10 chunks) | 10 × 24 KB = 240 KB | 240 KB |
| Typical wire size (10 chunks) | ~240 KB | **~30–50 KB** (~5–8× compression) |
| Segment endpoint | `/v1/track` × N | **`/v1/batch`** × 1 |
| Client lifecycle | New client per payload | **Persistent (process lifetime)** |

> **Compression note:** Metrics JSON is highly repetitive (repeated field names, numeric arrays, common strings). Gzip typically achieves 5–8× on this payload shape, so a 240 KB uncompressed payload lands around 30–50 KB on the wire.

---

## Component ownership

```mermaid
graph LR
    subgraph web["Web container (long-lived)"]
        A[APScheduler\n_poll_segment_payloads\nevery 5 min]
        CL[analytics.Client\npersistent singleton\ngzip=True]
    end

    subgraph dispatcher["dispatcherd workers (short-lived)"]
        D[daily_anonymize_and_prepare\ncreates payload only]
    end

    DB[(Postgres\nAnonymizedMetricsPayload\nstatus=pending)]
    SEG[Segment API\n/v1/batch]

    D -->|write| DB
    A -->|poll| DB
    A --> CL
    CL -->|gzip batch POST| SEG
```

The persistent client lives in the web process, which survives across daily sends.
Dispatcherd workers remain short-lived and are no longer involved in the send path.
