import os
from pathlib import Path

from split_settings.tools import include

from ansible_base.lib import dynamic_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Set environment before including any settings
os.environ.setdefault("MY_SERVICE_ENV", "development")
environment = os.environ.get("MY_SERVICE_ENV", "development")

# Include base Django-Ansible-Base settings
settings_file = os.path.join(
    os.path.dirname(dynamic_config.__file__),
    "dynamic_settings.py",
)

# Include all settings files in order
include(
    "defaults.py",
    f"{environment}.py",
    settings_file,
    "post_load.py",
)
