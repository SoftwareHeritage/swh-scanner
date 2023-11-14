# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import abc
import itertools
from typing import Iterable, List, no_type_check

from swh.model import discovery, from_disk
from swh.model.from_disk import model
from swh.model.model import Sha1Git

from .client import Client
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
