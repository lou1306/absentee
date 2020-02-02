#!/usr/bin/env python3

import unittest
from pycparser import c_parser, c_generator
from absentee.transforms import *

parser = c_parser.CParser()
cgen = c_generator.CGenerator()
ULLONG_MAX = 18446744073709551615


class TransformTestCase(unittest.TestCase):

    def _test_single(self, input_, expected_output, transform, params={}):
        ast = parser.parse(input_)
        transform(ast, params).visit(ast)
        result = cgen.visit(ast).replace("\n", "").strip()
        self.assertEqual(result, expected_output)

    def _test_instances(self, instances, transform, params={}):
        for in_, expected in instances:
            self._test_single(in_, expected, transform, params)


class TestInitialize(TransformTestCase):
    def test_type(self):
        instances = (
            ("int main(){ int x; }", "int main(){  int x = f();}"),
            ("int x;", "int x;")
        )

        self._test_instances(instances, Initialize, {"int": "f"})


class TestConstantFolding(TransformTestCase):
    def test_axioms(self):
        instances = (
            # Commutative axioms
            ("int b = a * 0;", "int b = 0;"),
            ("int b = 0 * a;", "int b = 0;"),
            ("int b = a + 0;", "int b = a;"),
            ("int b = 0 + a;", "int b = a;"),
            ("int b = a - 0;", "int b = a;"),
            ("int b = 0 - a;", "int b = a;"),
            ("int b = a * 1;", "int b = a;"),
            ("int b = 1 * a;", "int b = a;"),
            ("int b = -1 * a;", "int b = -a;"),
            ("int b = a * -1;", "int b = -a;"),
            # Non-commutative axioms
            ("int b = 0 / a;", "int b = 0;"),
            ("int b = 0 % a;", "int b = 0;"),
            ("int b = 0 << a;", "int b = 0;"),
            ("int b = 0 >> a;", "int b = 0;"),
            ("int b = a << 0;", "int b = a;"),
            ("int b = a >> 0;", "int b = a;"),
            ("int b = a / 1;", "int b = a;"),
            ("int b = a / -1;", "int b = -a;"),
            ("int b = a % 1;", "int b = 0;"),
            ("int b = a % -1;", "int b = 0;"),
            # Stay unopinionated about invalid operations
            ("int b = a / 0;", "int b = a / 0;"),
            ("int b = a % 0;", "int b = a % 0;"),
            # Do not fold if the result is noT representable
            (f"int a = {ULLONG_MAX} * 2;", f"int a = {ULLONG_MAX} * 2;")
        )

        self._test_instances(instances, ConstantFolding)


if __name__ == '__main__':
    unittest.main()
