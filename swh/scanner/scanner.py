# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import asyncio
from typing import Any, Dict, Iterable

import aiohttp

from swh.model.cli import model_of_dir
from swh.model.from_disk import Directory

from .data import MerkleNodeInfo
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


async def run(config: Dict[str, Any], policy) -> None:
    """Scan a given source code according to the policy given in input.

    Args:
        root: the root path to scan
        api_url: url for the API request

    """
    api_url = config["web-api"]["url"]

    if config["web-api"]["auth-token"]:
        headers = {"Authorization": f"Bearer {config['web-api']['auth-token']}"}
    else:
        headers = {}

    async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
        await policy.run(session, api_url)


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


def scan(
    config: Dict[str, Any],
    root_path: str,
    exclude_patterns: Iterable[str],
    out_fmt: str,
    interactive: bool,
    policy: str,
):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    converted_patterns = [pattern.encode() for pattern in exclude_patterns]
    source_tree = model_of_dir(root_path.encode(), converted_patterns)
    nodes_data = MerkleNodeInfo()
    policy = get_policy_obj(source_tree, nodes_data, policy)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(config, policy))

    out = Output(root_path, nodes_data, source_tree)
    if interactive:
        out.show("interactive")
    else:
        out.show(out_fmt)
