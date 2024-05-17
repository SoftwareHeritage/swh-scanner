# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
import logging
import os
import textwrap
from typing import Any, Dict, Optional

import click
from click.exceptions import FileError
from importlib_metadata import version

from swh.auth.cli import DEFAULT_CONFIG as DEFAULT_AUTH_CONFIG
from swh.core import config
from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group
from swh.core.config import SWH_GLOBAL_CONFIG

from .data import get_ignore_patterns_templates
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


def get_default_config_path():
    # Default Scanner configuration file path
    return DEFAULT_CONFIG_PATH


def get_exclude_templates_list_repr(width=0):
    """Format and return a list of ignore patterns templates
    for CLI help"""
    ignore_templates = get_ignore_patterns_templates()
    ignore_templates_list = sorted(ignore_templates.keys())
    ignore_templates_list_str = ", ".join(map(str, ignore_templates_list))
    if width > 0:
        ignore_templates_list_repr = textwrap.fill(
            ignore_templates_list_str, width=width
        )
        return ignore_templates_list_repr
    else:
        return ignore_templates_list_str


EXCLUDE_TEMPLATES_HELP = f"""Repeatable option to exclude files and
directories using an exclusion template
(e.g., ``Python`` for common exclusion patterns
in a Python project).
Valid values are:
{get_exclude_templates_list_repr(40)}
"""


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
    "--exclude-template",
    "-t",
    "exclude_templates",
    metavar="EXCLUDE_TEMPLATES",
    multiple=True,
    help=EXCLUDE_TEMPLATES_HELP,
)
@click.option(
    "--exclude",
    "-x",
    "patterns",
    metavar="PATTERNS",
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
    "-i",
    "--interactive",
    is_flag=True,
    help="Launch the default graphical web browser to explore the results in a dashboard.",
)
@click.option(
    "--provenance",
    "provenance",
    is_flag=True,
    help="Also fetch provenance data (requires special permission from SWH).",
)
@click.option(
    "--debug-http",
    "debug_http",
    is_flag=True,
    help="Show debug information about the http request",
)
@click.option(
    "--disable-global-patterns",
    "disable_global_patterns",
    is_flag=True,
    help="Disable common and global exclusion patterns.",
)
@click.option(
    "--disable-vcs-patterns",
    "disable_vcs_patterns",
    is_flag=True,
    help="Disable vcs ignore detection for exclusion patterns",
)
@click.option(
    "-c",
    "--project-config-file",
    type=click.Path(dir_okay=False, path_type=str),
    help="Project Configuration file path.",
    show_default=False,
)
@click.pass_context
def scan(
    ctx,
    root_path,
    api_url,
    exclude_templates,
    patterns,
    out_fmt,
    interactive,
    provenance,
    debug_http,
    disable_global_patterns,
    disable_vcs_patterns,
    project_config_file: Optional[str],
):
    """Scan a source code project to discover files and directories already
    present in the archive.

    The command can provide different output using the --output-format option:\n
    \b
      summary: display a general summary of what the scanner found

      text: display the scan result as a text based tree-like view of all the
            file, using color to indicate the file status.

      json: write all collected data on standard output as JSON

      ndjson: write all collected data on standard output as Newline Delimited JSON

      sunburst: produce a dynamic chart as .html file. (in $PWD/chart.html)

    Exclusion patterns can be set with the repeatable -x/--exclude option:\n
    \b
      pattern: glob pattern (e.g., ``*.git`` to exclude all .git directories)

    Common default exclusion patterns and exclusion patterns defined in your global
    SWH configuration file can be disabled using the --disable-global-patterns option.\n

    Version control system ignore files detection for exclusion (e.g. .gitignore,
    .hgignore, svn ignore file) can be disabled using the --disable-vcs-patterns option. \n
    """
    from pathlib import Path

    import swh.scanner.scanner as scanner

    # merge global config with per project one if any
    if project_config_file:
        project_cfg_path = Path(project_config_file)
    else:
        project_cfg_path = Path(root_path) / "swh.scanner.project.yml"

    if project_cfg_path.exists():
        ctx.obj["config"] = config.merge_configs(
            ctx.obj["config"], config.read_raw_config(str(project_cfg_path))
        )
        # Exclude from scan the per project configuration file if it is within root path
        if str(project_cfg_path.parent) in str(root_path):
            ctx.obj["config"]["scanner"]["exclude"].extend([str(project_cfg_path)])

    # override config with command parameters if provided
    if disable_global_patterns:
        ctx.obj["config"]["scanner"][
            "disable_global_patterns"
        ] = disable_global_patterns
        ctx.obj["config"]["scanner"]["exclude"] = []

    if disable_vcs_patterns:
        ctx.obj["config"]["scanner"]["disable_vcs_patterns"] = disable_vcs_patterns

    if exclude_templates is not None:
        ctx.obj["config"]["scanner"]["exclude_templates"].extend(exclude_templates)

    # check that the exclude templates are valid
    if "exclude_templates" in ctx.obj["config"]["scanner"]:
        templates = get_ignore_patterns_templates()
        for template in ctx.obj["config"]["scanner"]["exclude_templates"]:
            if template not in templates:
                err_msg = f"Unknown exclusion template '{template}'. Use one of:\n"
                ctx.fail(
                    click.style(err_msg, fg="yellow")
                    + f"{get_exclude_templates_list_repr()}"
                )

        exclude_templates = ctx.obj["config"]["scanner"]["exclude_templates"]

    if patterns is not None:
        ctx.obj["config"]["scanner"]["exclude"].extend(patterns)

    assert "url" in ctx.obj["config"]["web-api"]
    if api_url is not None:
        ctx.obj["config"]["web-api"]["url"] = api_url

    if debug_http:
        http_logger = logging.getLogger("swh.web.client.client")
        http_logger.setLevel(logging.DEBUG)

    # Check authentication only for production URL
    if ctx.obj["config"]["web-api"]["url"] == SWH_API_ROOT:
        check_auth(ctx)

    root_path_fmt = click.format_filename(root_path)
    msg = f"Ready to scan {root_path_fmt}"
    click.echo(click.style(msg, fg="green"), err=True)

    directory_from_disk_progress = 0
    policy_discovery_progress = 0

    def progress_callback(context, arg=None):
        nonlocal directory_from_disk_progress
        nonlocal policy_discovery_progress

        if context is None:
            # step finished move past the progress line
            click.echo("", err=True)
        elif context == "Directory.from_disk":
            assert isinstance(arg, int)
            directory_from_disk_progress += arg
            click.echo(
                f"\r{directory_from_disk_progress} local objects scanned",
                nl=False,
                err=True,
            )
        elif context == "Policy.discovery":
            policy_discovery_progress += 1
            click.echo(
                f"\r{policy_discovery_progress} objects compared with the"
                f" Software Heritage archive",
                nl=False,
                err=True,
            )
        else:
            # explicitly ignoring unknown context
            pass

    scanner.scan(
        ctx.obj["config"],
        root_path,
        out_fmt,
        interactive,
        provenance,
        debug_http,
        progress_callback=progress_callback,
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
