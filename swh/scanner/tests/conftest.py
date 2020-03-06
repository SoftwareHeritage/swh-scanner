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
def temp_paths(tmp_path_factory):
    """Fixture to generate temporary paths"""
    subpath = tmp_path_factory.getbasetemp()
    subdir = tmp_path_factory.mktemp('subdir')
    subdir2 = tmp_path_factory.mktemp('subdir2')
    subfile = subpath.joinpath(PosixPath('./subfile.txt'))
    subfile.touch()

    avail_path = [subdir, subdir2, subfile]
    avail_pid = [pid_of_dir(bytes(subdir)), pid_of_dir(bytes(subdir2)),
                 pid_of_file(bytes(subfile))]

    return {'paths': avail_path, 'pids': avail_pid}


@pytest.fixture(scope='session')
def app():
    """Flask backend API (used by live_server)."""
    app = create_app()
    return app


@pytest.fixture
def test_folder():
    tests_path = PosixPath(os.path.abspath(__file__)).parent
    tests_data_folder = tests_path.joinpath('data')
    assert tests_data_folder.exists()
    return tests_data_folder
