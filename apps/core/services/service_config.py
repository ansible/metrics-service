"""
Service configuration management.

Handles configuration validation and defaults for the metrics service.
"""

from typing import Any, Dict


class ServiceConfig:
    """Manages configuration for the metrics service."""

    # Default configuration values
    DEFAULTS = {
        "host": "127.0.0.1",
        "port": "8000",
        "workers": 4,
        "timeout": 3600,
        "max_tasks": 100,
        "log_level": "INFO",
    }

    # Valid log levels
    VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]

    def __init__(self, options: Dict[str, Any]):
        """
        Initialize service configuration.

        Args:
            options: Dictionary containing configuration options
        """
        self.host = self._get_option(options, "host", self.DEFAULTS["host"])
        self.port = self._get_option(options, "port", self.DEFAULTS["port"])
        self.workers = self._get_option(options, "workers", self.DEFAULTS["workers"])
        self.timeout = self._get_option(options, "timeout", self.DEFAULTS["timeout"])
        self.max_tasks = self._get_option(options, "max_tasks", self.DEFAULTS["max_tasks"])
        self.log_level = self._get_option(options, "log_level", self.DEFAULTS["log_level"])

        self._validate_config()

    def _get_option(self, options: Dict[str, Any], key: str, default: Any) -> Any:
        """Get option value with fallback to default."""
        return options.get(key, default)

    def _validate_config(self) -> None:
        """Validate configuration values."""
        # Validate host
        if not isinstance(self.host, str) or not self.host:
            raise ValueError(f"Invalid host: {self.host}")

        # Validate port
        if not isinstance(self.port, (int, str)) or not str(self.port).isdigit():
            raise ValueError(f"Invalid port: {self.port}")

        # Validate workers
        if not isinstance(self.workers, int) or self.workers <= 0:
            raise ValueError(f"Invalid workers count: {self.workers}")

        # Validate timeout
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            raise ValueError(f"Invalid timeout: {self.timeout}")

        # Validate max_tasks
        if not isinstance(self.max_tasks, int) or self.max_tasks <= 0:
            raise ValueError(f"Invalid max_tasks: {self.max_tasks}")

        # Validate log_level
        if self.log_level not in self.VALID_LOG_LEVELS:
            raise ValueError(f"Invalid log_level: {self.log_level}. Must be one of {self.VALID_LOG_LEVELS}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "workers": self.workers,
            "timeout": self.timeout,
            "max_tasks": self.max_tasks,
            "log_level": self.log_level,
        }

    def __str__(self) -> str:
        """String representation of configuration."""
        return f"ServiceConfig(host={self.host}, port={self.port}, workers={self.workers}, log_level={self.log_level})"
