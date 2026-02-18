"""
Output formatting utilities for CLI commands.

Provides consistent formatting for success, error, warning, and info messages
across all management commands.
"""


class OutputFormatter:
    """Handles consistent output formatting for CLI commands."""

    def __init__(self, stdout, style):
        """
        Initialize the output formatter.

        Args:
            stdout: Django's stdout object
            style: Django's style object for colors
        """
        self.stdout = stdout
        self.style = style

    def success(self, message: str) -> None:
        """Format and write a success message."""
        self.stdout.write(self.style.SUCCESS(message))

    def error(self, message: str) -> None:
        """Format and write an error message."""
        self.stdout.write(self.style.ERROR(message))

    def warning(self, message: str) -> None:
        """Format and write a warning message."""
        self.stdout.write(self.style.WARNING(message))

    def info(self, message: str) -> None:
        """Format and write an info message."""
        self.stdout.write(message)

    def write(self, message: str) -> None:
        """Write a plain message."""
        self.stdout.write(message)

    def write_separator(self, char: str = "=", length: int = 50) -> None:
        """Write a separator line."""
        self.stdout.write(char * length)
