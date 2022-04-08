# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path
from typing import Dict, Optional, Tuple

from swh.model.exceptions import ValidationError
from swh.model.from_disk import Directory
from swh.model.swhids import CoreSWHID

from .client import Client

SUPPORTED_INFO = {"known", "origin"}


class MerkleNodeInfo(dict):
    """Store additional information about Merkle DAG nodes, using SWHIDs as keys"""

    def __setitem__(self, key, value):
        """The keys must be valid valid Software Heritage Persistent Identifiers
        while values must be dict.
        """
        if not isinstance(key, CoreSWHID):
            raise ValidationError("keys must be valid SWHID(s)")

        if not isinstance(value, dict):
            raise ValidationError(f"values must be dict, not {type(value)}")

        super(MerkleNodeInfo, self).__setitem__(key, value)


def init_merkle_node_info(source_tree: Directory, data: MerkleNodeInfo, info: set):
    """Populate the MerkleNodeInfo with the SWHIDs of the given source tree and the
    attributes that will be stored.
    """
    if not info:
        raise Exception("Data initialization requires node attributes values.")
    nodes_info: Dict[str, Optional[str]] = {}
    for ainfo in info:
        if ainfo in SUPPORTED_INFO:
            nodes_info[ainfo] = None
        else:
            raise Exception(f"Information {ainfo} is not supported.")

    for node in source_tree.iter_tree():
        data[node.swhid()] = nodes_info.copy()  # type: ignore


async def add_origin(source_tree: Directory, data: MerkleNodeInfo, client: Client):
    """Store origin information about software artifacts retrieved from the Software
    Heritage graph service.
    """
    queue = []
    queue.append(source_tree)
    while queue:
        for node in queue.copy():
            queue.remove(node)
            node_ori = await client.get_origin(node.swhid())
            if node_ori:
                data[node.swhid()]["origin"] = node_ori
                if node.object_type == "directory":
                    for sub_node in node.iter_tree():
                        data[sub_node.swhid()]["origin"] = node_ori  # type: ignore
            else:
                if node.object_type == "directory":
                    children = [sub_node for sub_node in node.iter_tree()]
                    children.remove(node)
                    queue.extend(children)  # type: ignore


def get_directory_data(
    root_path: str,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    directory_data: Dict = {},
) -> Dict[Path, dict]:
    """Get content information for each directory inside source_tree.

    Returns:
     A dictionary with a directory path as key and the relative
     contents information as values.
    """

    def _get_directory_data(
        source_tree: Directory, nodes_data: MerkleNodeInfo, directory_data: Dict
    ):
        directories = list(
            filter(
                lambda n: n.object_type == "directory",
                map(lambda n: n[1], source_tree.items()),
            )
        )
        for node in directories:
            directory_info = directory_content(node, nodes_data)
            rel_path = Path(node.data["path"].decode()).relative_to(Path(root_path))
            directory_data[rel_path] = directory_info
            if has_dirs(node):
                _get_directory_data(node, nodes_data, directory_data)

    _get_directory_data(source_tree, nodes_data, directory_data)
    return directory_data


def directory_content(node: Directory, nodes_data: MerkleNodeInfo) -> Tuple[int, int]:
    """Count known contents inside the given directory.

    Returns:
     A tuple with the total number of contents inside the directory and the number
     of known contents.
    """
    known_cnt = 0
    node_contents = list(
        filter(lambda n: n.object_type == "content", map(lambda n: n[1], node.items()))
    )
    for sub_node in node_contents:
        if nodes_data[sub_node.swhid()]["known"]:
            known_cnt += 1

    return (len(node_contents), known_cnt)


def has_dirs(node: Directory) -> bool:
    """Check if the given directory has other directories inside."""
    for _, sub_node in node.items():
        if isinstance(sub_node, Directory):
            return True
    return False


def get_content_from(
    node_path: bytes, source_tree: Directory, nodes_data: MerkleNodeInfo
) -> Dict[bytes, dict]:
    """Get content information from the given directory node."""
    # root in model.from_disk.Directory should be accessed with b""
    directory = source_tree[node_path if node_path != source_tree.data["path"] else b""]
    node_contents = list(
        filter(
            lambda n: n.object_type == "content", map(lambda n: n[1], directory.items())
        )
    )
    files_data = {}
    for node in node_contents:
        node_info = nodes_data[node.swhid()]
        node_info["swhid"] = str(node.swhid())
        path_name = "path" if "path" in node.data.keys() else "data"
        files_data[node.data[path_name]] = node_info

    return files_data
