"""
Performance testing utilities for metrics-service.

Provides helpers for:
- Timing measurements with millisecond precision
- Memory usage tracking
- Result logging and reporting
- Test data management
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance measurement results."""

    task_name: str
    start_time: str
    end_time: str
    duration_seconds: float
    duration_ms: float
    memory_before_mb: float
    memory_after_mb: float
    memory_delta_mb: float
    memory_peak_mb: float
    status: str
    error_message: str | None = None
    additional_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class PerformanceTimer:
    """Context manager for measuring task performance with timing and memory."""

    def __init__(self, task_name: str, log_file: Path | None = None):
        """
        Initialize performance timer.

        Args:
            task_name: Name of the task being measured
            log_file: Optional file to append timing logs
        """
        self.task_name = task_name
        self.log_file = log_file
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.memory_before: float | None = None
        self.memory_after: float | None = None
        self.memory_peak: float | None = None
        self.metrics: PerformanceMetrics | None = None
        self.error: Exception | None = None
        self.process = psutil.Process()

    def __enter__(self) -> "PerformanceTimer":
        """Start timing and memory measurement."""
        logger.info(f"[START] {self.task_name}")
        self.start_time = time.time()
        self.memory_before = self._get_memory_usage()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and memory measurement, log results."""
        self.end_time = time.time()
        self.memory_after = self._get_memory_usage()
        self.memory_peak = max(self.memory_after, self.memory_before)

        # Calculate metrics
        duration_seconds = self.end_time - self.start_time
        duration_ms = duration_seconds * 1000
        memory_delta = self.memory_after - self.memory_before

        status = "success" if exc_type is None else "failed"
        error_message = str(exc_val) if exc_val else None

        if exc_val:
            self.error = exc_val
            logger.error(f"[FAILED] {self.task_name}: {exc_val}")
        else:
            logger.info(
                f"[COMPLETE] {self.task_name} - "
                f"Duration: {duration_ms:.2f}ms, "
                f"Memory: {self.memory_before:.2f}MB -> {self.memory_after:.2f}MB "
                f"(Δ {memory_delta:+.2f}MB, Peak: {self.memory_peak:.2f}MB)"
            )

        # Create metrics object
        self.metrics = PerformanceMetrics(
            task_name=self.task_name,
            start_time=format_iso8601_timestamp(datetime.fromtimestamp(self.start_time, tz=UTC)),
            end_time=format_iso8601_timestamp(datetime.fromtimestamp(self.end_time, tz=UTC)),
            duration_seconds=duration_seconds,
            duration_ms=duration_ms,
            memory_before_mb=self.memory_before,
            memory_after_mb=self.memory_after,
            memory_delta_mb=memory_delta,
            memory_peak_mb=self.memory_peak,
            status=status,
            error_message=error_message,
        )

        # Write to log file if specified
        if self.log_file:
            self._write_log()

        return False  # Don't suppress exceptions

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        return self.process.memory_info().rss / 1024 / 1024

    def _write_log(self) -> None:
        """Write performance metrics to log file."""
        try:
            # Ensure parent directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

            # Append to log file
            with open(self.log_file, "a") as f:
                f.write(self.metrics.to_json() + "\n")
                f.write("-" * 80 + "\n")

        except Exception as e:
            logger.error(f"Failed to write log file: {e}")


class PerformanceReport:
    """Generate performance test reports."""

    def __init__(self, results: list[PerformanceMetrics]):
        """Initialize with list of performance metrics."""
        self.results = results

    def _calculate_summary(self) -> dict:
        """Calculate summary statistics."""
        return {
            "total_tests": len(self.results),
            "successful": sum(1 for r in self.results if r.status == "success"),
            "failed": sum(1 for r in self.results if r.status == "failed"),
            "total_duration_seconds": sum(r.duration_seconds for r in self.results),
            "total_memory_delta_mb": sum(r.memory_delta_mb for r in self.results),
        }

    def generate_markdown(self, output_file: Path) -> None:
        """Generate markdown report."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        summary = self._calculate_summary()

        with open(output_file, "w") as f:
            f.write("# Performance Test Results\n\n")
            f.write(f"**Generated:** {datetime.now(UTC).isoformat()}\n\n")

            # Summary statistics
            f.write("## Summary\n\n")
            f.write(f"- **Total Tests:** {summary['total_tests']}\n")
            f.write(f"- **Successful:** {summary['successful']}\n")
            f.write(f"- **Failed:** {summary['failed']}\n")
            f.write(f"- **Total Duration:** {summary['total_duration_seconds']:.2f}s\n")
            f.write(f"- **Total Memory Delta:** {summary['total_memory_delta_mb']:+.2f}MB\n\n")

            # Individual results table
            f.write("## Individual Task Results\n\n")
            f.write(
                "| Task | Duration (ms) | Memory Before (MB) | Memory After (MB) | Memory Δ (MB) | Peak (MB) | Status |\n"
            )
            f.write(
                "|------|---------------|-------------------|------------------|--------------|-----------|--------|\n"
            )

            for result in self.results:
                f.write(
                    f"| {result.task_name} | "
                    f"{result.duration_ms:.2f} | "
                    f"{result.memory_before_mb:.2f} | "
                    f"{result.memory_after_mb:.2f} | "
                    f"{result.memory_delta_mb:+.2f} | "
                    f"{result.memory_peak_mb:.2f} | "
                    f"{result.status} |\n"
                )

            # Failed tasks details
            failed_tasks = [r for r in self.results if r.status == "failed"]
            if failed_tasks:
                f.write("\n## Failed Tasks\n\n")
                for result in failed_tasks:
                    f.write(f"### {result.task_name}\n\n")
                    f.write(f"**Error:** {result.error_message}\n\n")

        logger.info(f"Markdown report written to {output_file}")

    def generate_json(self, output_file: Path) -> None:
        """Generate JSON report."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": self._calculate_summary(),
            "results": [r.to_dict() for r in self.results],
        }

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"JSON report written to {output_file}")


def get_output_dir(base_name: str = "perf_test") -> Path:
    """
    Get output directory for performance test results.

    Args:
        base_name: Base name for the output directory

    Returns:
        Path to output directory with timestamp
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"tools/performance_tests/output/{base_name}_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def format_iso8601_timestamp(dt: datetime | None = None) -> str:
    """
    Format timestamp to ISO 8601 with milliseconds and Z suffix.

    Args:
        dt: Datetime to format, defaults to current UTC time

    Returns:
        ISO 8601 formatted string: YYYY-MM-DDTHH:MM:SS.sssZ
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        # Assume UTC if no timezone
        dt = dt.replace(tzinfo=UTC)

    # Format with milliseconds: YYYY-MM-DDTHH:MM:SS.sssZ
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
