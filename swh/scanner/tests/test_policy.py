# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


from flask import url_for

from swh.model.swhids import CoreSWHID, ObjectType
from swh.scanner.data import MerkleNodeInfo, init_merkle_node_info
from swh.scanner.policy import RandomDirSamplingPriority
from swh.web.client.client import WebAPIClient


def get_backend_swhids_order(tmp_requests):
    with open(tmp_requests, "r") as f:
        backend_swhids_order = f.readlines()

    return [x.strip() for x in backend_swhids_order]


def get_backend_known_requests(tmp_accesses):
    with open(tmp_accesses, "r") as f:
        calls = f.readlines()

    return [int(call.strip()) for call in calls]


def test_randomdir_policy(
    live_server,
    big_source_tree,
    tmp_requests,
    tmp_accesses,
    mocker,
    event_loop,
):
    # This is harder to test with exact assertions due to the random nature
    # of our sampling algorithm and everything else that can be random.
    # Setting random.seed has failed to produce stable results.
    # TODO figure out why?

    open(tmp_requests, "w").close()
    open(tmp_accesses, "w").close()
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(big_source_tree, nodes_data, {"known"})
    policy = RandomDirSamplingPriority(big_source_tree, nodes_data)
    client = WebAPIClient(api_url)
    event_loop.run_until_complete(policy.run(client))

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

    # Test with smaller sample sizes to actually trigger the random sampling
    open(tmp_requests, "w").close()
    open(tmp_accesses, "w").close()
    mocker.patch("swh.scanner.policy.discovery.SAMPLE_SIZE", 10)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(big_source_tree, nodes_data, {"known"})
    policy = RandomDirSamplingPriority(big_source_tree, nodes_data)
    client = WebAPIClient(api_url)
    event_loop.run_until_complete(policy.run(client))

    assert all(v["known"] is True for k, v in policy.data.items())

    # Check that we only do at least two queries of < 10 items
    backend_known_requests = get_backend_known_requests(tmp_accesses)
    assert len(backend_known_requests) >= 2
    assert all(length <= 10 for length in backend_known_requests)
