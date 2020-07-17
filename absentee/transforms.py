#!/usr/bin/env python3

# from functools import reduce
# from operator import mul

from pycparser.c_ast import (
    NodeVisitor, IdentifierType, Compound, UnaryOp,
    EmptyStatement, TypeDecl, FuncCall, ExprList, ID, Constant)

from .utils import track_parent, track_scope
from .error import TransformError


def parse_int(val):
    """ C99-Section 6.4.4.1
    """

    if val.startswith("0x"):
        return int(val, base=16)
    elif val.startswith("0"):
        return int(val, base=8)
    else:
        return int(val)


def is_const(n):
    return isinstance(n, Constant)


def to_dict(lst):
    try:
        return dict(lst)
    except ValueError:
        raise TransformError(
            f"""({" ".join(lst)}) invalid: expected a list of pairs.""",
            None)


class Transformation(NodeVisitor):
    def __init__(self, ast, params={}):
        self.ast = ast
        self.params = to_dict(params)

    def __call__(self):
        self.visit(self.ast)

    def get_list_attrs(self, node):
        return (a[:a.find("[")] for a, _ in node.children() if "[" in a)

    def get_attrs(self, node):
        return set(
            attr[:attr.find("[")]
            if "[" in attr else attr
            for attr, _ in node.children())


@track_scope
class Initialize(Transformation):
    """Add explicit initializers to declarations that lack one.

    Example: int a; --> int a = call();
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def visit_ParamList(self, node):
        # Do not visit parameters
        pass

    def visit_IdentifierType(self, node):
        self.type_ = node.names[0]

    def visit_Decl(self, node):
        self.generic_visit(node)
        if all((type(node.type) == TypeDecl, node.init is None, self.scope,
                self.type_ in self.params or tuple() in self.params)):
            func = self.params.get(self.type_, self.params.get(tuple(), None))
            if func:
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


class PurgeTypedefs(Transformation):
    """Removes all typedefs that are synonyms for C base types.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._visitingTypedef = ""
        self._visitingDecl = False
        self._markedForRemoval = set()

    def visit_FileAST(self, node):
        self.generic_visit(node)
        node.ext = [n for n in node.ext if n not in self._markedForRemoval]

    def visit_Typedef(self, node):
        # ignore structs, enums etc.
        if type(node.type.type) == IdentifierType:
            self._visitingTypedef = node.name
            self.generic_visit(node)
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


class RemoveArgs(Transformation):
    """Removes arguments from function calls.

    Examples:
    (removeArgs (f 0)) removes the 1st argument from all calls to f
    (removeArgs (f (1 3))) removes 2nd and 4th argument from all calls to f
    """

    def visit_FuncCall(self, node):
        if (node.name.name) in self.params:
            argsToRemove = self.params[node.name.name]
            if isinstance(argsToRemove, int):
                argsToRemove = [argsToRemove]
            for i in argsToRemove:
                try:
                    node.args.exprs[i] = None
                except IndexError:
                    continue  # TODO add a warning message?
            node.args.exprs = [n for n in node.args.exprs if n is not None]


@track_parent
class RenameCalls(Transformation):
    """Substitutes function calls.

    The function replaces calls to `f` with calls to `self.params[f]` (if any).
    If `self.params[f]` is the empty tuple AND the call does NOT occur as part
    of an expression, the call is replaced by an empty statement.
    """

    def visit_FuncCall(self, node):
        if node.name.name in self.params:
            new_name = self.params.get(node.name.name, node.name.name)
            if new_name == tuple():
                if type(self.parent) == Compound:
                    self.replace(node, EmptyStatement())
            else:
                node.name.name = new_name


