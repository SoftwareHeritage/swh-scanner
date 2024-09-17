# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
import logging
import os
import textwrap
from typing import Optional

import click
from importlib_metadata import version
import requests

from swh.core import config
from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group
from swh.web.client.client import WebAPIClient

from .config import DEFAULT_CONFIG_PATH, SWH_API_ROOT, get_default_config
from .data import NoProvenanceAPIAccess, get_ignore_patterns_templates
from .setup_wizard import invoke_auth, run_setup, should_run_setup


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
    type=click.Path(dir_okay=False, path_type=str),
    help=f"Configuration file path. [default:{DEFAULT_CONFIG_PATH}]",
    envvar="SWH_CONFIG_FILENAME",
    show_default=False,
)
@click.version_option(
    version=version("swh.scanner"),
    prog_name="swh.scanner",
)
@click.pass_context
def scanner(ctx: click.Context, config_file: Optional[str]):
    ctx.ensure_object(dict)
    config_file = config_file or DEFAULT_CONFIG_PATH
    ctx.obj["config_file"] = config_file

    # Get Scanner default config
    cfg = get_default_config()

    # Let the setup do its own auth and config setup
    if ctx.invoked_subcommand != "setup" and not should_run_setup():
        # Invoke auth CLI command to get an OIDC client
        # It will load configuration file if any and populate a ctx 'config' object
        invoke_auth(ctx, config_file=config_file)
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
    type=click.Choice(["summary", "text", "json", "ndjson"], case_sensitive=False),
    help="The output format",
)
@click.option(
    "--web-ui/--no-web-ui",
    "interactive",
    is_flag=True,
    default=True,
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
@click.option(
    "--provenance-concurrency",
    default=5,
    help="Number of concurrent connections to the web API.",
)
@click.option(
    "--provenance-batch-size",
    default=100,
    help="Batch size when querying the provenance API.",
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
    provenance_concurrency,
    provenance_batch_size,
):
    """Scan a source code project to discover files and directories already
    present in the archive.

    The command opens by default an interactive dashboard after scanning. Can
    be disabled by the --no-web-ui flag.

    The command can provide different output using the --output-format option:\n
    \b
      summary: display a general summary of what the scanner found

      text: display the scan result as a text based tree-like view of all the
            file, using color to indicate the file status.

      json: write all collected data on standard output as JSON

      ndjson: write all collected data on standard output as Newline Delimited JSON

    Exclusion patterns can be set with the repeatable -x/--exclude option:\n
    \b
      pattern: glob pattern (e.g., ``*.git`` to exclude all .git directories)

    Common default exclusion patterns and exclusion patterns defined in your global
    SWH configuration file can be disabled using the --disable-global-patterns option.\n

    Version control system ignore files detection for exclusion (e.g. .gitignore,
    .hgignore, svn ignore file) can be disabled using the --disable-vcs-patterns option. \n

    """
    from pathlib import Path

    import swh.scanner.data as data
    import swh.scanner.scanner as scanner

    if should_run_setup():
        run_setup(ctx)
        click.echo("")  # Separate setup and command a little more

    root_path = os.path.abspath(root_path)

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
    # TODO why do we do this?
    # TODO Should we remove the `swh scanner login` command in favor of the setup?
    if ctx.obj["config"]["web-api"]["url"] == SWH_API_ROOT:
        check_auth(ctx)

    root_path_fmt = click.format_filename(root_path)
    msg = f"Ready to scan {root_path_fmt}"
    click.echo(click.style(msg, fg="green"), err=True)

    class CLIProgress(scanner.Progress):
        def __init__(
            self,
            step: scanner.Progress.Step,
            total: Optional[int] = None,
            web_client: Optional[WebAPIClient] = None,
        ):
            self._count = 0
            self._total = total
            self._web_client = web_client
            if step == scanner.Progress.Step.DISK_SCAN:
                self._text = "local objects scanned"
            elif step == scanner.Progress.Step.KNOWN_DISCOVERY:
                self._text = "objects compared with the Software Heritage archive"
            elif step == scanner.Progress.Step.PROVENANCE:
                self._text = "provenance data fetched"

        def increment(self, count=1):
            """move the progress forward and refresh the output"""
            self._count += count
            self._display()

        def update(self, current_count, total=None):
            self._count = current_count
            self._total = total
            self._display()

        def _display(self):
            """refresh the output"""
            rate_limit = ""
            rate_limit_delay = getattr(self._web_client, "rate_limit_delay", 0)
            if rate_limit_delay > 0:
                requests_per_second = 1 / rate_limit_delay
                rate_limit = (
                    f" (rate limited: {requests_per_second:.2f} requests / seconds)"
                )
            if self._total is None:
                msg = f"\r{self._count} {self._text}{rate_limit}"
            else:
                msg = f"\r{self._count}/{self._total} {self._text}{rate_limit}"

            click.echo(msg, nl=False, err=True)

        def __enter__(self):
            return self

        def __exit__(self, *args, **kwargs):
            click.echo("", err=True)

    data.MAX_WHEREARE_BATCH = provenance_batch_size
    data.MAX_CONCURRENT_PROVENANCE_QUERIES = provenance_concurrency

    try:
        scanner.scan(
            ctx.obj["config"],
            root_path,
            out_fmt,
            interactive,
            provenance,
            debug_http,
            progress_class=CLIProgress,
        )
    except requests.HTTPError as exc:
        r = exc.response
        click.secho(
            "ERROR: Unexpected errors from the Software Heritage Archive:",
            fg="red",
        )
        click.secho(
            f"ERROR:     {r.url}",
            fg="red",
        )
        click.secho(
            f"ERROR:     {r.status_code} {r.reason}",
            fg="red",
        )
        return 2
    except NoProvenanceAPIAccess:
        msg = (
            "ERROR: Your account does not have permission to query the Provenance API\n"
        )
        msg += "(Contact the Software Heritage team to get such permission)"
        click.echo(click.style(msg, fg="red"))
        return 1


@scanner.command("setup")
@click.pass_context
def setup_cmd(ctx: click.Context):
    """Get guided through setting up the scanner

    This interactive command gives a quick explanation of what the scanner is,
    and guides you through the optional authentication as well as the config
    options, then gives you a few examples for invocations.

    This setup will run the first time you run the `scan` command, but you
    may invoke it at anytime using `swh scanner setup`."""
    run_setup(ctx)


def main():
    return scanner(auto_envvar_prefix="SWH_SCANNER")


if __name__ == "__main__":
    main()
