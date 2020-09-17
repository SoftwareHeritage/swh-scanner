# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import asyncio
import os
from pathlib import Path
import shutil

import aiohttp
from aioresponses import aioresponses  # type: ignore
import pytest

from swh.model.cli import swhid_of_dir, swhid_of_file
from swh.scanner.model import Tree

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


@pytest.fixture(scope="session")
def temp_folder(tmp_path_factory):
    """Fixture that generates a temporary folder with the following
    structure:

    .. code-block:: python

        root = {
            subdir: {
                subsubdir
                filesample.txt
                filesample2.txt
            }
            subdir2
            subfile.txt
        }
    """
    root = tmp_path_factory.getbasetemp()
    subdir = tmp_path_factory.mktemp("subdir")
    subsubdir = subdir.joinpath("subsubdir")
    subsubdir.mkdir()
    subdir2 = tmp_path_factory.mktemp("subdir2")
    subfile = root / "subfile.txt"
    subfile.touch()
    filesample = subdir / "filesample.txt"
    filesample.touch()
    filesample2 = subdir / "filesample2.txt"
    filesample2.touch()

    avail_path = {
        subdir: swhid_of_dir(bytes(subdir)),
        subsubdir: swhid_of_dir(bytes(subsubdir)),
        subdir2: swhid_of_dir(bytes(subdir2)),
        subfile: swhid_of_file(bytes(subfile)),
        filesample: swhid_of_file(bytes(filesample)),
        filesample2: swhid_of_file(bytes(filesample2)),
    }

    return {
        "root": root,
        "paths": avail_path,
        "filesample": filesample,
        "filesample2": filesample2,
        "subsubdir": subsubdir,
        "subdir": subdir,
    }


@pytest.fixture(scope="function")
def example_tree(temp_folder):
    """Fixture that generate a Tree with the root present in the
       session fixture "temp_folder".
    """
    example_tree = Tree(temp_folder["root"])
    assert example_tree.path == temp_folder["root"]

    return example_tree


@pytest.fixture(scope="function")
def example_dirs(example_tree, temp_folder):
    """
        Fixture that fill the fixture example_tree with the values contained in
        the fixture temp_folder and returns the directories information of the
        filled example_tree.

    """
    root = temp_folder["root"]
    filesample_path = temp_folder["filesample"]
    filesample2_path = temp_folder["filesample2"]
    subsubdir_path = temp_folder["subsubdir"]
    known_paths = [filesample_path, filesample2_path, subsubdir_path]

    for path, swhid in temp_folder["paths"].items():
        if path in known_paths:
            example_tree.addNode(path, swhid, True)
        else:
            example_tree.addNode(path, swhid, False)

    return example_tree.getDirectoriesInfo(root)


@pytest.fixture
def test_sample_folder(datadir, tmp_path):
    """Location of the "data" folder """
    archive_path = Path(os.path.join(datadir, "sample-folder.tgz"))
    assert archive_path.exists()
    shutil.unpack_archive(archive_path, extract_dir=tmp_path)
    test_sample_folder = Path(os.path.join(tmp_path, "sample-folder"))
    assert test_sample_folder.exists()
    return test_sample_folder


@pytest.fixture(scope="session")
def app():
    """Flask backend API (used by live_server)."""
    app = create_app()
    return app
