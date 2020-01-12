#!/usr/bin/env python3


from sys import stderr, exit

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
        ast.show()
        exit(0)

    with open(conf) as f:
        transforms, includes, raw = build(f.read())

    # %%%%%%%% OUTPUT %%%%%%%% #

    for i in includes:
        print(i)

    print(raw)

    # transforms.sort(key=lambda v:v.priority)
    for v in transforms:
        v.visit(ast)

    cgen = c_generator.CGenerator()
    print(cgen.visit(ast))

    # %%%%%% END OUTPUT %%%%%% #


if __name__ == '__main__':
    try:
        main()
        exit(0)
    except (BaseError) as e:
        e.handle()
    except plyparser.ParseError as e:
        ParseError(e).handle()
