#!/usr/bin/env python3

from pyparsing import (
    Suppress, OneOrMore, Forward, Word, QuotedString, alphanums, Group, SkipTo, 
    LineEnd, ParseException)
from pyparsing import pyparsing_common as ppc

from pycparser import c_generator

from .error import warn, ConfigError
from .transforms import *
from .symboltable import NoArrays

LPAR, RPAR = map(Suppress, "()")
SEXPR = Forward()
EMPTY = (LPAR + RPAR).setParseAction(lambda _: tuple())
ATOM = ppc.number() | Word(alphanums + "+-.:*/_=")
STR = QuotedString('"', escChar='\\', unquoteResults=False)
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
        "addLabels": AddLabels,
        "constantFolding": ConstantFolding,
        "initialize": Initialize,
        "noArrays": NoArrays,
        "purgeTypedefs": PurgeTypedefs,
        "removeArgs": RemoveArgs,
        "renameCalls": RenameCalls,
        "retype": Retype,
        "toLogical": ToLogical,
        "prepend": None,
        "append": None
    }
    undefined_transforms = [s[0] for s in recipe if s[0] not in BIND]
    if undefined_transforms:
        warn(
            f"""The following transformations are not defined and will be ignored: {", ".join(undefined_transforms)}""")

    others = [s for s in recipe if s[0] not in ("append", "prepend")]
    prepends = [s[1:] for s in recipe if s[0] == "prepend"]
    appends = [s[1:] for s in recipe if s[0] == "append"]

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


# if __name__ == "__main__":
#     tests = [
#         "()",
#         "(+ 1 2 3)",
#         "(+ (* 1 2) 3)",
#         """("Hello" "\\"World\\" !!")"""
#         """
#         ; Multiple lines
#         (+ (* 1 2) 3) ; comment
#         ()
#         (+ "a" "b") ; comment
#         """,
#         """
#         (toLogical)
#         (initialize
#             (char __VERIFIER_nondet_char)
#             (int __VERIFIER_nondet_char)
#             ; Wildcard, will apply to all other declarations
#             (() __VERIFIER_nondet_int)
#         )
#         (renameCalls __VERIFIER_nondet __VERIFIER_nondet_int)
#         (renameCalls nondet __VERIFIER_nondet_int)
#         (retype TYPEOFVALUES char)
#         (noArrays)
#         """

#     ]
#     for s in tests:
#         print(s, ">>", parseConfig(s))
