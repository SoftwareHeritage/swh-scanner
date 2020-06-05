# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest
import json
from pathlib import PosixPath

from .data import correct_api_response, present_swhids, to_exclude_swhid

from swh.scanner.scanner import pids_discovery, get_subpaths, run
from swh.scanner.model import Tree
from swh.scanner.cli import extract_regex_objs
from swh.scanner.exceptions import APIError

aio_url = "http://example.org/api/known/"


def test_scanner_correct_api_request(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(
        aio_url,
        status=200,
        content_type="application/json",
        body=json.dumps(correct_api_response),
    )

    actual_result = event_loop.run_until_complete(
        pids_discovery([], aiosession, "http://example.org/api/")
    )

    assert correct_api_response == actual_result


def test_scanner_raise_apierror(mock_aioresponse, event_loop, aiosession):
    mock_aioresponse.post(aio_url, content_type="application/json", status=413)

    with pytest.raises(APIError):
        event_loop.run_until_complete(
            pids_discovery([], aiosession, "http://example.org/api/")
        )


def test_scanner_raise_apierror_input_size_limit(event_loop, aiosession, live_server):

    api_url = live_server.url() + "/"
    request = [
        "swh:1:cnt:7c4c57ba9ff496ad179b8f65b1d286edbda34c9a" for i in range(901)
    ]  # /known/ is limited at 900

    with pytest.raises(APIError):
        event_loop.run_until_complete(pids_discovery(request, aiosession, api_url))


def test_scanner_get_subpaths(temp_folder):
    root = temp_folder["root"]

    actual_result = []
    for subpath, pid in get_subpaths(root, tuple()):
        # also check if it's a symlink since pytest tmp_dir fixture create
        # also a symlink to each directory inside the tmp_dir path
        if subpath.is_dir() and not subpath.is_symlink():
            actual_result.append((subpath, pid))

    assert len(actual_result) == 2


@pytest.mark.options(debug=False)
def test_app(app):
    assert not app.debug


def test_scanner_result(live_server, event_loop, test_folder):
    api_url = live_server.url() + "/"

    sample_folder = test_folder.joinpath(PosixPath("sample-folder"))

    source_tree = Tree(sample_folder)
    event_loop.run_until_complete(run(sample_folder, api_url, source_tree, set()))

    for child_node in source_tree.iterate():
        node_info = list(child_node.attributes.values())[0]
        if node_info["swhid"] in present_swhids:
            assert node_info["known"] is True
        else:
            assert node_info["known"] is False


def test_scanner_result_with_exclude_patterns(live_server, event_loop, test_folder):
    api_url = live_server.url() + "/"

    sample_folder = test_folder.joinpath(PosixPath("sample-folder"))

    patterns = (str(sample_folder) + "/toexclude",)
    exclude_pattern = {
        reg_obj for reg_obj in extract_regex_objs(sample_folder, patterns)
    }

    source_tree = Tree(sample_folder)
    event_loop.run_until_complete(
        run(sample_folder, api_url, source_tree, exclude_pattern)
    )

    for child_node in source_tree.iterate():
        node_info = list(child_node.attributes.values())[0]
        assert node_info["swhid"] != to_exclude_swhid
