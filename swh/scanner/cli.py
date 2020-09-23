# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
import os
from typing import Any, Dict

import click

from swh.core import config
from swh.core.cli import CONTEXT_SETTINGS, swh as swh_cli_group

# All generic config code should reside in swh.core.config
DEFAULT_CONFIG_PATH = os.environ.get(
    "SWH_CONFIG_FILE", os.path.join(click.get_app_dir("swh"), "global.yml")
)


DEFAULT_CONFIG: Dict[str, Any] = {
    "web-api": {
        "url": "https://archive.softwareheritage.org/api/1/",
        "auth-token": None,
    }
}


def parse_url(url):
    """CLI-specific helper to 'autocomplete' the provided url."""
    if not url.startswith("https://"):
        url = "https://" + url
    if not url.endswith("/"):
        url += "/"
    return url


@swh_cli_group.group(name="scanner", context_settings=CONTEXT_SETTINGS)
@click.option(
    "-C",
    "--config-file",
    default=DEFAULT_CONFIG_PATH,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="YAML configuration file",
)
@click.pass_context
def scanner(ctx, config_file: str):
    """Software Heritage Scanner tools."""

    # recursive merge not done by config.read
    conf = config.read_raw_config(config.config_basepath(config_file))
    conf = config.merge_configs(DEFAULT_CONFIG, conf)

    ctx.ensure_object(dict)
    ctx.obj["config"] = conf


@scanner.command(name="scan")
@click.argument("root_path", required=True, type=click.Path(exists=True))
@click.option(
    "-u",
    "--api-url",
    default=None,
    metavar="API_URL",
    show_default=True,
    help="URL for the api request",
)
@click.option(
    "--exclude",
    "-x",
    "patterns",
    metavar="PATTERN",
    multiple=True,
    help="Exclude directories using glob patterns \
    (e.g., '*.git' to exclude all .git directories)",
)
@click.option(
    "-f",
    "--output-format",
    "out_fmt",
    default="text",
    show_default=True,
    type=click.Choice(["text", "json", "ndjson", "sunburst"], case_sensitive=False),
    help="The output format",
)
@click.option(
    "-i", "--interactive", is_flag=True, help="Show the result in a dashboard"
)
@click.pass_context
def scan(ctx, root_path, api_url, patterns, out_fmt, interactive):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    from .scanner import scan

    config = ctx.obj["config"]
    if api_url:
        config["web-api"]["url"] = parse_url(api_url)

    scan(config, root_path, patterns, out_fmt, interactive)


def main():
    return scanner(auto_envvar_prefix="SWH_SCANNER")


if __name__ == "__main__":
    main()
