import os
from pathlib import Path

from ansible_base.lib import dynamic_config
from split_settings.tools import include

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Set environment before including any settings
os.environ.setdefault("METRICS_SERVICE_ENV", "default")
environment = os.environ.get("METRICS_SERVICE_ENV", "default")

# Include base Django-Ansible-Base settings
settings_file = os.path.join(
    os.path.dirname(dynamic_config.__file__),
    "dynamic_settings.py",
)

# Include all settings files in order
include("defaults.py", settings_file)
