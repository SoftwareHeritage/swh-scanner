# Copyright (C) 2021-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from abc import ABC, abstractmethod
from enum import Enum
import json
import os
import sys
from typing import Any, Dict, Set

import ndjson

from swh.model.from_disk import Directory
from swh.model.swhids import CoreSWHID, ExtendedSWHID, QualifiedSWHID
from swh.web.client.client import WebAPIClient

from .dashboard.dashboard import run_app
from .data import MerkleNodeInfo

DEFAULT_OUTPUT = "text"
OUTPUT_MAP = {}


class Color(Enum):
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    END = "\033[0m"


def colorize(text: str, color: Color):
    return color.value + text + Color.END.value


def _register(name):
    """decorator to register an output class under mode `name`"""

    def dec(cls):
        OUTPUT_MAP[name] = cls
        return cls

    return dec


def get_output_class(mode=DEFAULT_OUTPUT):
    """return the output class that correspond to `mode`"""
    cls = OUTPUT_MAP.get(mode)
    if cls is None:
        raise Exception(f"mode {mode} is not an output format")
    return cls


class BaseOutput(ABC):
    """base class for object able to display scan result"""

    def __init__(
        self,
        root_path: str,
        nodes_data: MerkleNodeInfo,
        source_tree: Directory,
        config: Dict[str, Any],
        web_client: WebAPIClient,
    ):
        self.root_path = root_path
        self.nodes_data = nodes_data
        self.source_tree = source_tree
        self.config = config
        self.web_client = web_client

    def get_path_name(self, node):
        return "path" if "path" in node.data.keys() else "data"

    @abstractmethod
    def show(self):
        pass


@_register("summary")
class SummaryOutput(BaseOutput):
    """display a summary of the scan results"""

    def compute_summary(self):
        directories_with_known_files = set()

        total_files = 0
        total_directories = 0
        known_files = 0
        full_known_directories = set()
        partially_known_directories = set()

        contents = set()
        directories = set()

        for node in self.source_tree.iter_tree():
            if node.object_type == "content":
                contents.add(node)
            elif node.object_type == "directory":
                directories.add(node)
            else:
                assert False, "unreachable"

        total_files = len(contents)
        for c in contents:
            if self.nodes_data[c.swhid()]["known"]:
                known_files += 1
                path = c.data[self.get_path_name(c)]
                dir_name = os.path.dirname(path)
                directories_with_known_files.add(dir_name)

        for d in directories:
            if self.nodes_data[d.swhid()]["known"]:
                path_name = self.get_path_name(d)
                path = d.data[path_name]
                full_known_directories.add(path)

        self.compute_partially_known_recursive(
            directories_with_known_files,
            partially_known_directories,
            full_known_directories,
            self.source_tree,
        )

        total_directories = len(directories)
        kp = known_files * 100 // total_files
        fkp = len(full_known_directories) * 100 // total_directories
        pkp = len(partially_known_directories) * 100 // total_directories

        return {
            "total_files": total_files,
            "known_files": known_files,
            "known_files_percent": kp,
            "total_directories": total_directories,
            "full_known_directories": full_known_directories,
            "full_known_directories_percent": fkp,
            "partially_known_directories": partially_known_directories,
            "partially_known_directories_percent": pkp,
        }

    def compute_partially_known_recursive(
        self,
        directories_with_known_files: Set[bytes],
        partially_known_directories: Set[bytes],
        full_known_directories: Set[bytes],
        d: Directory,
    ):
        """Recursively compute partially known directories."""

        path_name = self.get_path_name(d)
        path = d.data[path_name]
        partially_known = False

        if path in full_known_directories:
            return False

        if path not in full_known_directories and path in directories_with_known_files:
            partially_known_directories.add(path)
            partially_known = True

        for entry in d.values():
            if entry.object_type == "directory":
                partially_known_child = self.compute_partially_known_recursive(
                    directories_with_known_files,
                    partially_known_directories,
                    full_known_directories,
                    entry,
                )
                if partially_known_child:
                    partially_known_directories.add(path)
                partially_known = partially_known or partially_known_child
        return partially_known

    def show(self):
        summary = self.compute_summary()
        kp = summary["known_files_percent"]
        fkp = summary["full_known_directories_percent"]
        pkp = summary["partially_known_directories_percent"]
        print(f"Files:             {summary['total_files']:10d}")
        print(f"            known: {summary['known_files']:10d} ({kp:3d}%)")
        print(f"directories:       {summary['total_directories']:10d}")
        print(
            f"      fully-known: {len(summary['full_known_directories']):10d} ({fkp:3d}%)"
        )
        print(
            f"  partially-known: {len(summary['partially_known_directories']):10d} ({pkp:3d}%)"
        )


@_register("text")
class TextOutput(BaseOutput):
    """display an exhaustive result of the scan in text form

    note: as soon as the scan target something larger than a toy project, the
    usability of this mode is poor."""

    def show(self) -> None:
        isatty = sys.stdout.isatty()
        for node in self.source_tree.iter_tree():
            self.print_node(node, isatty, self._compute_level(node))

    def _compute_level(self, node: Any):
        node_path = str(node.data[self.get_path_name(node)]).split("/")
        source_path = str(self.source_tree.data["path"]).split("/")
        return len(node_path) - len(source_path)

    def print_node(self, node: Any, isatty: bool, level: int) -> None:
        rel_path = os.path.basename(node.data[self.get_path_name(node)])
        rel_path = rel_path.decode()
        begin = "│   " * level
        end = "/" if node.object_type == "directory" else ""

        if isatty:
            if not self.nodes_data[node.swhid()]["known"]:
                rel_path = colorize(rel_path, Color.RED)
            elif node.object_type == "directory":
                rel_path = colorize(rel_path, Color.BLUE)
            elif node.object_type == "content":
                rel_path = colorize(rel_path, Color.GREEN)

        print(f"{begin}{rel_path}{end}")


class SWHIDEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, (CoreSWHID, ExtendedSWHID, QualifiedSWHID)):
            return str(value)
        else:
            return super().default(value)


@_register("json")
class JsonOutput(BaseOutput):
    """display the scan result in json"""

    def data_as_json(self):
        json = {}
        for node in self.source_tree.iter_tree():
            rel_path = os.path.relpath(
                node.data[self.get_path_name(node)].decode(),
                self.source_tree.data["path"].decode(),
            )
            json[rel_path] = {"swhid": str(node.swhid())}
            for k, v in self.nodes_data[node.swhid()].items():
                json[rel_path][k] = v
        return json

    def show(self):
        print(
            json.dumps(
                self.data_as_json(),
                indent=4,
                sort_keys=True,
                cls=SWHIDEncoder,
            )
        )


@_register("ndjson")
class NDJsonTextOutput(JsonOutput):
    """display the scan result in newline-delimited json"""

    def show(self):
        print(ndjson.dumps({k: v} for k, v in self.data_as_json().items()), flush=True)


@_register("interactive")
class InteractiveDashboardOutput(SummaryOutput):
    """Dashboard to explore the scan results"""

    def show(self) -> None:
        run_app(
            self.config,
            self.root_path,
            self.source_tree,
            self.nodes_data,
            self.compute_summary(),
            web_client=self.web_client,
        )
