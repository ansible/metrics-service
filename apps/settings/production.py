"""
Production environment - NO sensitive defaults!
All sensitive values MUST be set via environment variables
Inherits from ./defaults.py and adds pro-specific defaults
"""

DEBUG = False
CORS_ALLOW_ALL_ORIGINS = False
ALLOW_SHARED_RESOURCE_CUSTOM_ROLES = False
