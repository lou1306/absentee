#!/usr/bin/env python3


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
                if "[" in attr:
                    attr, i, array = self._handle_array_attr(attr, self.parent)
                    array = [*array[:i], *nodes, *array[i:]]
                    setattr(self.parent, attr, array)
            else:
                continue

    def delete(self, node):
        self.replace(node, None)

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
    # result = ScopeInfo()
    old_visit = getattr(cls, "visit_Compound", None)
    setattr(cls, "scope", None)

    def visit_Compound(self, node):
        old_scope = self.scope
        self.scope = node.coord
        if old_visit is not None:
            old_visit(self, node)
        self.generic_visit(node)
        self.scope = old_scope

    setattr(cls, "visit_Compound", visit_Compound)
    return cls
