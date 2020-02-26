# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from __future__ import annotations
from pathlib import PosixPath
from typing import Any, Dict
from enum import Enum

from swh.model.identifiers import (
    DIRECTORY, CONTENT
)


class Color(Enum):
    blue = '\033[94m'
    green = '\033[92m'
    red = '\033[91m'
    end = '\033[0m'


def colorize(text: str, color: Color):
    return color.value + text + Color.end.value


class Tree:
    """Representation of a file system structure
    """
    def __init__(self, father: Tree, path: PosixPath):
        self.father = father
        self.path = path
        self.otype = DIRECTORY if path.is_dir() else CONTENT
        self.pid = ''
        self.children: Dict[PosixPath, Tree] = {}

    def addNode(self, path: PosixPath, pid: str = None) -> None:
        """Recursively add a new node path
        """
        relative_path = path.relative_to(self.path)

        if relative_path == PosixPath('.'):
            if pid is not None:
                self.pid = pid
            return

        new_path = self.path.joinpath(relative_path.parts[0])
        if new_path not in self.children:
            self.children[new_path] = Tree(self, new_path)

        self.children[new_path].addNode(path, pid)

    def show(self) -> None:
        """Print all the tree"""
        print(Color.blue.value+str(self.path)+Color.end.value)
        self.printChildren()

    def printChildren(self, inc: int = 0) -> None:
        for path, node in self.children.items():
            self.printNode(node, inc)
            if node.children:
                node.printChildren(inc+1)

    def printNode(self, node: Any, inc: int) -> None:
        rel_path = str(node.path.relative_to(self.path))
        if node.otype == DIRECTORY:
            if node.pid:
                print('│   '*inc + colorize(rel_path, Color.blue) + '/')
            else:
                print('│   '*inc + colorize(rel_path, Color.red) + '/')

        if node.otype == CONTENT:
            if node.pid:
                print('│   '*inc + colorize(rel_path, Color.green))
            else:
                print('│   '*inc + colorize(rel_path, Color.red))
