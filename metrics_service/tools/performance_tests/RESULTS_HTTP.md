# Metrics-Service HTTP Benchmark Results

## Scaling Comparison

| Scale  | Generator params    | Endpoints tested | Sequential p50 | Sequential p95 | Load p50 | Load p95 | Load p99 | RPS (avg) | Server mean latency | RSS memory |
|--------|---------------------|------------------|----------------|----------------|----------|----------|----------|-----------|---------------------|------------|
| Small  | J=100, T=50, H=16   | 9 of 10           | 198.0ms        | 205.3ms        | 1201.5ms | 1906.6ms | 2127.4ms | ~3.8      | 1004.8ms            | 83.9 MB    |
| Medium | J=1000, T=50, H=20  | 9 of 10           | 206.0ms        | 263.9ms        | 1098.7ms | 1704.5ms | 1902.0ms | ~4.2      | 817.3ms             | 84.5 MB    |
| Large  | J=2000, T=100, H=40 | 9 of 10           | 205.3ms        | 259.4ms        | 1159.8ms | 1703.5ms | 1964.5ms | ~4.1      | 781.4ms             | 85.0 MB    |

---

## Medium Run Detail

**Date of test run:** 2026-03-11
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
| /v1/role_definitions/      | ✓ 200  |
| /v1/role_user_assignments/ | ✓ 200  |
| /v1/role_team_assignments/ | ✓ 200  |
| /v1/feature_flags/         | ✗ 404 — skipped |
| /v1/settings/              | ✓ 200  |

### Phase 1: Sequential Latency (10 requests per endpoint)

| Endpoint                   | min     | p50     | p95     | max     |
|----------------------------|---------|---------|---------|---------|
| /v1/                       | 201.6ms | 206.5ms | 296.9ms | 361.8ms |
| /v1/organizations/         | 200.1ms | 205.9ms | 277.3ms | 295.5ms |
| /v1/teams/                 | 201.2ms | 205.9ms | 232.3ms | 245.0ms |
| /v1/users/                 | 200.5ms | 211.5ms | 276.2ms | 291.6ms |
| /v1/tasks/                 | 200.2ms | 205.4ms | 232.1ms | 242.9ms |
| /v1/role_definitions/      | 200.3ms | 204.8ms | 239.8ms | 246.2ms |
| /v1/role_user_assignments/ | 199.2ms | 205.2ms | 246.1ms | 246.7ms |
| /v1/role_team_assignments/ | 201.6ms | 208.3ms | 259.4ms | 268.9ms |
| /v1/settings/              | 202.0ms | 206.9ms | 265.6ms | 271.9ms |
| **Summary**                |         | **206.0ms** | **263.9ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1132.4ms | 1499.5ms | 1604.0ms | 4.2  |
| /v1/organizations/         | 1098.0ms | 1766.7ms | 1894.1ms | 4.2  |
| /v1/teams/                 | 1194.7ms | 1598.8ms | 1637.2ms | 4.1  |
| /v1/users/                 | 1032.9ms | 1707.5ms | 1805.9ms | 4.3  |
| /v1/tasks/                 | 1135.2ms | 1597.0ms | 1698.5ms | 4.3  |
| /v1/role_definitions/      | 1104.6ms | 1701.6ms | 1824.4ms | 4.2  |
| /v1/role_user_assignments/ | 1065.0ms | 1902.4ms | 1995.7ms | 4.2  |
| /v1/role_team_assignments/ | 1060.4ms | 1704.5ms | 1806.7ms | 4.2  |
| /v1/settings/              | 1098.3ms | 1889.2ms | 2598.7ms | 4.1  |
| **Summary**                | **1098.7ms** | **1704.5ms** | **1902.0ms** | **~4.2** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| Requests received | 255 |
| Responses sent | 255 |
| Mean latency (server-side) | 817.3ms |
| CPU time used | 25.440s |
| RSS memory (end) | 84.5 MB |

---

## Small Run Detail

**Date of test run:** 2026-03-10
**Scale:** ~368K events
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Workers:** 5 | **Requests:** 100 per endpoint

> **Note:** When using the AAP `admin` user via the gateway (`localhost:44926`),
> most endpoints returned 403. A Django superuser hitting the pod directly was
> required to benchmark all endpoints.

### Endpoint Availability

| Endpoint                  | Status |
|---------------------------|--------|
| /v1/                      | ✓ 200  |
| /v1/organizations/        | ✓ 200  |
| /v1/teams/                | ✓ 200  |
| /v1/users/                | ✓ 200  |
| /v1/tasks/                | ✓ 200  |
| /v1/role_definitions/     | ✓ 200  |
| /v1/role_user_assignments/ | ✓ 200 |
| /v1/role_team_assignments/ | ✓ 200 |
| /v1/feature_flags/        | ✗ 404 — skipped |
| /v1/settings/             | ✓ 200  |

### Phase 1: Sequential Latency (10 requests per endpoint)

