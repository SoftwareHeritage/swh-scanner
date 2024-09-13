# Copyright (C) 2020-2024  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from unittest.mock import Mock, call

from click.exceptions import FileError
from click.testing import CliRunner
from flask import url_for
import pytest
import yaml

from swh.auth.keycloak import KeycloakError
from swh.core import config as core_config_mod
from swh.scanner import cli
from swh.scanner import config as scanner_config_mod
from swh.scanner import scanner
from swh.scanner.setup_wizard import MARKER_TEXT

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
        },
        "exclude": [],
        "exclude_templates": [],
        "disable_global_patterns": False,
        "disable_vcs_patterns": False,
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


@pytest.fixture
def tmp_data(tmp_path, datadir):
    """Copy the tests/data directory to a temporary one
    for further manipulation purpose"""
    root_path = tmp_path / "data"
    return shutil.copytree(datadir, root_path)


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


@pytest.fixture(autouse=True)
def no_run_setup(request, mocker):
    if "setup_test" in request.keywords:
        return
    mocker.patch("swh.scanner.cli.should_run_setup", lambda: False)


@pytest.fixture(autouse=True)
def sandbox_config(mocker, tmp_path):
    """Make sure the scanner doesn't write anything outside of the test"""
    mocker.patch("swh.scanner.setup_wizard.CACHE_HOME_DIR", tmp_path)
    mocker.patch("swh.scanner.setup_wizard.MARKER_FILE", tmp_path / "setup_marker")


@pytest.fixture()
def default_test_config_path(tmp_path):
    # Set Swh global config file path to a temp directory
    cfg_file = tmp_path / "global.yml"
    return cfg_file


@pytest.fixture()
def exclude_templates(tmp_path, mocker):
    """Monkeypatch get_ignore_patterns_templates to return a list of exclusion
    templates from temp directory"""

    test_template_path = tmp_path / "Test.gitignore"
    content = """# Test comment
    test/
    *.test
    """
    test_template_path.write_text(content)

    yaml_template_path = tmp_path / "Yaml.gitignore"
    content = """# Yaml ignore test
    *.yaml
    *.yml
    """
    yaml_template_path.write_text(content)

    tar_template_path = tmp_path / "Tar.gitignore"
    content = """# Tar ignore test
    *.tar
    *.tar.gz
    *.tgz
    """
    tar_template_path.write_text(content)

    templates = {
        "Test": test_template_path,
        "Yaml": yaml_template_path,
        "Tar": tar_template_path,
    }

    cli_mock = mocker.patch("swh.scanner.cli.get_ignore_patterns_templates")
    cli_mock.side_effect = [templates]
    scanner_mock = mocker.patch("swh.scanner.scanner.get_ignore_patterns_templates")
    scanner_mock.side_effect = [templates]

    return templates


@pytest.fixture()
def per_project_test_config_path(tmp_path):
    # Set per project config file path to a temp directory
    per_project_cfg_file = tmp_path / "swh.scanner.project.yml"
    return per_project_cfg_file


@pytest.fixture()
def cli_runner(monkeypatch, default_test_config_path):
    """Return a Click CliRunner

    Unset env SWH_CONFIG_FILENAME
    Set default config path to a temp directory
    """
    monkeypatch.delenv("SWH_CONFIG_FILENAME", raising=False)
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", str(default_test_config_path))
    monkeypatch.setattr(
        scanner_config_mod, "DEFAULT_CONFIG_PATH", str(default_test_config_path)
    )
    monkeypatch.setattr(cli, "get_default_config", lambda: DEFAULT_TEST_CONFIG)
    return CliRunner(mix_stderr=False)


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

        raise KeycloakError("Mock keycloack error")


def fake_invoke_auth(oidc_success):
    def fake_invoke_auth_inner(ctx, config_file, oidc_server_url=None, realm_name=None):
        if core_config_mod.config_path(config_file) is None:
            source = ctx.get_parameter_source("config_file") or None
            if source and source.name != "DEFAULT":
                raise FileError(config_file, hint=f"From {source.name}")

            realm_name = DEFAULT_TEST_CONFIG["keycloak"]["realm_name"]
            client_id = DEFAULT_TEST_CONFIG["keycloak"]["client_id"]
            ctx.obj["config"] = DEFAULT_TEST_CONFIG
        else:
            config = core_config_mod.read_raw_config(config_file)
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
    oidc_mock = mocker.patch("swh.scanner.setup_wizard.invoke_auth")
    oidc_mock.side_effect = fake_invoke_auth(oidc_success=True)
    oidc_mock = mocker.patch("swh.scanner.cli.invoke_auth")
    oidc_mock.side_effect = fake_invoke_auth(oidc_success=True)
    yield oidc_mock


