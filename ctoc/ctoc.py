#!/usr/bin/env python3


from sys import exit

from pycparser import c_parser, c_generator, plyparser
import click


from error import BaseError, ParseError, ConfigError
from recipe import build_toml


@click.command()
@click.argument('file', required=True, type=click.Path(exists=True))
@click.option('--conf', type=click.Path(exists=True))
@click.option('--show-ast', default=False, is_flag=True)
def main(file, conf, show_ast):
    if not conf and (not show_ast):
        raise ConfigError("No configuration file!")

    parser = c_parser.CParser()
    with open(file) as f:
        ast = parser.parse(f.read(), filename=file)

    if show_ast:
        ast.show(showcoord=True)
        exit(0)

    with open(conf) as f:
        transforms, includes, raw = build_toml(f.read(), ast)

    # %%%%%%%% OUTPUT %%%%%%%% #

    for i in includes:
        click.echo(i)

    click.echo(raw)

    # transforms.sort(key=lambda v:v.priority)
    for v in transforms:
        v.visit(ast)

    cgen = c_generator.CGenerator()
    click.echo(cgen.visit(ast))

    # %%%%%% END OUTPUT %%%%%% #


if __name__ == '__main__':
    try:
        main()
        exit(0)
    except (BaseError) as e:
        e.handle()
    except plyparser.ParseError as e:
        ParseError(e).handle()
