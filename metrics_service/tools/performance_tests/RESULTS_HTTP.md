# Metrics-Service HTTP Benchmark Results

## Scaling Comparison

| Scale  | Generator params    | Endpoints tested | Sequential p50 | Sequential p95 | Load p50 | Load p95 | Load p99 | RPS (avg) | RSS memory |
|--------|---------------------|------------------|----------------|----------------|----------|----------|----------|-----------|------------|
| Small  | J=100, T=50, H=16   | 10 of 10         | 202.6ms        | 296.4ms        | 1203.3ms | 1999.1ms | 2287.1ms | ~3.8      | 85.3 MB    |
| Medium | J=1000, T=50, H=20  | 10 of 10         | 202.0ms        | 232.7ms        | 1205.5ms | 2086.5ms | 2265.8ms | ~3.8      | 85.6 MB    |
| Large  | J=2000, T=100, H=40 | 10 of 10         | 203.8ms        | 296.4ms        | 1194.9ms | 1936.6ms | 2125.0ms | ~3.9      | 86.0 MB    |

> Medium and Large runs are pending re-run with the updated endpoint list
> (added `/v1/tasks/executions/`, removed `/v1/feature_flags/`).

---

## Small Run Detail

**Date of test run:** 2026-03-16
**Scale:** ~368K events
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Workers:** 5 | **Requests:** 100 per endpoint

### Endpoint Availability

| Endpoint                   | Status |
|----------------------------|--------|
| /v1/                       | ✓ 200  |
| /v1/organizations/         | ✓ 200  |
| /v1/teams/                 | ✓ 200  |
| /v1/users/                 | ✓ 200  |
| /v1/tasks/                 | ✓ 200  |
| /v1/tasks/executions/      | ✓ 200  |
| /v1/role_definitions/      | ✓ 200  |
| /v1/role_user_assignments/ | ✓ 200  |
| /v1/role_team_assignments/ | ✓ 200  |
| /v1/settings/              | ✓ 200  |

### Phase 1: Sequential Latency (10 requests per endpoint)

| Endpoint                   | min     | p50     | p95     | max     |
|----------------------------|---------|---------|---------|---------|
| /v1/                       | 193.9ms | 201.3ms | 207.4ms | 206.9ms |
| /v1/organizations/         | 193.0ms | 200.9ms | 259.4ms | 243.5ms |
| /v1/teams/                 | 198.1ms | 199.4ms | 483.4ms | 396.3ms |
| /v1/users/                 | 198.2ms | 201.0ms | 223.0ms | 218.3ms |
| /v1/tasks/                 | 200.5ms | 209.6ms | 336.7ms | 307.2ms |
| /v1/tasks/executions/      | 197.7ms | 203.8ms | 321.4ms | 296.9ms |
| /v1/role_definitions/      | 196.5ms | 202.5ms | 324.0ms | 287.4ms |
| /v1/role_user_assignments/ | 181.5ms | 201.8ms | 253.3ms | 242.3ms |
| /v1/role_team_assignments/ | 198.7ms | 202.2ms | 237.1ms | 226.7ms |
| /v1/settings/              | 200.1ms | 216.5ms | 409.7ms | 402.9ms |
| **Summary**                |         | **202.6ms** | **296.4ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1215.9ms | 1793.5ms | 1903.2ms | 3.9  |
| /v1/organizations/         | 1197.6ms | 1899.2ms | 2161.8ms | 3.9  |
| /v1/teams/                 | 1207.4ms | 1899.1ms | 2199.3ms | 3.8  |
| /v1/users/                 | 1194.6ms | 2101.3ms | 2198.1ms | 3.8  |
| /v1/tasks/                 | 1195.3ms | 2104.3ms | 2303.8ms | 3.7  |
| /v1/tasks/executions/      | 1179.2ms | 1763.7ms | 1963.5ms | 4.0  |
| /v1/role_definitions/      | 1306.4ms | 1898.6ms | 2339.7ms | 3.6  |
| /v1/role_user_assignments/ | 1297.1ms | 2297.9ms | 2493.5ms | 3.6  |
| /v1/role_team_assignments/ | 1201.1ms | 2188.7ms | 2497.4ms | 3.7  |
| /v1/settings/              | 1203.8ms | 1993.1ms | 2284.6ms | 3.8  |
| **Summary**                | **1203.3ms** | **1999.1ms** | **2287.1ms** | **~3.8** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 32.880s |
| RSS memory (end) | 85.3 MB |

---

## Medium Run Detail

**Date of test run:** 2026-03-16
**Scale:** ~4.6M events
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Workers:** 5 | **Requests:** 100 per endpoint

### Endpoint Availability

| Endpoint                   | Status |
|----------------------------|--------|
| /v1/                       | ✓ 200  |
| /v1/organizations/         | ✓ 200  |
| /v1/teams/                 | ✓ 200  |
| /v1/users/                 | ✓ 200  |
| /v1/tasks/                 | ✓ 200  |
| /v1/tasks/executions/      | ✓ 200  |
| /v1/role_definitions/      | ✓ 200  |
| /v1/role_user_assignments/ | ✓ 200  |
| /v1/role_team_assignments/ | ✓ 200  |
| /v1/settings/              | ✓ 200  |

### Phase 1: Sequential Latency (10 requests per endpoint)