@pytest.fixture(scope="function")
def oidc_fail(mocker):
    oidc_mock = mocker.patch("swh.scanner.setup_wizard.invoke_auth")
    oidc_mock.side_effect = fake_invoke_auth(oidc_success=False)
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
    assert res.exit_code == 0
    positional, named = m_scanner.scan.call_args
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
    assert res.stderr.startswith(f"Error: Could not open file '{unexisting_path}'")


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
    assert res.stderr.startswith(f"Error: Could not open file '{unexisting_path}'")


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


def test_ignore_vcs_patterns(cli_runner, live_server, datadir, mocker):
    api_url = url_for("index", _external=True)
    mocker.patch("swh.scanner.scanner.COMMON_EXCLUDE_PATTERNS", [])
    vcs_mock = mocker.patch("swh.scanner.scanner.get_vcs_ignore_patterns")
    vcs_mock.side_effect = [[]]

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", "--no-web-ui", "--output-format", "json", datadir, "-u", api_url],
    )
    assert res.exit_code == 0
    output = json.loads(res.stdout)

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
        cli.scanner,
        ["scan", "--no-web-ui", "--output-format", "json", datadir, "-u", api_url],
    )
    assert res.exit_code == 0
    output = json.loads(res.stdout)
    # Filtering via VCS works
    assert output.keys() == {
        ".",
        "global2.yml",
        "sample-folder.tgz",
    }


def test_disable_ignore_vcs_patterns(cli_runner, live_server, datadir, mocker):
    api_url = url_for("index", _external=True)
    mocker.patch("swh.scanner.scanner.COMMON_EXCLUDE_PATTERNS", [])
    vcs_mock = mocker.patch("swh.scanner.scanner.get_vcs_ignore_patterns")
    vcs_mock.side_effect = [[b"global.yml", b"sample-folder-policy.tgz"]]

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # Filtering via VCS works
    assert output.keys() == {
        ".",
        "global2.yml",
        "sample-folder.tgz",
    }

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--disable-vcs-patterns",
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # Disable vcs patterns gives all results back
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
        "sample-folder-policy.tgz",
        "sample-folder.tgz",
    }


def test_global_excluded_patterns(cli_runner, live_server, datadir, mocker):
    api_url = url_for("index", _external=True)

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", "--no-web-ui", "--output-format", "json", datadir, "-u", api_url],
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

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", "--no-web-ui", "--output-format", "json", datadir, "-u", api_url],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)
    # Filtering via common exclude patterns works
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
    }


def test_global_excluded_patterns_from_default_config_file(
    cli_runner, live_server, datadir, mocker, default_test_config_path
):
    # Put valid configuration in default global configuration file
    shutil.copyfile(Path(datadir) / "global.yml", default_test_config_path)

    api_url = url_for("index", _external=True)

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", "--no-web-ui", "--output-format", "json", datadir, "-u", api_url],
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

    cfg = yaml.safe_load(default_test_config_path.read_text())
    # Add exclusion patterns to configuration file
    cfg["scanner"]["exclude"] = ["*.ci", "global.yml", "*policy.tgz"]
    default_test_config_path.write_text(yaml.safe_dump(cfg))

    res = cli_runner.invoke(
        cli.scanner,
        ["scan", "--no-web-ui", "--output-format", "json", datadir, "-u", api_url],
    )

    assert res.exit_code == 0
    output = json.loads(res.output)
    # Filtering via common exclude patterns works
    assert output.keys() == {".", "global2.yml", "sample-folder.tgz"}


def test_disable_global_excluded_patterns_arg(
    cli_runner, live_server, mocker, tmp_data
):
    api_url = url_for("index", _external=True)

    # Add a file and directory that common exclusion patterns should ignore
    x_file = tmp_data / "test.x_file"
    x_file.touch()
    x_dir = tmp_data / "x_dir"
    x_dir.mkdir(parents=True, exist_ok=True)

    mocker.patch("swh.scanner.scanner.COMMON_EXCLUDE_PATTERNS", [b"*.x_file", b"x_dir"])

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--disable-global-patterns",
            "--output-format",
            "json",
            str(tmp_data),
            "-u",
            api_url,
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # No filtering gives all results back + the non ignored ones
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
        "sample-folder-policy.tgz",
        "sample-folder.tgz",
        "test.x_file",
        "x_dir",
    }