| Endpoint                   | min     | p50     | p95     | max     |
|----------------------------|---------|---------|---------|---------|
| /v1/                       | 167.7ms | 197.5ms | 200.8ms | 201.1ms |
| /v1/organizations/         | 195.0ms | 197.1ms | 201.4ms | 202.7ms |
| /v1/teams/                 | 193.3ms | 198.8ms | 214.2ms | 222.8ms |
| /v1/users/                 | 169.2ms | 197.7ms | 230.8ms | 249.4ms |
| /v1/tasks/                 | 196.4ms | 199.4ms | 227.6ms | 248.1ms |
| /v1/role_definitions/      | 171.9ms | 198.2ms | 201.4ms | 202.0ms |
| /v1/role_user_assignments/ | 194.3ms | 197.0ms | 199.8ms | 200.0ms |
| /v1/role_team_assignments/ | 195.5ms | 199.2ms | 204.1ms | 206.0ms |
| /v1/settings/              | 168.3ms | 196.9ms | 200.5ms | 201.2ms |
| **Summary**                |         | **198.0ms** | **205.3ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1300.1ms | 1830.6ms | 2159.2ms | 3.7  |
| /v1/organizations/         | 1203.4ms | 1935.6ms | 2001.5ms | 3.8  |
| /v1/teams/                 | 1247.1ms | 1898.9ms | 2064.9ms | 3.8  |
| /v1/users/                 | 1030.7ms | 1436.0ms | 1744.7ms | 4.5  |
| /v1/tasks/                 | 1243.9ms | 1865.8ms | 2127.7ms | 3.7  |
| /v1/role_definitions/      | 1216.6ms | 1969.5ms | 1998.4ms | 3.7  |
| /v1/role_user_assignments/ | 1200.5ms | 1998.4ms | 2098.3ms | 3.7  |
| /v1/role_team_assignments/ | 1193.9ms | 1910.0ms | 2206.9ms | 3.8  |
| /v1/settings/              | 1204.7ms | 1887.1ms | 2194.9ms | 3.8  |
| **Summary**                | **1201.5ms** | **1906.6ms** | **2127.4ms** | **~3.8** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| Requests received | 231 |
| Responses sent | 231 |
| Mean latency (server-side) | 1004.8ms |
| CPU time used | 29.300s |
| RSS memory (end) | 83.9 MB |

---

## Large Run Detail

**Date of test run:** 2026-03-12
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
| /v1/role_definitions/      | ✓ 200  |
| /v1/role_user_assignments/ | ✓ 200  |
| /v1/role_team_assignments/ | ✓ 200  |
| /v1/feature_flags/         | ✗ 404 — skipped |
| /v1/settings/              | ✓ 200  |

### Phase 1: Sequential Latency (10 requests per endpoint)

| Endpoint                   | min     | p50     | p95     | max     |
|----------------------------|---------|---------|---------|---------|
| /v1/                       | 199.5ms | 202.9ms | 232.2ms | 254.1ms |
| /v1/organizations/         | 201.2ms | 211.8ms | 283.5ms | 313.9ms |
| /v1/teams/                 | 199.6ms | 201.1ms | 218.0ms | 230.4ms |
| /v1/users/                 | 202.9ms | 223.6ms | 338.6ms | 410.4ms |
| /v1/tasks/                 | 199.4ms | 208.5ms | 240.9ms | 242.5ms |
| /v1/role_definitions/      | 202.2ms | 205.2ms | 252.3ms | 263.8ms |
| /v1/role_user_assignments/ | 199.1ms | 227.0ms | 272.7ms | 293.7ms |
| /v1/role_team_assignments/ | 202.0ms | 214.7ms | 262.5ms | 282.9ms |
| /v1/settings/              | 200.1ms | 204.2ms | 230.9ms | 238.7ms |
| **Summary**                |         | **205.3ms** | **259.4ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1167.0ms | 1800.7ms | 1940.3ms | 4.0  |
| /v1/organizations/         | 1195.0ms | 1705.0ms | 1831.3ms | 4.0  |
| /v1/teams/                 | 1203.6ms | 1837.7ms | 1964.6ms | 3.9  |
| /v1/users/                 | 1132.4ms | 1609.0ms | 1892.1ms | 4.2  |
| /v1/tasks/                 | 1005.9ms | 1496.7ms | 1701.7ms | 4.5  |
| /v1/role_definitions/      | 1148.4ms | 1934.5ms | 2193.7ms | 4.0  |
| /v1/role_user_assignments/ | 1002.4ms | 1597.5ms | 1705.9ms | 4.6  |
| /v1/role_team_assignments/ | 1208.1ms | 1538.6ms | 1667.3ms | 4.1  |
| /v1/settings/              | 1209.7ms | 1607.1ms | 1793.1ms | 3.9  |
| **Summary**                | **1159.8ms** | **1703.5ms** | **1964.5ms** | **~4.1** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 24.740s |
| RSS memory (end) | 85.0 MB |

---
