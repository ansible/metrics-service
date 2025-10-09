#!/usr/bin/env python
"""
Script to run integration tests with a real server.
This demonstrates the difference between Django test client and real server testing.
"""

import subprocess
import time
import requests
import sys
import os


def start_server():
    """Start the Django development server."""
    print("🚀 Starting Django development server...")
    server_process = subprocess.Popen(
        ["python", "manage.py", "runserver", "127.0.0.1:8001"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Wait for server to start
    time.sleep(3)
    return server_process


def test_api_endpoints():
    """Test API endpoints with real HTTP requests."""
    base_url = "http://127.0.0.1:8001"

    print("🧪 Testing API endpoints with real server...")

    # Test basic endpoints
    endpoints = [
        "/admin/",
        "/api/v1/",
        "/api/docs/",
        "/api/redoc/",
        "/api/schema/",
    ]

    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            print(f"✅ {endpoint}: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ {endpoint}: Error - {e}")


def run_django_tests():
    """Run Django integration tests (test client)."""
    print("🧪 Running Django integration tests (test client)...")
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/integration/test_api.py", "-v"], capture_output=True, text=True
    )

    print("Django Test Client Results:")
    print(result.stdout)
    if result.stderr:
        print("Errors:")
        print(result.stderr)


def main():
    """Main function to demonstrate both testing approaches."""
    print("=" * 60)
    print("INTEGRATION TESTING COMPARISON")
    print("=" * 60)

    # Change to project directory
    os.chdir("/Users/cshiels/Documents/Repos/Forked/metrics-service")

    # 1. Run Django test client tests (fast, no server needed)
    print("\n1️⃣ DJANGO TEST CLIENT TESTS (No Server Required)")
    print("-" * 50)
    run_django_tests()

    # 2. Start real server and test
    print("\n2️⃣ REAL SERVER TESTS (Server Required)")
    print("-" * 50)
    server_process = None
    try:
        server_process = start_server()
        test_api_endpoints()
    except KeyboardInterrupt:
        print("\n⏹️  Stopping server...")
    finally:
        if server_process:
            server_process.terminate()
            server_process.wait()
            print("✅ Server stopped")


if __name__ == "__main__":
    main()


