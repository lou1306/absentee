#!/usr/bin/env python3

from sys import exit, stdin

from pycparser import c_parser, c_generator, plyparser
import click


from absentee.error import BaseError, ParseError, ConfigError
from absentee.parser import parse_config, execute


@click.command()
@click.argument('file', required=True,
                type=click.Path(exists=True, allow_dash=True))
@click.option('--conf', type=click.Path(exists=True))
@click.option('--show-ast', default=False, is_flag=True)
def main(file, conf, show_ast):

    if not conf and (not show_ast):
        raise ConfigError("No configuration file!")

    parser = c_parser.CParser()
    with (stdin if file == "-" else open(file)) as f:
        ast = parser.parse(f.read(), filename=file)

    if show_ast:
        ast.show(showcoord=True)
        exit(0)

    with open(conf) as f:
        for r in execute(parse_config(f.read()), ast):
            click.echo(r, nl=False)
        click.echo()

        

if __name__ == '__main__':
    try:
        main()
        exit(0)
    except (BaseError) as e:
        e.handle()
    except plyparser.ParseError as e:
        ParseError(e).handle()
