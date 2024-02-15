# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import abc
import itertools
from typing import Iterable, List, no_type_check

from swh.core.utils import grouper
from swh.model import discovery, from_disk
from swh.model.from_disk import model
from swh.model.model import Sha1Git

from .client import QUERY_LIMIT, Client
from .data import MerkleNodeInfo


def source_size(source_tree: from_disk.Directory):
    """return the size of a source tree as the number of nodes it contains"""
    return sum(1 for n in source_tree.iter_tree(dedup=False))


class Policy(metaclass=abc.ABCMeta):
    data: MerkleNodeInfo
    """information about contents and directories of the merkle tree"""

    source_tree: from_disk.Directory
    """representation of a source code project directory in the merkle tree"""

    def __init__(self, source_tree: from_disk.Directory, data: MerkleNodeInfo):
        self.source_tree = source_tree
        self.data = data

    @abc.abstractmethod
    async def run(self, client: Client):
        """Scan a source code project"""
        raise NotImplementedError("Must implement run method")


class LazyBFS(Policy):
    """Read nodes in the merkle tree using the BFS algorithm.
    Lookup only directories that are unknown otherwise set all the downstream
    contents to known.
    """

    async def run(self, client: Client):
        queue = []
        queue.append(self.source_tree)

        while queue:
            swhids = [node.swhid() for node in queue]
            swhids_res = await client.known(swhids)
            for node in queue.copy():
                queue.remove(node)
                self.data[node.swhid()]["known"] = swhids_res[str(node.swhid())][
                    "known"
                ]
                if node.object_type == "directory":
                    if not self.data[node.swhid()]["known"]:
                        children = [n[1] for n in list(node.items())]
                        queue.extend(children)
                    else:
                        for sub_node in node.iter_tree():
                            if sub_node == node:
                                continue
                            self.data[sub_node.swhid()]["known"] = True  # type: ignore


class GreedyBFS(Policy):
    """Query graph nodes in chunks (to maximize the Web API rate limit use) and set the
    downstream contents of known directories to known.
    """

    async def run(self, client: Client):
        ssize = source_size(self.source_tree)
        seen = []

        async for nodes_chunk in self.get_nodes_chunks(client, ssize):
            for node in nodes_chunk:
                seen.append(node)
                if len(seen) == ssize:
                    return
                if node.object_type == "directory" and self.data[node.swhid()]["known"]:
                    sub_nodes = [n for n in node.iter_tree(dedup=False)]
                    sub_nodes.remove(node)  # remove root node
                    for sub_node in sub_nodes:
                        seen.append(sub_node)
                        self.data[sub_node.swhid()]["known"] = True

    @no_type_check
    async def get_nodes_chunks(self, client: Client, ssize: int):
        """Query chunks of QUERY_LIMIT nodes at once in order to fill the Web API
        rate limit. It query all the nodes in the case the source code contains
        less than QUERY_LIMIT nodes.
        """
        nodes = self.source_tree.iter_tree(dedup=False)
        for nodes_chunk in grouper(nodes, QUERY_LIMIT):
            nodes_chunk = [n for n in nodes_chunk]
            swhids = [node.swhid() for node in nodes_chunk]
            swhids_res = await client.known(swhids)
            for node in nodes_chunk:
                swhid = node.swhid()
                self.data[swhid]["known"] = swhids_res[str(swhid)]["known"]
            yield nodes_chunk


class FilePriority(Policy):
    """Check the Merkle tree querying all the file contents and set all the upstream
    directories to unknown in the case a file content is unknown.
    Finally check all the directories which status is still unknown and set all the
    sub-directories of known directories to known.
    """

    @no_type_check
    async def run(self, client: Client):
        # get all the files
        all_contents = list(
            filter(
                lambda node: node.object_type == "content", self.source_tree.iter_tree()
            )
        )
        all_contents.reverse()  # check deepest node first

        # query the backend to get all file contents status
        cnt_swhids = [node.swhid() for node in all_contents]
        cnt_status_res = await client.known(cnt_swhids)
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
                lambda node: node.object_type == "directory"
                and self.data[node.swhid()]["known"] is None,
                self.source_tree.iter_tree(),
            )
        )

        # check unset directories
        for dir_ in unset_dirs:
            if self.data[dir_.swhid()]["known"] is None:
                # update directory status
                dir_status = await client.known([dir_.swhid()])
                dir_known = dir_status[str(dir_.swhid())]["known"]
                self.data[dir_.swhid()]["known"] = dir_known
                if dir_known:
                    sub_dirs = list(
                        filter(
                            lambda n: n.object_type == "directory"
                            and self.data[n.swhid()]["known"] is None,
                            dir_.iter_tree(),
                        )
                    )
                    for node in sub_dirs:
                        self.data[node.swhid()]["known"] = True


