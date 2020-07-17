#!/usr/bin/env python3

from dataclasses import dataclass, field
from typing import List
from functools import reduce
from copy import deepcopy
from collections import defaultdict

from pycparser.c_ast import (
    Node, NodeVisitor, ID, BinaryOp, Constant, Switch, Case, Compound,
    IdentifierType, Assignment, Decl, Break, ArrayDecl, Return, Struct,
    InitList, Typedef, FuncDef, FuncCall, ExprList
)

from .error import TransformError
from .utils import (
    make_decl, make_function, track_parent, track_scope
)
from .transforms import Transformation, GetId, FoldConstants


@dataclass
class TableEntry:
    decl: Node
    scope: Node
    type: Node
    belongs_to: "SymbolTable" = field(repr=False)
    size: List[Node]
    is_param: bool
    init: Node

    def int_size(self):
        for s in self.size:
            try:
                if isinstance(s, ID):
                    var = list(self.belongs_to.lookup(s.name))[0]
                    init = deepcopy(var.init)
                    FoldConstants(var.init)()
                    s = init
                yield int(s.value)
            except (AttributeError, IndexError):
                raise TransformError("Cannot statically determine size.",
                                     "" if s is None else s.coord)

    def sizeof(self):
        return reduce(lambda x, y: x * y, self.int_size())


class SymbolTable:
    def __init__(self):
        self._data = defaultdict(dict)
        self._parents = {None: None}
        self._scope = None

    def pop_scope(self):
        self._scope = self._parents[self._scope]

    def push_scope(self, new_scope, info=None):
        self._parents[new_scope] = self._scope
        self._scope = new_scope
        if info:
            self.data[new_scope] = info

    def get_or_default(self, key, scope, default):
        try:
            return self.get_info(key, scope)
        except KeyError:
            return default

    def get_info(self, key, scope):
        while scope:
            if key in self._data[scope]:
                return self._data[scope][key]
            else:
                scope = self._parents[scope]
        if key in self._data[scope]:
            return self._data[scope][key]
        else:
            raise KeyError(key)

    def lookup(self, key):
        result = (v.get(key, None) for v in self._data.values())
        return (entry for entry in result if entry)

    def __contains__(self, item):
        return any(True for _ in self.lookup(item))

    def __getitem__(self, key):
        return self.get_info(key, self._scope)

    def __setitem__(self, key, val):
        self._data[self._scope][key] = val

    def __repr__(self):
        return str({str(k): v for k, v in self._data.items()}) + \
            str({str(k): str(v) for k, v in self._parents.items()})


@track_scope
class SymbolTableBuilder(NodeVisitor):

    def __init__(self):
        self._visit_paramlist = False
        self._reset()
        self._init = None

    def make_table(self, node):
        self.symbol_table = SymbolTable()
        self.visit(node)
        return self.symbol_table

    def _reset(self):
        self._dim = []

    def visit_Compound(self, node):
        self.symbol_table.push_scope(self.scope)
        self.generic_visit(node)

    def visit_ParamList(self, node):
        self._visit_paramlist = True
        self.symbol_table.push_scope(self.scope)
        self.generic_visit(node)
        self._visit_paramlist = False

    def pop_scope(self):
        self.symbol_table.pop_scope()

    def visit_ArrayDecl(self, node):
        self._dim.append(node.dim)
        self.generic_visit(node)

    def visit_Decl(self, node):
        self._init = node.init
        self.generic_visit(node)
        self._init = None

    def visit_TypeDecl(self, node):
        self.symbol_table[node.declname] = TableEntry(
            belongs_to=self.symbol_table,
            decl=node,
            scope=self.scope,
            size=self._dim,
            type=node.type,
            is_param=self._visit_paramlist,
            init=self._init
        )
        self._reset()


