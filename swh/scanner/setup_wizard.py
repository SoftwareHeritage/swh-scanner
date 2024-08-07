import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Optional

import click
from click import FileError
import yaml

from swh.auth.cli import DEFAULT_CONFIG as DEFAULT_AUTH_CONFIG
from swh.auth.keycloak import KeycloakError, keycloak_error_message
from swh.core import config

from .config import DEFAULT_SCANNER_CONFIG, SWH_API_ROOT, get_default_config

CACHE_HOME_DIR: Path = (
    Path(os.environ["XDG_CACHE_HOME"])
    if "XDG_CACHE_HOME" in os.environ
    else Path.home() / ".cache"
)

MARKER_FILE = CACHE_HOME_DIR / "swh" / "scanner_setup_was_run"
MARKER_TEXT = "SWH SCANNER SETUP 1.0\n"


def invoke_auth(
    ctx,
    config_file: str,
    oidc_server_url: Optional[str] = None,
    realm_name: Optional[str] = None,
):
    from swh.auth.cli import auth

    # Invoke swh.auth.cli.auth command to get an OIDC client
    # The invoked `auth` command manage the configuration file mechanism
    # TODO: Do we need / want to pass args for each OIDC params?
    # If `config_file` is set via env or option, raise if the path does not exist
    if config.config_path(config_file) is None:
        source = ctx.get_parameter_source("config_file") or None
        # TODO also accept if the first (interactive as in tty) run of the scanner
        is_wizard = ctx.invoked_subcommand == "wizard"
        if source and source.name != "DEFAULT" and not is_wizard:
            raise FileError(config_file, hint=f"From {source.name}")
        ctx.invoke(
            auth,
            config_file=config_file,
            oidc_server_url=oidc_server_url,
            realm_name=realm_name,
        )
    else:
        ctx.invoke(
            auth,
            config_file=config_file,
            oidc_server_url=oidc_server_url,
            realm_name=realm_name,
        )


def echo_yaml_error(exc):
    click.secho(
        "Configuration file is not valid YAML:",
        fg="red",
        file=sys.stderr,
    )
    if hasattr(exc, "problem_mark"):
        if exc.context is not None:
            click.secho(
                f"    {exc.problem} {exc.context}\nPlease correct and retry.",
                fg="red",
                file=sys.stderr,
            )
        else:
            click.secho(
                f"    {exc.problem_mark}\n  {exc.problem}"
                + "\nPlease correct data and retry.",
                fg="red",
                file=sys.stderr,
            )
    else:
        click.secho(
            "    Something went wrong while parsing",
            fg="red",
            file=sys.stderr,
        )


def configure_exclude_files_interactive(config_file, config_path):
    try:
        existing_config = config_path.read_text()
    except FileNotFoundError:
        existing_config = yaml.safe_dump(DEFAULT_SCANNER_CONFIG)

    # Show the defaults and some helpful text.
    # Keep in sync with `DEFAULT_SCANNER_CONFIG`
    help_text = """Below is your configuration for the Software Heritage tools.
Here are the defaults for the `scanner` section and their explanations:
    # Whether to disable the base exclusion patterns that the scanner defines
    # like `.git`, `.hg`, etc.
    disable_global_patterns: false
    # Whether to disable using `.gitignore`, `.hgignore` or `.svnignore`
    # found during the scan to exclude files
    disable_vcs_patterns: false
    # Exclude directories using glob patterns
    # (e.g., `*build` to exclude all `build` directories)
    exclude: []
    # Use the following templates. (see `swh scanner scan --help` for more info)
    # (e.g., `['Python', 'Java', 'Rust']`)
    exclude_templates: []
All lines starting with "#HELP:" at the start of the file will be discarded.
"""
    help_text = "\n".join(f"#HELP: {h}" for h in help_text.splitlines())
    buffer = f"{help_text}\n{existing_config}"

    # Loop until the config is valid at least syntactically
    # TODO check the config semantically?
    while True:
        text = click.edit(buffer, extension=".yml")
        if text is None:
            # User saved with no changes
            text = buffer
        filtered = "\n".join(L for L in text.splitlines() if not L.startswith("#HELP:"))
        try:
            yaml.safe_load(filtered)
        except yaml.YAMLError as exc:
            echo_yaml_error(exc)
            if click.confirm(
                click.style(
                    "Continue editing? ('n' will discard changes)",
                    fg="yellow",
                ),
                default=True,
            ):
                # Give back the exact same buffer to the user
                buffer = text
                continue

        # Save to a temporary file then copy back
        with tempfile.NamedTemporaryFile("w") as new_config:
            new_config.write(filtered)
            new_config.flush()
            shutil.copyfile(new_config.name, config_path)

        break

    click.secho(
        f"Successfully saved changes to {config_file}.",
        fg="green",
    )
    click.echo(
        "Tip: you can set project-specific configuration "
        + "in a `swh.scanner.project.yml` file in your project's directory."
    )


