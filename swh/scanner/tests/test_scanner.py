# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import url_for
import pytest

from swh.scanner.data import MerkleNodeInfo
from swh.scanner.policy import DirectoryPriority, FilePriority, LazyBFS
from swh.scanner.scanner import run

from .data import unknown_swhids


@pytest.mark.options(debug=False)
def test_app(app):
    assert not app.debug


def test_scanner_result_bfs(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    policy = LazyBFS(source_tree, nodes_data)
    event_loop.run_until_complete(run(config, policy))
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True


def test_scanner_result_file_priority(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    policy = FilePriority(source_tree, nodes_data)
    event_loop.run_until_complete(run(config, policy))
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True


def test_scanner_result_directory_priority(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    policy = DirectoryPriority(source_tree, nodes_data)
    event_loop.run_until_complete(run(config, policy))
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True
