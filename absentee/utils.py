#!/usr/bin/env python3


from io import StringIO
from pycparser.c_ast import *

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


def make_decl(name, type_, init=None):
    return Decl(
        name=name, type=type_,
        quals=[], align=[], storage=[], funcspec=[], init=init, bitsize=None)


def make_typedecl(type_, name):
    return TypeDecl(name, [], [], TypeDecl(name, [], IdentifierType([type_])))


def make_function(type_, name, params, body):
    param_list = ParamList([
        make_decl(param_name, make_typedecl(param_type, param_name))
        for param_type, param_name in params])
    fdecl = FuncDecl(param_list, TypeDecl(name, [], type_))
    decl = make_decl(name, fdecl)
    return FuncDef(decl, [], body)


def track_parent(cls):
    old_visit = getattr(cls, "generic_visit")
    setattr(cls, "parent", None)

    def generic_visit(self, node):
        oldparent = self.parent
        self.parent = node
        old_visit(self, node)
        self.parent = oldparent

    def _handle_array_attr(self, attr, node):
        if "[" not in attr:
            return attr, None, getattr(node, attr, None)
        pos = attr.find("[")
        index = int(attr[pos + 1:][:-1])
        attr = attr[:pos]
        return attr, index, getattr(node, attr, [])

    def insert_before(self, node, nodes):
        for attr, n in self.parent.children():
            if n == node:
                attr, i, array = self._handle_array_attr(attr, self.parent)
                if i is None:
                    raise TransformError(f"insert_before() on invalid node: {self.parent}")
                array = [*array[:i], *nodes, *array[i:]]
                setattr(self.parent, attr, array)

    def delete(self, node):
        self.replace(node, EmptyStatement())

    def replace(self, node, new_node):
        for attr, n in self.parent.children():
            if n == node:
                attr, i, elem = self._handle_array_attr(attr, self.parent)
                if i is None:
                    setattr(self.parent, attr, new_node)
                else:
                    elem[i] = new_node
                    setattr(self.parent, attr, elem)

    setattr(cls, "_handle_array_attr", _handle_array_attr)
    setattr(cls, "generic_visit", generic_visit)
    setattr(cls, "replace", replace)
    setattr(cls, "insert_before", insert_before)
    setattr(cls, "delete", delete)
    return cls


def track_scope(cls):
    old_visit_Compound = getattr(cls, "visit_Compound", None)
    old_visit_ParamList = getattr(cls, "visit_ParamList", None)
    pop_scope = getattr(cls, "pop_scope", None)
    setattr(cls, "scope", None)

    def _push_scope(self, node):
        old_scope, self.scope = self.scope, (node.coord if node else None)
        return old_scope

    def _visit_and_pop_scope(self, node, goto_scope):
        self.generic_visit(node)
        self.scope = goto_scope
        if pop_scope is not None:
            pop_scope(self)

    def visit_Compound(self, node):
        old_scope, self.scope = self.scope, (node.coord if node else None)
        if old_visit_Compound is not None:
            old_visit_Compound(self, node)
        _visit_and_pop_scope(self, node, old_scope)

    def visit_ParamList(self, node):
        old_scope, self.scope = self.scope, (node.coord if node else None)
        if old_visit_ParamList is not None:
            old_visit_ParamList(self, node)
        _visit_and_pop_scope(self, node, old_scope)

    setattr(cls, "visit_Compound", visit_Compound)
    return cls
