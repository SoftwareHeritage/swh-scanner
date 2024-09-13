# Copyright (C) 2021-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from dataclasses import dataclass
import subprocess

from flask import url_for
import pytest
from pytest_flask.live_server import LiveServer

from swh.model.exceptions import ValidationError
from swh.model.from_disk import Directory
from swh.scanner.data import (
    MerkleNodeInfo,
    add_provenance,
    get_ignore_patterns_templates,
    get_vcs_ignore_patterns,
    has_dirs,
    init_merkle_node_info,
    parse_ignore_patterns_template,
)
from swh.web.client.client import WebAPIClient

from .data import fake_origin, fake_release, fake_revision


def test_merkle_node_data_wrong_args() -> None:
    nodes_data = MerkleNodeInfo()

    with pytest.raises(ValidationError):
        nodes_data["wrong key"] = {"known": True}

    with pytest.raises(ValidationError):
        nodes_data["swh:1:dir:17d207da3804cc60a77cba58e76c3b2f767cb112"] = "wrong value"


def test_init_merkle_supported_node_info(source_tree: Directory) -> None:
    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, provenance=True)
    for _, node_attrs in nodes_data.items():
        assert "known" in node_attrs.keys()
        assert "provenance" in node_attrs.keys()


def test_add_provenance_with_release(
    live_server: LiveServer, source_tree: Directory, nodes_data: MerkleNodeInfo
) -> None:
    api_url = url_for("index", _external=True)
    init_merkle_node_info(source_tree, nodes_data, provenance=True)
    client = WebAPIClient(api_url)

    add_provenance(source_tree, nodes_data, client)
    source_tree_id = str(source_tree.swhid())
    for node, attrs in nodes_data.items():
        assert "provenance" in attrs
        assert attrs["provenance"] is not None
        assert attrs["provenance"].origin == fake_origin[source_tree_id]
        assert str(attrs["provenance"].anchor) == fake_release[source_tree_id]


def test_add_provenance_with_revision(
    live_server: LiveServer, source_tree: Directory, nodes_data: MerkleNodeInfo
) -> None:
    api_url = url_for("index", _external=True)
    init_merkle_node_info(source_tree, nodes_data, provenance=True)
    client = WebAPIClient(api_url)
    a_file = source_tree[b"some-binary"]

    add_provenance(a_file, nodes_data, client)
    a_file_id = str(a_file.swhid())
    attrs = nodes_data[a_file.swhid()]
    assert "provenance" in attrs
    assert attrs["provenance"] is not None
    assert attrs["provenance"].origin == fake_origin[a_file_id]
    assert str(attrs["provenance"].anchor) == fake_revision[a_file_id]


def test_has_dirs(source_tree: Directory) -> None:
    assert has_dirs(source_tree)


@dataclass
class DummyCommandResult:
    """Acts as a command result, as if we just called to a subprocess."""

    stdout: bytes


def test_get_vcs_ignore_patterns_no_vcs(mocker) -> None:
    mock = mocker.patch("swh.scanner.data.vcs_detected")
    mock.return_value = False
    assert get_vcs_ignore_patterns() == []
    assert mock.call_count == 3


def test_get_vcs_ignore_patterns_vcs_error(mocker) -> None:
    detected_mock = mocker.patch("swh.scanner.data.vcs_detected")
    detected_mock.return_value = True
    mock = mocker.patch("swh.scanner.data._call_vcs")
    mock.side_effect = [
        subprocess.CalledProcessError(1, "git"),
        subprocess.CalledProcessError(255, "hg"),
        subprocess.CalledProcessError(1, "svn"),
    ]
    assert get_vcs_ignore_patterns() == []
    assert detected_mock.call_count == 3
    assert mock.call_count == 3


def test_get_vcs_ignore_patterns_git(mocker) -> None:
    detected_mock = mocker.patch("swh.scanner.data.vcs_detected")
    detected_mock.side_effect = [
        True,
    ]
    mock = mocker.patch("swh.scanner.data._call_vcs")
    mock.side_effect = [
        DummyCommandResult(b"M myfile\0!! Some_Folder/\0!! file with spaces"),
    ]
    res = get_vcs_ignore_patterns()
    assert detected_mock.call_count == 1
    assert mock.call_count == 1
    assert res == [b"Some_Folder", b"file with spaces"]


def test_get_vcs_ignore_patterns_hg(mocker) -> None:
    # Mercurial answers
    detected_mock = mocker.patch("swh.scanner.data.vcs_detected")
    detected_mock.side_effect = [
        False,  # Git
        True,  # Mercurial
    ]
    mock = mocker.patch("swh.scanner.data._call_vcs")
    mock.side_effect = [
        DummyCommandResult(b"myfile\0Other_File\0file with spaces"),
    ]
    res = get_vcs_ignore_patterns()
    assert detected_mock.call_count == 2
    assert mock.call_count == 1
    assert res == [b"myfile", b"Other_File", b"file with spaces"]


def test_get_vcs_ignore_patterns_svn(mocker) -> None:
    # SVN answers
    detected_mock = mocker.patch("swh.scanner.data.vcs_detected")
    detected_mock.side_effect = [
        False,  # Git
        False,  # Mercurial
        True,  # SVN
    ]
    mock = mocker.patch("swh.scanner.data._call_vcs")
    mock.side_effect = [
        DummyCommandResult(
            b"""<?xml version="1.0" encoding="UTF-8"?>
<status>
<target
path=".">
<entry
path="myfile/with/nested/things">
<wc-status
item="ignored"
props="none">
</wc-status>
</entry>
<entry
path="myfile/with/nested/external">
<wc-status
item="external"
props="none">
</wc-status>
</entry>
<entry
path="Other_File">
<wc-status
item="ignored"
props="none">
</wc-status>
</entry>
<entry
path="Should not appear">
<wc-status
item="modified"
props="none">
</wc-status>
</entry>
<entry
path="file with spaces">
<wc-status
item="ignored"
props="none">
</wc-status>
</entry>
</target>
</status>
"""
        ),
    ]
    res = get_vcs_ignore_patterns()
    assert detected_mock.call_count == 3
    assert mock.call_count == 1
    assert res == [b"myfile/with/nested/things", b"Other_File", b"file with spaces"]


def test_get_ignore_patterns_templates() -> None:
    templates = get_ignore_patterns_templates()
    assert len(templates) > 0
    assert "Rust" in templates
    rust = templates["Rust"]
    assert rust.exists()


def test_parse_ignore_patterns_template(tmp_path) -> None:
    template_path = tmp_path / "test.gitignore"
    content = """# Test comment
    test/
    *.test
    """
    template_path.write_text(content)
    patterns = parse_ignore_patterns_template(template_path)
    assert patterns == [b"test/", b"*.test"]
