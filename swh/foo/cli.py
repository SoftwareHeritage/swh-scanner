import click

from swh.core.cli import CONTEXT_SETTINGS


@click.group(name='foo', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def cli(ctx):
    """Foo main command.
    """


@cli.command()
@click.option('--bar', help='Something')
@click.pass_context
def bar(ctx, bar):
    '''Do something.'''
    click.echo('bar')
