"""
Test utilities for metrics_service tests.

This module provides common utilities and constants used across test files.
"""


def get_test_password() -> str:
    """
    Get the standard test password for use in test cases.
    
    Centralized to avoid SonarQube hard-coded credential warnings.
    Only this function should be excluded from SonarQube password detection.
    
    Returns:
        str: The test password
    """
    return "testpass123"  # noqa: S105 - This is intentionally a test credential


def get_test_user_data(username: str = "testuser", email: str = "test@example.com") -> dict:
    """
    Get standard test user data with the test password.
    
    Args:
        username: Username for the test user
        email: Email for the test user
        
    Returns:
        dict: User data dictionary with password included
    """
    return {
        "username": username,
        "email": email,
        "password": get_test_password(),
    }