# Copyright (C) 2020-2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from unittest.mock import Mock, call

from click.exceptions import FileError
from click.testing import CliRunner
from flask import url_for
import pytest

from swh.auth.keycloak import KeycloakError
from swh.core import config as config_mod
from swh.scanner import cli, scanner

from .data import present_swhids

DEFAULT_TEST_CONFIG = {
    "keycloak": {
        "client_id": "client-test",
        "realm_name": "realm-test",
        "server_url": "http://keycloak:8080/keycloak/auth/",
    },
    "web-api": {
        "url": "https://example.com/api/1/",
    },
    "scanner": {
        "server": {
            "port": 9001,
        }
    },
}

EXPECTED_TEST_CONFIG = DEFAULT_TEST_CONFIG.copy()
EXPECTED_TEST_CONFIG["keycloak_tokens"] = {"realm-test": {"client-test": "xxxtokenxxx"}}


@pytest.fixture
def scan_paths(tmp_path):
    """Create some temporary contents to scan"""
    scan_paths = {}
    # One unknown file
    unknown = tmp_path / "to_scan" / "unknown"
    scan_paths["unknown"] = str(unknown)
    unknown.mkdir(parents=True)
    unknown_file = unknown / "README"
    unknown_file.touch()
    unknown_file.write_text("Unknown\n")
    # One known file
    known = tmp_path / "to_scan" / "known"
    scan_paths["known"] = str(known)
    known.mkdir(parents=True)
    known_file = known / "README"
    known_file.touch()
    known_file.write_text("Known\n")
    return scan_paths


@pytest.fixture()
def swhids_input_file(tmp_path):
    swhids_input_file = Path(os.path.join(tmp_path, "input_file.txt"))

    with open(swhids_input_file, "w") as f:
        f.write("\n".join(swhid for swhid in present_swhids))

    assert swhids_input_file.exists()
    return swhids_input_file


@pytest.fixture
def user_credentials():
    return {"username": "foo", "password": "bar"}


@pytest.fixture()
def default_test_config_path(tmp_path):
    # Set Swh global config file path to a temp directory
    cfg_file = tmp_path / "global.yml"
    return cfg_file


@pytest.fixture()
def cli_runner(monkeypatch, default_test_config_path):
    """Return a Click CliRunner

    Unset env SWH_CONFIG_FILENAME
    Set default config path to a temp directory
    """
    monkeypatch.delenv("SWH_CONFIG_FILENAME", raising=False)
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", default_test_config_path)
    return CliRunner()


@pytest.fixture()
def m_scanner(mocker):
    """Returns a mock swh.scanner.scanner object with all attributes mocked"""
    # Customizable mock of scanner module
    # Fortunately, noop is the default behavior for all methods
    scanner_mock = Mock(scanner)
    yield mocker.patch("swh.scanner.scanner", scanner_mock)


@pytest.fixture()
def spy_configopen(mocker):
    """Returns a mock of open builtin scoped to swh.core.config"""
    yield mocker.patch("swh.core.config.open", wraps=open)


@dataclass
class FakeOidcClient:
    realm_name: str
    client_id: str
    oidc_success: bool

    def login(self, username, password, scope):
        assert username == "foo"
        assert password == "bar"
        return {"refresh_token": "xxxtokenxxx"}

    def userinfo(self, access_token):
        assert access_token == "access-token-test"
        return {"preferred_username": "foo"}

    def refresh_token(self, refresh_token):
        if self.oidc_success:
            return {"access_token": "access-token-test"}

        raise KeycloakError


