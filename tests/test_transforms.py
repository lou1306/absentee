#!/usr/bin/env python3

import unittest
from pycparser import c_parser, c_generator
from absentee.transforms import FoldConstants, AddInitializers

parser = c_parser.CParser()
cgen = c_generator.CGenerator()
ULLONG_MAX = 18446744073709551615


class TransformTestCase(unittest.TestCase):

    def _test_single(self, input_, expected_output, transform, params={}):
        ast = parser.parse(input_)
        transform(ast, params).visit(ast)
        result = cgen.visit(ast).replace("\n", "").strip()
        self.assertEqual(result, expected_output)
        self.assertEqual(result, expected_output)

    def _test_instances(self, instances, transform, params={}):
        for in_string, expected in instances:
            self._test_single(in_string, expected.strip(), transform, params)


class TestAddInitializers(TransformTestCase):
    def test_type(self):
        instances = (
            ("int main(){ int x; }", "int main(){  int x = f();}"),
            ("int x;", "int x;")
        )

        self._test_instances(instances, AddInitializers, {"int": "f"})


class TestFoldConstants(TransformTestCase):
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

        self._test_instances(instances, FoldConstants)


if __name__ == '__main__':
    unittest.main()
