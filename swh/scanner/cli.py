# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
from typing import Any, Dict, Optional

import click
from click.exceptions import FileError
from importlib_metadata import version

from swh.auth.cli import DEFAULT_CONFIG as DEFAULT_AUTH_CONFIG
from swh.core import config
from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group
from swh.core.config import SWH_GLOBAL_CONFIG

from .exceptions import DBError

# Config for the "serve" option
BACKEND_DEFAULT_PORT = 5011

DEFAULT_CONFIG_PATH = os.path.join(click.get_app_dir("swh"), SWH_GLOBAL_CONFIG)
SWH_API_ROOT = "https://archive.softwareheritage.org/api/1/"
DEFAULT_WEB_API_CONFIG: Dict[str, Any] = {
    "web-api": {
        "url": SWH_API_ROOT,
    }
}
DEFAULT_SCANNER_CONFIG: Dict[str, Any] = {
    "scanner": {
        "server": {
            "port": BACKEND_DEFAULT_PORT,
        },
        "exclude": [],
    }
}


def get_default_config():
    # Default Scanner configuration
    # Merge AUTH, WEB_API, SCANNER defaults config
    DEFAULT_CONFIG = config.merge_configs(DEFAULT_AUTH_CONFIG, DEFAULT_WEB_API_CONFIG)
    cfg = config.merge_configs(DEFAULT_CONFIG, DEFAULT_SCANNER_CONFIG)
    return cfg


def get_default_config_path():
    # Default Scanner configuration file path
    return DEFAULT_CONFIG_PATH


SCANNER_HELP = """Software Heritage Scanner tools

Scan a source code project to discover files and directories existing in the
Software Heritage archive.
"""


def invoke_auth(ctx, auth, config_file):
    # Invoke swh.auth.cli.auth command to get an OIDC client
    # The invoked `auth` command manage the configuration file mechanism
    # TODO: Do we need / want to pass args for each OIDC params?

    # If `config_file` is set via env or option, raise if the path does not exists
    if config.config_path(config_file) is None:
        source = ctx.get_parameter_source("config_file") or None
        if source and source.name != "DEFAULT":
            raise FileError(config_file, hint=f"From {source.name}")
        ctx.invoke(auth)
    else:
        ctx.invoke(auth, config_file=config_file)


def check_auth(ctx):
    """Check there is some authentication configured

    Issue a warning otherwise"""

    assert "config" in ctx.obj
    assert "oidc_client" in ctx.obj

    config = ctx.obj["config"]
    oidc_client = ctx.obj["oidc_client"]
    realm_name = oidc_client.realm_name
    client_id = oidc_client.client_id

    # Check auth for `production` url only
    if "keycloak_tokens" in config and config["keycloak_tokens"][realm_name][client_id]:
        auth_token = config["keycloak_tokens"][realm_name][client_id]
        from swh.auth.keycloak import KeycloakError, keycloak_error_message

        # Ensure authentication token is valid
        try:
            oidc_client.refresh_token(refresh_token=auth_token)["access_token"]
            # TODO: Display more OIDC information (username, realm, client_id)?
            msg = f'Authenticated to "{ oidc_client.server_url }".'
            click.echo(click.style(msg, fg="green"))
        except KeycloakError as ke:
            msg = "Error while verifying your authentication configuration."
            click.echo(click.style(msg, fg="yellow"))
            msg = "Run `swh scanner login` to configure or verify authentication."
            click.echo(click.style(msg))
            ctx.fail(keycloak_error_message(ke))
    else:
        msg = "Warning: you are not authenticated with the Software Heritage API\n"
        msg += "Log in to get a higher rate-limit."
        click.echo(click.style(msg, fg="yellow"))
        msg = "Run `swh scanner login` to configure or verify authentication."
        click.echo(click.style(msg))


