# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from dataclasses import dataclass
from pathlib import Path
import subprocess

from flask import url_for
import pytest

from swh.model.exceptions import ValidationError
from swh.scanner.data import (
    MerkleNodeInfo,
    add_origin,
    directory_content,
    get_directory_data,
    get_ignore_patterns_templates,
    get_vcs_ignore_patterns,
    has_dirs,
    init_merkle_node_info,
    parse_ignore_patterns_template,
)
from swh.web.client.client import WebAPIClient

from .data import fake_origin, fake_release, fake_revision


def test_merkle_node_data_wrong_args():
    nodes_data = MerkleNodeInfo()

    with pytest.raises(ValidationError):
        nodes_data["wrong key"] = {"known": True}

    with pytest.raises(ValidationError):
        nodes_data["swh:1:dir:17d207da3804cc60a77cba58e76c3b2f767cb112"] = "wrong value"


def test_init_merkle_supported_node_info(source_tree):
    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, {"known", "origin"})
    for _, node_attrs in nodes_data.items():
        assert "known" and "origin" in node_attrs.keys()


def test_init_merkle_not_supported_node_info(source_tree):
    nodes_data = MerkleNodeInfo()
    with pytest.raises(Exception):
        init_merkle_node_info(source_tree, nodes_data, {"unsupported_info"})


def test_add_origin_with_release(live_server, source_tree, nodes_data):
    api_url = url_for("index", _external=True)
    init_merkle_node_info(source_tree, nodes_data, {"known", "origin"})
    client = WebAPIClient(api_url)

    add_origin(source_tree, nodes_data, client)
    source_tree_id = str(source_tree.swhid())
    for node, attrs in nodes_data.items():
        assert "origin" in attrs
        assert attrs["origin"] is not None
        assert attrs["origin"].origin == fake_origin[source_tree_id]
        assert str(attrs["origin"].anchor) == fake_release[source_tree_id]


def test_add_origin_with_revision_only(live_server, source_tree, nodes_data):
    api_url = url_for("index", _external=True)
    init_merkle_node_info(source_tree, nodes_data, {"known", "origin"})
    client = WebAPIClient(api_url)
    a_file = source_tree[b"some-binary"]

    add_origin(a_file, nodes_data, client)
    a_file_id = str(a_file.swhid())
    attrs = nodes_data[a_file.swhid()]
    assert "origin" in attrs
    assert attrs["origin"] is not None
    assert attrs["origin"].origin == fake_origin[a_file_id]
    assert str(attrs["origin"].anchor) == fake_revision[a_file_id]


def test_get_directory_data(source_tree, nodes_data):
    root = Path(source_tree.data["path"].decode())
    dirs_data = get_directory_data(root, source_tree, nodes_data)

    assert len(dirs_data) == 5


def test_directory_content(source_tree, nodes_data):
    foo_dir = source_tree[b"foo"]
    foo_content = directory_content(foo_dir, nodes_data)
    assert foo_content[0] == 3
    assert foo_content[1] == 3


def test_has_dirs(source_tree):
    assert has_dirs(source_tree)


@dataclass
class DummyCommandResult:
    """Acts as a command result, as if we just called to a subprocess."""

    stdout: bytes


def test_get_vcs_ignore_patterns_no_vcs(mocker):
    mock = mocker.patch("swh.scanner.data.vcs_detected")
    mock.return_value = False
    assert get_vcs_ignore_patterns() == []
    assert mock.call_count == 3


def test_get_vcs_ignore_patterns_vcs_error(mocker):
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


def test_get_vcs_ignore_patterns_git(mocker):
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


def test_get_vcs_ignore_patterns_hg(mocker):
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


def test_get_vcs_ignore_patterns_svn(mocker):
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
            """<?xml version="1.0" encoding="UTF-8"?>
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


def test_get_ignore_patterns_templates():
    templates = get_ignore_patterns_templates()
    assert len(templates) > 0
    assert "Rust" in templates
    rust = templates["Rust"]
    assert rust.exists()


def test_parse_ignore_patterns_template(tmp_path):
    template_path = tmp_path / "test.gitignore"
    content = """# Test comment
    test/
    *.test
    """
    template_path.write_text(content)
    patterns = parse_ignore_patterns_template(template_path)
    assert patterns == [b"test/", b"*.test"]
