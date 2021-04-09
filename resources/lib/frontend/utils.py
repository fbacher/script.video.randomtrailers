# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: fbacher
'''

import threading

from common.imports import *
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ReasonEvent:
    '''
        Provides a threading.Event with an attached reason
    '''
    TIMED_OUT: Final[str] = 'timed out'
    CLEARED: Final[str] = 'Cleared'
    KODI_ABORT: Final[str] = 'Kodi Abort'
    SHUTDOWN: Final[str] = 'Shutdown'
    RUN_STATE_CHANGE: Final[str] = 'Run State Changed'

    def __init__(self):
        self._event = threading.Event()
        self._reason: Union[str, None] = None

    def get_reason(self):
        return self._reason

    def set(self, reason):
        self._reason = reason
        self._event.set()

    def clear(self):
        self._reason = ReasonEvent.CLEARED
        self._event.clear()

    def wait(self, timeout=None):
        self._reason = ReasonEvent.TIMED_OUT
        self._event.wait(timeout)
