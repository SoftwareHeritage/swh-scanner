# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click
import asyncio
import os
from pathlib import PosixPath
from urllib.parse import urlparse

from .scanner import run
from .exceptions import InvalidPath
from .logger import setup_logger, log_counters
from .model import Tree

from swh.core.cli import CONTEXT_SETTINGS


def parse_url(url):
    if url.port == 80:
        return 'https://' + url.hostname
    else:
        return url.geturl()


@click.command(context_settings=CONTEXT_SETTINGS)
@click.argument('path', required=True)
@click.option('--host', '-h', default='localhost',
              metavar='IP', show_default=True,
              help="web api endpoint ip")
@click.option('--port', '-p', default='',
              metavar='PORT', show_default=True,
              help="web api endpoint port")
@click.option('--debug/--no-debug', default=True,
              help="enable debug")
@click.option('--verbose', '-v', is_flag=True, default=False,
              help="show debug information")
def scanner(path, host, port, debug, verbose):
    """Software Heritage tool to scan the source code of a project"""
    if not os.path.exists(path):
        raise InvalidPath(path)

    if debug:
        setup_logger(bool(verbose))

    url = parse_url(urlparse('https://%s:%s' % (host, port)))
    source_tree = Tree(None, PosixPath(path))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(path, url, source_tree))
    source_tree.show()
    log_counters()


if __name__ == '__main__':
    scanner()
