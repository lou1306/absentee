#!/usr/bin/env python3


from sys import stderr, exit

from pycparser import c_parser, c_generator, plyparser
from pycparser.c_ast import NodeVisitor, IdentifierType, Compound, \
    EmptyStatement, Label, TypeDecl, FuncCall, ExprList, ID
import toml
import click


class BaseError(Exception):
    def handle(self):
        click.echo(f"{self.HEADER} error: {self.message}", err=True)
        exit(self.CODE)


class ConfigError(BaseError):
    HEADER = "Configuration"
    CODE = 1

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return f"Configuration error: {self.message}"


class TransformError(BaseError):
    HEADER = "Transformation"
    CODE = 6

    def __init__(self, message, coords):
        self.message = f"{message}\nat: {coords}"
        self.coords = coords


class ParseError(BaseError):
    HEADER = "Parsing"
    CODE = 10

    def __init__(self, ply_exception):
        self.message = ply_exception



class Transformation(NodeVisitor):
    def __init__(self, params={}):
        self.params = params


class Initialize(Transformation):
    """Add explicit initializers to declarations that lack one.

    Example: int a; --> int a = call()
    """

    def __init__(self, params):
        super().__init__(params)
        self._scope = ""

    def visit_FuncDef(self, node):
        old_scope = self._scope
        self._scope = "::".join([self._scope, node.decl.name])
        NodeVisitor.generic_visit(self, node)
        self._scope = old_scope

    def visit_ParamList(self, node):
        pass

    def visit_IdentifierType(self, node):
        self.type_ = node.names[0]

    def visit_Decl(self, node):
        self.generic_visit(node)
        if all((type(node.type) == TypeDecl, node.init is None, self._scope,
                self.type_ in self.params or "*" in self.type_)):
            func = self.params.get(self.type_, self.params["*"])
            node.init = FuncCall(ID(func), ExprList([]))


class AddLabels(Transformation):
    """Decorate each function <f> with ENTRY_<f> and EXIT_<f> labels
    """

    def visit_FuncDef(self, node):
        if type(node.body) == Compound:
            name = node.decl.name
            entry_label = Label("ENTRY_{}".format(name), EmptyStatement())
            exit_label = Label("EXIT_{}".format(name), EmptyStatement())

            if node.body.block_items:
                node.body.block_items.insert(0, entry_label)
                node.body.block_items.append(exit_label)


class PurgeTypedefs(NodeVisitor):
    """Removes all typedefs that are synonyms for C base types.
    """

    def __init__(self):
        self.priority = 1
        self._visitingTypedef = ""
        self._visitingDecl = False
        self._markedForRemoval = set()

    def visit_FileAST(self, node):
        NodeVisitor.generic_visit(self, node)
        node.ext = [n for n in node.ext if n not in self._markedForRemoval]

    def visit_Typedef(self, node):
        # ignore structs, enums etc.
        if type(node.type.type) == IdentifierType:
            self._visitingTypedef = node.name
            NodeVisitor.generic_visit(self, node)
            self._markedForRemoval.add(node)
            self._visitingTypedef = ""

    def visit_IdentifierType(self, node):
        if self._visitingTypedef:
            self.params[self._visitingTypedef] = node.names[0]
        if self._visitingDecl:
            node.names = [self.params.get(node.names[0], node.names[0])]

    def visit_Decl(self, node):
        self._visitingDecl = True
        self.generic_visit(node)
        self._visitingDecl = False

    def visit_TypeDecl(self, node):
        self.visit_Decl(node)

    def visit_PointerDecl(self, node):
        self.visit_Decl(node)


class RenameCalls(Transformation):
    """Substitutes function calls.
    """

    def visit_FuncCall(self, node):
        node.name.name = self.params.get(node.name.name, node.name.name)


class Retype(NodeVisitor):
    """Transforms the type of variables.
    """

    def __init__(self, params):
        self.params = params
        self.visiting = ""

    def visit_Typedef(self, node):
        # print(node)
        # Only recurse if the typedef must be retyped
        if node.name in self.params.keys():
            self.visiting = node.name
            NodeVisitor.generic_visit(self, node)
            self.visiting = ""

    def visit_TypeDecl(self, node):
        if node.declname == self.visiting:
            node.type.names = [self.params[self.visiting]]


class ToLogical(Transformation):
    """Transforms all bitwise operators into their logical counterparts.
    """

    def visit_BinaryOp(self, node):
        ops = {
            "&": "&&",
            "|": "||"
        }
        node.op = ops.get(node.op, node.op)
        NodeVisitor.generic_visit(self, node)


def build(toml_input):

    BIND = {
        "renameCalls": RenameCalls,
        "toLogical": ToLogical,
        "retype": Retype,
        "purgeTypedefs": PurgeTypedefs,
        "addLabels": AddLabels,
        "initialize": Initialize
    }

    conf = toml.loads(toml_input)

    if "main" not in conf:
        raise ConfigError("Missing \"main\" in configuration")

    main = conf["main"]

    undefined_transforms = [k for k in main.get("do", []) if k not in BIND]
    if undefined_transforms:
        print("Warning: The following transformations are not defined:",
              ", ".join(undefined_transforms), file=stderr)

    transforms = [
        BIND[k](conf.get(k, {}))
        for k in main.get("do", [])
        if k in BIND
    ]

    includes = [
        f"#include {i}"
        if i.startswith("<")
        else f"#include \"{i}\""
        for i in main.get("includes", [])
    ]

    return transforms, includes, main.get("rawPrelude", "")


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


def handle_error(header, content, code):
    click.echo(f"{header} error: {content}", err=True)
    exit(code)


if __name__ == '__main__':
    try:
        main()
        exit(0)
    except ConfigError as e:
        handle_error("Configuration", e.message, 1)
    except plyparser.ParseError as e:
        handle_error("Parser", e, 10)