class DirectoryPriority(Policy):
    """Check the Merkle tree querying all the directories that have at least one file
    content and set all the upstream directories to unknown in the case a directory
    is unknown otherwise set all the downstream contents to known.
    Finally check the status of empty directories and all the remaining file
    contents.
    """

    @no_type_check
    async def run(self, client: Client):
        # get all directory contents that have at least one file content
        unknown_dirs = list(
            filter(
                lambda dir_: dir_.object_type == "directory"
                and self.has_contents(dir_),
                self.source_tree.iter_tree(),
            )
        )
        unknown_dirs.reverse()  # check deepest node first

        for dir_ in unknown_dirs:
            if self.data[dir_.swhid()]["known"] is None:
                dir_status = await client.known([dir_.swhid()])
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
                lambda n: n.object_type == "directory"
                and not self.has_contents(n)
                and self.data[n.swhid()]["known"] is None,
                self.source_tree.iter_tree(),
            )
        )
        empty_dirs_swhids = [n.swhid() for n in empty_dirs]
        empty_dir_status = await client.known(empty_dirs_swhids)

        # update status of directories that have no file contents
        for dir_ in empty_dirs:
            self.data[dir_.swhid()]["known"] = empty_dir_status[str(dir_.swhid())][
                "known"
            ]

        # check unknown file contents
        unknown_cnts = list(
            filter(
                lambda n: n.object_type == "content"
                and self.data[n.swhid()]["known"] is None,
                self.source_tree.iter_tree(),
            )
        )
        unknown_cnts_swhids = [n.swhid() for n in unknown_cnts]
        unknown_cnts_status = await client.known(unknown_cnts_swhids)

        for cnt in unknown_cnts:
            self.data[cnt.swhid()]["known"] = unknown_cnts_status[str(cnt.swhid())][
                "known"
            ]

    def has_contents(self, directory: from_disk.Directory):
        """Check if the directory given in input has contents"""
        for entry in directory.entries:
            if entry["type"] == "file":
                return True
        return False

    def get_contents(self, dir_: from_disk.Directory):
        """Get all the contents of a given directory"""
        for _, node in list(dir_.items()):
            if node.object_type == "content":
                yield node


class WebAPIConnection(discovery.ArchiveDiscoveryInterface):
    """Use the web APIs to query the archive"""

    def __init__(
        self,
        contents: List[model.Content],
        skipped_contents: List[model.SkippedContent],
        directories: List[model.Directory],
        client: Client,
    ) -> None:
        self.contents = contents
        self.skipped_contents = skipped_contents
        self.directories = directories
        self.client = client

        self.sha_to_swhid = {}
        self.swhid_to_sha = {}
        for content in contents:
            swhid = str(content.swhid())
            self.sha_to_swhid[content.sha1_git] = swhid
            self.swhid_to_sha[swhid] = content.sha1_git

        for directory in directories:
            swhid = str(directory.swhid())
            self.sha_to_swhid[directory.id] = swhid
            self.swhid_to_sha[swhid] = directory.id

    async def content_missing(self, contents: List[Sha1Git]) -> List[Sha1Git]:
        """List content missing from the archive by sha1"""
        return await self._missing(contents)

    async def skipped_content_missing(
        self, skipped_contents: List[Sha1Git]
    ) -> Iterable[Sha1Git]:
        """List skipped content missing from the archive by sha1"""
        # TODO what should we do about skipped contents?
        return skipped_contents

    async def directory_missing(self, directories: List[Sha1Git]) -> Iterable[Sha1Git]:
        """List directories missing from the archive by sha1"""
        return await self._missing(directories)

    async def _missing(self, shas: List[Sha1Git]) -> List[Sha1Git]:
        # Ignore mypy complaining about string being passed, since `known`
        # transforms them to string immediately.
        res = await self.client.known([self.sha_to_swhid[o] for o in shas])  # type: ignore
        return [self.swhid_to_sha[k] for k, v in res.items() if not v["known"]]


class RandomDirSamplingPriority(Policy):
    """Check the Merkle tree querying random directories. Set all ancestors to
    unknown for unknown directories, otherwise set all descendants to known.
    Finally check all the remaining file contents.
    """

    @no_type_check
    async def run(self, client: Client):
        contents, skipped_contents, directories = from_disk.iter_directory(
            self.source_tree
        )

        # `filter_known_objects` only does filtering by random directory
        # sampling for now.
        # In the future, it could/will grow a parameter to choose/pass in a
        # different discovery implementation.
        # From this call site, we are relying on this behavior in order to
        # *actually* be a random directory sampling policy, but any change away
        # from under us in `filter_known_objects` should trigger a test failure.
        get_unknowns = discovery.filter_known_objects(
            WebAPIConnection(contents, skipped_contents, directories, client),
        )

        unknowns = set(itertools.chain(*await get_unknowns))

        for obj in itertools.chain(contents, skipped_contents, directories):
            self.data[obj.swhid()]["known"] = obj not in unknowns


class QueryAll(Policy):
    """Check the status of every node in the Merkle tree."""

    @no_type_check
    async def run(self, client: Client):
        all_nodes = [node for node in self.source_tree.iter_tree()]
        all_swhids = [node.swhid() for node in all_nodes]
        swhids_res = await client.known(all_swhids)
        for node in all_nodes:
            self.data[node.swhid()]["known"] = swhids_res[str(node.swhid())]["known"]
