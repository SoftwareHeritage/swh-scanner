# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from enum import Enum
import json
import os
import sys
from typing import Any

import ndjson

from swh.model.from_disk import Directory

from .dashboard.dashboard import run_app
from .data import MerkleNodeInfo, get_directory_data
from .plot import generate_sunburst, offline_plot

DEFAULT_OUTPUT = "text"


class Color(Enum):
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    END = "\033[0m"


def colorize(text: str, color: Color):
    return color.value + text + Color.END.value


class Output:
    def __init__(
        self, root_path: str, nodes_data: MerkleNodeInfo, source_tree: Directory
    ):
        self.root_path = root_path
        self.nodes_data = nodes_data
        self.source_tree = source_tree

    def show(self, mode=DEFAULT_OUTPUT):
        if mode == "summary":
            self.summary()
        elif mode == "text":
            isatty = sys.stdout.isatty()
            self.print_text(isatty)
        elif mode == "sunburst":
            directory_data = get_directory_data(
                self.root_path, self.source_tree, self.nodes_data
            )
            sunburst_figure = generate_sunburst(directory_data, self.root_path)
            offline_plot(sunburst_figure)
        elif mode == "interactive":
            directory_data = get_directory_data(
                self.root_path, self.source_tree, self.nodes_data
            )
            sunburst_figure = generate_sunburst(directory_data, self.root_path)
            run_app(sunburst_figure, self.source_tree, self.nodes_data)
        elif mode == "json":
            self.print_json()
        elif mode == "ndjson":
            self.print_ndjson()
        else:
            raise Exception(f"mode {mode} is not an output format")

    def get_path_name(self, node):
        return "path" if "path" in node.data.keys() else "data"

    def print_text(self, isatty: bool) -> None:
        def compute_level(node):
            node_path = str(node.data[self.get_path_name(node)]).split("/")
            source_path = str(self.source_tree.data["path"]).split("/")
            return len(node_path) - len(source_path)

        for node in self.source_tree.iter_tree():
            self.print_node(node, isatty, compute_level(node))

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

    def summary(self):
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
        print(f"Files:             {total_files:10d}")
        print(f"            known: {known_files:10d} ({kp:3d}%)")
        print(f"directories:       {total_directories:10d}")
        print(f"      fully-known: {full_known_directories:10d} ({fkp:3d}%)")
        print(f"  partially-known: {partially_known_directories:10d} ({pkp:3d}%)")
        print("(see other --output-format for more details)")

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

    def print_json(self):
        print(json.dumps(self.data_as_json(), indent=4, sort_keys=True))

    def print_ndjson(self):
        print(ndjson.dumps({k: v} for k, v in self.data_as_json().items()))
