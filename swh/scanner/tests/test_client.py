# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json

import pytest

from swh.model.swhids import CoreSWHID
from swh.scanner.client import Client
from swh.scanner.exceptions import APIError

from .data import correct_known_api_response, correct_origin_api_response

AIO_URL = "http://example.org/api/"
KNOWN_URL = f"{AIO_URL}known/"
ORIGIN_URL = f"{AIO_URL}graph/randomwalk/"


def test_client_known_correct_api_request(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(
        KNOWN_URL,
        status=200,
        content_type="application/json",
        body=json.dumps(correct_known_api_response),
    )

    client = Client(AIO_URL, aiosession)
    actual_result = event_loop.run_until_complete(client.known([]))

    assert correct_known_api_response == actual_result


def test_client_known_raise_apierror(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(KNOWN_URL, content_type="application/json", status=413)

    client = Client(AIO_URL, aiosession)
    with pytest.raises(APIError):
        event_loop.run_until_complete(client.known([]))


def test_client_get_origin_correct_api_request(
    mock_aioresponse, event_loop, aiosession
):
    origin_url = (
        f"{ORIGIN_URL}swh:1:dir:01fa282bb80be5907505d44b4692d3fa40fad140/ori"
        f"/?direction=backward&limit=-1&resolve_origins=true"
    )
    mock_aioresponse.get(
        origin_url,
        status=200,
        body=correct_origin_api_response,
    )

    client = Client(AIO_URL, aiosession)
    swhid = CoreSWHID.from_string("swh:1:dir:01fa282bb80be5907505d44b4692d3fa40fad140")
    actual_result = event_loop.run_until_complete(client.get_origin(swhid))

    assert correct_origin_api_response == actual_result
