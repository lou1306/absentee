#!/usr/bin/env python3

import unittest
from absentee.parser import parse_config


class ParserTestCase(unittest.TestCase):
    def _test_single(self, input_, expected):
        parsed = parse_config(input_)
        self.assertEqual(parsed, expected)

    def _test_instances(self, instances):
        for input_string, expected in instances:
            self._test_single(input_string, expected)

    def test_parser(self):
        long_sexpr = """
        ; Multiple lines
        (+ (* 1 2) 3) ; comment
        ()
        (+ "a" "b") ; comment
        """
        expected = [
            ["+", ["*", 1, 2], 3],
            tuple(),
            ["+", '"a"', '"b"']
        ]
        self._test_instances([
            ("()", [tuple()]),
            ("(1)", [[1]]),
            (
                """("Hello" "\\"World\\" !!")""",
                [['"Hello"', '''""World" !!"''']]),
            ("(+ (* 1 2) 3)", [["+", ["*", 1, 2], 3]]),
            (long_sexpr, expected)
        ])


if __name__ == '__main__':
    unittest.main()
