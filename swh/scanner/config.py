import os
from typing import Any, Dict

import click

from swh.auth.cli import DEFAULT_CONFIG as DEFAULT_AUTH_CONFIG
from swh.core import config
from swh.core.config import SWH_GLOBAL_CONFIG

DEFAULT_CONFIG_PATH = os.path.join(click.get_app_dir("swh"), SWH_GLOBAL_CONFIG)
SWH_API_ROOT = "https://archive.softwareheritage.org/api/1/"
DEFAULT_WEB_API_CONFIG: Dict[str, Any] = {
    "web-api": {
        "url": SWH_API_ROOT,
    }
}
# Keep in sync with the wizard
DEFAULT_SCANNER_CONFIG: Dict[str, Any] = {
    "scanner": {
        "dashboard": {
            "port": 0,
        },
        "exclude": [],
        "exclude_templates": [],
        "disable_global_patterns": False,
        "disable_vcs_patterns": False,
    }
}


def get_default_config():
    # Default Scanner configuration
    # Merge AUTH, WEB_API, SCANNER defaults config
    DEFAULT_CONFIG = config.merge_configs(DEFAULT_AUTH_CONFIG, DEFAULT_WEB_API_CONFIG)
    cfg = config.merge_configs(DEFAULT_CONFIG, DEFAULT_SCANNER_CONFIG)
    return cfg
