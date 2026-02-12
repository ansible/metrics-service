# Metrics-Service Performance Test Results

**Date of test run:** 2026-02-02

**Test Date Selected:**

- January 25, 2024
- Total events in db: 4,599,376 events
- Events on this date: 1,264,938

## Results

Collections
Snapshot (main_host): 0.56s
Hourly collection total: 510.2s (8.5 min)
    job_host_summary: 3.9s total, peak 1124.1 MB
    main_jobevent: 506.3s total, peak 1122.0 MB

Rollup:     218.80s, 626.6 MB after
Total (collections + rollup):      729.5s (12.2 min)
Baseline memory: 982.3 MB
Peak memory:     1122.1 MB
Delta:           139.7 MB
