# -*- coding: utf-8 -*-

"""
Created on Apr 17, 2019

@author: Frank Feuerbacher
"""

import unittest

import sys
import traceback


from common.logger import *
import common.logger as logger

lazy_module_logger = BasicLogger.get_module_logger(module_path=__file__)


class BasicLoggerTestCase(unittest.TestCase):
    def setUp(self):
        self._logger = BasicLogger.get_module_logger().getChild(self.__class__.__name__)

    def tearDown(self):
        pass

    def test_capture_stack(self):
        trace_back, thread_name = self._logger.capture_stack()
        assert trace_back is not None
        current_frame = trace_back[-1]
        assert current_frame[2] == 'test_capture_stack'
        # Checking line number is too damn fragile.If we have correct
        # thread and method, that is good enough.

        assert thread_name == 'MainThread'

    def test_static_log_exception(self):
        try:
            raise ZeroDivisionError
        except ZeroDivisionError:
            self._logger.log_exception(msg='')

        pass

    def test_exception(self):
        try:
            raise ZeroDivisionError
        except ZeroDivisionError:
            self._logger.exception(msg='')

    def test_log_stack(self):
        pass

    def test_dump_stack(self):
        pass