def test_excluded_per_project_configuration_file_option(
    cli_runner,
    live_server,
    datadir,
    mocker,
    default_test_config_path,
    per_project_test_config_path,
):
    api_url = url_for("index", _external=True)
    project_cfg = {"scanner": {"exclude": ["*.tgz"]}}
    per_project_test_config_path.write_text(yaml.safe_dump(project_cfg))

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
            "--project-config-file",
            str(per_project_test_config_path),
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # The .tgz files has been excluded from project configuration file
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
    }


def test_excluded_per_project_configuration_file_default_path(
    cli_runner,
    live_server,
    tmp_data,
    mocker,
    default_test_config_path,
):
    api_url = url_for("index", _external=True)
    per_project_cfg_file_default_path = tmp_data / "swh.scanner.project.yml"
    per_project_cfg_file_default_path.touch()

    project_cfg = {"scanner": {"exclude": ["*.tgz"]}}
    per_project_cfg_file_default_path.write_text(yaml.safe_dump(project_cfg))

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--output-format",
            "json",
            str(tmp_data),
            "-u",
            api_url,
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # The .tgz files has been excluded from project configuration file
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
    }


def test_exclude_template_arg_fail(cli_runner, live_server, datadir):
    api_url = url_for("index", _external=True)
    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--exclude-template",
            "Test",  # The Test exclusion template does not exists
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
        ],
    )
    assert res.exit_code > 0
    assert "Error: Unknown exclusion template 'Test'. Use one of:" in res.stderr


def test_exclude_template_arg(cli_runner, live_server, datadir, exclude_templates):
    api_url = url_for("index", _external=True)
    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--exclude-template",
            "Tar",
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # *.tgz ignored
    assert output.keys() == {
        ".",
        "global.yml",
        "global2.yml",
    }


def test_exclude_template_multiple_arg(
    cli_runner, live_server, datadir, exclude_templates
):
    api_url = url_for("index", _external=True)

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--exclude-template",
            "Tar",
            "-t",
            "Yaml",
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # *.tgz and *.yml ignored
    assert output.keys() == {
        ".",
    }


