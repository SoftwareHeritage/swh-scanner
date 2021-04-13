# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
import os
from typing import Any, Dict, Optional

import click
from importlib_metadata import version
import yaml

from swh.core import config
from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group

from .exceptions import DBError

# Config for the "serve" option
BACKEND_DEFAULT_PORT = 5011

# All generic config code should reside in swh.core.config
CONFIG_ENVVAR = "SWH_CONFIG_FILE"
DEFAULT_CONFIG_PATH = os.path.join(click.get_app_dir("swh"), "global.yml")

DEFAULT_CONFIG: Dict[str, Any] = {
    "web-api": {
        "url": "https://archive.softwareheritage.org/api/1/",
        "auth-token": None,
    }
}


CONFIG_FILE_HELP = f"""Configuration file:

\b
The CLI option or the environment variable will fail if invalid.
CLI option is checked first.
Then, environment variable {CONFIG_ENVVAR} is checked.
Then, if cannot load the default path, a set of default values are used.
Default config path is {DEFAULT_CONFIG_PATH}.
Default config values are:

\b
{yaml.dump(DEFAULT_CONFIG)}"""
SCANNER_HELP = f"""Software Heritage Scanner tools.

{CONFIG_FILE_HELP}"""


def setup_config(ctx, api_url):
    config = ctx.obj["config"]
    if api_url:
        if not api_url.endswith("/"):
            api_url += "/"
        config["web-api"]["url"] = api_url

    return config


@swh_cli_group.group(
    name="scanner", context_settings=CONTEXT_SETTINGS, help=SCANNER_HELP,
)
@click.option(
    "-C",
    "--config-file",
    default=None,
    type=click.Path(exists=False, dir_okay=False, path_type=str),
    help="""YAML configuration file""",
)
@click.version_option(
    version=version("swh-scanner"), prog_name="swh-scanner",
)
@click.pass_context
def scanner(ctx, config_file: Optional[str]):

    env_config_path = os.environ.get(CONFIG_ENVVAR)

    # read_raw_config do not fail if file does not exist, so check it beforehand
    # while enforcing loading priority
    if config_file:
        if not config.config_exists(config_file):
            raise click.BadParameter(
                f"File '{config_file}' cannot be opened.", param_hint="--config-file"
            )
    elif env_config_path:
        if not config.config_exists(env_config_path):
            raise click.BadParameter(
                f"File '{env_config_path}' cannot be opened.", param_hint=CONFIG_ENVVAR
            )
        config_file = env_config_path
    elif config.config_exists(DEFAULT_CONFIG_PATH):
        config_file = DEFAULT_CONFIG_PATH

    conf = DEFAULT_CONFIG
    if config_file is not None:
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
    (e.g., ``*.git`` to exclude all .git directories)",
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
    import swh.scanner.scanner as scanner

    config = setup_config(ctx, api_url)
    scanner.scan(config, root_path, patterns, out_fmt, interactive)


@scanner.group("db", help="Manage local knowledge base for swh-scanner")
@click.pass_context
def db(ctx):
    pass


@db.command("import")
@click.option(
    "-i",
    "--input",
    "input_file",
    metavar="INPUT_FILE",
    required=True,
    type=click.File("r"),
    help="A file containing SWHIDs",
)
@click.option(
    "-o",
    "--output",
    "output_file_db",
    metavar="OUTPUT_DB_FILE",
    required=True,
    show_default=True,
    help="The name of the generated sqlite database",
)
@click.option(
    "-s",
    "--chunk-size",
    "chunk_size",
    default="10000",
    metavar="SIZE",
    show_default=True,
    type=int,
    help="The chunk size ",
)
@click.pass_context
def import_(ctx, chunk_size, input_file, output_file_db):
    """Create SQLite database of known SWHIDs from a textual list of SWHIDs

    """
    from .db import Db

    db = Db(output_file_db)
    cur = db.conn.cursor()
    try:
        db.create_from(input_file, chunk_size, cur)
        db.close()
    except DBError as e:
        ctx.fail("Failed to import SWHIDs into database: {0}".format(e))


@db.command("serve")
@click.option(
    "-h",
    "--host",
    metavar="HOST",
    default="127.0.0.1",
    show_default=True,
    help="The host of the API server",
)
@click.option(
    "-p",
    "--port",
    metavar="PORT",
    default=f"{BACKEND_DEFAULT_PORT}",
    show_default=True,
    help="The port of the API server",
)
@click.option(
    "-f",
    "--db-file",
    "db_file",
    metavar="DB_FILE",
    default="SWHID_DB.sqlite",
    show_default=True,
    type=click.Path(exists=True),
    help="An sqlite database file (it can be generated with: 'swh scanner db import')",
)
@click.pass_context
def serve(ctx, host, port, db_file):
    """Start an API service using the sqlite database generated with the "db import"
    option."""
    import swh.scanner.backend as backend

    from .db import Db

    db = Db(db_file)
    backend.run(host, port, db)
    db.close()


def main():
    return scanner(auto_envvar_prefix="SWH_SCANNER")


if __name__ == "__main__":
    main()
