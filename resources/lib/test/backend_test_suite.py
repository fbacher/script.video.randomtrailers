# -*- coding: utf-8 -*-
"""
Created on Aug 18, 2019

@author: Frank Feuerbacher
"""
import unittest
import sys

from common.imports import *
from test.common.test_logger import (LazyLoggerTestCase)


class BackendTestSuite(unittest.TestSuite):
    def __init__(self):
        suite = unittest.makeSuite(LazyLoggerTestCase, 'test')

        super().__init__(suite)

    @staticmethod
    def run_suite():
        runner = unittest.TextTestRunner(stream=sys.stderr,
                                         descriptions=True, verbosity=1,
                                         failfast=False, buffer=False,
                                         resultclass=None)
        runner.run(BackendTestSuite())
