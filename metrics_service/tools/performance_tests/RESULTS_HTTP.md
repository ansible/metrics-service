# Metrics-Service HTTP Benchmark Results

## Scaling Comparison

| Scale  | Generator params    | Endpoints tested | Sequential p50 | Sequential p95 | Load p50 | Load p95 | Load p99 | RPS (avg) | RSS memory |
|--------|---------------------|------------------|----------------|----------------|----------|----------|----------|-----------|------------|
| Small  | J=100, T=50, H=16   | 10 of 10         | 212.8ms        | 285.5ms        | 1099.1ms | 1664.9ms | 1823.7ms | ~4.3      | 85.6 MB    |
| Medium | J=1000, T=50, H=20  | 10 of 10         | 208.4ms        | 280.3ms        | 1200.3ms | 1702.8ms | 1900.6ms | ~4.0      | 85.8 MB    |
| Large  | J=2000, T=100, H=40 | 10 of 10         | 203.4ms        | 258.9ms        | 1199.9ms | 2006.0ms | 2292.3ms | ~3.8      | 86.5 MB    |

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
| /v1/                       | 203.2ms | 212.2ms | 265.6ms | 258.8ms |
| /v1/organizations/         | 202.9ms | 205.4ms | 252.4ms | 242.5ms |
| /v1/teams/                 | 198.9ms | 210.4ms | 254.5ms | 243.5ms |
| /v1/users/                 | 203.4ms | 233.0ms | 765.6ms | 614.9ms |
| /v1/tasks/                 | 204.0ms | 209.4ms | 304.4ms | 285.7ms |
| /v1/tasks/executions/      | 206.8ms | 215.1ms | 260.5ms | 255.9ms |
| /v1/role_definitions/      | 204.6ms | 212.7ms | 264.3ms | 250.7ms |
| /v1/role_user_assignments/ | 206.1ms | 215.8ms | 242.9ms | 242.4ms |
| /v1/role_team_assignments/ | 203.7ms | 220.6ms | 323.8ms | 322.0ms |
| /v1/settings/              | 200.8ms | 226.0ms | 320.3ms | 305.0ms |
| **Summary**                |         | **212.8ms** | **285.5ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1099.5ms | 1547.3ms | 1665.3ms | 4.4  |
| /v1/organizations/         | 1117.6ms | 1558.4ms | 1735.0ms | 4.3  |
| /v1/teams/                 | 1106.5ms | 1466.3ms | 1643.3ms | 4.3  |
| /v1/users/                 | 1063.6ms | 1600.5ms | 1732.4ms | 4.3  |
| /v1/tasks/                 | 1062.3ms | 1594.7ms | 1822.6ms | 4.4  |
| /v1/tasks/executions/      | 1092.3ms | 1705.6ms | 1840.1ms | 4.2  |
| /v1/role_definitions/      | 1193.9ms | 1602.3ms | 1874.6ms | 4.1  |
| /v1/role_user_assignments/ | 1099.7ms | 1665.2ms | 1835.7ms | 4.2  |
| /v1/role_team_assignments/ | 1096.9ms | 1805.3ms | 1997.6ms | 4.2  |
| /v1/settings/              | 1062.1ms | 1700.5ms | 1981.1ms | 4.2  |
| **Summary**                | **1099.1ms** | **1664.9ms** | **1823.7ms** | **~4.3** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 29.210s |
| RSS memory (end) | 85.6 MB |

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
| /v1/                       | 202.8ms | 208.4ms | 397.1ms | 349.4ms |
| /v1/organizations/         | 202.5ms | 205.1ms | 425.9ms | 379.5ms |
| /v1/teams/                 | 202.8ms | 207.8ms | 296.8ms | 280.5ms |
| /v1/users/                 | 205.7ms | 223.5ms | 253.2ms | 250.4ms |
| /v1/tasks/                 | 202.1ms | 209.4ms | 259.9ms | 251.3ms |
| /v1/tasks/executions/      | 201.3ms | 207.7ms | 247.0ms | 244.1ms |
| /v1/role_definitions/      | 201.8ms | 208.5ms | 299.5ms | 281.8ms |
| /v1/role_user_assignments/ | 197.1ms | 206.5ms | 283.3ms | 267.0ms |
| /v1/role_team_assignments/ | 198.3ms | 204.7ms | 240.7ms | 238.1ms |
| /v1/settings/              | 201.1ms | 213.0ms | 410.1ms | 362.1ms |
| **Summary**                |         | **208.4ms** | **280.3ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1121.6ms | 1899.5ms | 2063.8ms | 4.0  |
| /v1/organizations/         | 1163.3ms | 1701.0ms | 1905.6ms | 4.1  |
| /v1/teams/                 | 1200.9ms | 1591.4ms | 1885.5ms | 4.0  |
| /v1/users/                 | 1218.0ms | 1565.7ms | 2038.6ms | 4.0  |
| /v1/tasks/                 | 1182.4ms | 1804.6ms | 2002.3ms | 4.1  |
| /v1/tasks/executions/      | 1197.7ms | 1696.4ms | 1895.8ms | 4.1  |
| /v1/role_definitions/      | 1203.9ms | 1797.7ms | 1996.9ms | 3.9  |
| /v1/role_user_assignments/ | 1194.2ms | 1694.1ms | 1799.2ms | 4.1  |
| /v1/role_team_assignments/ | 1259.2ms | 1693.6ms | 1899.2ms | 3.9  |
| /v1/settings/              | 1202.8ms | 1802.8ms | 1900.6ms | 4.0  |
| **Summary**                | **1200.3ms** | **1702.8ms** | **1900.6ms** | **~4.0** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 28.450s |
| RSS memory (end) | 85.8 MB |

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
| /v1/                       | 200.2ms | 205.0ms | 327.8ms | 306.5ms |
| /v1/organizations/         | 200.6ms | 207.3ms | 308.5ms | 293.3ms |
| /v1/teams/                 | 198.0ms | 202.5ms | 215.3ms | 211.9ms |
| /v1/users/                 | 201.2ms | 204.3ms | 240.2ms | 235.2ms |
| /v1/tasks/                 | 196.0ms | 201.3ms | 207.9ms | 207.0ms |
| /v1/tasks/executions/      | 198.4ms | 202.6ms | 275.1ms | 253.8ms |
| /v1/role_definitions/      | 202.1ms | 205.9ms | 239.5ms | 233.6ms |
| /v1/role_user_assignments/ | 199.6ms | 202.5ms | 229.2ms | 224.5ms |
| /v1/role_team_assignments/ | 198.1ms | 208.4ms | 243.5ms | 241.3ms |
| /v1/settings/              | 197.6ms | 202.7ms | 205.4ms | 205.2ms |
| **Summary**                |         | **203.4ms** | **258.9ms** | |

