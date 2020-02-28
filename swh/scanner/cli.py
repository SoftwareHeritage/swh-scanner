# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click
import asyncio
from pathlib import PosixPath

from .scanner import run
from .model import Tree

from swh.core.cli import CONTEXT_SETTINGS

@click.group(name='scanner', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def scanner(ctx):
    '''Software Heritage Scanner tools.'''
    pass


def parse_url(url):
    if not url.startswith('http://') or not url.startswith('https://'):
        url = 'https://' + url
    if not url.endswith('/'):
        url += '/'
    return url


@scanner.command(name='scan')
@click.argument('path', required=True, type=click.Path(exists=True))
@click.option('--api-url', default='https://archive.softwareheritage.org/api/1',
              metavar='API_URL', show_default=True,
              help="url for the api request")
@click.pass_context
def scan(ctx, path, api_url):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    api_url = parse_url(api_url)
    source_tree = Tree(PosixPath(path))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(path, api_url, source_tree))
    source_tree.show()


if __name__ == '__main__':
    scan()