def fake_invoke_auth(oidc_success):
    def fake_invoke_auth_inner(ctx, auth, config_file):

        if config_mod.config_path(config_file) is None:
            source = ctx.get_parameter_source("config_file") or None
            if source and source.name != "DEFAULT":
                raise FileError(config_file, hint=f"From {source.name}")

            realm_name = DEFAULT_TEST_CONFIG["keycloak"]["realm_name"]
            client_id = DEFAULT_TEST_CONFIG["keycloak"]["client_id"]
            ctx.obj["config"] = DEFAULT_TEST_CONFIG
        else:
            config = config_mod.read_raw_config(config_file)
            realm_name = config["keycloak"]["realm_name"]
            assert realm_name == "realm-test"
            client_id = config["keycloak"]["client_id"]
            assert client_id == "client-test"
            ctx.obj["config"] = config

        ctx.obj["config_file"] = config_file
        ctx.obj["oidc_client"] = FakeOidcClient(realm_name, client_id, oidc_success)

    return fake_invoke_auth_inner


@pytest.fixture(scope="function")
def oidc_success(mocker):
    oidc_mock = mocker.patch("swh.scanner.cli.invoke_auth")
    oidc_mock.side_effect = fake_invoke_auth(oidc_success=True)
    yield oidc_mock


@pytest.fixture(scope="function")
def oidc_fail(mocker):
    oidc_mock = mocker.patch("swh.scanner.cli.invoke_auth")
    oidc_mock.side_effect = fake_invoke_auth(oidc_success=False)
    yield oidc_mock


def test_smoke(cli_runner, oidc_fail):
    """Break if basic functionality
    breaks

        swh scanner
        swh scanner --help

    """
    res = cli_runner.invoke(cli.scanner)
    res_h = cli_runner.invoke(cli.scanner, ["--help"])

    assert res.exit_code == 0
    assert res_h.exit_code == 0
    assert res.output.startswith("Usage: scanner [OPTIONS] COMMAND [ARGS]")
    assert res.output == res_h.output


def test_smoke_scan(cli_runner, oidc_fail):
    """Scanner scan command
    help

        swh scanner scan --help

    """
    res = cli_runner.invoke(cli.scanner, ["scan", "--help"])

    assert res.exit_code == 0
    assert res.output.startswith("Usage: scanner scan [OPTIONS] [ROOT_PATH]")


def test_scan_config_default_success(
    cli_runner, scan_paths, m_scanner, oidc_fail, spy_configopen
):
    """Ensure scanner default configuration

    Unexisting default global configuration file
    No OIDC authentication

        swh scanner scan /some-path

    """
    res = cli_runner.invoke(
        cli.scanner,
        ["scan", scan_paths["known"]],
    )
    positional, named = m_scanner.scan.call_args
    assert res.exit_code == 0
    assert positional[0] == DEFAULT_TEST_CONFIG
    assert spy_configopen.call_args is None
    oidc_fail.assert_called_once()
    m_scanner.scan.assert_called_once()


def test_scan_config_with_configuration_file_set_by_env_success(
    monkeypatch,
    cli_runner,
    datadir,
    default_test_config_path,
    scan_paths,
    m_scanner,
    oidc_success,
    spy_configopen,
):
    """Ensure scanner configuration when global configuration file exists and
    is set by env (SWH_CONFIG_FILENAME)

        export SWH_CONFIG_FILENAME=~/.config/swh/global.yml
        swh scanner scan /some-path

    """
    # Put valid configuration in default global configuration file
    shutil.copyfile(Path(datadir) / "global.yml", default_test_config_path)

    # Set env SWH_CONFIG_FILENAME
    monkeypatch.setenv("SWH_CONFIG_FILENAME", str(default_test_config_path))

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", scan_paths["known"]],
    )
    positional, named = m_scanner.scan.call_args

    assert res.exit_code == 0
    assert positional[0] == EXPECTED_TEST_CONFIG
    assert spy_configopen.call_args == call(str(default_test_config_path))
    oidc_success.assert_called_once()
    m_scanner.scan.assert_called_once()


