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
    swhid,
    parse_swhid,
    DIRECTORY,
    CONTENT,
)


async def swhids_discovery(
    swhids: List[str], session: aiohttp.ClientSession, api_url: str,
) -> Dict[str, Dict[str, bool]]:
    """API Request to get information about the SoftWare Heritage persistent
    IDentifiers (SWHIDs) given in input.

    Args:
        swhids: a list of SWHIDS
        api_url: url for the API request

    Returns:
        A dictionary with:
        key: SWHID searched
        value:
            value['known'] = True if the SWHID is found
            value['known'] = False if the SWHID is not found

    """
    endpoint = api_url + "known/"
    chunk_size = 1000
    requests = []

    def get_chunk(swhids):
        for i in range(0, len(swhids), chunk_size):
            yield swhids[i : i + chunk_size]

    async def make_request(swhids):
        async with session.post(endpoint, json=swhids) as resp:
            if resp.status != 200:
                error_response(resp.reason, resp.status, endpoint)

            return await resp.json()

    if len(swhids) > chunk_size:
        for swhids_chunk in get_chunk(swhids):
            requests.append(asyncio.create_task(make_request(swhids_chunk)))

        res = await asyncio.gather(*requests)
        # concatenate list of dictionaries
        return dict(itertools.chain.from_iterable(e.items() for e in res))
    else:
        return await make_request(swhids)


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
    """Find the SoftWare Heritage persistent IDentifier (SWHID) of
    the directories and files under a given path.

    Args:
        path: the root path

    Yields:
        pairs of: path, the relative SWHID

    """

    def swhid_of(path):
        if path.is_dir():
            if exclude_patterns:

                def dir_filter(dirpath, *args):
                    return directory_filter(dirpath, exclude_patterns)

            else:
                dir_filter = accept_all_directories

            obj = Directory.from_disk(
                path=bytes(path), dir_filter=dir_filter
            ).get_data()

            return swhid(DIRECTORY, obj)
        else:
            obj = Content.from_file(path=bytes(path)).get_data()
            return swhid(CONTENT, obj)

    dirpath, dnames, fnames = next(os.walk(path))
    for node in itertools.chain(dnames, fnames):
        sub_path = PosixPath(dirpath).joinpath(node)
        yield (sub_path, swhid_of(sub_path))


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
        the SWHID of the subpath and the result of the api call

    """
    parsed_paths = dict(get_subpaths(path, exclude_patterns))
    parsed_swhids = await swhids_discovery(
        list(parsed_paths.values()), session, api_url
    )

    def unpack(tup):
        subpath, swhid = tup
        return (subpath, swhid, parsed_swhids[swhid]["known"])

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
        for path, obj_swhid, known in await parse_path(
            root, session, api_url, exclude_patterns
        ):
            obj_type = parse_swhid(obj_swhid).object_type

            if obj_type == CONTENT:
                source_tree.addNode(path, obj_swhid, known)
            elif obj_type == DIRECTORY and directory_filter(path, exclude_patterns):
                source_tree.addNode(path, obj_swhid, known)
                if not known:
                    await _scan(path, session, api_url, source_tree, exclude_patterns)

    async with aiohttp.ClientSession() as session:
        await _scan(root, session, api_url, source_tree, exclude_patterns)
