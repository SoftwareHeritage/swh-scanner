# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest
import json
from pathlib import PosixPath

from .data import correct_api_response

from swh.scanner.scanner import pids_discovery, get_subpaths, run
from swh.scanner.model import Tree
from swh.scanner.exceptions import APIError

aio_url = 'http://example.org/api/known/'


def test_scanner_correct_api_request(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(aio_url, status=200, content_type='application/json',
                          body=json.dumps(correct_api_response))

    actual_result = event_loop.run_until_complete(
       pids_discovery([], aiosession, 'http://example.org/api/'))

    assert correct_api_response == actual_result


def test_scanner_raise_apierror(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(aio_url, content_type='application/json',
                          status=413)

    with pytest.raises(APIError):
        event_loop.run_until_complete(
           pids_discovery([], aiosession, 'http://example.org/api/'))


def test_scanner_raise_apierror_input_size_limit(
        event_loop, aiosession, live_server):

    api_url = live_server.url() + '/'
    request = ["swh:1:cnt:7c4c57ba9ff496ad179b8f65b1d286edbda34c9a"
               for i in range(901)]  # /known/ is limited at 900

    with pytest.raises(APIError):
        event_loop.run_until_complete(
           pids_discovery(request, aiosession, api_url))


def test_scanner_get_subpaths(tmp_path, temp_paths):
    for subpath, pid in get_subpaths(tmp_path):
        assert subpath in temp_paths['paths']
        assert pid in temp_paths['pids']


@pytest.mark.options(debug=False)
def test_app(app):
    assert not app.debug


def test_scanner_result(live_server, event_loop, test_folder):
    api_url = live_server.url() + '/'

    result_path = test_folder.joinpath(PosixPath('sample-folder-result.json'))
    with open(result_path, 'r') as json_file:
        expected_result = json.loads(json_file.read())

    sample_folder = test_folder.joinpath(PosixPath('sample-folder'))

    source_tree = Tree(sample_folder)
    event_loop.run_until_complete(
        run(sample_folder, api_url, source_tree))

    actual_result = source_tree.getJsonTree()

    assert actual_result == expected_result
