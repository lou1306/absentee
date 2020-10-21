#!/usr/bin/env python3

from pyparsing import (
    Suppress, OneOrMore, Forward, Word, QuotedString, alphanums, Group, SkipTo,
    LineEnd, ParseException)
from pyparsing import pyparsing_common as ppc

from pycparser import c_generator

from .error import warn, ConfigError
from .transforms import (
    FoldConstants, AddInitializers, WithoutTypedefs,
    RemoveArgs, ReplaceCalls, ReplaceTypes, WithoutBitwise)
from .symboltable import WithoutArrays

LPAR, RPAR = map(Suppress, "()")
SEXPR = Forward()
EMPTY = (LPAR + RPAR).setParseAction(lambda _: tuple())
ATOM = ppc.number() | Word(alphanums + "+-.:*/_=")
STR = QuotedString('"', escChar='\\', unquoteResults=False)\
      .addParseAction(lambda toks: toks[0].replace('\\"', '"'))
SEXPR <<= EMPTY | Group((LPAR + OneOrMore(STR | ATOM | SEXPR) + RPAR))
CONF = OneOrMore(SEXPR)
COMMENT = Suppress(";") + SkipTo(LineEnd())
CONF.ignore(COMMENT)


def parse_config(s):
    try:
        return CONF.parseString(s, parseAll=True).asList()
    except ParseException as e:
        raise ConfigError(e)


def execute(recipe, ast):
    BIND = {
        "fold-constants": FoldConstants,
        "add-initializers": AddInitializers,
        "without-arrays": WithoutArrays,
        "without-typedefs": WithoutTypedefs,
        "remove-args": RemoveArgs,
        "replace-calls": ReplaceCalls,
        "replace-types": ReplaceTypes,
        "without-bitwise": WithoutBitwise,
        "add-text-before": None,
        "add-text-after": None
    }
    recipe = [s for s in recipe if s]
    undefined_transforms = [s[0] for s in recipe if s[0] not in BIND]
    if undefined_transforms:
        warn(
            "The following transformations " +
            "are not defined and will be ignored: " +
            ", ".join(undefined_transforms))

    others = [s for s in recipe if not s[0].startswith("add-text")]
    prepends = [s[1:] for s in recipe if s[0] == "add-text-before"]
    appends = [s[1:] for s in recipe if s[0] == "add-text-after"]

    transforms = [
        BIND[s[0]](ast, s[1:])
        for s in others
        if s[0] in BIND
    ]

    # The x[1:-1] is to remove quotes
    yield from ("\n".join(x[1:-1] for x in s) for s in prepends)
    for t in transforms:
        t()
    cgen = c_generator.CGenerator()  # todo make a streaming C generator
    yield cgen.visit(ast)
    yield from ("\n".join(x[1:-1] for x in s) for s in appends)