DEFAULT_AUTH_SERVER = DEFAULT_AUTH_CONFIG["keycloak"]["server_url"]


def setup_connection_and_config(
    ctx: click.Context,
    config_file: str,
    wants_auth: bool = False,
) -> str:
    oidc_server_url = None
    realm_name = None
    # If the user doesn't want to authenticate, we still leave the choice of instance
    api_root = click.prompt(
        text=click.style(
            "[?] Which archive URL do you wish to use?", fg="blue", bold=True
        ),
        default=SWH_API_ROOT,
    ).strip()

    oidc_server_url = click.prompt(
        text=click.style(
            "[?] Which auth server do you wish to use?", fg="blue", bold=True
        ),
        default=DEFAULT_AUTH_SERVER,
    ).strip()
    if wants_auth:
        realm_name = click.prompt(
            text=click.style(
                "[?] What OIDC realm do you wish to use?", fg="blue", bold=True
            ),
            default=DEFAULT_AUTH_CONFIG["keycloak"]["realm_name"],
        ).strip()

    cfg = get_default_config()

    # Invoke auth CLI command to get an OIDC client
    # It will load configuration file if any and populate a ctx 'config' object
    try:
        invoke_auth(
            ctx,
            config_file=config_file,
            realm_name=realm_name,
            oidc_server_url=oidc_server_url,
        )
    except KeycloakError as exc:
        ctx.fail(keycloak_error_message(exc))

    assert ctx.obj["config"]

    # Merge scanner defaults with config object
    ctx.obj["config"] = config.merge_configs(cfg, ctx.obj["config"])
    assert ctx.obj["oidc_client"]

    # Set the chosen API root now that the default config is merged in
    ctx.obj["config"]["web-api"]["url"] = api_root

    return oidc_server_url or SWH_API_ROOT


def run_setup(ctx: click.Context):
    click.echo(
        """Welcome to the Software Heritage scanner, a source code scanner to
analyze code bases and compare them with source code artifacts archived
by Software Heritage.

    - The scan is done locally on your machine
    - Only anonymous fingerprints (hashes) are sent
    - No private data will be sent anywhere
    - No false positives
"""
    )

    config_file = ctx.obj["config_file"]
    config_path = Path(config_file)

    if click.confirm(
        text=click.style("[?] Authenticate with the archive?", fg="blue", bold=True),
        default=True,
    ):
        click.echo("Tip: if you don't know, press Enter")
        auth_root = setup_connection_and_config(
            ctx, config_file=config_file, wants_auth=True
        )

        from swh.auth.cli import auth_config

        if auth_root == DEFAULT_AUTH_SERVER:
            click.secho(
                "If you do not already have an account, "
                + 'create one at "https://archive.softwareheritage.org/"',
                fg="yellow",
            )
        else:
            click.secho(
                f"You need to have valid credentials for {auth_root}",
                fg="yellow",
            )

        for retry in range(0, 3):
            try:
                ctx.invoke(auth_config)
            except click.exceptions.Exit as e:
                # `auth_config` exits prematurely when saving is skipped
                if e.exit_code != 0:
                    raise
            except click.exceptions.UsageError as e:
                # Authentication failed, retry
                click.secho(f"Authentication failed: {e}", fg="red", file=sys.stderr)
                click.secho(f"Retry {retry + 1}/3")
                continue
            break
        else:
            click.secho(
                "Authentication failed after 3 tries, skipping",
                fg="yellow",
                file=sys.stderr,
            )
    else:
        setup_connection_and_config(
            ctx, config_file=ctx.obj["config_file"], wants_auth=False
        )

    if click.confirm(
        text=click.style("[?] Configure files to exclude?", fg="blue", bold=True),
        default=True,
    ):
        configure_exclude_files_interactive(config_file, config_path)

    click.secho(
        "You can use the scanner now. Here are some examples:", fg="blue", bold=True
    )
    click.echo(
        """
    Scan the current directory
    $ swh scanner scan

    Scan a folder and open the interactive dashboard
    $ swh scanner scan /path/to/folder --interactive

    Scan a folder with JSON output
    $ swh scanner scan /path/to/folder --output-format json

    See the scanner's help
    $ swh scanner --help

    Run this setup again
    $ swh scanner setup"""
    )

    # Save that we've run the setup
    # Write some version identifier in case we need to re-run the setup
    # anyway in a later version.
    MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text(MARKER_TEXT)


def should_run_setup() -> bool:
    try:
        return MARKER_FILE.read_text() != MARKER_TEXT
    except FileNotFoundError:
        return True
