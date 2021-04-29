# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import collections
import itertools
import json
import logging
import os
from pathlib import Path
import random
import time
from typing import Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from swh.model.from_disk import Content, Directory, accept_all_directories
from swh.model.identifiers import CONTENT, DIRECTORY, CoreSWHID, ObjectType

from .exceptions import APIError
from .model import Status, Tree
from .scanner import directory_filter, extract_regex_objs

session = requests.Session()
retries_rule = Retry(total=5, backoff_factor=1)
session.mount("http://", HTTPAdapter(max_retries=retries_rule))


def query_swhids(
    swhids: List[Tree], api_url: str, counter: Optional[collections.Counter] = None
) -> Dict[str, Dict[str, bool]]:
    """
    Returns:
        A dictionary with:
        key(str): persistent identifier
        value(dict):
            value['known'] = True if pid is found
            value['known'] = False if pid is not found
    """
    endpoint = api_url + "known/"
    chunk_size = 1000

    if counter:
        counter["queries"] += len(swhids)

    def make_request(swhids):
        swhids = [swhid.swhid for swhid in swhids]
        req = session.post(endpoint, json=swhids)
        if req.status_code != 200:
            error_message = "%s with given values %s" % (req.text, str(swhids))
            raise APIError(error_message)
        if counter:
            counter["api_calls"] += 1
        resp = req.text
        return json.loads(resp)

    def get_chunk(swhids):
        for i in range(0, len(swhids), chunk_size):
            yield swhids[i : i + chunk_size]

    if len(swhids) > chunk_size:
        return dict(
            itertools.chain.from_iterable(
                make_request(swhids_chunk).items() for swhids_chunk in get_chunk(swhids)
            )
        )
    else:
        return make_request(swhids)


def stopngo(source_tree: Tree, api_url: str, counter: collections.Counter):
    nodes = []
    nodes.append(source_tree)

    while len(nodes) > 0:
        parsed_nodes = query_swhids(nodes, api_url, counter)
        for node in nodes.copy():
            nodes.remove(node)
            node.known = parsed_nodes[node.swhid]["known"]
            node.status = Status.queried
            if node.otype == DIRECTORY:
                if not node.known:
                    nodes.extend(list(node.children.values()))
                else:
                    set_children_status(node, [CONTENT, DIRECTORY], True)


def set_father_status(node, known):
    """
    Recursively change father known and visited status of a given node
    """
    parent = node.father

    if parent is None:
        return
    if parent.status != Status.unset:
        return

    parent.known = known
    set_father_status(parent, known)


def set_children_status(
    node: Tree, node_types: Iterable[str], known: bool, status: Status = Status.unset
):
    """
    Recursively change the status of the children of the provided node
    """
    for child_node in node.iterate():
        if child_node.otype in node_types and child_node.status == status:
            child_node.known = known


def file_priority(source_tree: Tree, api_url: str, counter: collections.Counter):
    # get all the files
    all_contents = list(
        filter(lambda node: node.otype == CONTENT, source_tree.iterate_bfs())
    )
    all_contents.reverse()  # we check nodes from the deepest

    # query the backend to get all file contents status
    parsed_contents = query_swhids(all_contents, api_url, counter)
    # set all the file contents status
    for cnt in all_contents:
        cnt.known = parsed_contents[cnt.swhid]["known"]
        cnt.status = Status.queried
        # set all the upstream directories of unknown file contents to unknown
        if not cnt.known:
            set_father_status(cnt, False)

    # get all unset directories and check their status
    # (update children directories accordingly)
    unset_dirs = list(
        filter(
            lambda node: node.otype == DIRECTORY and node.status == Status.unset,
            source_tree.iterate(),
        )
    )

    if source_tree.status == Status.unset:
        unset_dirs.append(source_tree)

    # check unset directories
    for dir_ in unset_dirs:
        if dir_.status == Status.unset:
            # update directory status
            dir_.known = query_swhids([dir_], api_url, counter)[dir_.swhid]["known"]
            dir_.status = Status.queried
            if dir_.known:
                set_children_status(dir_, [DIRECTORY], True)


def directory_priority(source_tree: Tree, api_url: str, counter: collections.Counter):
    # get all directory contents that have at least one file content
    unset_dirs = list(
        filter(
            lambda dir_: dir_.otype == DIRECTORY and dir_.has_contents,
            source_tree.iterate_bfs(),
        )
    )
    unset_dirs.reverse()

    for dir_ in unset_dirs:
        # if the directory is known set all the downstream file contents to known
        if dir_.status == Status.unset:
            dir_.known = query_swhids([dir_], api_url, counter)[dir_.swhid]["known"]
            dir_.status = Status.queried
            if dir_.known:
                set_children_status(dir_, [CONTENT], True)
            else:
                set_father_status(dir_, False)

    # get remaining directories that have no file contents
    unset_dirs_no_cnts = list(
        filter(
            lambda node: node.otype == DIRECTORY and not node.has_contents,
            source_tree.iterate_bfs(),
        )
    )
    parsed_dirs_no_cnts = query_swhids(unset_dirs_no_cnts, api_url, counter)

    # update status of directories that have no file contents
    for dir_ in unset_dirs_no_cnts:
        dir_.known = parsed_dirs_no_cnts[dir_.swhid]["known"]
        dir_.status = Status.queried

    # check unknown file contents
    unset_files = list(
        filter(
            lambda node: node.otype == CONTENT and node.status == Status.unset,
            source_tree.iterate(),
        )
    )
    parsed_unset_files = query_swhids(unset_files, api_url, counter)

    for file_ in unset_files:
        file_.known = parsed_unset_files[file_.swhid]["known"]
        file_.status = Status.queried


