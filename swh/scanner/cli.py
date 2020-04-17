# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click
import asyncio
import glob
import re
import fnmatch
from pathlib import PosixPath
from typing import Tuple

from .scanner import run
from .model import Tree
from .exceptions import InvalidDirectoryPath

from swh.core.cli import CONTEXT_SETTINGS


@click.group(name="scanner", context_settings=CONTEXT_SETTINGS)
@click.pass_context
def scanner(ctx):
    """Software Heritage Scanner tools."""
    pass


def parse_url(url):
    if not url.startswith("https://"):
        url = "https://" + url
    if not url.endswith("/"):
        url += "/"
    return url


def extract_regex_objs(root_path: PosixPath, patterns: Tuple[str]) -> object:
    """Generates a regex object for each pattern given in input and checks if
       the path is a subdirectory or relative to the root path.

       Yields:
          an SRE_Pattern object
    """
    for pattern in patterns:
        for path in glob.glob(pattern):
            dirpath = PosixPath(path)
            if root_path not in dirpath.parents:
                error_msg = (
                    f'The path "{dirpath}" is not a subdirectory or relative '
                    f'to the root directory path: "{root_path}"'
                )
                raise InvalidDirectoryPath(error_msg)

        if glob.glob(pattern):
            regex = fnmatch.translate(str(PosixPath(pattern)))
            yield re.compile(regex)


@scanner.command(name="scan")
@click.argument("root_path", required=True, type=click.Path(exists=True))
@click.option(
    "-u",
    "--api-url",
    default="https://archive.softwareheritage.org/api/1",
    metavar="API_URL",
    show_default=True,
    help="url for the api request",
)
@click.option(
    "--exclude",
    "-x",
    "patterns",
    metavar="PATTERN",
    multiple=True,
    help="recursively exclude a specific pattern",
)
@click.option(
    "-f",
    "--format",
    type=click.Choice(["text", "json", "sunburst"], case_sensitive=False),
    default="text",
    help="select the output format",
)
@click.pass_context
def scan(ctx, root_path, api_url, patterns, format):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    sre_patterns = set()
    if patterns:
        sre_patterns = {
            reg_obj for reg_obj in extract_regex_objs(PosixPath(root_path), patterns)
        }

    api_url = parse_url(api_url)
    source_tree = Tree(PosixPath(root_path))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(root_path, api_url, source_tree, sre_patterns))

    source_tree.show(format)


if __name__ == "__main__":
    scan()
