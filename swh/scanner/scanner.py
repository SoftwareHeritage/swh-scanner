# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import requests
import os
import json
import itertools
from pathlib import PosixPath

from swh.model.cli import pid_of_file, pid_of_dir
from swh.model.identifiers import (
        parse_persistent_identifier,
        DIRECTORY, CONTENT
)


def pids_discovery(pids, host, port):
    """
    Args:
        pids list(str): A list of persistent identifier
    Returns:
        A dictionary with:
        key(str): persistent identifier
        value(dict):
            value['known'] = True if pid is found
            value['known'] = False if pid is not found
    """
    endpoint = 'http://%s:%s/api/1/known/' % (host, port)
    req = requests.post(endpoint, json=pids)
    resp = req.text
    return json.loads(resp)


def get_sub_paths(path):
    """Find the persistent identifier of the paths and files under
    a given path.

    Args:
        path(PosixPath): the entry root

    Yields:
        tuple(path, pid): pairs of path and the relative persistent
        identifier
    """
    def pid_of(path):
        if path.is_dir():
            return pid_of_dir(bytes(path))
        elif path.is_file():
            return pid_of_file(bytes(path))

    dirpath, dnames, fnames = next(os.walk(path))
    for node in itertools.chain(dnames, fnames):
        path = PosixPath(dirpath).joinpath(node)
        yield (path, pid_of(path))


def parse_path(path, host, port):
    """Check if the sub paths of the given path is present in the
    archive or not.
    Args:
        path(PosixPath): The source path
        host(str): ip for the api request
        port(str): port for the api request
    Yields:
        a tuple with the path found, the persistent identifier
        relative to the path and a boolean: False if not found,
        True if found.
    """
    pid_map = dict(get_sub_paths(path))
    parsed_pids = pids_discovery(list(pid_map.values()), host, port)

    for sub_path, pid in pid_map.items():
        yield (sub_path, pid, parsed_pids[pid]['known'])


def run(root, host, port):
    """Scan the given root
    Args:
        path: the path to scan
        host(str): ip for the api request
        port(str): port for the api request
    Returns:
        A set containing pairs of the path discovered and the
        relative persistent identifier
    """
    def _scan(root, host, port, accum):
        assert root not in accum

        next_paths = []
        for path, pid, found in parse_path(root, host, port):
            obj_type = parse_persistent_identifier(pid).object_type

            if obj_type == CONTENT and found:
                accum.add((str(path), pid))
            elif obj_type == DIRECTORY:
                if found:
                    accum.add((str(path), pid))
                else:
                    next_paths.append(path)

        for new_path in next_paths:
            accum = _scan(new_path, host, port, accum)

        return accum

    return _scan(root, host, port, set())
