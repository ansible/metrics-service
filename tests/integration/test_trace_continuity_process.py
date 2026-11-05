"""
Tier 3 trace-continuity test (AAP-79590): true cross-process, opt-in.

This is the only test that proves the mock boundary used by Tier 1/2 matches
reality: it starts a real scheduler and a real dispatcherd worker as
subprocesses (real pg_notify broker, real worker process) and asserts the
request ID of an API-created task shows up in the worker process's own log
output.

**It is opt-in and it is NOT run in CI.** Nothing in
``.github/workflows/pytest.yml`` sets ``TRACE_E2E``, so this module is collected
and skipped by the normal ``pytest`` job; Tiers 1–2 are the CI-enforced
guarantee, this test is the manual/local proof of the real hop. Opt in with::

    TRACE_E2E=1 uv run pytest tests/integration/test_trace_continuity_process.py -s -v

or ``make test-trace-e2e``. It needs a PostgreSQL instance reachable with the
test database already created (the same prerequisite as the rest of the
suite) and takes roughly half a minute. The manual procedure for a deployed
instance is documented in ``docs/trace-propagation.md``.

Hygiene: the scheduler's readiness probe needs a ``main_unifiedjob`` table, so
this test creates it inside its own ``trace_e2e_probe`` schema and drops that
schema again afterwards — a ``--reuse-db`` database is never mutated. Both
subprocesses are started in their own session so the whole process group
(including dispatcherd's forked workers) is terminated and reaped in a
``finally``, and a SIGALRM hard timeout bounds the test so an opted-in CI job
could never hang.
"""

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.tasks.models import Task
from tests.unit.tasks.conftest import TRACE_REQUEST_ID

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("TRACE_E2E") != "1", reason="set TRACE_E2E=1 to run the cross-process trace test"
    ),
]

# How long the task may take to reach ``completed`` before the test fails.
POLL_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 1
# Hard ceiling for the whole test, including subprocess start-up and teardown.
# Well above POLL_TIMEOUT_SECONDS so the poll fails first with a useful log dump.
HARD_TIMEOUT_SECONDS = 240

# Dedicated schema for the scheduler's readiness-probe table, so a reused test
# database never gains a stray ``public.main_unifiedjob``.
PROBE_SCHEMA = "trace_e2e_probe"


class _HardTimeoutError(Exception):
    """Raised by the SIGALRM handler when the test overruns its hard deadline."""


