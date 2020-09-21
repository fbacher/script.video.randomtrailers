# -*- coding: utf-8 -*-

"""
Created on Apr 17, 2019

@author: Frank Feuerbacher
"""

import unittest
import os
import re
import sys
import threading
import traceback
import cStringIO

from kodi_six import xbmc, utils
from kodi65.kodiaddon import Addon

from common.constants import Constants
from common.critical_settings import CriticalSettings
from common.exceptions import AbortException
from common.imports import *
from common.logger import (LazyLogger, Trace)
import common.logger as logger

lazy_module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class LazyLoggerTestCase(unittest.TestCase):
    def setUp(self):
        self._logger = lazy_module_logger.getChild(self.__class__.__name__)

    def tearDown(self):
        pass

    def test_current_frame(self):
        frame = logger.current_frame()
        assert frame is not None
        trace_back = traceback.extract_stack(frame, 15)

        current_frame = trace_back[-1]
        assert current_frame[2] == 'test_current_frame'

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
            frame = sys._getframe(0)
            self._logger.log_exception()

        pass

    def test_exception(self):
        try:
            raise ZeroDivisionError
        except ZeroDivisionError:
            frame = sys._getframe(0)
            self._logger.exception()

    def test_log_stack(self):
        pass

    def test_dump_stack(self):
        pass
