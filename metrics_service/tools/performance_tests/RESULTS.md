# Metrics-Service Performance Test Results

**Date of test run:** 2026-02-16

**Test Date Selected:**

- January 25, 2024
- Total events in db: 4,599,376 events
- Events on this date: 1,264,938

## Results

Collections
Snapshot (main_host): 0.96s
Hourly collection total: 555.6s (9.3 min)
    job_host_summary: 5.7s total, peak 1869.1 MB
    main_jobevent: 549.9s total, peak 2001.1 MB

Rollup:     94.63s, 4762.7 MB after
Total (collections + rollup):      651.2s (10.9 min)
Baseline memory: 1204.8 MB
Peak memory:     4747.0 MB
Delta:           3542.2 MB
