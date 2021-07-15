# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json

from flask import url_for
import pytest

from swh.model.identifiers import CoreSWHID, ObjectType
from swh.scanner.data import MerkleNodeInfo
from swh.scanner.exceptions import APIError
from swh.scanner.policy import (
    DirectoryPriority,
    FilePriority,
    LazyBFS,
    swhids_discovery,
)

from .data import correct_api_response

aio_url = "http://example.org/api/known/"


def test_scanner_correct_api_request(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(
        aio_url,
        status=200,
        content_type="application/json",
        body=json.dumps(correct_api_response),
    )

    actual_result = event_loop.run_until_complete(
        swhids_discovery([], aiosession, "http://example.org/api/")
    )

    assert correct_api_response == actual_result


def test_scanner_raise_apierror(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(aio_url, content_type="application/json", status=413)

    with pytest.raises(APIError):
        event_loop.run_until_complete(
            swhids_discovery([], aiosession, "http://example.org/api/")
        )


def test_scanner_raise_apierror_input_size_limit(event_loop, aiosession, live_server):

    api_url = url_for("index", _external=True)
    request = [
        "swh:1:cnt:7c4c57ba9ff496ad179b8f65b1d286edbda34c9a" for i in range(901)
    ]  # /known/ is limited at 900

    with pytest.raises(APIError):
        event_loop.run_until_complete(swhids_discovery(request, aiosession, api_url))


def test_scanner_directory_priority_has_contents(source_tree):
    nodes_data = MerkleNodeInfo()
    policy = DirectoryPriority(source_tree, nodes_data)
    assert policy.has_contents(source_tree[b"/bar/barfoo"])


def get_backend_swhids_order(tmp_requests):
    with open(tmp_requests, "r") as f:
        backend_swhids_order = f.readlines()

    return [x.strip() for x in backend_swhids_order]


def test_lazybfs_policy(
    live_server, aiosession, event_loop, source_tree_policy, tmp_requests
):
    open(tmp_requests, "w").close()
    api_url = url_for("index", _external=True)

    nodes_data = MerkleNodeInfo()
    policy = LazyBFS(source_tree_policy, nodes_data)
    event_loop.run_until_complete(policy.run(aiosession, api_url))

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
    policy = DirectoryPriority(source_tree_policy, nodes_data)
    event_loop.run_until_complete(policy.run(aiosession, api_url))

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
    policy = FilePriority(source_tree_policy, nodes_data)
    event_loop.run_until_complete(policy.run(aiosession, api_url))

    backend_swhids_requests = get_backend_swhids_order(tmp_requests)

    for swhid in backend_swhids_requests[0:4]:
        assert CoreSWHID.from_string(swhid).object_type == ObjectType.CONTENT

    for swhid in backend_swhids_requests[5:]:
        assert CoreSWHID.from_string(swhid).object_type == ObjectType.DIRECTORY
