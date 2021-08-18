# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import url_for
import pytest

from swh.scanner.data import MerkleNodeInfo, init_merkle_node_info
from swh.scanner.policy import DirectoryPriority, FilePriority, LazyBFS, QueryAll
from swh.scanner.scanner import get_policy_obj, run

from .data import unknown_swhids


@pytest.mark.options(debug=False)
def test_app(app):
    assert not app.debug


def test_get_policy_obj_auto(source_tree, nodes_data):
    assert isinstance(get_policy_obj(source_tree, nodes_data, "auto"), QueryAll)


def test_get_policy_obj_bfs(big_source_tree, nodes_data):
    # check that the policy object is the LazyBFS if the source tree contains more than
    # 1000 nodes
    assert isinstance(get_policy_obj(big_source_tree, nodes_data, "auto"), LazyBFS)


def test_scanner_result_bfs(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, {"known"})
    policy = LazyBFS(source_tree, nodes_data)
    event_loop.run_until_complete(
        run(config, policy, source_tree, nodes_data, {"known"})
    )
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True


def test_scanner_result_file_priority(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, {"known"})
    policy = FilePriority(source_tree, nodes_data)
    event_loop.run_until_complete(
        run(config, policy, source_tree, nodes_data, {"known"})
    )
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True


def test_scanner_result_directory_priority(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, {"known"})
    policy = DirectoryPriority(source_tree, nodes_data)
    event_loop.run_until_complete(
        run(config, policy, source_tree, nodes_data, {"known"})
    )
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True


def test_scanner_result_query_all(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, {"known"})
    policy = QueryAll(source_tree, nodes_data)
    event_loop.run_until_complete(
        run(config, policy, source_tree, nodes_data, {"known"})
    )
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True
