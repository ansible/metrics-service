#!/usr/bin/env python
"""
Script to run integration tests with a real server.
This demonstrates the difference between Django test client and real server testing.
"""

import contextlib
import os
import subprocess
import sys
import time

import requests


def start_server():
    """Start the Django development server."""
    server_process = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "127.0.0.1:8001"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Wait for server to start
    time.sleep(3)
    return server_process


def test_api_endpoints():
    """Test API endpoints with real HTTP requests."""
    base_url = "http://127.0.0.1:8001"

    # Test basic endpoints
    endpoints = [
        "/admin/",
        "/api/v1/",
        "/api/docs/",
        "/api/redoc/",
        "/api/schema/",
    ]

    for endpoint in endpoints:
        with contextlib.suppress(requests.exceptions.RequestException):
            requests.get(f"{base_url}{endpoint}", timeout=5)


def run_django_tests():
    """Run Django integration tests (test client)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration/test_api.py", "-v"], capture_output=True, text=True
    )

    if result.stderr:
        pass


def main():
    """Main function to demonstrate both testing approaches."""

    # Change to project directory
    os.chdir("/Users/cshiels/Documents/Repos/Forked/metrics-service")

    # 1. Run Django test client tests (fast, no server needed)
    run_django_tests()

    # 2. Start real server and test
    server_process = None
    try:
        server_process = start_server()
        test_api_endpoints()
    except KeyboardInterrupt:
        pass
    finally:
        if server_process:
            server_process.terminate()
            server_process.wait()


if __name__ == "__main__":
    main()
