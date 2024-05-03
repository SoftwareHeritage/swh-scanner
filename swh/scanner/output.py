# Copyright (C) 2021-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from abc import ABC, abstractmethod
from enum import Enum
import json
import os
import sys
from typing import Any, Dict

import ndjson

from swh.model.from_disk import Directory
from swh.model.swhids import CoreSWHID, ExtendedSWHID, QualifiedSWHID

from .dashboard.dashboard import run_app
from .data import MerkleNodeInfo, get_directory_data
from .plot import generate_sunburst, offline_plot

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
    ):
        self.root_path = root_path
        self.nodes_data = nodes_data
        self.source_tree = source_tree
        self.config = config

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
        full_known_directories = 0
        partially_known_directories = 0

        contents = []
        directories = []

        for node in self.source_tree.iter_tree():
            if node.object_type == "content":
                contents.append(node)
            elif node.object_type == "directory":
                directories.append(node)
            else:
                assert False, "unreachable"

        total_files = len(contents)
        for c in contents:
            if self.nodes_data[c.swhid()]["known"]:
                known_files += 1
                path = c.data[self.get_path_name(c)]
                dir_name = os.path.dirname(path)
                directories_with_known_files.add(dir_name)

        total_directories = len(directories)
        for d in directories:
            if self.nodes_data[d.swhid()]["known"]:
                full_known_directories += 1
            else:
                path = d.data[self.get_path_name(d)]
                if path in directories_with_known_files:
                    partially_known_directories += 1

        kp = known_files * 100 // total_files
        fkp = full_known_directories * 100 // total_directories
        pkp = partially_known_directories * 100 // total_directories

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

    def show(self):
        summary = self.compute_summary()
        kp = summary["known_files_percent"]
        fkp = summary["full_known_directories_percent"]
        pkp = summary["partially_known_directories_percent"]
        print(f"Files:             {summary['total_files']:10d}")
        print(f"            known: {summary['known_files']:10d} ({kp:3d}%)")
        print(f"directories:       {summary['total_directories']:10d}")
        print(f"      fully-known: {summary['full_known_directories']:10d} ({fkp:3d}%)")
        print(
            f"  partially-known: {summary['partially_known_directories']:10d} ({pkp:3d}%)"
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


@_register("sunburst")
class SunburstOutput(BaseOutput):
    """display the scan result as a sunburst plot

    note: as soon as the scan target something larger than a toy project, the
    usability of this mode is poor."""

    def _make_sunburst(self):
        directory_data = get_directory_data(
            self.root_path, self.source_tree, self.nodes_data
        )
        return generate_sunburst(directory_data, self.root_path)

    def show(self):
        sunburst_figure = self._make_sunburst()
        offline_plot(sunburst_figure)


@_register("interactive")
class InteractiveDashboardOutput(SummaryOutput):
    """Dashboard to explore the scan results"""

    def show(self):
        run_app(
            self.config,
            self.root_path,
            self.source_tree,
            self.nodes_data,
            self.compute_summary(),
        )
