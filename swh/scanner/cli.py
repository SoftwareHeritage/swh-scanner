# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
import os
from pathlib import Path
import sys
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

SWH_API_ROOT = "https://archive.softwareheritage.org/api/1/"
DEFAULT_CONFIG: Dict[str, Any] = {
    "web-api": {
        "url": SWH_API_ROOT,
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


def check_auth(config):
    """check there is some authentication configured

    Issue a warning otherwise"""
    web_api_conf = config["web-api"]
    if web_api_conf["url"] == SWH_API_ROOT and not web_api_conf.get("auth-token"):
        # Only warn for the production API
        #
        # XXX We should probably warn at the time of the creation of the HTTP
        # Client, after checking if the token is actually valid.
        msg = "Warning: you are not authenticated with the Software Heritage API\n"
        msg += "login to get a higher rate-limit"
        click.echo(click.style(msg, fg="red"), file=sys.stderr)
        msg = "See `swh scanner login -h` for more information."
        click.echo(click.style(msg, fg="yellow"), file=sys.stderr)


@swh_cli_group.group(
    name="scanner",
    context_settings=CONTEXT_SETTINGS,
    help=SCANNER_HELP,
)
@click.option(
    "-C",
    "--config-file",
    default=None,
    type=click.Path(exists=False, dir_okay=False, path_type=str),
    help="""YAML configuration file""",
)
@click.version_option(
    version=version("swh.scanner"),
    prog_name="swh.scanner",
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
    else:
        config_file = DEFAULT_CONFIG_PATH

    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config_file)
    ctx.obj["config"] = conf


@scanner.command(name="login")
@click.option(
    "-f",
    "--force/--no-force",
    default=False,
    help="Proceed even if a token is already present in the config",
)
@click.pass_context
def login(ctx, force):
    """Perform the necessary step to log yourself in the API

    You will need to first create an account before running this operation. To
    create an account, visit: https://archive.softwareheritage.org/
    """
    context = ctx.obj

    # Check we are actually talking to the Software Heritage itself.
    web_api_config = context["config"]["web-api"]
    current_url = web_api_config["url"]
    config_path = context["config_path"]
    if current_url != SWH_API_ROOT:
        msg = "`swh scanner login` only works with the Software Heritage API\n"
        click.echo(click.style(msg, fg="red"), file=sys.stderr)
        msg = f"Configured in '%s' as web-api.url={current_url}\n"
        msg %= click.format_filename(bytes(config_path))
        click.echo(click.style(msg, fg="red"), file=sys.stderr)
        ctx.exit(1)

    # Check for an existing value in the configuration
    if web_api_config.get("auth-token") is not None:
        click.echo(click.style("You appear to already be logged in.", fg="green"))
        if not force:
            click.echo("Hint: use `--force` to overwrite the current token")
            ctx.exit()
        click.echo(click.style("Continuing because of `--force`.", fg="yellow"))

    # Obtain a valid token through the API
    #
    # Coming from the swh auth generate-token code
    # (this command might eventually move there)
    from getpass import getpass

    from swh.auth.keycloak import (
        KeycloakError,
        KeycloakOpenIDConnect,
        keycloak_error_message,
    )

    msg = "Please enter your SWH Archive credentials"
    click.echo(click.style(msg, fg="yellow"))
    msg = "If you do not already have an account, create one one at:"
    click.echo(click.style(msg, fg="yellow"))
    msg = "    https://archive.softwareheritage.org/"
    click.echo(click.style(msg, fg="yellow"))
    username = click.prompt("username")
    password = getpass()
    try:
        url = "https://auth.softwareheritage.org/auth/"
        realm = "SoftwareHeritage"
        client = "swh-web"
        oidc_client = KeycloakOpenIDConnect(url, realm, client)
        scope = "openid offline_access"
        oidc_info = oidc_client.login(username, password, scope)
        token = oidc_info["refresh_token"]
        msg = "token retrieved successfully"
        click.echo(click.style(msg, fg="green"))
    except KeycloakError as ke:
        print(keycloak_error_message(ke))
        click.exit(1)

    # Write the new token into the file.
    web_api_config["auth-token"] = token
    # TODO use ruamel.yaml to preserve comments in config file
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(context["config"]))
    msg = "\nConfiguration file '%s' written successfully."
    msg %= click.format_filename(bytes(config_path))
    click.echo(click.style(msg, fg="green"))
    click.echo("`swh scanner` will now be authenticated with the new token.")


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
    "-p",
    "--policy",
    default="auto",
    show_default=True,
    type=click.Choice(["auto", "bfs", "greedybfs", "filepriority", "dirpriority"]),
    help="The scan policy.",
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
def scan(ctx, root_path, api_url, patterns, out_fmt, interactive, policy, extra_info):
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

    The source code project can be checked using different policies that can be set
    using the -p/--policy option:\n
    \b
      auto: it selects the best policy based on the source code, for codebase(s)
      with less than 1000 file/dir contents all the nodes will be queried.

      bfs: scan the source code in the BFS order, checking unknown directories only.

    \b
      greedybfs: same as "bfs" policy, but lookup the status of source code artifacts
      in chunks, in order to minimize the number of Web API round-trips with the
      archive.

    \b
      filepriority: scan all the source code file contents, checking only unset
      directories. (useful if the codebase contains a lot of source files)

      dirpriority: scan all the source code directories and check only unknown
      directory contents.

    Other information about software artifacts could be specified with the -e/
    --extra-info option:\n
    \b
      origin: search the origin url of each source code files/dirs using the in-memory
      compressed graph."""
    import swh.scanner.scanner as scanner

    config = setup_config(ctx, api_url)
    check_auth(config)
    extra_info = set(extra_info)
    scanner.scan(config, root_path, patterns, out_fmt, interactive, policy, extra_info)


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
