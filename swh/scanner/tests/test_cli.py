# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os
from pathlib import Path
from unittest.mock import Mock, call

from click.testing import CliRunner
import pytest

import swh.scanner.cli as cli
import swh.scanner.scanner as scanner

from .data import present_swhids

DATADIR = Path(__file__).absolute().parent / "data"
CONFIG_PATH_GOOD = str(DATADIR / "global.yml")
CONFIG_PATH_GOOD2 = str(DATADIR / "global2.yml")  # alternative to global.yml
ROOTPATH_GOOD = str(DATADIR)


@pytest.fixture(scope="function")
def m_scanner(mocker):
    """Returns a mock swh.scanner.scanner object with all attributes mocked"""
    # Customizable mock of scanner module
    # Fortunately, noop is the default behavior for all methods
    scanner_mock = Mock(scanner)
    yield mocker.patch("swh.scanner.scanner", scanner_mock)


@pytest.fixture(scope="function")
def spy_configopen(mocker):
    """Returns a mock of open builtin scoped to swh.core.config"""
    yield mocker.patch("swh.core.config.open", wraps=open)


@pytest.fixture(scope="function")
def cli_runner(monkeypatch, tmp_path):
    """Return a CliRunner with default environment variable SWH_CONFIG_FILE unset"""
    BAD_CONFIG_PATH = str(tmp_path / "missing")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", BAD_CONFIG_PATH)
    return CliRunner(env={"SWH_CONFIG_FILE": None})


@pytest.fixture(scope="function")
def swhids_input_file(tmp_path):
    swhids_input_file = Path(os.path.join(tmp_path, "input_file.txt"))

    with open(swhids_input_file, "w") as f:
        f.write("\n".join(swhid for swhid in present_swhids))

    assert swhids_input_file.exists()
    return swhids_input_file


# TEST BEGIN

# For nominal code paths, check that the right config file is loaded
# scanner is mocked to not run actual scan, config loading is mocked to check its usage


def test_smoke(cli_runner):
    """Break if basic functionality breaks"""
    res = cli_runner.invoke(cli.scanner, ["scan", "-h"])
    assert res.exit_code == 0


def test_config_path_option_bad(cli_runner, tmp_path):
    """Test bad option no envvar bad default"""
    CONFPATH_BAD = str(tmp_path / "missing")
    res = cli_runner.invoke(cli.scanner, ["-C", CONFPATH_BAD, "scan", ROOTPATH_GOOD])
    assert res.exit_code != 0


def test_default_config_path(cli_runner, m_scanner, spy_configopen, monkeypatch):
    """Test no option no envvar good default"""
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", CONFIG_PATH_GOOD)
    res = cli_runner.invoke(cli.scanner, ["scan", ROOTPATH_GOOD])
    assert res.exit_code == 0
    assert spy_configopen.call_args == call(CONFIG_PATH_GOOD)
    assert m_scanner.scan.call_count == 1


def test_root_no_config(cli_runner, m_scanner, spy_configopen):
    """Test no config = no option no envvar bad default, good root"""
    res = cli_runner.invoke(cli.scanner, ["scan", ROOTPATH_GOOD])
    assert res.exit_code == 0
    assert spy_configopen.call_count == 0
    assert m_scanner.scan.call_count == 1


def test_root_bad(cli_runner, tmp_path):
    """Test no option no envvar bad default bad root"""
    ROOTPATH_BAD = str(tmp_path / "missing")
    res = cli_runner.invoke(cli.scanner, ["scan", ROOTPATH_BAD])
    assert res.exit_code != 0


def test_config_path_envvar_good(cli_runner, m_scanner, spy_configopen):
    """Test no option good envvar bad default good root"""
    cli_runner.env["SWH_CONFIG_FILE"] = CONFIG_PATH_GOOD
    res = cli_runner.invoke(cli.scanner, ["scan", ROOTPATH_GOOD])
    assert res.exit_code == 0
    assert spy_configopen.call_args == call(CONFIG_PATH_GOOD)
    assert m_scanner.scan.call_count == 1


def test_config_path_envvar_bad(cli_runner, tmp_path):
    """Test no option bad envvar bad default good root"""
    CONFPATH_BAD = str(tmp_path / "missing")
    cli_runner.env["SWH_CONFIG_FILE"] = CONFPATH_BAD
    res = cli_runner.invoke(cli.scanner, ["scan", ROOTPATH_GOOD])
    assert res.exit_code != 0


def test_config_path_option_envvar(cli_runner, m_scanner, spy_configopen):
    """Test good option good envvar bad default good root
    Check that option has precedence over envvar"""
    cli_runner.env["SWH_CONFIG_FILE"] = CONFIG_PATH_GOOD2
    res = cli_runner.invoke(
        cli.scanner, ["-C", CONFIG_PATH_GOOD, "scan", ROOTPATH_GOOD]
    )
    assert res.exit_code == 0
    assert spy_configopen.call_args == call(CONFIG_PATH_GOOD)
    assert m_scanner.scan.call_count == 1


def test_api_url_option(cli_runner, m_scanner):
    """Test no config good root good url"""
    API_URL = "https://example.com/api/1"  # without trailing "/"
    res = cli_runner.invoke(cli.scanner, ["scan", ROOTPATH_GOOD, "-u", API_URL])
    assert res.exit_code == 0
    assert m_scanner.scan.call_count == 1


def test_db_option(cli_runner, swhids_input_file, tmp_path):
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