@contextlib.contextmanager
def _hard_timeout(seconds: int):
    """Abort the block after *seconds*, even if a subprocess or socket hangs."""
    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - Windows only
        yield
        return

    def _raise(signum, frame):
        raise _HardTimeoutError(f"test exceeded its {seconds}s hard timeout")

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@contextlib.contextmanager
def _probe_table_schema():
    """
    Provide the ``main_unifiedjob`` table the scheduler probes for.

    ``apps.tasks.utils._check_db_ready`` looks the table up in
    ``information_schema.tables`` without a schema filter, so a dedicated schema
    satisfies the probe. Creating and dropping it here keeps the (possibly
    ``--reuse-db``) test database byte-identical before and after the run.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {PROBE_SCHEMA}")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {PROBE_SCHEMA}.main_unifiedjob (id integer)")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {PROBE_SCHEMA} CASCADE")


def _subprocess_env() -> dict[str, str]:
    """
    Environment for the scheduler/worker subprocesses.

    Both run in production mode (so the real console logging with the
    ``request_id`` filter is active — test mode replaces logging with a
    NullHandler) against the database pytest-django created for this session,
    which the in-process API call below writes to.
    """
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "metrics_service.settings"
    env["METRICS_SERVICE_MODE"] = "production"
    env["METRICS_SERVICE_DISPATCHERD_ENABLED"] = "true"

    # Point both database aliases at the pytest-django test database using the
    # connection parameters this process actually connected with (pytest-django
    # rewrites DATABASES, so reading settings.DATABASES directly is not enough).
    # Production-mode validators additionally require non-empty HOST/USER/PASSWORD
    # for both aliases; the hello_world task never touches the awx alias, so it
    # is mirrored onto the test database.
    from django.db import connection

    connection.ensure_connection()
    params = connection.get_connection_params()
    test_db_name = settings.DATABASES["default"]["NAME"]
    host = params.get("host") or "localhost"
    port = str(params.get("port") or "5432")
    user = params.get("user") or "metrics_service"
    password = params.get("password") or "metrics_service"
    for alias in ("default", "awx"):
        env[f"METRICS_SERVICE_DATABASES__{alias}__ENGINE"] = "django.db.backends.postgresql"
        env[f"METRICS_SERVICE_DATABASES__{alias}__NAME"] = str(test_db_name)
        env[f"METRICS_SERVICE_DATABASES__{alias}__HOST"] = str(host)
        env[f"METRICS_SERVICE_DATABASES__{alias}__PORT"] = port
        env[f"METRICS_SERVICE_DATABASES__{alias}__USER"] = str(user)
        env[f"METRICS_SERVICE_DATABASES__{alias}__PASSWORD"] = str(password)

    # Production-mode validators require these to be set. The scheduler and
    # worker never serve HTTP or talk to the gateway in this test, so dummy
    # values satisfy validation without any secret material.
    env.setdefault("METRICS_SERVICE_SECRET_KEY", "trace-e2e-dummy-secret-key")
    env.setdefault("METRICS_SERVICE_RESOURCE_SERVER__URL", "http://localhost:1")
    env.setdefault("METRICS_SERVICE_RESOURCE_SERVER__SECRET_KEY", "trace-e2e-dummy")
    env.setdefault("METRICS_SERVICE_ANSIBLE_BASE_JWT_KEY", "trace-e2e-dummy")
    env.setdefault("METRICS_SERVICE_SEGMENT_WRITE_KEY", "trace-e2e-dummy")
    env.setdefault("METRICS_SERVICE_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    return env


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def _terminate_process_group(process: subprocess.Popen) -> None:
    """
    SIGTERM then SIGKILL the subprocess's whole session, and reap it.

    ``dispatcherd --workers 1`` forks a worker pool, so terminating only the
    direct child would leave grandchildren alive holding PostgreSQL
    connections; that shows up later as "database is being accessed by other
    users" or a hang at session teardown. ``start_new_session=True`` at spawn
    time makes the child a process-group leader, so ``killpg`` reaches all of
    them.
    """
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait(timeout=10)


@pytest.mark.django_db(transaction=True)
def test_request_id_reaches_worker_process(api_client, admin_user, tmp_path):
    """The API request's ID appears in the worker subprocess's log output."""
    with _hard_timeout(HARD_TIMEOUT_SECONDS):
        api_client.force_authenticate(user=admin_user)
        response = api_client.post(
            reverse("tasks:v1:task-schedule-immediate"),
            {"name": "trace-e2e", "function_name": "hello_world", "task_data": {}},
            format="json",
            HTTP_X_REQUEST_ID=TRACE_REQUEST_ID,
        )
        assert response.status_code == 200
        assert response["X-Request-ID"] == TRACE_REQUEST_ID

        task_id = response.data["task_id"]
        task = Task.objects.get(id=task_id)
        assert task.request_id == TRACE_REQUEST_ID

        env = _subprocess_env()
        project_root = Path(settings.BASE_DIR)
        commands = {
            "scheduler": [sys.executable, "manage.py", "run_task_scheduler", "--check-interval", "1"],
            "worker": [sys.executable, "manage.py", "run_dispatcherd", "--workers", "1"],
        }
        log_files = {name: tmp_path / f"{name}.log" for name in commands}

        processes: list[subprocess.Popen] = []
        try:
            # The scheduler refuses to schedule anything until the controller
            # ("awx") database reports ready by probing for main_unifiedjob.
            with _probe_table_schema():
                for name, cmd in commands.items():
                    log_handle = log_files[name].open("w")
                    processes.append(
                        subprocess.Popen(  # noqa: S603
                            cmd,
                            cwd=project_root,
                            env=env,
                            stdout=log_handle,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                    )
                    # Keep a reference so the handle outlives Popen's use of it.
                    processes[-1]._trace_log_handle = log_handle  # noqa: SLF001

                deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    if Task.objects.filter(id=task_id, status="completed").exists():
                        break
                    if any(process.poll() is not None for process in processes):
                        logs = "\n".join(f"--- {name} ---\n{_read(path)}" for name, path in log_files.items())
                        pytest.fail(f"a subprocess exited early:\n{logs}")
                    time.sleep(POLL_INTERVAL_SECONDS)
                else:
                    logs = "\n".join(f"--- {name} ---\n{_read(path)}" for name, path in log_files.items())
                    pytest.fail(f"task {task_id} did not complete within {POLL_TIMEOUT_SECONDS}s:\n{logs}")

            assert Task.objects.filter(id=task_id, status="completed").exists()

            worker_log = _read(log_files["worker"])
            assert worker_log, "worker produced no log output"
            # Production mode uses apps.core.logging_config.JsonFormatter, which
            # emits the ID as a top-level request_id key on every record written
            # inside the task's request context.
            assert TRACE_REQUEST_ID in worker_log, (
                f"request ID missing from worker log; worker log tail:\n{worker_log[-2000:]}"
            )
            # And it is on task-run records, not just incidental output.
            matching = [line for line in worker_log.splitlines() if TRACE_REQUEST_ID in line]
            assert any("hello_world" in line or "trace-e2e" in line for line in matching), (
                f"no task-execution log line carries the ID; matching lines:\n{matching}"
            )
        finally:
            for process in processes:
                _terminate_process_group(process)
            for process in processes:
                handle = getattr(process, "_trace_log_handle", None)
                if handle:
                    handle.close()
