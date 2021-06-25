# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json

from flask import url_for
import pytest

from swh.scanner.data import MerkleNodeInfo
from swh.scanner.exceptions import APIError
from swh.scanner.scanner import run, swhids_discovery

from .data import correct_api_response, unknown_swhids

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


@pytest.mark.options(debug=False)
def test_app(app):
    assert not app.debug


def test_scanner_result(live_server, event_loop, source_tree):
    api_url = url_for("index", _external=True)
    config = {"web-api": {"url": api_url, "auth-token": None}}

    nodes_data = MerkleNodeInfo()
    event_loop.run_until_complete(run(config, source_tree, nodes_data))
    for node in source_tree.iter_tree():
        if str(node.swhid()) in unknown_swhids:
            assert nodes_data[node.swhid()]["known"] is False
        else:
            assert nodes_data[node.swhid()]["known"] is True
