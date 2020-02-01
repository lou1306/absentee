#!/usr/bin/env python3

# from functools import reduce
# from operator import mul
from copy import deepcopy
from collections import defaultdict
from io import StringIO

from pycparser.c_ast import NodeVisitor, IdentifierType, Compound, \
    EmptyStatement, Label, TypeDecl, FuncCall, ExprList, ID, Constant, \
    ArrayRef, ArrayDecl, Decl, Switch, Case, Return, FuncDecl, FuncDef, \
    ParamList, Assignment, Break, BinaryOp, Struct, Typedef, UnaryOp


from .symboltable import SymbolTableBuilder
from .utils import track_scope, track_parent
from .error import TransformError


def to_string(node):
    """Hacky hack to get a string representation for an AST node
    """

    __s = StringIO()

    def f(node):
        __s.truncate(0)
        __s.seek(0)
        node.show(buf=__s)
        __s.seek(0)
        return __s.read()
    return f(node)


def make_decl(name, type_):
    return Decl(
        name=name, type=type_,
        quals=[], storage=[], funcspec=[], init=None, bitsize=None)


def make_typedecl(type_, name):
    return TypeDecl(name, [], TypeDecl(name, [], IdentifierType([type_])))


def make_function(type_, name, params, body):
    param_list = ParamList([
        make_decl(param_name, make_typedecl(param_type, param_name))
        for param_type, param_name in params])
    fdecl = FuncDecl(param_list, TypeDecl(name, [], type_))
    decl = make_decl(name, fdecl)
    return FuncDef(decl, [], body)


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


class Transformation(NodeVisitor):
    def __init__(self, ast, params={}):
        self.ast = ast
        self.params = params

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
                self.type_ in self.params or "*" in self.type_)):
            func = self.params.get(self.type_, self.params.get("*", None))
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


class RenameCalls(Transformation):
    """Substitutes function calls.
    """

    def visit_FuncCall(self, node):
        node.name.name = self.params.get(node.name.name, node.name.name)


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