def test_exclude_template_per_project_configuration_file(
    cli_runner,
    live_server,
    datadir,
    mocker,
    default_test_config_path,
    per_project_test_config_path,
    exclude_templates,
):
    api_url = url_for("index", _external=True)
    project_cfg = {"scanner": {"exclude_templates": ["Tar", "Yaml"]}}
    per_project_test_config_path.write_text(yaml.safe_dump(project_cfg))

    res = cli_runner.invoke(
        cli.scanner,
        [
            "scan",
            "--no-web-ui",
            "--output-format",
            "json",
            datadir,
            "-u",
            api_url,
            "--project-config-file",
            str(per_project_test_config_path),
        ],
    )
    assert res.exit_code == 0
    output = json.loads(res.output)

    # *.tgz and *.yml ignored
    assert output.keys() == {
        ".",
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


@pytest.mark.setup_test
def test_setup_short_path(cli_runner, oidc_fail, spy_configopen):
    res = cli_runner.invoke(
        cli.scanner,
        ["setup"],
        input="n\n\n\nn",
    )

    assert res.exit_code == 0
    assert spy_configopen.call_args is None


@pytest.mark.setup_test
def test_setup_long_path(
    mocker, cli_runner, oidc_fail, spy_configopen, default_test_config_path, tmp_path
):
    """Test the setup for all optional prompts"""
    marker_file = tmp_path / "setup_marker"
    assert not default_test_config_path.is_file()
    assert not marker_file.exists()

    mock_getpass = mocker.patch("getpass.getpass")
    mock_getpass.return_value = "bar"

    # Trap the edits to the config file
    spy = mocker.patch.object(
        cli.click, "edit", side_effect=["[", "validyaml:\n    value: yes\n"]
    )
    res = cli_runner.invoke(
        cli.scanner,
        ["setup"],
        input="\n\n\n\nfoo\nfoo\nfoo\n\n\n",
    )
    assert mock_getpass.called
    assert mock_getpass.call_count == 3

    # Make sure we've retried the edit
    assert spy.called
    assert spy.call_count == 2
    # That the first call contains help text
    assert "#HELP" in spy.call_args_list[0][0][0]
    # That the second call contains whatever the user saved the first time
    assert spy.call_args_list[1] == call("[", extension=".yml")

    assert (
        res.stderr
        == """Authentication failed: Mock keycloack error
Authentication failed: Mock keycloack error
Authentication failed: Mock keycloack error
Authentication failed after 3 tries, skipping
Configuration file is not valid YAML:
    expected the node content, but found '<stream end>' while parsing a flow node
Please correct and retry.
"""
    )
    assert (
        """Welcome to the Software Heritage scanner, a source code scanner to
analyze code bases and compare them with source code artifacts archived
by Software Heritage.

    - The scan is done locally on your machine
    - Only anonymous fingerprints (hashes) are sent
    - No private data will be sent anywhere
    - No false positives
"""
        in res.stdout
    )
    assert "[?] Authenticate with the archive? [Y/n]:" in res.stdout
    assert (
        "[?] Which archive URL do you wish to use? "
        + "[https://archive.softwareheritage.org/api/1/]: "
        in res.stdout
    )
    assert (
        "[?] Which auth server do you wish to use? [https://auth.softwareheritage.org/auth/]: "
        in res.stdout
    )
    assert "[?] What OIDC realm do you wish to use? [SoftwareHeritage]: " in res.stdout
    assert "Retry 1/3" in res.stdout
    assert "Retry 2/3" in res.stdout
    assert "Retry 3/3" in res.stdout
    assert "[?] Configure files to exclude? [Y/n]: " in res.stdout
    assert "Successfully saved changes to " in res.stdout
    assert (
        """You can use the scanner now. Here are some examples:

    Scan the current directory
    $ swh scanner scan

    Scan a folder and open the interactive dashboard
    $ swh scanner scan /path/to/folder --interactive

    Scan a folder with JSON output
    $ swh scanner scan /path/to/folder --output-format json

    See the scanner's help
    $ swh scanner --help

    Run this setup again
    $ swh scanner setup
"""
        in res.stdout
    )
    assert res.exit_code == 0
    assert spy_configopen.call_args is None
    assert default_test_config_path.is_file()
    assert marker_file.read_text() == MARKER_TEXT


@pytest.mark.setup_test
def test_setup_existing_valid_config(
    mocker,
    cli_runner,
    oidc_success,
    spy_configopen,
    default_test_config_path: Path,
    tmp_path,
):
    """Test the setup for a valid config"""
    marker_file = tmp_path / "setup_marker"
    default_test_config_path.write_text(yaml.safe_dump(EXPECTED_TEST_CONFIG))
    assert default_test_config_path.is_file()
    assert not marker_file.exists()

    mock_getpass = mocker.patch("getpass.getpass")

    # Trap the edit to the config file
    edited_config = "validyaml:\n    value: yes"
    spy = mocker.patch.object(cli.click, "edit", side_effect=[edited_config])
    res = cli_runner.invoke(
        cli.scanner,
        ["setup"],
        input="\n\n\n\n\n\n\n",
    )
    assert not mock_getpass.called

    # Make sure we've called the edit
    assert spy.called
    assert spy.call_count == 1
    # That the text contains help
    editor_buffer = spy.call_args_list[0][0][0]
    assert "#HELP" in editor_buffer
    # That the text contains the config
    assert yaml.safe_dump(EXPECTED_TEST_CONFIG) in editor_buffer

    assert res.stderr == ""
    assert "[?] Authenticate with the archive? [Y/n]:" in res.stdout
    assert (
        "[?] Which archive URL do you wish to use? "
        + "[https://archive.softwareheritage.org/api/1/]: "
        in res.stdout
    )
    assert (
        "[?] Which auth server do you wish to use? [https://auth.softwareheritage.org/auth/]: "
        in res.stdout
    )
    assert "[?] What OIDC realm do you wish to use? [SoftwareHeritage]: " in res.stdout
    assert "[?] Configure files to exclude? [Y/n]: " in res.stdout
    assert "A token was found in " in res.stdout
    assert (
        "Would you like to verify the token or "
        + "generate a new one? (verify, generate) [verify]: "
        in res.stdout
    )
    assert "Token verification success for username foo" in res.stdout
    assert "Successfully saved changes to " in res.stdout
    assert res.exit_code == 0
    assert spy_configopen.called
    assert spy_configopen.call_count == 1
    assert default_test_config_path.is_file()
    assert default_test_config_path.read_text() == edited_config
    assert marker_file.read_text() == MARKER_TEXT
