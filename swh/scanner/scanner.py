# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os
import itertools
import asyncio
import aiohttp
from typing import List, Dict, Tuple, Iterator
from pathlib import PosixPath

from .exceptions import APIError
from .model import Tree

from swh.model.cli import pid_of_file, pid_of_dir
from swh.model.identifiers import (
        parse_persistent_identifier,
        DIRECTORY, CONTENT
)


async def pids_discovery(
        pids: List[str], session: aiohttp.ClientSession, api_url: str,
        ) -> Dict[str, Dict[str, bool]]:
    """API Request to get information about the persistent identifiers given in
    input.

    Args:
        pids: a list of persistent identifier
        api_url: url for the API request

    Returns:
        A dictionary with:
        key: persistent identifier searched
        value:
            value['known'] = True if the pid is found
            value['known'] = False if the pid is not found

    """
    endpoint = api_url + 'known/'
    chunk_size = 1000
    requests = []

    def get_chunk(pids):
        for i in range(0, len(pids), chunk_size):
            yield pids[i:i + chunk_size]

    async def make_request(pids):
        async with session.post(endpoint, json=pids) as resp:
            if resp.status != 200:
                error_message = '%s with given values %s' % (
                    resp.text, str(pids))
                raise APIError(error_message)

            return await resp.json()

    if len(pids) > chunk_size:
        for pids_chunk in get_chunk(pids):
            requests.append(asyncio.create_task(
                make_request(pids_chunk)))

        res = await asyncio.gather(*requests)
        # concatenate list of dictionaries
        return dict(itertools.chain.from_iterable(e.items() for e in res))
    else:
        return await make_request(pids)


def get_subpaths(
        path: PosixPath) -> Iterator[Tuple[PosixPath, str]]:
    """Find the persistent identifier of the directories and files under a
    given path.

    Args:
        path: the root path

    Yields:
        pairs of: path, the relative persistent identifier

    """
    def pid_of(path):
        if path.is_dir():
            return pid_of_dir(bytes(path))
        elif path.is_file():
            return pid_of_file(bytes(path))

    dirpath, dnames, fnames = next(os.walk(path))
    for node in itertools.chain(dnames, fnames):
        sub_path = PosixPath(dirpath).joinpath(node)
        yield (sub_path, pid_of(sub_path))


async def parse_path(
        path: PosixPath, session: aiohttp.ClientSession, api_url: str
        ) -> Iterator[Tuple[str, str, bool]]:
    """Check if the sub paths of the given path are present in the
    archive or not.

    Args:
        path: the source path
        api_url: url for the API request

    Returns:
        a map containing tuples with: a subpath of the given path,
        the pid of the subpath and the result of the api call

    """
    parsed_paths = dict(get_subpaths(path))
    parsed_pids = await pids_discovery(
        list(parsed_paths.values()), session, api_url)

    def unpack(tup):
        subpath, pid = tup
        return (subpath, pid, parsed_pids[pid]['known'])

    return map(unpack, parsed_paths.items())


async def run(
        root: PosixPath, api_url: str, source_tree: Tree) -> None:
    """Start scanning from the given root.

    It fills the source tree with the path discovered.

    Args:
        root: the root path to scan
        api_url: url for the API request

    """
    async def _scan(root, session, api_url, source_tree):
        for path, pid, found in await parse_path(root, session, api_url):
            obj_type = parse_persistent_identifier(pid).object_type

            if obj_type == CONTENT:
                source_tree.addNode(path, pid if found else None)
            elif obj_type == DIRECTORY:
                if found:
                    source_tree.addNode(path, pid)
                else:
                    source_tree.addNode(path)
                    await _scan(path, session, api_url, source_tree)

    async with aiohttp.ClientSession() as session:
        await _scan(root, session, api_url, source_tree)
