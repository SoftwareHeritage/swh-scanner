# Copyright (C) 2020-2021  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import asyncio
import os
from pathlib import Path
import shutil
import sys

import aiohttp
from aioresponses import aioresponses
import pytest

from swh.model.cli import model_of_dir
from swh.scanner.data import MerkleNodeInfo
from swh.scanner.policy import QUERY_LIMIT

from .data import present_swhids
from .flask_api import create_app


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m


@pytest.fixture
def event_loop():
    """Fixture that generate an asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def aiosession():
    """Fixture that generate an aiohttp Client Session."""
    session = aiohttp.ClientSession()
    yield session
    session.detach()


@pytest.fixture(scope="function")
def test_sample_folder(datadir, tmp_path):
    """Location of the "data" folder"""
    archive_path = Path(os.path.join(datadir, "sample-folder.tgz"))
    assert archive_path.exists()
    shutil.unpack_archive(archive_path, extract_dir=tmp_path)
    test_sample_folder = Path(os.path.join(tmp_path, "sample-folder"))
    assert test_sample_folder.exists()
    return test_sample_folder


@pytest.fixture(scope="function")
def test_sample_folder_policy(datadir, tmp_path):
    """Location of the sample source code project to test the scanner policies"""
    archive_path = Path(os.path.join(datadir, "sample-folder-policy.tgz"))
    assert archive_path.exists()
    shutil.unpack_archive(archive_path, extract_dir=tmp_path)
    test_sample_folder = Path(os.path.join(tmp_path, "sample-folder-policy"))
    assert test_sample_folder.exists()
    return test_sample_folder


@pytest.fixture(scope="function")
def source_tree(test_sample_folder):
    """Generate a model.from_disk.Directory object from the test sample
    folder
    """
    return model_of_dir(str(test_sample_folder).encode())


@pytest.fixture(scope="function")
def big_source_tree(tmp_path):
    """Generate a model.from_disk.Directory from a "big" temporary directory
    (more than 1000 nodes)
    """
    # workaround to avoid a RecursionError that could be generated while creating
    # a large number of directories
    sys.setrecursionlimit(1100)
    dir_ = tmp_path / "big-directory"
    sub_dirs = dir_
    for i in range(0, QUERY_LIMIT + 1):
        sub_dirs = sub_dirs / "dir"
    sub_dirs.mkdir(parents=True, exist_ok=True)
    file_ = sub_dirs / "file.org"
    file_.touch()
    dir_obj = model_of_dir(str(dir_).encode())
    return dir_obj


@pytest.fixture(scope="function")
def source_tree_policy(test_sample_folder_policy):
    """Generate a model.from_disk.Directory object from the test sample
    folder
    """
    return model_of_dir(str(test_sample_folder_policy).encode())


@pytest.fixture(scope="function")
def source_tree_dirs(source_tree):
    """Returns a list of all directories contained inside the test sample
    folder
    """
    root = source_tree.data["path"]
    return list(
        map(
            lambda n: Path(n.data["path"].decode()).relative_to(Path(root.decode())),
            filter(
                lambda n: n.object_type == "directory"
                and not n.data["path"] == source_tree.data["path"],
                source_tree.iter_tree(dedup=False),
            ),
        )
    )


@pytest.fixture(scope="function")
def nodes_data(source_tree):
    """mock known status of file/dirs in test_sample_folder"""
    nodes_data = MerkleNodeInfo()
    for node in source_tree.iter_tree():
        nodes_data[node.swhid()] = {"known": True}
    return nodes_data


@pytest.fixture
def test_swhids_sample(tmp_path):
    """Create and return the opened "swhids_sample" file,
    filled with present swhids present in data.py
    """
    test_swhids_sample = Path(os.path.join(tmp_path, "swhids_sample.txt"))

    with open(test_swhids_sample, "w") as f:
        f.write("\n".join(swhid for swhid in present_swhids))

    assert test_swhids_sample.exists()
    return open(test_swhids_sample, "r")


@pytest.fixture(scope="session")
def tmp_requests(tmpdir_factory):
    requests_file = tmpdir_factory.mktemp("data").join("requests.json")
    return requests_file


@pytest.fixture(scope="session")
def app(tmp_requests):
    """Flask backend API (used by live_server)."""
    app = create_app(tmp_requests)
    return app