class Retype(Transformation):
    """Transforms the type of variables.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visiting = ""

    def visit_Typedef(self, node):
        if node.name in self.params.keys():
            self.visiting = node.name
            self.generic_visit(node)
            self.visiting = ""

    def visit_TypeDecl(self, node):
        if node.declname == self.visiting:
            node.type.names = [self.params[self.visiting]]


class ToLogical(Transformation):
    """Transforms bitwise AND/OR operators into their logical counterparts.
    """

    def visit_BinaryOp(self, node):
        node.op = {"&": "&&", "|": "||"}.get(node.op, node.op)
        self.generic_visit(node)


@track_parent
class ConstantFolding(Transformation):

    def is_int_const(self, n):
        return is_const(n) and (n.type) == "int"

    def visit_UnaryOp(self, node):
        _ops = {
            "!": lambda x: 1 if x == 0 else 0,
            "+": lambda x: x,
            "-": lambda x: -x
        }
        self.generic_visit(node)
        if is_const(node.expr) and node.op in _ops:
            val = str(_ops[node.op](parse_int(node.expr.value)))
            new_node = Constant("int", val)
            self.replace(node, new_node)

    def visit_BinaryOp(self, node):
        """C99-Section 6.5
        """
        _ops = {
            "+": lambda x, y: x + y,
            "-": lambda x, y: x - y,
            "*": lambda x, y: x * y,
            "/": lambda x, y: x // y,
            "%": lambda x, y: abs(x) % abs(y) * (1 - 2 * (x < 0)),
            "<<": lambda x, y: x << y,
            ">>": lambda x, y: x >> y,
            "&": lambda x, y: x & y,
            "|": lambda x, y: x | y,
            "&&": lambda x, y: 0 if not bool(x) else int(bool(x & y)),
            "||": lambda x, y: 1 if bool(x) else int(bool(x | y))
        }
        self.generic_visit(node)

        # Commutative axioms
        for n1, n2 in ((node.left, node.right), (node.right, node.left)):
            if self.is_int_const(n1):
                v1 = parse_int(n1.value)
                if v1 == 0:
                    if node.op in ("+", "-"):
                        self.replace(node, n2)  # 0+x = 0-x = 0
                    elif node.op == "*":
                        self.replace(node, n1)  # 0*x = 0
                elif v1 == 1 and node.op == "*":
                    self.replace(node, n2)  # 1*x = x
                elif v1 == -1 and node.op == "*":
                    self.replace(node, UnaryOp("-", n2))  # -1*x = -x

        # Non-commutative axioms
        if self.is_int_const(node.left):
            v = parse_int(node.left.value)
            if v == 0 and node.op in (">>", "<<", "/", "%"):
                self.replace(node, node.left)  # 0<<x = 0>>x = 0/x = 0%x = 0

        if self.is_int_const(node.right):
            v = parse_int(node.right.value)
            if v == 0 and node.op in ("<<", ">>"):
                self.replace(node, node.left)  # x<<0 = x>>0 = x
            elif v == 1 and node.op == "/":
                self.replace(node, node.left)  # x/1 = x
            elif v == -1 and node.op == "/":
                self.replace(node, UnaryOp("-", node.left))  # x/-1 = -x
            elif abs(v) == 1 and node.op == "%":
                node.right.value = "0"
                self.replace(node, node.right)  # x%1 = 0

        # Generic folding
        ULLONG_MAX = 18446744073709551615
        if self.is_int_const(node.left) and self.is_int_const(node.right):
            if node.op in _ops:
                try:
                    val = _ops[node.op](
                        parse_int(node.left.value),
                        parse_int(node.right.value))
                    # print(">>>",val)
                    if abs(val) <= ULLONG_MAX:
                        new_node = Constant("int", str(val))
                        self.replace(node, new_node)
                except ZeroDivisionError:
                    pass


class GetId(NodeVisitor):
    """Return the ID node for the given node
    """

    def generic_visit(self, node):
        if not self.result:
            super().generic_visit(node)

    def find_id(self, node):
        self.result = None
        self.visit(node)
        return self.result

    def visit_ArrayRef(self, node):
        self.visit(node.name)

    def visit_ID(self, node):
        self.result = node


class NoneRemoval(Transformation):
    """Removes None elements from all lists within the AST
    """

    def generic_visit(self, node):
        for attr in self.get_list_attrs(node):
            ls = getattr(node, attr, [])
            ls = [x for x in ls if x is not None]
            setattr(node, attr, ls)
        super().generic_visit(node)
