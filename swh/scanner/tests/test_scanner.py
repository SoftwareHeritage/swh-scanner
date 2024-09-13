# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import url_for
import pytest

from swh.scanner.data import MerkleNodeInfo, init_merkle_node_info
from swh.scanner.policy import RandomDirSamplingPriority
from swh.scanner.scanner import run

from .data import unknown_swhids


@pytest.mark.options(debug=False)
def test_app(app):
    assert not app.debug


def test_scanner_result(live_server, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, provenance=False)
    policy = RandomDirSamplingPriority(source_tree, nodes_data)
    run(config, policy, source_tree, nodes_data, set())
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True
