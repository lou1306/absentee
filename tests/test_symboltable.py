#!/usr/bin/env python3

import unittest
from absentee.symboltable import WithoutArrays
from .test_transforms import TransformTestCase


class TestWithoutArrays(TransformTestCase):
    def test_1d(self):
        instances = (
            ("int arr[2];", "int arr_0;int arr_1;"),
            ("int arr[2] = {0, 1};", "int arr_0 = 0;int arr_1 = 1;"),
        )
        self._test_instances(instances, WithoutArrays)

    def test_2d(self):
        instances = (
            ("int arr[2][2];", "int arr_0;int arr_1;int arr_2;int arr_3;"),
            ("int arr[2][2] = { {0, 1}, {2, 3} };",
             "int arr_0 = 0;int arr_1 = 1;int arr_2 = 2;int arr_3 = 3;"),
        )
        self._test_instances(instances, WithoutArrays)


if __name__ == '__main__':
    unittest.main()
