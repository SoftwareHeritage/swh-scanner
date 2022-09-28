# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import asyncio
from typing import Any, Dict, Iterable

import aiohttp

from swh.model.cli import model_of_dir
from swh.model.from_disk import Directory

from .client import Client
from .data import MerkleNodeInfo, add_origin, init_merkle_node_info
from .output import Output
from .policy import (
    QUERY_LIMIT,
    DirectoryPriority,
    FilePriority,
    GreedyBFS,
    LazyBFS,
    QueryAll,
    source_size,
)


async def run(
    config: Dict[str, Any],
    policy,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    extra_info: set,
) -> None:
    """Scan a given source code according to the policy given in input."""
    api_url = config["web-api"]["url"]

    if config["web-api"]["auth-token"]:
        headers = {"Authorization": f"Bearer {config['web-api']['auth-token']}"}
    else:
        headers = {}

    async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
        client = Client(api_url, session)
        for info in extra_info:
            if info == "known":
                await policy.run(client)
            elif info == "origin":
                await add_origin(source_tree, nodes_data, client)
            else:
                raise Exception(f"The information '{info}' cannot be retrieved")


def get_policy_obj(source_tree: Directory, nodes_data: MerkleNodeInfo, policy: str):
    if policy == "auto":
        return (
            QueryAll(source_tree, nodes_data)
            if source_size(source_tree) <= QUERY_LIMIT
            else LazyBFS(source_tree, nodes_data)
        )
    elif policy == "bfs":
        return LazyBFS(source_tree, nodes_data)
    elif policy == "greedybfs":
        return GreedyBFS(source_tree, nodes_data)
    elif policy == "filepriority":
        return FilePriority(source_tree, nodes_data)
    elif policy == "dirpriority":
        return DirectoryPriority(source_tree, nodes_data)
    else:
        raise Exception(f"policy '{policy}' not found")


# here is a set of directory we should disregard
#
# TODO: make its usage configurable
# TODO: make it extensible through configuration
COMMON_EXCLUDE_PATTERNS = [
    b".bzr",
    b".coverage",
    b"*.egg-info",
    b".eggs",
    b".git",
    b".hg",
    b".mypy_cache",
    b"__pycache__",
    b".svn",
    b".tox",
]
COMMON_EXCLUDE_PATTERNS.extend([b"*/" + p for p in COMMON_EXCLUDE_PATTERNS])


def scan(
    config: Dict[str, Any],
    root_path: str,
    exclude_patterns: Iterable[str],
    out_fmt: str,
    interactive: bool,
    policy: str,
    extra_info: set,
):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    converted_patterns = [pattern.encode() for pattern in exclude_patterns]
    converted_patterns.extend(COMMON_EXCLUDE_PATTERNS)
    source_tree = model_of_dir(root_path.encode(), converted_patterns)

    nodes_data = MerkleNodeInfo()
    extra_info.add("known")
    init_merkle_node_info(source_tree, nodes_data, extra_info)

    policy = get_policy_obj(source_tree, nodes_data, policy)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(config, policy, source_tree, nodes_data, extra_info))

    out = Output(root_path, nodes_data, source_tree)
    if interactive:
        out.show("interactive")
    else:
        out.show(out_fmt)
