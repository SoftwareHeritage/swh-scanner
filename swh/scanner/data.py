# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import logging
from pathlib import Path
import subprocess
from typing import Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree

from swh.model.exceptions import ValidationError
from swh.model.from_disk import Directory
from swh.model.swhids import CoreSWHID
from swh.web.client.client import WebAPIClient

SUPPORTED_INFO = {"known", "origin"}

logger = logging.getLogger(__name__)


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


def add_origin(
    source_tree: Directory,
    data: MerkleNodeInfo,
    client: WebAPIClient,
):
    """Store origin information about software artifacts retrieved from the Software
    Heritage graph service.
    """
    queue = []
    queue.append(source_tree)
    while queue:
        for node in queue.copy():
            queue.remove(node)
            node_ori = client.get_origin(node.swhid())
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


def _call_vcs(command, cwd: Optional[Path], **cmd_kwargs):
    """Separate function for ease of overriding in tests"""
    return subprocess.run(
        command, check=True, capture_output=True, cwd=cwd, **cmd_kwargs
    )


def get_git_ignore_patterns(cwd: Optional[Path]):
    try:
        res = _call_vcs(["git", "status", "--ignored", "--no-renames", "-z"], cwd)
    except subprocess.CalledProcessError as e:
        logger.debug("Failed to call out to git [%d]: %s", e.stderr)
        return False, []

    patterns = []
    stdout = res.stdout
    if not stdout:
        # No status output, so no ignored files
        return True, []
    # The `-z` CLI flag gives us a stable, null byte-separated output
    lines = stdout.split(b"\0")
    for line in lines:
        if not line:
            continue
        status, name = line.split(b" ", 1)
        if status != b"!!":
            # skip non-ignored files
            continue
        patterns.append(name.rstrip(b"/"))

    return True, patterns


def get_hg_ignore_patterns(cwd: Optional[Path]):
    try:
        res = _call_vcs(
            ["hg", "status", "--ignored", "--no-status", "-0"],
            cwd,
            env={"HGPLAIN": "1"},
        )
    except subprocess.CalledProcessError as e:
        logger.debug("Failed to call out to hg [%d]: %s", e.returncode, e.stderr)
        return False, []

    stdout = res.stdout
    if not stdout:
        # No status output, so no ignored files
        return True, []

    # The `-0` CLI flag gives us a stable, null byte-separated output
    patterns = [line for line in stdout.split(b"\0") if line]

    return True, patterns


def get_svn_ignore_patterns(cwd: Optional[Path]):
    try:
        res = _call_vcs(["svn", "status", "--no-ignore", "--xml"], cwd)
    except subprocess.CalledProcessError as e:
        logger.debug("Failed to call out to svn [%d]: %s", e.returncode, e.stderr)
        return False, []

    patterns = []
    stdout = res.stdout
    if not stdout:
        # No status output, so no ignored files
        return True, []
    # We've asked for XML output since it's easily parsable and stable, unlike
    # the normal Subversion output.
    root = ElementTree.fromstring(stdout)
    status = root.find("target")
    assert status is not None
    for entry in status:
        path = entry.attrib["path"]
        wc_status = entry.find("wc-status")
        assert wc_status is not None
        entry_status = wc_status.attrib["item"]
        if entry_status == "ignored":
            # SVN uses UTF8 for all paths
            patterns.append(path.encode())

    return True, patterns


# Associates a Version Control System to its on-disk folder and a method of
# getting its ignore patterns.
VCS_IGNORE_PATTERNS_METHODS: Dict[
    str, Tuple[str, Callable[[Optional[Path]], Tuple[bool, List[bytes]]]]
] = {
    "git": (".git", get_git_ignore_patterns),
    "hg": (".hg", get_hg_ignore_patterns),
    "svn": (".svn", get_svn_ignore_patterns),
}


def vcs_detected(folder_path: str) -> bool:
    try:
        return Path(folder_path).is_dir()
    except Exception as e:
        logger.debug("Got an exception while looking for %s: %s", folder_path, e)
        return False


def get_vcs_ignore_patterns(cwd: Optional[Path] = None) -> List[bytes]:
    """Return a list of all patterns to ignore according to the VCS used for
    the project being scanned, if any."""
    ignore_patterns = []

    for vcs, (folder_path, method) in VCS_IGNORE_PATTERNS_METHODS.items():
        if vcs_detected(folder_path):
            logger.debug("Trying to get ignore patterns from '%s'", vcs)
            success, patterns = method(cwd)
            if success:
                logger.debug("Successfully obtained ignore patterns from '%s'", vcs)
                ignore_patterns.extend(patterns)
                break
    else:
        logger.debug("No VCS found in the current working directory")

    return ignore_patterns
