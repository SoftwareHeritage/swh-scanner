# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest
import asyncio
import aiohttp
import os
from pathlib import PosixPath
from aioresponses import aioresponses  # type: ignore

from swh.model.cli import pid_of_file, pid_of_dir
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


@pytest.fixture(scope='session')
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
    subdir = tmp_path_factory.mktemp('subdir')
    subsubdir = subdir.joinpath('subsubdir')
    subsubdir.mkdir()
    subdir2 = tmp_path_factory.mktemp('subdir2')
    subfile = root / 'subfile.txt'
    subfile.touch()
    filesample = subdir / 'filesample.txt'
    filesample.touch()
    filesample2 = subdir / 'filesample2.txt'
    filesample2.touch()

    avail_path = {
        subdir: pid_of_dir(bytes(subdir)),
        subsubdir: pid_of_dir(bytes(subsubdir)),
        subdir2: pid_of_dir(bytes(subdir2)),
        subfile: pid_of_file(bytes(subfile)),
        filesample: pid_of_file(bytes(filesample)),
        filesample2: pid_of_file(bytes(filesample2))
        }

    return {
        'root': root,
        'paths': avail_path,
        'filesample': filesample,
        'filesample2': filesample2,
        'subsubdir': subsubdir,
        'subdir': subdir
    }


@pytest.fixture(scope='function')
def example_tree(temp_folder):
    """Fixture that generate a Tree with the root present in the
    session fixture "temp_folder".
    """
    example_tree = Tree(temp_folder['root'])
    assert example_tree.path == temp_folder['root']

    return example_tree


@pytest.fixture(scope='function')
def example_dirs(example_tree, temp_folder):
    """
        Fixture that fill the fixture example_tree with the values contained in
        the fixture temp_folder and returns the directories information of the
        filled example_tree.

    """
    root = temp_folder['root']
    filesample_path = temp_folder['filesample']
    filesample2_path = temp_folder['filesample2']
    subsubdir_path = temp_folder['subsubdir']
    known_paths = [filesample_path, filesample2_path, subsubdir_path]

    for path, pid in temp_folder['paths'].items():
        if path in known_paths:
            example_tree.addNode(path, pid)
        else:
            example_tree.addNode(path)

    return example_tree.getDirectoriesInfo(root)


@pytest.fixture
def test_folder():
    """Location of the "data" folder """
    tests_path = PosixPath(os.path.abspath(__file__)).parent
    tests_data_folder = tests_path.joinpath('data')
    assert tests_data_folder.exists()
    return tests_data_folder


@pytest.fixture(scope='session')
def app():
    """Flask backend API (used by live_server)."""
    app = create_app()
    return app
