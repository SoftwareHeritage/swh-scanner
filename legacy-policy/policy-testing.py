# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


from flask import url_for
import pytest

from swh.model.swhids import CoreSWHID, ObjectType
from swh.scanner.client import Client
from swh.scanner.data import MerkleNodeInfo, init_merkle_node_info
from swh.scanner.policy import (
    DirectoryPriority,
    FilePriority,
    GreedyBFS,
    LazyBFS,
    RandomDirSamplingPriority,
    source_size,
)


def test_scanner_directory_priority_has_contents(source_tree):
    nodes_data = MerkleNodeInfo()
    policy = DirectoryPriority(source_tree, nodes_data)
    assert policy.has_contents(source_tree[b"/bar/barfoo"])


def get_backend_swhids_order(tmp_requests):
    with open(tmp_requests, "r") as f:
        backend_swhids_order = f.readlines()

    return [x.strip() for x in backend_swhids_order]


def get_backend_known_requests(tmp_accesses):
    with open(tmp_accesses, "r") as f:
        calls = f.readlines()

    return [int(call.strip()) for call in calls]


def test_lazybfs_policy(
    live_server, aiosession, event_loop, source_tree_policy, tmp_requests
):
    open(tmp_requests, "w").close()
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree_policy, nodes_data, {"known"})
    policy = LazyBFS(source_tree_policy, nodes_data)
    client = Client(api_url, aiosession)
    event_loop.run_until_complete(policy.run(client))

    backend_swhids_requests = get_backend_swhids_order(tmp_requests)

    assert (
        backend_swhids_requests[0]
        == "swh:1:dir:fe8cd7076bef324eb8865f818ef08617879022ce"
    )

    # the second request must contain 3 SWHIDs related to directories and one content
    dir_count, cnt_count = 0, 0
    for swhid in backend_swhids_requests[1:5]:
        if CoreSWHID.from_string(swhid).object_type == ObjectType.DIRECTORY:
            dir_count += 1
        else:
            cnt_count += 1

    assert dir_count == 3
    assert cnt_count == 1

    # the last swhid must be a content related to the unknown directory
    # "sample-folder-policy/toexclude"
    assert (
        backend_swhids_requests[5]
        == "swh:1:cnt:5f1cfce26640056bed3710cfaf3062a6a326a119"
    )


def test_directory_priority_policy(
    live_server, aiosession, event_loop, source_tree_policy, tmp_requests
):
    open(tmp_requests, "w").close()
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree_policy, nodes_data, {"known"})
    policy = DirectoryPriority(source_tree_policy, nodes_data)
    client = Client(api_url, aiosession)
    event_loop.run_until_complete(policy.run(client))

    backend_swhids_requests = get_backend_swhids_order(tmp_requests)

    for swhid in backend_swhids_requests[0:4]:
        assert CoreSWHID.from_string(swhid).object_type == ObjectType.DIRECTORY

    for swhid in backend_swhids_requests[5:]:
        assert CoreSWHID.from_string(swhid).object_type == ObjectType.CONTENT


def test_file_priority_policy(
    live_server, aiosession, event_loop, source_tree_policy, tmp_requests
):
    open(tmp_requests, "w").close()
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree_policy, nodes_data, {"known"})
    policy = FilePriority(source_tree_policy, nodes_data)
    client = Client(api_url, aiosession)
    event_loop.run_until_complete(policy.run(client))

    backend_swhids_requests = get_backend_swhids_order(tmp_requests)

    for swhid in backend_swhids_requests[0:4]:
        assert CoreSWHID.from_string(swhid).object_type == ObjectType.CONTENT

    for swhid in backend_swhids_requests[5:]:
        assert CoreSWHID.from_string(swhid).object_type == ObjectType.DIRECTORY


def test_greedy_bfs_policy(
    live_server, event_loop, aiosession, big_source_tree, tmp_requests
):
    open(tmp_requests, "w").close()
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(big_source_tree, nodes_data, {"known"})
    policy = GreedyBFS(big_source_tree, nodes_data)
    client = Client(api_url, aiosession)
    event_loop.run_until_complete(policy.run(client))

    backend_swhids_requests = get_backend_swhids_order(tmp_requests)

    last_swhid = backend_swhids_requests[-1]
    assert CoreSWHID.from_string(last_swhid).object_type == ObjectType.CONTENT


def test_randomdir_policy(
    live_server,
    event_loop,
    aiosession,
    big_source_tree,
    tmp_requests,
    tmp_accesses,
    mocker,
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
    client = Client(api_url, aiosession)
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
    client = Client(api_url, aiosession)
    event_loop.run_until_complete(policy.run(client))

    assert all(v["known"] is True for k, v in policy.data.items())

    # Check that we only do at least two queries of < 10 items
    backend_known_requests = get_backend_known_requests(tmp_accesses)
    assert len(backend_known_requests) >= 2
    assert all(length <= 10 for length in backend_known_requests)


@pytest.mark.asyncio
async def test_greedy_bfs_get_nodes_chunks(live_server, aiosession, big_source_tree):
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(big_source_tree, nodes_data, {"known"})
    policy = GreedyBFS(big_source_tree, nodes_data)
    client = Client(api_url, aiosession)
    chunks = [
        n_chunk
        async for n_chunk in policy.get_nodes_chunks(
            client, source_size(big_source_tree)
        )
    ]
    assert len(chunks) == 2
    assert chunks[1][-1].object_type == "content"