@swh_cli_group.group(
    name="scanner",
    context_settings=CONTEXT_SETTINGS,
    help=SCANNER_HELP,
)
@click.option(
    "-C",
    "--config-file",
    default=get_default_config_path,
    type=click.Path(dir_okay=False, path_type=str),
    help=f"Configuration file path. [default:{get_default_config_path()}]",
    envvar="SWH_CONFIG_FILENAME",
    show_default=False,
)
@click.version_option(
    version=version("swh.scanner"),
    prog_name="swh.scanner",
)
@click.pass_context
def scanner(ctx, config_file: Optional[str]):
    from swh.auth.cli import auth

    ctx.ensure_object(dict)

    # Get Scanner default config
    cfg = get_default_config()

    # Invoke auth CLI command to get an OIDC client
    # It will load configuration file if any and populate a ctx 'config' object
    invoke_auth(ctx, auth, config_file)
    assert ctx.obj["config"]

    # Merge scanner defaults with config object
    ctx.obj["config"] = config.merge_configs(cfg, ctx.obj["config"])
    assert ctx.obj["oidc_client"]


@scanner.command(name="login")
@click.option(
    "--username",
    "username",
    default=None,
    help=("OpenID username"),
)
@click.option(
    "--token",
    "token",
    default=None,
    help=("A valid OpenId connect token to authenticate to"),
)
@click.pass_context
def login(ctx, username: str, token: str):
    """Authentication configuration guide for Swh Api services.
    Helps in verifying authentication credentials
    """
    from swh.auth.cli import auth_config

    ctx.forward(auth_config)


@scanner.command(name="scan")
@click.argument("root_path", default=".", type=click.Path(exists=True))
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
    default="summary",
    show_default=True,
    type=click.Choice(
        ["summary", "text", "json", "ndjson", "sunburst"], case_sensitive=False
    ),
    help="The output format",
)
@click.option(
    "-i", "--interactive", is_flag=True, help="Show the result in a dashboard"
)
@click.option(
    "-e",
    "--extra-info",
    "extra_info",
    multiple=True,
    type=click.Choice(["origin"]),
    help="Add selected additional information about known software artifacts.",
)
@click.pass_context
def scan(ctx, root_path, api_url, patterns, out_fmt, interactive, extra_info):
    """Scan a source code project to discover files and directories already
    present in the archive.

    The command can provide different output using the --output-format option:\n
    \b
      summary: display a general summary of what the scanner found

      text: display the scan result as a text based tree-like view of all the
            file, using color to indicate the file status.

      json: write all collected data on standard output as JSON

      json: write all collected data on standard output as Newline Delimited JSON

      sunburst: produce a dynamic chart as .html file. (in $PWD/chart.html)

    Other information about software artifacts could be specified with the -e/
    --extra-info option:\n
    \b
      origin: search the origin url of each source code files/dirs using the in-memory
      compressed graph.

    Global exclusion patterns can be set with the repeatable -x/--exclude option:\n
    \b
      pattern: glob pattern (e.g., ``*.git`` to exclude all .git directories)
    """
    import swh.scanner.scanner as scanner

    # override config with command parameters if provided
    assert "exclude" in ctx.obj["config"]["scanner"]
    if patterns is not None:
        ctx.obj["config"]["scanner"]["exclude"].extend(patterns)

    patterns = ctx.obj["config"]["scanner"]["exclude"]

    assert "url" in ctx.obj["config"]["web-api"]
    if api_url is not None:
        ctx.obj["config"]["web-api"]["url"] = api_url

    web_api_url = ctx.obj["config"]["web-api"]["url"]

    # Check authentication only for production URL
    if web_api_url == SWH_API_ROOT:
        check_auth(ctx)

    extra_info = set(extra_info)
    scanner.scan(
        ctx.obj["config"], root_path, patterns, out_fmt, interactive, extra_info
    )


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
    """Create SQLite database of known SWHIDs from a textual list of SWHIDs"""
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
