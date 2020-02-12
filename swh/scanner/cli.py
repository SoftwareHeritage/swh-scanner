# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click

from swh.core.cli import CONTEXT_SETTINGS
from swh.scanner.scanner import run


@click.group(name='scanner', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def scanner(ctx):
    '''Software Heritage Scanner tools.'''
    pass


@scanner.command(name='scan')
@click.argument('path', required=True)
@click.option('--host', '-h', default='localhost',
              metavar='IP', show_default=True,
              help="web api endpoint ip")
@click.option('--port', '-p', default='5080',
              metavar='PORT', show_default=True,
              help="web api endpoint port")
@click.pass_context
def scan(ctx, path, host, port):
    result = run(path, host, port)
    print(result)


def main():
    return scanner(auto_envvar_prefix='SWH_SCANNER')


if __name__ == '__main__':
    main()
