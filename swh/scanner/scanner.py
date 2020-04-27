# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os
import itertools
import asyncio
import aiohttp
from typing import List, Dict, Tuple, Iterator, Union, Set, Any
from pathlib import PosixPath

from .exceptions import error_response
from .model import Tree

from swh.model.from_disk import Directory, Content, accept_all_directories
from swh.model.identifiers import (
    persistent_identifier,
    parse_persistent_identifier,
    DIRECTORY,
    CONTENT,
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
    endpoint = api_url + "known/"
    chunk_size = 1000
    requests = []

    def get_chunk(pids):
        for i in range(0, len(pids), chunk_size):
            yield pids[i : i + chunk_size]

    async def make_request(pids):
        async with session.post(endpoint, json=pids) as resp:
            if resp.status != 200:
                error_response(resp.reason, resp.status, endpoint)

            return await resp.json()

    if len(pids) > chunk_size:
        for pids_chunk in get_chunk(pids):
            requests.append(asyncio.create_task(make_request(pids_chunk)))

        res = await asyncio.gather(*requests)
        # concatenate list of dictionaries
        return dict(itertools.chain.from_iterable(e.items() for e in res))
    else:
        return await make_request(pids)


def directory_filter(path_name: Union[str, bytes], exclude_patterns: Set[Any]) -> bool:
    """It checks if the path_name is matching with the patterns given in input.

    It is also used as a `dir_filter` function when generating the directory
    object from `swh.model.from_disk`

    Returns:
        False if the directory has to be ignored, True otherwise

    """
    path = PosixPath(path_name.decode() if isinstance(path_name, bytes) else path_name)
    for sre_pattern in exclude_patterns:
        if sre_pattern.match(str(path)):
            return False
    return True


def get_subpaths(
    path: PosixPath, exclude_patterns: Set[Any]
) -> Iterator[Tuple[PosixPath, str]]:
    """Find the persistent identifier of the directories and files under a
    given path.

    Args:
        path: the root path

    Yields:
        pairs of: path, the relative persistent identifier

    """

    def pid_of(path):
        if path.is_dir():
            if exclude_patterns:

                def dir_filter(dirpath, *args):
                    return directory_filter(dirpath, exclude_patterns)

            else:
                dir_filter = accept_all_directories

            obj = Directory.from_disk(
                path=bytes(path), dir_filter=dir_filter
            ).get_data()

            return persistent_identifier(DIRECTORY, obj)
        else:
            obj = Content.from_file(path=bytes(path)).get_data()
            return persistent_identifier(CONTENT, obj)

    dirpath, dnames, fnames = next(os.walk(path))
    for node in itertools.chain(dnames, fnames):
        sub_path = PosixPath(dirpath).joinpath(node)
        yield (sub_path, pid_of(sub_path))


async def parse_path(
    path: PosixPath,
    session: aiohttp.ClientSession,
    api_url: str,
    exclude_patterns: Set[Any],
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
    parsed_paths = dict(get_subpaths(path, exclude_patterns))
    parsed_pids = await pids_discovery(list(parsed_paths.values()), session, api_url)

    def unpack(tup):
        subpath, pid = tup
        return (subpath, pid, parsed_pids[pid]["known"])

    return map(unpack, parsed_paths.items())


async def run(
    root: PosixPath, api_url: str, source_tree: Tree, exclude_patterns: Set[Any]
) -> None:
    """Start scanning from the given root.

    It fills the source tree with the path discovered.

    Args:
        root: the root path to scan
        api_url: url for the API request

    """

    async def _scan(root, session, api_url, source_tree, exclude_patterns):
        for path, pid, known in await parse_path(
            root, session, api_url, exclude_patterns
        ):
            obj_type = parse_persistent_identifier(pid).object_type

            if obj_type == CONTENT:
                source_tree.addNode(path, pid, known)
            elif obj_type == DIRECTORY and directory_filter(path, exclude_patterns):
                source_tree.addNode(path, pid, known)
                if not known:
                    await _scan(path, session, api_url, source_tree, exclude_patterns)

    async with aiohttp.ClientSession() as session:
        await _scan(root, session, api_url, source_tree, exclude_patterns)