@track_scope
@track_parent
class WithoutArrays(Transformation):
    """Splits arrays into separate variables.

    Array lookups `x[i]` are replaced by calls to a getter: `getx(i)`, or by a
    variable reference when all indices are constants.

    Array assignments (e.g. x[i] = v) are replaced by calls to a setter:
    `setx(i, v)`.
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.used = set()
        self.accessors = set()
        self.new_code = []
        self.id_finder = GetId()

    def _make_accessors(self, info):
        """Build get() and set() function based on info.
        """
        name = self._array_name(info)
        fname = self._make_getter_name(info)
        size = info.sizeof()
        params = [("int", f"x{i}") for i in range(len(info.size))]
        mults = [
            BinaryOp("*", a, ID(b[1]))
            for a, b in zip(info.size[1:], params[:-1])]

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

    def _array_name(self, info):
        scope_slug = ""
        if info.scope:
            scope = str(info.scope)
            scope_slug = scope[scope.find(":"):].replace(":", "_")
        return f"{info.decl.declname}{scope_slug}"

    def visit_Decl(self, node):
        def flatten_init(init: InitList):
            for expr in init.exprs:
                if isinstance(expr, InitList):
                    yield from flatten_init(expr)
                else:
                    yield expr

        if type(node.type) == ArrayDecl:
            info = self._info.get_info(node.name, self.scope)
            if not info.is_param:
                new_name = self._array_name(info)
                init = list(flatten_init(node.init)) if node.init else None

                def do_decl(i):
                    new_info = deepcopy(info)
                    new_info.decl.declname = f"{new_name}_{i}"
                    try:
                        expr = init[i] if init else None
                    except IndexError:
                        raise TransformError(
                                "Unsupported array initializer.",
                                node.init.coord)
                    return make_decl(
                        new_info.decl.declname, new_info.decl, expr)

                self.delete(node)
                decls = (do_decl(i) for i in range(info.sizeof()))
                self.new_code += decls
                self._make_accessors(info)
        self.generic_visit(node)

    def visit_FileAST(self, node):
        self._info = SymbolTableBuilder().make_table(node)
        self.generic_visit(node)
        self.ast.ext.extend(self.new_code)
        self.ast.ext.extend(
            x for x in self.accessors if x.decl.name in self.used)
        Reorder(node).visit(node)

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        # todo warning/error if an array element is incremented/decremented
        # from within an expression.

    def visit_Assignment(self, node):
        self.generic_visit(node)
        if (
            isinstance(node.lvalue.coord, tuple) and
            node.lvalue.coord[0] == "NoArrays"
        ):
            node.lvalue.args.exprs.append(node.rvalue)
            node.lvalue.name.name = \
                node.lvalue.name.name.replace("get", "set", 1)
            self.replace(node, node.lvalue)
            self.used.add(node.lvalue.name.name)

    def visit_ArrayRef(self, node):
        def replace_with(n, info):
            """If the array size is statically determined,
            all indices in `n` are constants, and the number of indices
            is the same as the number of array dimensions (i.e., we are
            done with building the getter function call), then replace
            `node` with a reference to the corresponding array variable.
            Otherwise, replace `node` with `n`

            Eg.
            ```c
            int x[2][2];
            int y = x[1][0];
            int z = x[y];
            ```
            becomes
            ```c
            int x_0, x_1, x_2, x_3;
            int y = x_2; // Was: getx(1, 0)
            int z = getx(y);
            ```
            """

            if all((
                all(type(i) == Constant for i in info.size),
                all(type(i) == Constant for i in n.args.exprs),
                len(n.args.exprs) == len(info.size)
            )):
                var_stem = self._array_name(info)
                offset = sum(
                    int(a.value) * int(b.value)
                    for a, b in zip(info.size[1:], n.args.exprs[:-1]))
                offset += int(n.args.exprs[-1].value)
                self.replace(node, ID(f"{var_stem}_{offset}"))
            else:
                self.replace(node, n)

        # first, recurse into node's children
        self.generic_visit(node)
        # base case: name[subscript] where name is an ID
        if type(node.name) == ID:
            info = self._info.get_info(node.name.name, self.scope)
            fname = self._make_getter_name(info)
            _node = FuncCall(ID(fname), ExprList([]))
            _node.coord = ("NoArrays", info)
            _node.args.exprs.append(node.subscript)
            # _node = try_turn_into_id(_node, info)
            replace_with(_node, info)
            self.used.add(fname)
        # node.name (was) itself an ArrayRef & got replaced during the visit
        elif (
            isinstance(node.name.coord, tuple) and
            node.name.coord[0] == "NoArrays"
        ):
            _node = node.name
            _node.args.exprs.append(node.subscript)
            _node = replace_with(_node, node.name.coord[1])

    def _make_getter_name(self, info):
        name = f"get{self._array_name(info)}"
        while True:
            setter_name = name.replace("get", "set", 1)
            if name in self._info or setter_name in self._info:
                name = "_" + name
            else:
                break
        return name


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
