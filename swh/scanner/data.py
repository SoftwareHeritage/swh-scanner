# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from collections import deque
import logging
from os import path
from pathlib import Path
import subprocess
from typing import Callable, Dict, List, Optional, Tuple, Union, cast
from xml.etree import ElementTree

import requests

from swh.model.exceptions import ValidationError
from swh.model.from_disk import Content, Directory
from swh.model.swhids import CoreSWHID, ObjectType, QualifiedSWHID
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


def init_merkle_node_info(
    source_tree: Directory, data: MerkleNodeInfo, provenance: bool
):
    """Populate the MerkleNodeInfo with the SWHIDs of the given source tree

    The dictionary value are pre-filed with dictionary holding the
    information about the nodes.

    The "known" key is always stored as it is always fetched. The "provenance"
    key is stored if the `provenance` parameter is :const:`True`.
    """
    nodes_info: Dict[str, Optional[str]] = {"known": None}
    if provenance:
        nodes_info["origin"] = None
    for node in source_tree.iter_tree():
        data[node.swhid()] = nodes_info.copy()


def _get_leaf(
    client,
    node: str,
    return_types: str,
    direction="forward",
    edges="*",
    resolve_origins=True,
) -> Optional[str]:
    """internal function used by _get_provenance_info"""
    query = (
        f"graph/leaves/{node}/?direction={direction}"
        f"&edges={edges}"
        f"&return_types={return_types}"
        f"&max_matching_nodes=1"
    )
    if resolve_origins:
        query += "&resolve_origins=true"
    try:
        with client._call(query, http_method="get") as r:
            value = r.text.rstrip("\n")
    except requests.HTTPError as fail:
        # the graph raise 404 for unknown node so we have catch 404 for now
        # https://gitlab.softwareheritage.org/swh/devel/swh-graph/-/issues/4763
        if fail.response.status_code not in (400, 404):
            raise
        return None
    if not value:  # empty result
        return None
    return value


def _get_provenance_info(client, swhid: CoreSWHID) -> Optional[QualifiedSWHID]:
    """find a revision or release and origin containing this content or directory

    Revision and Release might not be found, we prioritize finding a
    Release over finding a Revision when possible.

    note: The quality of the result is not guaranteed whatsoever. Since the
    definition of "best" likely vary from one usage to the next, this API
    will evolve in the futur when this notion get better defined.

    For example, if we are looking for provenance information to detect
    prior art. We search for the first appearance of a content. So the
    "best answer" is the oldest content, something a bit tricky to
    determine as we can't fully trust the date of revision. On the other
    hand, if we try to known which library are used and at which version,
    to detect CVE or outdated dependencies, the best answer is the most
    recent release/revision in the authoritative origin relevant to a
    content.  Finding the authoritative origin is a challenge in itclient.

    This function exist until we have some proper provenance entry point on the
    archive level. And will, hopefully, soon be removed.

    Args
        swhid: the SWHID of the Content or Directory to find info for

    Returns:
        None or QualifiedSWHID for the current Content or Directory.

        The QualifiedSWHID will have the following attributes set:
        - swhid: the swhid of the provided content or directory
        - anchor: swhid of a Release or Revision containing it
        - origin: the origin containing this Release or Revision

        If no anchor could be found, this function return None.

    Raises:
        requests.HTTPError: if HTTP request fails
    """
    if swhid.object_type not in (ObjectType.DIRECTORY, ObjectType.CONTENT):
        msg = "swhid should be %r or %r as parameter, not: %r"
        msg %= (ObjectType.DIRECTORY, ObjectType.CONTENT, swhid.object_type)
        raise ValueError(msg)

    content_or_dir = str(swhid)

    # XXX: If we have a content, the provenance API could search for a rev
    # or rel more efficiently. However it does not work for Directory and
    # only cover some of the node, so we need the call the graph anyway.

    # XXX: The graph can also lag behind the archive so it is possible that
    # we identify a known content without being able to find an origin.

    # Try to find a release first
    anchor = _get_leaf(
        client,
        node=content_or_dir,
        direction="backward",
        edges="dir:dir,cnt:dir,dir:rev,rev:rel,dir:rel,cnt:rel",
        return_types="rel",
    )
    if anchor is None:
        # We did not find a release,
        # directly search for a revision instead.
        anchor = _get_leaf(
            client,
            node=content_or_dir,
            direction="backward",
            edges="dir:dir,cnt:dir,dir:rev",
            return_types="rev",
        )
    if anchor is None:
        # could not find anything, give up
        return None

    # now search the associated origin
    origin = _get_leaf(
        client,
        node=anchor,
        direction="backward",
        edges="*:snp,*:ori",
        return_types="ori",
    )
    return QualifiedSWHID(
        object_type=swhid.object_type,
        object_id=swhid.object_id,
        anchor=CoreSWHID.from_string(anchor),
        origin=origin,
    )


_IN_MEM_NODE = Union[Directory, Content]


def add_origin(
    source_tree: Directory,
    data: MerkleNodeInfo,
    client: WebAPIClient,
):
    """Store origin information about software artifacts retrieved from the Software
    Heritage graph service.
    """
    seen: set[_IN_MEM_NODE] = set()
    queue: deque[_IN_MEM_NODE] = deque([source_tree])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        qualified_swhid = None
        node_data = data.get(node.swhid())
        if node_data is not None:
            known = node_data.get("known")
            if known or known is None:
                qualified_swhid = _get_provenance_info(client, node.swhid())
        if qualified_swhid is None and node.object_type == "directory":
            # add children to the queue.
            queue.extend(node.values())
        elif qualified_swhid is not None:
            data[node.swhid()]["origin"] = qualified_swhid
            # propagate the information to the leafs
            if node.object_type == "directory":
                for sub_node in node.iter_tree():
                    # XXX swh.model probably need to improve so that we don't
                    # have to deal with this here.
                    sub_node = cast(_IN_MEM_NODE, sub_node)
                    if sub_node in seen:
                        continue
                    seen.add(sub_node)
                    data[sub_node.swhid()]["origin"] = qualified_swhid


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


def get_ignore_patterns_templates() -> Dict[str, Path]:
    """Return a dict where keys are ignore templates names and value a path to the
    ignore definition file."""
    here = Path(path.abspath(path.dirname(__file__)))
    gitignore_path = here / "resources" / "gitignore"
    assert gitignore_path.exists()
    skip = [".git", ".github"]
    templates = {
        item.stem: item
        for item in gitignore_path.rglob("*.gitignore")
        if set(item.parts).isdisjoint(skip)
    }
    return templates


def parse_ignore_patterns_template(source: Path) -> List[bytes]:
    """Given a file path to a gitignore template, return an ignore patterns list"""
    patterns: List[bytes] = []
    assert source.exists()
    assert source.is_file()
    patterns_str = source.read_text()
    patterns_list = patterns_str.splitlines()
    for pattern in patterns_list:
        pattern = pattern.strip()
        if pattern and pattern.startswith("#") is False:
            patterns.append(pattern.encode())
    return patterns
