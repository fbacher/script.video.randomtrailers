# -*- coding: utf-8 -*-
"""
Created on Aug 18, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import unittest
import sys
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