def test_scan_config_with_unexisting_configuration_file_set_by_env_fail(
    monkeypatch,
    cli_runner,
    tmp_path,
    scan_paths,
    m_scanner,
    oidc_fail,
):
    """Ensure scanner configuration fail when SWH_CONFIG_FILENAME env is set
    with an unexisting path

        export SWH_CONFIG_FILENAME=nowhere.yml
        swh scanner scan /some-path

    """
    unexisting_path = tmp_path / "nowhere.yml"
    # Set env SWH_CONFIG_FILENAME
    monkeypatch.setenv("SWH_CONFIG_FILENAME", str(unexisting_path))

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", scan_paths["known"]],
    )
    assert res.exit_code != 0
    assert res.output.startswith(f"Error: Could not open file '{unexisting_path}'")


def test_scan_config_with_default_global_configuration_file_success(
    cli_runner,
    datadir,
    default_test_config_path,
    scan_paths,
    m_scanner,
    oidc_success,
    spy_configopen,
):
    """Ensure scanner configuration when a valid global configuration file
    exists

        swh scanner scan /some-path

    """
    # Put valid configuration in default global configuration file
    shutil.copyfile(Path(datadir) / "global.yml", default_test_config_path)
    res = cli_runner.invoke(
        cli.scanner,
        ["scan", scan_paths["known"]],
    )

    positional, named = m_scanner.scan.call_args

    assert res.exit_code == 0
    assert positional[0] == EXPECTED_TEST_CONFIG
    assert spy_configopen.call_args == call(str(default_test_config_path))
    oidc_success.assert_called_once()
    m_scanner.scan.assert_called_once()


def test_scan_config_with_option_configuration_file_success(
    cli_runner,
    tmp_path,
    datadir,
    default_test_config_path,
    scan_paths,
    m_scanner,
    oidc_success,
    spy_configopen,
):
    """Ensure scanner configuration when config_file option is set to an existing
    and valid configuration file

        swh scanner --config-file my_config.yml scan /some-path

    """
    config_file = str(tmp_path / "my_config.yml")
    shutil.copyfile(Path(datadir) / "global.yml", config_file)

    res = cli_runner.invoke(
        cli.scanner,
        ["--config-file", config_file, "scan", scan_paths["known"]],
    )

    positional, named = m_scanner.scan.call_args

    assert res.exit_code == 0
    assert positional[0] == EXPECTED_TEST_CONFIG
    assert spy_configopen.call_args == call(config_file)
    oidc_success.assert_called_once()
    m_scanner.scan.assert_called_once()


def test_scan_config_with_option_configuration_file_error(
    cli_runner,
    tmp_path,
    datadir,
    default_test_config_path,
    scan_paths,
    oidc_fail,
    spy_configopen,
):
    """Ensure scanner raise when config_file option is set to an unexisting
    one

        swh scanner --config-file nowhere.yml scan /some-path

    """
    # unexisting file
    unexisting_path = str(tmp_path / "nowhere.yml")

    res = cli_runner.invoke(
        cli.scanner,
        ["--config-file", unexisting_path, "scan", scan_paths["known"]],
    )

    assert res.exit_code != 0
    assert spy_configopen.call_args is None
    assert res.output.startswith(f"Error: Could not open file '{unexisting_path}'")


def test_scan_api_url_option_success(cli_runner, oidc_fail, m_scanner, scan_paths):
    """Test no config good root good url

    swh scanner scan --api-url https://example.com/api/1 scan /some-path

    """
    API_URL = "https://example.com/api/1"  # without trailing "/"

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", scan_paths["known"], "-u", API_URL],
    )

    positional, named = m_scanner.scan.call_args

    assert res.exit_code == 0
    assert m_scanner.scan.called_once()
    assert positional[0]["web-api"]["url"] == API_URL


def test_smoke_db(cli_runner, oidc_fail):
    """Scanner db
    command

        swh scanner db --help

    """
    res = cli_runner.invoke(cli.scanner, ["db", "--help"])

    assert res.exit_code == 0
    assert res.output.startswith("Usage: scanner db [OPTIONS] COMMAND [ARGS]")


