#!/usr/bin/env python3

from dataclasses import dataclass
from typing import List
from functools import reduce

from pycparser.c_ast import NodeVisitor, Node

from error import TransformError
from utils import track_scope


@dataclass
class TableEntry:
    decl: Node
    scope: Node
    type: Node
    size: List[Node]

    def int_size(self):
        for s in self.size:
            try:
                yield int(s.value)
            except AttributeError:
                raise TransformError("Cannot statically determine size.",
                                     s.coord)

    def sizeof(self):
        return reduce(lambda x, y: x * y, self.int_size())


class SymbolTable:
    def __init__(self):
        self._data = {None: {}}
        self._parents = {None: None}
        self._scope = None

    def pop_scope(self):
        self._scope = self._parents[self._scope]

    def push_scope(self, new_scope, info=None):
        self._data[new_scope] = info or {}
        self._parents[new_scope] = self._scope
        self._scope = new_scope

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
        self._reset()

    def make_table(self, node):
        self.symbol_table = SymbolTable()
        self.visit(node)
        return self.symbol_table

    def _reset(self):
        self._dim = []

    def visit_Compound(self, node):
        self.symbol_table.push_scope(self.scope)

    def visit_ArrayDecl(self, node):
        self._dim.append(node.dim)
        self.generic_visit(node)

    def visit_TypeDecl(self, node):
        # if self._dim:
        self.symbol_table[node.declname] = TableEntry(
            decl=node,
            scope=self.scope,
            size=self._dim,
            type=node.type,
        )
        self._reset()