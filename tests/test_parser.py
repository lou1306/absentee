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

    def test_simple(self):
        self._test_instances([
            ("()", [tuple()]),
            ("""("Hello" "\\"World\\" !!")""", [["Hello", """"World" !!"""]])
        ])

if __name__ == '__main__':
    unittest.main()
