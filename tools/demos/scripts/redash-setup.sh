#!/usr/bin/env python3
"""
Redash one-time setup.

1. Creates root admin via manage.py (CLI, runs in redash image)
2. Creates the JSON data source
3. Pre-loads 10 sample queries in YAML format (supports Authorization header)

Run by: demo-redash-setup container after demo-redash is healthy.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

REDASH_URL = "http://demo-redash:5000"
ADMIN_EMAIL = "admin@demo.com"
ADMIN_PASSWORD = "demo_password"
BI_TOKEN = "demo-bi-connector-token"
BI_BASE = "http://demo-metrics-web:8000"


def wait_for_redash(timeout: int = 180) -> None:
    print("=== Waiting for Redash ===", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{REDASH_URL}/ping") as r:
                if r.status == 200:
                    print("Redash is up.", flush=True)
                    return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(3)
    print("\nERROR: Redash timed out.", flush=True)
    sys.exit(1)


def api_post(path: str, payload: dict, key: str) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{REDASH_URL}{path}", data=data)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Key {key}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200]}


def api_get(path: str, key: str) -> dict:
    req = urllib.request.Request(f"{REDASH_URL}{path}")
    req.add_header("Authorization", f"Key {key}")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def get_api_key_from_db() -> str:
    """Read the admin user's API key directly from the Redash PostgreSQL DB."""
    import subprocess
    result = subprocess.run(
        ["psql", "-h", "demo-postgres", "-U", "redash", "-d", "redash", "-t",
         "-c", f"SELECT api_key FROM users WHERE email='{ADMIN_EMAIL}' LIMIT 1;"],
        capture_output=True, text=True, env={"PGPASSWORD": "redash", "PATH": "/usr/bin:/bin"}
    )
    return result.stdout.strip()


def main() -> None:
    wait_for_redash()

    print("\n=== Getting API key ===", flush=True)
    key = get_api_key_from_db()
    if not key:
        print("No API key found - user may not exist yet.", flush=True)
        sys.exit(1)
    print(f"  API key: {key[:12]}...", flush=True)

    print("\n=== Creating JSON data source ===", flush=True)
    existing = api_get("/api/data_sources", key)
    ds_names = [ds.get("name") for ds in (existing if isinstance(existing, list) else [])]
    if "Metrics Service BI Connector" in ds_names:
        ds_id = next(ds["id"] for ds in existing if ds.get("name") == "Metrics Service BI Connector")
        print(f"  Already exists (id={ds_id})", flush=True)
    else:
        result = api_post("/api/data_sources", {
            "name": "Metrics Service BI Connector",
            "type": "json",
            "options": {},
        }, key)
        ds_id = result.get("id")
        print(f"  Created id={ds_id}", flush=True)

    if not ds_id:
        print("ERROR: No data source ID.", flush=True)
        sys.exit(1)

    print("\n=== Creating queries ===", flush=True)

    def yaml_query(endpoint: str, path: str = "results") -> str:
        q = f"url: {BI_BASE}{endpoint}\nheaders:\n  Authorization: Token {BI_TOKEN}"
        if path:
            q += f"\npath: {path}"
        return q

    queries = [
        ("Host Automation - All Hosts",
         yaml_query("/api/v1/bi/stored/host-metrics/?limit=100")),
        ("Host Automation - Active Hosts",
         yaml_query("/api/v1/bi/stored/host-metrics/?deleted=false&limit=100")),
        ("Host Automation - Deleted Hosts",
         yaml_query("/api/v1/bi/stored/host-metrics/?deleted=true&limit=100")),
        ("Job Execution Summary",
         yaml_query("/api/v1/bi/stored/job-host-summaries/?limit=200")),
        ("Collection Batch History",
         yaml_query("/api/v1/bi/stored/batches/?limit=50")),
        ("Daily Metrics - 90 Days",
         yaml_query("/api/v1/bi/metrics/daily/?limit=90")),
        ("Module Compute Hours",
         yaml_query("/api/v1/bi/metrics/modules/")),
        ("Organization Breakdown",
         yaml_query("/api/v1/bi/metrics/organizations/")),
        ("Compute Hours Summary",
         yaml_query("/api/v1/bi/metrics/compute-hours/", path="")),
        ("Hourly Event Collections",
         yaml_query("/api/v1/bi/metrics/hourly/?collector_type=main_jobevent_service&limit=50")),
    ]

    existing_q = api_get("/api/queries", key)
    existing_names = {q.get("name") for q in existing_q.get("results", [])}

    for name, query_str in queries:
        if name in existing_names:
            print(f"  Skip (exists): {name}", flush=True)
            continue
        result = api_post("/api/queries", {
            "data_source_id": ds_id,
            "name": name,
            "query": query_str,
        }, key)
        qid = result.get("id", "ERR")
        print(f"  {qid}: {name}", flush=True)

    print("\n=== Redash setup complete ===", flush=True)
    print(f"   URL:      http://localhost:5002", flush=True)
    print(f"   Login:    {ADMIN_EMAIL} / {ADMIN_PASSWORD}", flush=True)
    print(f"   API key:  {key[:16]}...", flush=True)
    print(f"   Queries:  {len(queries)} pre-loaded", flush=True)


if __name__ == "__main__":
    main()
