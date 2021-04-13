# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterator, List, Tuple

import ndjson

from swh.model.identifiers import CONTENT, DIRECTORY

from .exceptions import InvalidDirectoryPath, InvalidObjectType
from .plot import generate_sunburst, offline_plot


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

    def __init__(self, path: Path, father: Tree = None):
        self.father = father
        self.path = path
        self.otype = DIRECTORY if path.is_dir() else CONTENT
        self.swhid = ""
        self.known = False
        self.children: Dict[Path, Tree] = {}

    def add_node(self, path: Path, swhid: str, known: bool) -> None:
        """Recursively add a new path.
        """
        relative_path = path.relative_to(self.path)

        if relative_path == Path("."):
            self.swhid = swhid
            self.known = known
            return

        new_path = self.path.joinpath(relative_path.parts[0])
        if new_path not in self.children:
            self.children[new_path] = Tree(new_path, self)

        self.children[new_path].add_node(path, swhid, known)

    def show(self, fmt) -> None:
        """Show tree in different formats"""
        if fmt == "json":
            print(json.dumps(self.to_dict(), indent=4, sort_keys=True))

        if fmt == "ndjson":
            print(
                ndjson.dumps(
                    {str(Path(k).relative_to(self.path)): v}
                    for node in self.iterate()
                    for k, v in node.attributes.items()
                )
            )

        elif fmt == "text":
            isatty = sys.stdout.isatty()
            root_dir = self.path.relative_to(self.path.parent)
            print(colorize(str(root_dir), Color.blue) if isatty else str(root_dir))
            self.print_children(isatty)

        elif fmt == "sunburst":
            root = self.path
            directories = self.get_directories_info(root)
            sunburst = generate_sunburst(directories, root)
            offline_plot(sunburst)

    def print_children(self, isatty: bool, inc: int = 1) -> None:
        for path, node in self.children.items():
            self.print_node(node, isatty, inc)
            if node.children:
                node.print_children(isatty, inc + 1)

    def print_node(self, node: Any, isatty: bool, inc: int) -> None:
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
    def attributes(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the attributes of the current node grouped by the relative path.

        Returns:
            a dictionary containing a path as key and its known/unknown status and the
            SWHID as values.

        """
        return {str(self.path): {"swhid": self.swhid, "known": self.known,}}

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Recursively flatten the current tree nodes into a dictionary.

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
        return {
            str(Path(k).relative_to(self.path)): v
            for node in self.iterate()
            for k, v in node.attributes.items()
        }

    def iterate(self) -> Iterator[Tree]:
        """
        Recursively iterate through the children of the current node

        """
        for _, child_node in self.children.items():
            yield child_node
            if child_node.otype == DIRECTORY:
                yield from child_node.iterate()

    def get_files_from_dir(self, dir_path: Path) -> List:
        """
        Retrieve files information about a specific directory path

        Returns:
            A list containing the files attributes present inside the directory given
            in input
        """

        def get_files(node):
            files = []
            for _, node in node.children.items():
                if node.otype == CONTENT:
                    files.append(node.attributes)
            return files

        if dir_path == self.path:
            return get_files(self)
        else:
            for node in self.iterate():
                if node.path == dir_path:
                    return get_files(node)
            raise InvalidDirectoryPath(
                "The directory provided doesn't match any stored directory"
            )

    def _get_sub_dirs_info(self, root, directories):
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
                    child_node._get_sub_dirs_info(root, directories)

    def get_directories_info(self, root: Path) -> Dict[Path, Tuple[int, int]]:
        """Get information about all directories under the given root.

        Returns:
            A dictionary with a directory path as key and the relative
            contents information (the result of count_contents) as values.

        """
        directories = {root: self.count_contents()}
        self._get_sub_dirs_info(root, directories)
        return directories

    def count_contents(self) -> Tuple[int, int]:
        """Count how many contents are present inside a directory.
           If a directory has a SWHID returns as it has all the contents.

        Returns:
            A tuple with the total number of the contents and the number
            of contents known (the ones that have a persistent identifier).

        """
        contents = 0
        discovered = 0

        if not self.otype == DIRECTORY:
            raise InvalidObjectType(
                "Can't count contents of the object type: %s" % self.otype
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