@track_scope
@track_parent
class NoArrays(Transformation):
    """Splits arrays into separate variables.
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.used = set()
        self.accessors = set()
        self.new_code = []
        self.id_finder = GetId()

    def make_accessors(self, info):
        """Build get() and set() function based on info.
        """
        name = self.array_name(info)
        fname = self.make_getter_name(info)
        size = info.sizeof()
        params = [("int", f"x{i}") for i in range(len(info.size))]
        mults = [
            BinaryOp("*", a, ID(b[1]))
            for a, b in zip(info.size, params[:-1])]

        offset = ID(params[-1][1])
        for m in mults:
            offset = BinaryOp("+", m, offset)

        cases = [
            Case(Constant("int", str(i)), [Return(ID(f"{name}_{i}"))])
            for i in range(size)
        ]
        body = Compound([Switch(offset, Compound(cases))])
        self.accessors.add(make_function(info.type, fname, params, body))

        cases = [
            Case(Constant("int", str(i)), [
                Assignment("=", ID(f"{name}_{i}"), ID("value")),
                Break()])
            for i in range(size)
        ]
        body = Compound([Switch(offset, Compound(cases))])
        type_ = (
            info.type.name
            if type(info.type) == Struct
            else info.type.names[0])
        setter = make_function(
            IdentifierType(["void"]), fname.replace("get", "set", 1),
            params + [(type_, "value")], body)
        self.accessors.add(setter)

    def array_name(self, info):
        scope_slug = ""
        if info.scope:
            scope = str(info.scope)
            scope_slug = scope[scope.find(":"):].replace(":", "_")
        return f"{info.decl.declname}{scope_slug}"

    def visit_Decl(self, node):
        if type(node.type) == ArrayDecl:
            info = self._info.get_info(node.name, self.scope)
            if not info.is_param:
                new_name = self.array_name(info)
                if node.init:
                    raise TransformError(
                        "Array initializers not supported.",
                        node.init.coord)

                def do_decl(i):
                    new_info = deepcopy(info)
                    new_info.decl.declname = f"{new_name}_{i}"
                    return make_decl(new_info.decl.declname, new_info.decl)

                self.delete(node)
                decls = (do_decl(i) for i in range(info.sizeof()))
                self.new_code += decls
                self.make_accessors(info)
        self.generic_visit(node)

    def visit_FileAST(self, node):
        self._info = SymbolTableBuilder().make_table(node)
        self.generic_visit(node)
        self.ast.ext.extend(self.new_code)
        self.ast.ext.extend(
            x for x in self.accessors if x.decl.name in self.used)
        NoneRemoval(node).visit(node)
        Reorder(node).visit(node)

    def visit_Assignment(self, node):
        self.generic_visit(node)
        if node.lvalue.coord == "NoArrays":
            node.lvalue.args.exprs.append(node.rvalue)
            node.lvalue.name.name = \
                node.lvalue.name.name.replace("get", "set", 1)
            self.replace(node, node.lvalue)
            self.used.add(node.lvalue.name.name)

    def visit_ArrayRef(self, node):
        self.generic_visit(node)
        if type(node.name) == ID:
            info = self._info.get_info(node.name.name, self.scope)
            fname = self.make_getter_name(info)
            _node = FuncCall(ID(fname), ExprList([]))
            _node.coord = "NoArrays"
            _node.args.exprs.append(node.subscript)
            self.replace(node, _node)
            self.used.add(fname)
        elif node.name.coord == "NoArrays":
            node.name.args.exprs.append(node.subscript)
            self.replace(node, node.name)

    def make_getter_name(self, info):
        name = f"get{self.array_name(info)}"
        while True:
            setter_name = name.replace("get", "set", 1)
            if name in self._info or setter_name in self._info:
                name = "_" + name
            else:
                break
        return name


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
                    val = _ops[node.op](parse_int(node.left.value), parse_int(node.right.value))
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


@track_scope
class Reorder(Transformation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_finder = GetId()
        self.current_node = None
        self.needs = defaultdict(set)
        self.declares = defaultdict(set)
        self.symbols = SymbolTableBuilder().make_table(self.ast)

    def visit_FileAST(self, node):
        def tpsort(lst):
            result = []
            # We use a dict because it preserves the ordering of elements
            # While allowing for constant-time remove (pop(), popitem())
            unmarked = {x: None for x in lst}
            tmp_marked = set()
            marked = set()

            def visit(n):
                if n in marked or n in tmp_marked:
                    return
                unmarked.pop(n, None)
                tmp_marked.add(n)

                # Neighbor = anybody who needs something declared by n
                neighbors = (x for x in tmp_marked.union(unmarked.keys())
                             if x != n and
                             self.needs[x].intersection(self.declares[n]))

                for m in neighbors:
                    visit(m)
                tmp_marked.discard(n)
                marked.add(n)
                result.append(n)

            while unmarked:
                visit(unmarked.popitem()[0])

            return result[::-1]

        for n in node.ext:
            self.current_node = n
            self.visit(n)

        typedefs = (n for n in node.ext if type(n) == Typedef)
        decls = (n for n in node.ext if type(n) == Decl)
        funcdefs = (n for n in node.ext if type(n) == FuncDef)

        node.ext = [*tpsort(typedefs), *tpsort(decls), *tpsort(funcdefs)]

    def visit_TypeDef(self, node):
        self.declares[self.current_node].add(node.name)
        self.generic_visit(node)

    def visit_ParamList(self, node):
        return

    def visit_Decl(self, node):
        if self.scope is None:
            self.declares[self.current_node].add(node.name)
        self.generic_visit(node)

    def visit_IdentifierType(self, node):
        self.needs[self.current_node].update(node.names)

    def visit_FuncCall(self, node):
        try:
            self.needs[self.current_node].add(node.name.name)
        except Exception:
            pass
        self.generic_visit(node)

    def visit_TypeDecl(self, node):
        if node.declname:
            self.declares[self.current_node].add(node.declname)
        self.generic_visit(node)
