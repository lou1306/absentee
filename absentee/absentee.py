#!/usr/bin/env python3

from sys import exit, stdin

from pycparser import c_parser, plyparser
import click

from .error import BaseError, ParseError, ConfigError
from .parser import parse_config, execute
from .__about__ import __title__, __version__


def from_string(string, conf):
    parser = c_parser.CParser()
    ast = parser.parse(string)
    with open(conf) as f:
        return "".join(execute(parse_config(f.read()), ast))


def absentee(file, conf, show_ast, to_stdout=True):

    if not conf and (not show_ast):
        raise ConfigError("No configuration file!")

    parser = c_parser.CParser()
    with (stdin if file == "-" else open(file)) as f:
        ast = parser.parse(f.read(), filename=file)

    if show_ast:
        ast.show(showcoord=True)
        exit(0)

    with open(conf) as f:
        if to_stdout:
            for r in execute(parse_config(f.read()), ast):
                click.echo(r, nl=False)
            click.echo()
        else:
            yield from execute(parse_config(f.read()), ast)


_show_ast = {
    "is_flag": True,
    "default": False,
    "show_default": True,
    "help": "Show the syntax tree of FILE and exit."
}
_conf = {
    "type": click.Path(exists=True),
    "help": "The path to the configuration file."
}


@click.command()
@click.argument('file', required=True,
                type=click.Path(exists=True, allow_dash=True))
@click.option('--conf', **_conf)
@click.option('--show-ast', **_show_ast)
@click.version_option(__version__, prog_name=__title__.lower())
@click.help_option('-h', '--help')
def main(file, conf, show_ast):
    """
    absentee C transformation tool
    """
    try:
        absentee(file, conf, show_ast)
        exit(0)
    except (BaseError) as e:
        e.handle()
    except plyparser.ParseError as e:
        ParseError(e).handle()
