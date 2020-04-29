# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from __future__ import annotations
import sys
import json
from pathlib import PosixPath
from typing import Any, Dict, Tuple, Iterable
from enum import Enum

from .plot import sunburst
from .exceptions import InvalidObjectType

from swh.model.identifiers import DIRECTORY, CONTENT


class Color(Enum):
    blue = "\033[94m"
    green = "\033[92m"
    red = "\033[91m"
    end = "\033[0m"


def colorize(text: str, color: Color):
    return color.value + text + Color.end.value


class Tree:
    """Representation of a file system structure
    """

    def __init__(self, path: PosixPath, father: Tree = None):
        self.father = father
        self.path = path
        self.otype = DIRECTORY if path.is_dir() else CONTENT
        self.swhid = ""
        self.known = False
        self.children: Dict[PosixPath, Tree] = {}

    def addNode(self, path: PosixPath, swhid: str, known: bool) -> None:
        """Recursively add a new path.
        """
        relative_path = path.relative_to(self.path)

        if relative_path == PosixPath("."):
            self.swhid = swhid
            self.known = known
            return

        new_path = self.path.joinpath(relative_path.parts[0])
        if new_path not in self.children:
            self.children[new_path] = Tree(new_path, self)

        self.children[new_path].addNode(path, swhid, known)

    def show(self, format) -> None:
        """Show tree in different formats"""
        if format == "json":
            print(json.dumps(self.toDict(), indent=4, sort_keys=True))

        elif format == "text":
            isatty = sys.stdout.isatty()

            print(colorize(str(self.path), Color.blue) if isatty else str(self.path))
            self.printChildren(isatty)

        elif format == "sunburst":
            root = self.path
            directories = self.getDirectoriesInfo(root)
            sunburst(directories, root)

    def printChildren(self, isatty: bool, inc: int = 1) -> None:
        for path, node in self.children.items():
            self.printNode(node, isatty, inc)
            if node.children:
                node.printChildren(isatty, inc + 1)

    def printNode(self, node: Any, isatty: bool, inc: int) -> None:
        rel_path = str(node.path.relative_to(self.path))
        begin = "│   " * inc
        end = "/" if node.otype == DIRECTORY else ""

        if isatty:
            if not node.known:
                rel_path = colorize(rel_path, Color.red)
            elif node.otype == DIRECTORY:
                rel_path = colorize(rel_path, Color.blue)
            elif node.otype == CONTENT:
                rel_path = colorize(rel_path, Color.green)

        print(f"{begin}{rel_path}{end}")

    @property
    def attributes(self):
        """
        Get the attributes of the current node grouped by the relative path.

        Returns:
            a dictionary containing a path as key and its known/unknown status and the
            Software Heritage persistent identifier as values.

        """
        return {str(self.path): {"swhid": self.swhid, "known": self.known,}}

    def toDict(self, dict_nodes={}) -> Dict[str, Dict[str, Dict]]:
        """
        Recursively groups the current child nodes inside a dictionary.

        For example, if you have the following structure:

        .. code-block:: none

        root {
            subdir: {
                file.txt
            }
        }

        The generated dictionary will be:

        .. code-block:: none

        {
            "root": {
                "swhid": "...",
                "known": True/False
            }
            "root/subdir": {
                "swhid": "...",
                "known": True/False
            }
            "root/subdir/file.txt": {
                "swhid": "...",
                "known": True/False
            }
        }


        """
        for node_dict in self.iterate():
            dict_nodes.update(node_dict)
        return dict_nodes

    def iterate(self) -> Iterable[Dict[str, Dict]]:
        """
        Recursively iterate through the children of the current node

        Yields:
            a dictionary containing a path with its known/unknown status and the
            Software Heritage persistent identifier

        """
        for _, child_node in self.children.items():
            yield child_node.attributes
            if child_node.otype == DIRECTORY:
                yield from child_node.iterate()

    def __getSubDirsInfo(self, root, directories):
        """Fills the directories given in input with the contents information
           stored inside the directory child, only if they have contents.
        """
        for path, child_node in self.children.items():
            if child_node.otype == DIRECTORY:
                rel_path = path.relative_to(root)
                contents_info = child_node.count_contents()
                # checks the first element of the tuple
                # (the number of contents in a directory)
                # if it is equal to zero it means that there are no contents
                # in that directory.
                if not contents_info[0] == 0:
                    directories[rel_path] = contents_info
                if child_node.has_dirs():
                    child_node.__getSubDirsInfo(root, directories)

    def getDirectoriesInfo(self, root: PosixPath) -> Dict[PosixPath, Tuple[int, int]]:
        """Get information about all directories under the given root.

        Returns:
            A dictionary with a directory path as key and the relative
            contents information (the result of count_contents) as values.

        """
        directories = {root: self.count_contents()}
        self.__getSubDirsInfo(root, directories)
        return directories

    def count_contents(self) -> Tuple[int, int]:
        """Count how many contents are present inside a directory.
           If a directory has a pid returns as it has all the contents.

        Returns:
            A tuple with the total number of the contents and the number
            of contents known (the ones that have a persistent identifier).

        """
        contents = 0
        discovered = 0

        if not self.otype == DIRECTORY:
            raise InvalidObjectType(
                "Can't calculate contents of the " "object type: %s" % self.otype
            )

        if self.known:
            # to identify a directory with all files/directories present
            return (1, 1)
        else:
            for _, child_node in self.children.items():
                if child_node.otype == CONTENT:
                    contents += 1
                    if child_node.known:
                        discovered += 1

        return (contents, discovered)

    def has_dirs(self) -> bool:
        """Checks if node has directories
        """
        for _, child_node in self.children.items():
            if child_node.otype == DIRECTORY:
                return True
        return False
