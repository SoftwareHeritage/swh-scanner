# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import asyncio
import itertools
from typing import Any, Dict, Iterable, List

import aiohttp

from swh.model.cli import model_of_dir
from swh.model.from_disk import Directory
from swh.model.identifiers import DIRECTORY

from .data import MerkleNodeInfo
from .exceptions import error_response
from .output import Output


async def lazy_bfs(
    source_tree: Directory,
    data: MerkleNodeInfo,
    session: aiohttp.ClientSession,
    api_url: str,
):

    queue = []
    queue.append(source_tree)

    while queue:
        swhids = [str(node.swhid()) for node in queue]
        swhids_res = await swhids_discovery(swhids, session, api_url)
        for node in queue.copy():
            queue.remove(node)
            data[node.swhid()]["known"] = swhids_res[str(node.swhid())]["known"]
            if node.object_type == DIRECTORY:
                if not data[node.swhid()]["known"]:
                    children = [n[1] for n in list(node.items())]
                    queue.extend(children)
                else:
                    for sub_node in node.iter_tree(dedup=False):
                        if sub_node == node:
                            continue
                        data[sub_node.swhid()]["known"] = True  # type: ignore


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

        key:
            SWHID searched
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


async def run(
    config: Dict[str, Any], source_tree: Directory, nodes_data: MerkleNodeInfo
) -> None:
    """Start scanning from the given root.

    It fills the source tree with the path discovered.

    Args:
        root: the root path to scan
        api_url: url for the API request

    """
    api_url = config["web-api"]["url"]

    if config["web-api"]["auth-token"]:
        headers = {"Authorization": f"Bearer {config['web-api']['auth-token']}"}
    else:
        headers = {}

    for node in source_tree.iter_tree():
        nodes_data[node.swhid()] = {}  # type: ignore

    async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
        await lazy_bfs(source_tree, nodes_data, session, api_url)


def scan(
    config: Dict[str, Any],
    root_path: str,
    exclude_patterns: Iterable[str],
    out_fmt: str,
    interactive: bool,
):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    converted_patterns = [pattern.encode() for pattern in exclude_patterns]
    source_tree = model_of_dir(root_path.encode(), converted_patterns)
    nodes_data = MerkleNodeInfo()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(config, source_tree, nodes_data))

    out = Output(root_path, nodes_data, source_tree)
    if interactive:
        out.show("interactive")
    else:
        out.show(out_fmt)
