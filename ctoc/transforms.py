#!/usr/bin/env python3

# from functools import reduce
# from operator import mul
from copy import deepcopy
from io import StringIO

from pycparser.c_ast import NodeVisitor, IdentifierType, Compound, \
    EmptyStatement, Label, TypeDecl, FuncCall, ExprList, ID, Constant, \
    ArrayRef, ArrayDecl, Decl, Switch, Case, Return, FuncDecl, FuncDef, \
    ParamList, Assignment, Break, BinaryOp


from symboltable import SymbolTableBuilder
from utils import track_scope, track_parent
from error import TransformError


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


class Initialize(Transformation):
    """Add explicit initializers to declarations that lack one.

    Example: int a; --> int a = call();
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scope = ""

    def visit_FuncDef(self, node):
        old_scope = self._scope
        self._scope = "::".join([self._scope, node.decl.name])
        self.generic_visit(node)
        self._scope = old_scope

    def visit_ParamList(self, node):
        # Do not visit parameters
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
        self._reset()
        self.new_code = []
        self.id_finder = GetId()

    def make_accessors(self, info):
        """Build get() and set() function based on info.
        """
        name = self.array_name(info)
        size = info.sizeof()

        cases = [
            Case(Constant("int", str(i)), [Return(ID(f"{name}_{i}"))])
            for i in range(size)
        ]
        body = Compound([Switch(ID("i"), Compound(cases))])
        getter = make_function(info.type, f"get{name}", (("int", "i"),), body)
        cases = [
            Case(Constant("int", str(i)),
                 [Assignment("=", ID(f"{name}_{i}"), ID("value")), Break()])
            for i in range(size)
        ]
        body = Compound([Switch(ID("i"), Compound(cases))])
        setter = make_function(
            IdentifierType(["void"]), f"set{name}",
            (("int", "i"), (info.type.names[0], "value")), body)

        return (getter, setter)

    def array_name(self, info):
        scope_slug = ""
        if info.scope:
            scope = str(info.scope)
            scope_slug = scope[scope.find(":"):].replace(":", "_")
        return f"{info.decl.declname}{scope_slug}"

    def _reset(self):
        self._op = "get"
        self._new_node = None
        self._dim = []

    def visit_Decl(self, node):
        if type(node.type) == ArrayDecl:
            info = self._info.get_info(node.name, self.scope)
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
            decls = [do_decl(i) for i in range(info.sizeof())]
            self.new_code += decls
            self.new_code.extend(self.make_accessors(info))
            self.generic_visit(node)

    def visit_FileAST(self, node):
        self._info = SymbolTableBuilder().make_table(node)
        self.generic_visit(node)
        self.ast.ext = [*self.new_code, *self.ast.ext]
        NoneRemoval(node).visit(node)

    def visit_Assignment(self, node):
        if type(node.lvalue) == ArrayRef:
            self._op = "set"
            id_node = self.id_finder.find_id(node.lvalue)
            self.visit(node.lvalue)
            new_node = self.make_funccall(id_node)
            self._reset()
            self.visit(node.rvalue)
            new_node.args.exprs.append(node.rvalue)
            self.replace(node, new_node)
        else:
            self.generic_visit(node)

    def visit_ArrayRef(self, node):
        if not self._dim:
            self._dim = [node.subscript]
            id_node = self.id_finder.find_id(node)
            self.generic_visit(node)
            if self._op == "get":
                new_node = self.make_funccall(id_node)
                self._reset()
                self.replace(node, new_node)
        else:
            self._dim.append(node.subscript)
            self.generic_visit(node)

    def make_funccall(self, id_node):
        dim = self._dim
        info = self._info.get_info(id_node.name, self.scope)
        size = list(info.int_size())
        if len(size) != len(dim):
            raise TransformError("Cannot remove arrays.", id_node.coord)
        mults = [
            BinaryOp("*", Constant("", str(a)), b)
            for a, b in zip(size, dim[1:])]

        offset = dim[0]
        for m in mults:
            offset = BinaryOp("+", m, offset)

        return FuncCall(
            ID(f"{self._op}{self.array_name(info)}"),
            ExprList([offset]))


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
    """Removes None elements from lists within the AST
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
        # self.visiting_params = False
        self.needs = defaultdict(set)
        self.declares = defaultdict(set)
        self.symbols = SymbolTableBuilder().make_table(self.ast)

    def visit_FileAST(self, node):
        def tpsort(lst):
            result = []
            # We use a dict because it guarantees ordering of the elements
            # While allowing for constant-time remove (pop(), popitem())
            unmarked = {x: None for x in lst}
            tmp_marked = set()
            marked = set()

            def visit(n):
                if n in marked:
                    return
                elif n in tmp_marked:
                    raise TransformError("Cannot reorder.", None)
                unmarked.pop(n, None)
                tmp_marked.add(n)

                neighbors = (x for x in lst
                             if self.needs[x].intersection(self.declares[n]))

                for m in neighbors:
                    visit(m)
                tmp_marked.discard(n)
                marked.add(n)
                result.append(n)

            while unmarked:
                visit(unmarked.popitem()[0])

            return reversed(result)

        for n in node.ext:
            self.current_node = n
            self.visit(n)

        node.ext = list(tpsort(node.ext))

    def visit_TypeDef(self, node):
        self.declares[self.current_node].add(node.name)
        self.generic_visit(node)

    def visit_ParamList(self, node):
        return
        # self.visiting_params = True
        # self.generic_visit(node)
        # self.visiting_params = False

    def visit_Decl(self, node):
        if self.scope is None:
            self.declares[self.current_node].add(node.name)
        self.generic_visit(node)

    def visit_IdentifierType(self, node):
        self.needs[self.current_node].update(node.names)

    def visit_ID(self, node):
        info = self.symbols.get_or_default(node.name, self.scope, None)
        if info and info.scope is None:
            self.needs[self.current_node].add(info.decl.declname)

    def visit_FuncCall(self, node):
        try:
            self.needs[self.current_node].add(node.name.name)
        except Exception:
            pass
        self.generic_visit(node)

    def visit_TypeDecl(self, node):
        if node.declname:  # and not self.visiting_params:
            self.declares[self.current_node].add(node.declname)
        self.generic_visit(node)
