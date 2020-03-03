# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from __future__ import annotations
import sys
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
    def __init__(self, path: PosixPath, father: Tree = None):
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
            self.children[new_path] = Tree(new_path, self)

        self.children[new_path].addNode(path, pid)

    def show(self, format) -> None:
        """Print all the tree"""
        if format == 'json':
            print(self.getJsonTree())
        elif format == 'text':
            isatty = sys.stdout.isatty()

            print(colorize(str(self.path), Color.blue) if isatty
                  else str(self.path))
            self.printChildren(isatty)

    def printChildren(self, isatty: bool, inc: int = 0) -> None:
        for path, node in self.children.items():
            self.printNode(node, isatty, inc)
            if node.children:
                node.printChildren(isatty, inc+1)

    def printNode(self, node: Any, isatty: bool, inc: int) -> None:
        rel_path = str(node.path.relative_to(self.path))
        begin = '│   ' * inc
        end = '/' if node.otype == DIRECTORY else ''

        if isatty:
            if not node.pid:
                rel_path = colorize(rel_path, Color.red)
            elif node.otype == DIRECTORY:
                rel_path = colorize(rel_path, Color.blue)
            elif node.otype == CONTENT:
                rel_path = colorize(rel_path, Color.green)

        print(f'{begin}{rel_path}{end}')

    def getJsonTree(self):
        """Walk through the tree to discover content or directory that have
        a persistent identifier. If a persistent identifier is found it saves
        the path with the relative PID.

        Returns:
            child_tree: the tree with the content/directory found

        """
        child_tree = {}
        for path, child_node in self.children.items():
            rel_path = str(child_node.path.relative_to(self.path))
            if child_node.pid:
                child_tree[rel_path] = child_node.pid
            else:
                next_tree = child_node.getJsonChild()
                if next_tree:
                    child_tree[rel_path] = child_node.getJsonTree()

        return child_tree
