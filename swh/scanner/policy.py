# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import abc
import asyncio
import itertools
from typing import Dict, List, no_type_check

import aiohttp

from swh.model.from_disk import Directory
from swh.model.identifiers import CONTENT, DIRECTORY

from .data import MerkleNodeInfo
from .exceptions import error_response


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


class Policy(metaclass=abc.ABCMeta):

    data: MerkleNodeInfo
    """information about contents and directories of the merkle tree"""

    source_tree: Directory
    """representation of a source code project directory in the merkle tree"""

    def __init__(self, source_tree: Directory, data: MerkleNodeInfo):
        self.data = data
        self.source_tree = source_tree
        for node in source_tree.iter_tree():
            self.data[node.swhid()] = {"known": None}  # type: ignore

    @abc.abstractmethod
    async def run(
        self, session: aiohttp.ClientSession, api_url: str,
    ):
        """Scan a source code project"""
        raise NotImplementedError("Must implement run method")


class LazyBFS(Policy):
    async def run(
        self, session: aiohttp.ClientSession, api_url: str,
    ):
        queue = []
        queue.append(self.source_tree)

        while queue:
            swhids = [str(node.swhid()) for node in queue]
            swhids_res = await swhids_discovery(swhids, session, api_url)
            for node in queue.copy():
                queue.remove(node)
                self.data[node.swhid()]["known"] = swhids_res[str(node.swhid())][
                    "known"
                ]
                if node.object_type == DIRECTORY:
                    if not self.data[node.swhid()]["known"]:
                        children = [n[1] for n in list(node.items())]
                        queue.extend(children)
                    else:
                        for sub_node in node.iter_tree():
                            if sub_node == node:
                                continue
                            self.data[sub_node.swhid()]["known"] = True  # type: ignore


class FilePriority(Policy):
    @no_type_check
    async def run(
        self, session: aiohttp.ClientSession, api_url: str,
    ):
        # get all the files
        all_contents = list(
            filter(
                lambda node: node.object_type == CONTENT, self.source_tree.iter_tree()
            )
        )
        all_contents.reverse()  # check deepest node first

        # query the backend to get all file contents status
        cnt_swhids = [str(node.swhid()) for node in all_contents]
        cnt_status_res = await swhids_discovery(cnt_swhids, session, api_url)
        # set all the file contents status
        for cnt in all_contents:
            self.data[cnt.swhid()]["known"] = cnt_status_res[str(cnt.swhid())]["known"]
            # set all the upstream directories of unknown file contents to unknown
            if not self.data[cnt.swhid()]["known"]:
                parent = cnt.parents[0]
                while parent:
                    self.data[parent.swhid()]["known"] = False
                    parent = parent.parents[0] if parent.parents else None

        # get all unset directories and check their status
        # (update children directories accordingly)
        unset_dirs = list(
            filter(
                lambda node: node.object_type == DIRECTORY
                and self.data[node.swhid()]["known"] is None,
                self.source_tree.iter_tree(),
            )
        )

        # check unset directories
        for dir_ in unset_dirs:
            if self.data[dir_.swhid()]["known"] is None:
                # update directory status
                dir_status = await swhids_discovery(
                    [str(dir_.swhid())], session, api_url
                )
                dir_known = dir_status[str(dir_.swhid())]["known"]
                self.data[dir_.swhid()]["known"] = dir_known
                if dir_known:
                    sub_dirs = list(
                        filter(
                            lambda n: n.object_type == DIRECTORY
                            and self.data[n.swhid()]["known"] is None,
                            dir_.iter_tree(),
                        )
                    )
                    for node in sub_dirs:
                        self.data[node.swhid()]["known"] = True


class DirectoryPriority(Policy):
    @no_type_check
    async def run(
        self, session: aiohttp.ClientSession, api_url: str,
    ):
        # get all directory contents that have at least one file content
        unknown_dirs = list(
            filter(
                lambda dir_: dir_.object_type == DIRECTORY and self.has_contents(dir_),
                self.source_tree.iter_tree(),
            )
        )
        unknown_dirs.reverse()  # check deepest node first

        for dir_ in unknown_dirs:
            if self.data[dir_.swhid()]["known"] is None:
                dir_status = await swhids_discovery(
                    [str(dir_.swhid())], session, api_url
                )
                dir_known = dir_status[str(dir_.swhid())]["known"]
                self.data[dir_.swhid()]["known"] = dir_known
                # set all the downstream file contents to known
                if dir_known:
                    for cnt in self.get_contents(dir_):
                        self.data[cnt.swhid()]["known"] = True
                # otherwise set all the upstream directories to unknown
                else:
                    parent = dir_.parents[0]
                    while parent:
                        self.data[parent.swhid()]["known"] = False
                        parent = parent.parents[0] if parent.parents else None

        # get remaining directories that have no file contents
        empty_dirs = list(
            filter(
                lambda n: n.object_type == DIRECTORY
                and not self.has_contents(n)
                and self.data[n.swhid()]["known"] is None,
                self.source_tree.iter_tree(),
            )
        )
        empty_dirs_swhids = [str(n.swhid()) for n in empty_dirs]
        empty_dir_status = await swhids_discovery(empty_dirs_swhids, session, api_url)

        # update status of directories that have no file contents
        for dir_ in empty_dirs:
            self.data[dir_.swhid()]["known"] = empty_dir_status[str(dir_.swhid())][
                "known"
            ]

        # check unknown file contents
        unknown_cnts = list(
            filter(
                lambda n: n.object_type == CONTENT
                and self.data[n.swhid()]["known"] is None,
                self.source_tree.iter_tree(),
            )
        )
        unknown_cnts_swhids = [str(n.swhid()) for n in unknown_cnts]
        unknown_cnts_status = await swhids_discovery(
            unknown_cnts_swhids, session, api_url
        )

        for cnt in unknown_cnts:
            self.data[cnt.swhid()]["known"] = unknown_cnts_status[str(cnt.swhid())][
                "known"
            ]

    def has_contents(self, directory: Directory):
        """Check if the directory given in input has contents"""
        for entry in directory.entries:
            if entry["type"] == "file":
                return True
        return False

    def get_contents(self, dir_: Directory):
        """Get all the contents of a given directory"""
        for _, node in list(dir_.items()):
            if node.object_type == CONTENT:
                yield node
