import logging
import os
import sys
import warnings

first = sys.argv[0]
if first.endswith("manage.py"):
    warnings.simplefilter(action="ignore", category=FutureWarning)


def get_logger(name):
    log_level = os.environ.get("METRICS_SERVICE_LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    return logger


logger = get_logger("metrics_service")