### Phase 2: Concurrent Load (100 requests, 5 workers)

| Endpoint                   | p50      | p95      | p99      | RPS  |
|----------------------------|----------|----------|----------|------|
| /v1/                       | 1109.9ms | 2185.9ms | 2302.8ms | 3.8  |
| /v1/organizations/         | 1197.8ms | 2057.0ms | 2400.1ms | 3.8  |
| /v1/teams/                 | 1200.2ms | 1998.5ms | 2299.1ms | 3.9  |
| /v1/users/                 | 1202.7ms | 1905.7ms | 2098.8ms | 3.7  |
| /v1/tasks/                 | 1198.0ms | 2004.7ms | 2295.0ms | 3.8  |
| /v1/tasks/executions/      | 1299.3ms | 1898.0ms | 2103.5ms | 3.7  |
| /v1/role_definitions/      | 1206.7ms | 2203.2ms | 2386.4ms | 3.6  |
| /v1/role_user_assignments/ | 1194.1ms | 2093.9ms | 2201.7ms | 3.8  |
| /v1/role_team_assignments/ | 1201.5ms | 2188.6ms | 2303.6ms | 3.7  |
| /v1/settings/              | 1197.6ms | 2090.8ms | 2402.2ms | 3.8  |
| **Summary**                | **1199.9ms** | **2006.0ms** | **2292.3ms** | **~3.8** |

### Server-side Metrics (Prometheus delta)

| Metric | Value |
|--------|-------|
| CPU time used | 27.280s |
| RSS memory (end) | 86.5 MB |

---