def random_(
    source_tree: Tree,
    api_url: str,
    counter: collections.Counter,
    seed: Optional[int] = None,
):

    if seed:
        random.seed(seed)
    # get all directory/file contents
    all_nodes = [node for node in source_tree.iterate()] + [source_tree]
    # shuffle contents
    random.shuffle(all_nodes)

    while len(all_nodes):
        node = all_nodes.pop()

        if node.status != Status.unset:
            continue

        node.known = query_swhids([node], api_url, counter)[node.swhid]["known"]
        node.status = Status.queried
        if node.otype == DIRECTORY and node.known:
            for child_node in node.iterate():
                child_node.known = True
        elif node.otype == CONTENT and not node.known:
            set_father_status(node, False)


def algo_min(source_tree: Tree, api_url: str, counter: collections.Counter):
    """
    The minimal number of queries knowing the known/unknown status of every node
    """

    def change_parent_status(node, status):
        parent = node.father

        if parent is None:
            return

        parent.status = status
        change_parent_status(parent, status)

    def change_children_status(node, status):
        for child_node in node.iterate():
            child_node.status = status

    all_nodes = [node for node in source_tree.iterate_bfs()]

    parsed_nodes = query_swhids(all_nodes, api_url)
    for node in all_nodes:
        node.known = parsed_nodes[node.swhid]["known"]

    unknown_cnts = list(
        filter(lambda node: node.known is False, source_tree.iterate_bfs())
    )
    unknown_cnts.reverse()

    for node in unknown_cnts:
        change_parent_status(node, Status.unset)

    known_dirs = list(
        filter(
            lambda node: node.otype == DIRECTORY and node.known is True,
            source_tree.iterate(),
        )
    )

    if source_tree.known:
        known_dirs += [source_tree]

    for dir_ in known_dirs:
        change_children_status(dir_, Status.unset)

    unset_cnts = list(
        filter(lambda node: node.status == Status.unset, source_tree.iterate_bfs())
    )

    counter["api_calls"] = -1
    counter["queries"] = len(source_tree) - len(unset_cnts)


def get_swhids(paths: Iterable[Path], exclude_patterns):
    def swhid_of(path):
        if path.is_dir():
            if exclude_patterns:

                def dir_filter(dirpath, *args):
                    return directory_filter(dirpath, exclude_patterns)

            else:
                dir_filter = accept_all_directories

            obj = Directory.from_disk(
                path=bytes(path), dir_filter=dir_filter
            ).get_data()

            return str(CoreSWHID(object_type=ObjectType.DIRECTORY, object_id=obj["id"]))
        else:
            obj = Content.from_file(path=bytes(path)).get_data()
            return str(
                CoreSWHID(object_type=ObjectType.CONTENT, object_id=obj["sha1_git"])
            )

    for path in paths:
        yield str(path), swhid_of(path)


def load_source(root, sre_patterns):
    """
    Load the source code inside the Tree data structure
    """

    def _scan(root_path, source_tree, sre_patterns):
        files = []
        dirs = []
        for elem in os.listdir(root_path):
            cnt = Path(root_path).joinpath(elem)
            if not os.path.islink(cnt):
                if os.path.isfile(cnt):
                    files.append(cnt)
                elif os.path.isdir(cnt):
                    dirs.append(cnt)

        if files:
            parsed_file_swhids = dict(get_swhids(files, sre_patterns))

            for path, swhid_ in parsed_file_swhids.items():
                source_tree.add_node(Path(path), swhid_)

        if dirs:
            parsed_dirs_swhids = dict(get_swhids(dirs, sre_patterns))

            for path, swhid_ in parsed_dirs_swhids.items():
                if not directory_filter(path, sre_patterns):
                    continue
                source_tree.add_node(Path(path), swhid_)
                _scan(path, source_tree, sre_patterns)

    source_tree = Tree(root)
    root_swhid = dict(get_swhids([root], sre_patterns))
    source_tree.swhid = root_swhid[str(root)]
    _scan(root, source_tree, sre_patterns)
    return source_tree


def run(
    root: str,
    api_url: str,
    backend_name: str,
    exclude_patterns: Iterable[str],
    algo: str,
    origin: str,
    commit: str,
    seed: Optional[int] = None,
):
    sre_patterns = set()
    if exclude_patterns:
        sre_patterns = {
            reg_obj for reg_obj in extract_regex_objs(Path(root), exclude_patterns)
        }

    # temporary directory prefix
    repo_id = Path(root).parts[-1].split("_")[0]
    counter: collections.Counter = collections.Counter()
    counter["api_calls"] = 0
    counter["queries"] = 0
    source_tree = load_source(Path(root), sre_patterns)
    logging.info(
        f'started processing repo "{repo_id}" with algorithm '
        f'"{algo}" and knowledge base "{backend_name}"'
    )
    tstart = time.time()

    if algo == "random":
        if seed:
            random_(source_tree, api_url, counter, seed)
        else:
            random_(source_tree, api_url, counter)
    elif algo == "algo_min":
        algo_min(source_tree, api_url, counter)
    elif algo == "stopngo":
        stopngo(source_tree, api_url, counter)
    elif algo == "file_priority":
        file_priority(source_tree, api_url, counter)
    elif algo == "directory_priority":
        directory_priority(source_tree, api_url, counter)
    else:
        raise Exception(f'Algorithm "{algo}" not found')

    tend = time.time()
    result = (
        repo_id,
        origin,
        commit,
        backend_name,
        len(source_tree),
        algo,
        counter["api_calls"],
        counter["queries"],
        tend - tstart,
    )

    logging.info(
        f'finished processing repo "{repo_id}" with algorithm '
        f'"{algo}" and knowledge base "{backend_name}"'
    )

    print(*result, sep=",")