| Endpoint                   | min     | p50     | p95     | max     |
|----------------------------|---------|---------|---------|---------|
| /v1/                       | 197.4ms | 203.2ms | 252.8ms | 237.6ms |
| /v1/organizations/         | 199.0ms | 201.3ms | 207.1ms | 206.4ms |
| /v1/teams/                 | 197.9ms | 203.0ms | 287.9ms | 263.0ms |
| /v1/users/                 | 198.3ms | 199.9ms | 203.2ms | 203.1ms |
| /v1/tasks/                 | 198.5ms | 201.8ms | 235.4ms | 226.0ms |
| /v1/tasks/executions/      | 199.4ms | 201.2ms | 243.2ms | 231.8ms |
| /v1/role_definitions/      | 200.3ms | 204.3ms | 286.5ms | 261.7ms |
| /v1/role_user_assignments/ | 196.4ms | 202.1ms | 212.2ms | 209.9ms |
| /v1/role_team_assignments/ | 199.3ms | 203.6ms | 241.5ms | 237.3ms |
| /v1/settings/              | 199.6ms | 202.2ms | 238.2ms | 232.8ms |
| **Summary**                |         | **202.0ms** | **232.7ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1210.2ms | 2196.9ms | 2436.8ms | 3.7  |
| /v1/organizations/         | 1205.6ms | 1950.8ms | 2308.0ms | 3.7  |
| /v1/teams/                 | 1192.1ms | 2200.6ms | 2366.4ms | 3.8  |
| /v1/users/                 | 1292.7ms | 1996.6ms | 2197.6ms | 3.6  |
| /v1/tasks/                 | 1292.1ms | 1905.3ms | 2198.5ms | 3.7  |
| /v1/tasks/executions/      | 1292.1ms | 2264.5ms | 2393.0ms | 3.6  |
| /v1/role_definitions/      | 1260.1ms | 1834.2ms | 2098.1ms | 3.9  |
| /v1/role_user_assignments/ | 1006.1ms | 1755.9ms | 2100.3ms | 4.3  |
| /v1/role_team_assignments/ | 1201.3ms | 2094.8ms | 2102.4ms | 3.8  |
| /v1/settings/              | 1297.8ms | 1862.8ms | 2097.3ms | 3.8  |
| **Summary**                | **1205.5ms** | **2086.5ms** | **2265.8ms** | **~3.8** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 34.190s |
| RSS memory (end) | 85.6 MB |

---

## Large Run Detail

**Date of test run:** 2026-03-16
**Scale:** ~36.8M events
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Workers:** 5 | **Requests:** 100 per endpoint

### Endpoint Availability

| Endpoint                   | Status |
|----------------------------|--------|
| /v1/                       | ✓ 200  |
| /v1/organizations/         | ✓ 200  |
| /v1/teams/                 | ✓ 200  |
| /v1/users/                 | ✓ 200  |
| /v1/tasks/                 | ✓ 200  |
| /v1/tasks/executions/      | ✓ 200  |
| /v1/role_definitions/      | ✓ 200  |
| /v1/role_user_assignments/ | ✓ 200  |
| /v1/role_team_assignments/ | ✓ 200  |
| /v1/settings/              | ✓ 200  |

### Phase 1: Sequential Latency (10 requests per endpoint)

| Endpoint                   | min     | p50     | p95     | max     |
|----------------------------|---------|---------|---------|---------|
| /v1/                       | 198.7ms | 201.2ms | 348.0ms | 303.8ms |
| /v1/organizations/         | 198.6ms | 207.2ms | 326.8ms | 297.3ms |
| /v1/teams/                 | 199.5ms | 202.7ms | 306.6ms | 278.9ms |
| /v1/users/                 | 198.4ms | 201.5ms | 235.6ms | 232.7ms |
| /v1/tasks/                 | 197.3ms | 202.4ms | 209.7ms | 208.1ms |
| /v1/tasks/executions/      | 199.7ms | 202.4ms | 236.9ms | 234.0ms |
| /v1/role_definitions/      | 202.6ms | 216.0ms | 232.4ms | 231.7ms |
| /v1/role_user_assignments/ | 200.1ms | 201.5ms | 237.6ms | 228.5ms |
| /v1/role_team_assignments/ | 200.8ms | 213.5ms | 333.9ms | 322.7ms |
| /v1/settings/              | 202.3ms | 219.5ms | 319.5ms | 297.5ms |
| **Summary**                |         | **203.8ms** | **296.4ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1192.8ms | 2005.2ms | 2195.0ms | 3.8  |
| /v1/organizations/         | 1176.2ms | 1992.5ms | 2135.3ms | 3.9  |
| /v1/teams/                 | 1197.9ms | 1995.9ms | 2095.0ms | 3.8  |
| /v1/users/                 | 1198.0ms | 1886.5ms | 2097.7ms | 3.9  |
| /v1/tasks/                 | 1197.4ms | 1989.5ms | 2188.2ms | 3.8  |
| /v1/tasks/executions/      | 1148.3ms | 2103.3ms | 2272.8ms | 3.9  |
| /v1/role_definitions/      | 1198.9ms | 1970.1ms | 2194.9ms | 3.8  |
| /v1/role_user_assignments/ | 1195.9ms | 1905.9ms | 1996.6ms | 3.9  |
| /v1/role_team_assignments/ | 1200.4ms | 1665.8ms | 2122.9ms | 4.0  |
| /v1/settings/              | 1164.4ms | 1917.4ms | 2163.4ms | 4.0  |
| **Summary**                | **1194.9ms** | **1936.6ms** | **2125.0ms** | **~3.9** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 27.050s |
| RSS memory (end) | 86.0 MB |

---
