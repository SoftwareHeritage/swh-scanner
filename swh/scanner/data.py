# Copyright (C) 2021-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import concurrent.futures
import json
import logging
from os import path
from pathlib import Path
import subprocess
from typing import Callable, Dict, Iterator, List, Optional, Tuple, TypeVar, Union, cast
from xml.etree import ElementTree

import requests

from swh.core.utils import grouper
from swh.model.exceptions import ValidationError
from swh.model.from_disk import Content, Directory, FromDiskType
from swh.model.swhids import CoreSWHID, ObjectType, QualifiedSWHID
from swh.web.client.client import WebAPIClient

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
) -> None:
    """Populate the MerkleNodeInfo with the SWHIDs of the given source tree

    The dictionary value are pre-filed with dictionary holding the
    information about the nodes.

    The "known" key is always stored as it is always fetched. The "provenance"
    key is stored if the `provenance` parameter is :const:`True`.
    """
    nodes_info: Dict[str, Optional[str]] = {"known": None}
    if provenance:
        nodes_info["provenance"] = None
    for node in source_tree.iter_tree():
        data[node.swhid()] = nodes_info.copy()
    return None


class NoProvenanceAPIAccess(RuntimeError):
    """Raise when the user have not Access to the Provenance API"""


def _get_provenance_info(client, swhid: CoreSWHID) -> Optional[QualifiedSWHID]:
    """find a revision or release and origin containing this object

    XXX This function is now only used by the "on demand" query that can be
    requested from the dashboard. Remove it whenever relevant XXX

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

        The QualifiedSWHID will have the following qualifiers set:
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
    return _call_whereis(client, swhid)


def _call_whereis(client, swhid: CoreSWHID) -> Optional[QualifiedSWHID]:
    """manually call provenance's `whereis` endpoind

    The WebAPIClient will eventually support this natively. At that point this
    function should be remove in favor on calling the associated method on
    WebAPIClient.
    """
    query = f"provenance/whereis/{swhid}/"
    try:
        with client._call(query) as r:
            raw_json = r.text
            if raw_json:
                result = json.loads(raw_json)
            else:
                result = None
    except requests.HTTPError as exc:
        r = exc.response
        if r.status_code == requests.codes.UNAUTHORIZED:
            raise NoProvenanceAPIAccess(r.text)
    if result is None:
        return None
    return QualifiedSWHID.from_string(result)


# We tried 1000, but the API was suffering (504 and 503 return)/
# Bump again when this get more reliable
MAX_WHEREARE_BATCH = 100


def _call_whereare(client, swhids: List[CoreSWHID]) -> List[Optional[QualifiedSWHID]]:
    """manually call provenance's `whereare` endpoind

    The WebAPIClient will eventually support this natively. At that point this
    function should be remove in favor on calling the associated method on
    WebAPIClient.
    """
    query = "provenance/whereare/"
    args = [str(s) for s in swhids]
    try:
        with client._call(query, http_method="post", json=args) as r:
            result = r.json()
    except requests.HTTPError as exc:
        r = exc.response
        if r.status_code == requests.codes.UNAUTHORIZED:
            raise NoProvenanceAPIAccess(r.text)
        raise

    to_q = QualifiedSWHID.from_string
    return [to_q(q) if q is not None else q for q in result]


_IN_MEM_NODE = Union[Directory, Content]

MAX_CONCURRENT_PROVENANCE_QUERIES = 5

Item = TypeVar("Item")


def _get_many_provenance_info(
    client, swhids: List[CoreSWHID]
) -> Iterator[Tuple[CoreSWHID, Optional[QualifiedSWHID]]]:
    """yield provenance data for multiple swhid

    For all SWHID we can find provenance data for, we will yield a (CoreSWHID,
    QualifiedSWHID) pair, (see provenance's API "whereis" documentation for the
    details on the QualifiedSWHID). SWHID for which we cannot find provenance
    yield a None value.

    note: We could drop the SWHID part of the pair and only return
    QualifiedSWHID, if they were some easy method for QualifiedSWHID →
    CoreSWHID conversion."""
    # XXX note that this concurrency can be dealt with by
    # WebAPIClient._call_groups one the WebAPIClient grown function to fetch
    # provenance.
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_CONCURRENT_PROVENANCE_QUERIES
    ) as executor:
        pending = {}
        for chunk in grouper(swhids, MAX_WHEREARE_BATCH):
            chunk = list(chunk)
            f = executor.submit(_call_whereare, client, chunk)
            pending[f] = chunk
        for future in concurrent.futures.as_completed(list(pending.keys())):
            provenances = future.result()
            sources = pending[future]
            yield from zip(sources, provenances)


def _no_update_progress(*args, **kwargs):
    pass


def add_provenance(
    source_tree: Directory,
    data: MerkleNodeInfo,
    client: WebAPIClient,
    update_progress: Optional[Callable[[int, int], None]] = _no_update_progress,
):
    """Store provenance information about software artifacts retrieved from the Software
    Heritage graph service.
    """
    # XXX Note that the current provenance handling highlight some limitation with
    # the underlying way we handle data in the scanner.
    #
    # Right now, we store unique data for each unique SWHID. However the same
    # SWHID appearing in different context might have different data relevant
    # to it. For example, the GPL Licence file might be found in multiple
    # places, and the best provenance for each of this location will likely
    # varies.
    #
    # So we might want to overhaul the way we connect data to be more path
    # centric (for some of it at least).  It would also help us to put the
    # "path" qualifier, of QualifiedSWHID to use.

    if update_progress is None:
        update_progress = _no_update_progress
    all_queries: set[_IN_MEM_NODE] = set()
    done_queries: set[_IN_MEM_NODE] = set()
    seen: set[_IN_MEM_NODE] = set()
    current_boundary: dict[CoreSWHID, _IN_MEM_NODE] = {}
    next_boundary: dict[CoreSWHID, _IN_MEM_NODE] = {}

    # search for the initial boundary of "known" set
    initial_walk_queue: set[_IN_MEM_NODE] = {source_tree}
    while initial_walk_queue:
        node = initial_walk_queue.pop()
        if node in seen:
            continue
        seen.add(node)
        known: Optional[bool] = data[node.swhid()]["known"]
        if known is None or known:
            # We found a "root" for a known set, we should query it.
            current_boundary[node.swhid()] = node
        elif node.object_type == FromDiskType.DIRECTORY:
            # that node is unknown, no need to query it, but there might be
            # known set of descendant that need provenance queries.
            initial_walk_queue.update(node.values())

    all_queries.update(current_boundary.values())
    update_progress(len(done_queries), len(all_queries))
    while current_boundary:
        boundary = list(current_boundary.keys())
        for info in _get_many_provenance_info(client, boundary):
            swhid, qualified_swhid = info
            node = current_boundary.pop(swhid)
            done_queries.add(node)
            if qualified_swhid is not None:
                data[node.swhid()]["provenance"] = qualified_swhid
                if node.object_type == FromDiskType.DIRECTORY:
                    node = cast(Directory, node)
                    for sub_node in node.iter_tree():
                        if sub_node in seen:
                            continue
                        seen.add(sub_node)
                        data[sub_node.swhid()]["provenance"] = qualified_swhid
            elif node.object_type == FromDiskType.DIRECTORY:
                for sub_node in node.values():
                    if sub_node in seen:
                        continue
                    seen.add(sub_node)
                    all_queries.add(sub_node)
                    next_boundary[sub_node.swhid()] = sub_node
            update_progress(len(done_queries), len(all_queries))
        current_boundary = next_boundary
        next_boundary = {}


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


def vcs_detected(folder_path: Path) -> bool:
    try:
        return folder_path.is_dir()
    except Exception as e:
        logger.debug("Got an exception while looking for %s: %s", folder_path, e)
        return False


def get_vcs_ignore_patterns(cwd: Optional[Path] = None) -> List[bytes]:
    """Return a list of all patterns to ignore according to the VCS used for
    the project being scanned, if any."""
    ignore_patterns = []
    for vcs, (folder_name, method) in VCS_IGNORE_PATTERNS_METHODS.items():
        if cwd is not None:
            folder_path = cwd / folder_name
        else:
            folder_path = Path(folder_name)
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
