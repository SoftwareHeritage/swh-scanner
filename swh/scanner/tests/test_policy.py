# Copyright (C) 2021-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path
from typing import List, Tuple

from flask import url_for
from pytest_flask.live_server import LiveServer

from swh.model.from_disk import Directory
from swh.model.swhids import CoreSWHID, ObjectType
from swh.scanner.data import MerkleNodeInfo, init_merkle_node_info
from swh.scanner.policy import RandomDirSamplingPriority
from swh.web.client.client import WebAPIClient


def get_backend_swhids_order(tmp_requests) -> List[str]:
    with open(tmp_requests, "r") as f:
        backend_swhids_order = f.readlines()

    return [x.strip() for x in backend_swhids_order]


def get_backend_known_requests(tmp_accesses) -> List[int]:
    with open(tmp_accesses, "r") as f:
        calls = f.readlines()

    return [int(call.strip()) for call in calls]


def _setup_base(source_tree: Directory) -> Tuple[WebAPIClient, MerkleNodeInfo]:
    api_url = url_for("index", _external=True)
    client = WebAPIClient(api_url)
    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, provenance=False)

    return client, nodes_data


def test_randomdir_policy(
    live_server: LiveServer,
    big_source_tree: Directory,
    tmp_requests: Path,
    tmp_accesses: Path,
    mocker,
):
    # This is harder to test with exact assertions due to the random nature
    # of our sampling algorithm and everything else that can be random.
    # Setting random.seed has failed to produce stable results.
    # TODO figure out why?
    open(tmp_requests, "w").close()
    open(tmp_accesses, "w").close()

    client, nodes_data = _setup_base(big_source_tree)

    policy = RandomDirSamplingPriority(big_source_tree, nodes_data)
    policy.run(client)

    backend_swhids_requests = get_backend_swhids_order(tmp_requests)
    # Check that we only query directories in the case where all directories
    # fit in a single request
    assert all(
        CoreSWHID.from_string(swhid).object_type == ObjectType.DIRECTORY
        for swhid in backend_swhids_requests
    )

    assert all(v["known"] is True for k, v in policy.data.items())

    # Check that we only do a single query of 1000 items
    backend_known_requests = get_backend_known_requests(tmp_accesses)
    assert [1000] == backend_known_requests


def test_randomdir_policy_small_request(
    live_server: LiveServer,
    big_source_tree: Directory,
    tmp_requests: Path,
    tmp_accesses: Path,
    mocker,
):
    # Test with smaller sample sizes to actually trigger the random sampling
    open(tmp_requests, "w").close()
    open(tmp_accesses, "w").close()
    mocker.patch("swh.scanner.policy.discovery.SAMPLE_SIZE", 10)
    client, nodes_data = _setup_base(big_source_tree)

    policy = RandomDirSamplingPriority(big_source_tree, nodes_data)
    policy.run(client)

    assert all(v["known"] is True for k, v in policy.data.items())

    # Check that we only do at least two queries of < 10 items
    backend_known_requests = get_backend_known_requests(tmp_accesses)
    assert len(backend_known_requests) >= 2
    assert all(length <= 10 for length in backend_known_requests)


def test_randomdir_policy_info_callback(
    live_server: LiveServer,
    big_source_tree: Directory,
    tmp_requests: Path,
    tmp_accesses: Path,
    mocker,
):
    # Test with smaller sample sizes to actually trigger the random sampling
    open(tmp_requests, "w").close()
    open(tmp_accesses, "w").close()
    client, nodes_data = _setup_base(big_source_tree)

    # set to gather all the item that got a callback ping
    updated = set()

    def gather(obj, known):
        updated.add(obj.swhid())

    policy = RandomDirSamplingPriority(
        big_source_tree,
        nodes_data,
    )
    policy.run(client, update_info=gather)

    assert all(v["known"] is True for k, v in policy.data.items())
    assert updated == set(policy.data.keys())