def test_db_option(cli_runner, oidc_fail, swhids_input_file, tmp_path):
    res = cli_runner.invoke(
        cli.scanner,
        [
            "db",
            "import",
            "--input",
            swhids_input_file,
            "--output",
            f"{tmp_path}/test_db.sqlite",
        ],
    )
    assert res.exit_code == 0


def test_ignore_vcs_patterns(cli_runner, live_server, datadir, mocker):
    api_url = url_for("index", _external=True)
    mocker.patch("swh.scanner.scanner.COMMON_EXCLUDE_PATTERNS", [])
    vcs_mock = mocker.patch("swh.scanner.scanner.get_vcs_ignore_patterns")
    vcs_mock.side_effect = [[]]

    res = cli_runner.invoke(
        cli.scanner, ["scan", "--output-format", "json", datadir, "-u", api_url]
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # No filtering gives all results back
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
        "sample-folder-policy.tgz",
        "sample-folder.tgz",
    }

    vcs_mock.side_effect = [[b"global.yml", b"sample-folder-policy.tgz"]]

    res = cli_runner.invoke(
        cli.scanner, ["scan", "--output-format", "json", datadir, "-u", api_url]
    )
    assert res.exit_code == 0
    output = json.loads(res.output)
    # Filtering via VCS works
    assert output.keys() == {
        ".",
        "global2.yml",
        "sample-folder.tgz",
    }


def test_global_excluded_patterns(cli_runner, live_server, datadir, mocker):
    api_url = url_for("index", _external=True)

    res = cli_runner.invoke(
        cli.scanner, ["scan", "--output-format", "json", datadir, "-u", api_url]
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # No filtering gives all results back
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
        "sample-folder-policy.tgz",
        "sample-folder.tgz",
    }

    mocker.patch("swh.scanner.scanner.COMMON_EXCLUDE_PATTERNS", [b"sample*"])
    vcs_mock = mocker.patch("swh.scanner.scanner.get_vcs_ignore_patterns")
    vcs_mock.side_effect = [[]]

    res = cli_runner.invoke(
        cli.scanner, ["scan", "--output-format", "json", datadir, "-u", api_url]
    )
    assert res.exit_code == 0
    output = json.loads(res.output)
    # Filtering via common exclude patterns works
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
    }


def test_smoke_login(cli_runner, oidc_fail):
    """Scanner login
    command

        swh scanner login --help

    """
    res = cli_runner.invoke(cli.scanner, ["login", "--help"])

    assert res.exit_code == 0
    assert res.output.startswith("Usage: scanner login [OPTIONS]")


def test_login_default_success(mocker, cli_runner, user_credentials, oidc_success):
    """Login command forward to swh auth config command
    Test only command options forwarding here

        swh scanner login

    """
    mock_getpass = mocker.patch("getpass.getpass")
    mock_getpass.return_value = user_credentials["password"]

    res = cli_runner.invoke(
        cli.scanner,
        [
            "login",
        ],
        input=f"{user_credentials['username']}\nno\n",
    )
    assert res.exit_code == 0
    assert (
        f"Token verification success for username {user_credentials['username']}"
        in res.output
    )


def test_login_option_username_success(
    mocker, cli_runner, user_credentials, oidc_success
):
    """Test login command with username
    option

        swh scanner login --username foo

    """
    mock_getpass = mocker.patch("getpass.getpass")
    mock_getpass.return_value = user_credentials["password"]

    res = cli_runner.invoke(
        cli.scanner,
        ["login", "--username", user_credentials["username"]],
        input="no\n",
    )
    assert res.exit_code == 0
    assert (
        f"Token verification success for username {user_credentials['username']}"
        in res.output
    )


def test_login_option_token_success(mocker, cli_runner, user_credentials, oidc_success):
    """Test login command with token
    option

        swh scanner login --token xxx-token-xxx

    """
    res = cli_runner.invoke(
        cli.scanner,
        ["login", "--token", "xxx-token-xxx"],
        input="verify\nno\n",
    )

    assert res.exit_code == 0
    assert (
        f"Token verification success for username {user_credentials['username']}"
        in res.output
    )
