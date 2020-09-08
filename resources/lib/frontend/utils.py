# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: fbacher
'''

import threading
import xbmc
import xbmcgui

from common.imports import *
from common.logger import (LazyLogger)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ReasonEvent(object):
    '''
        Provides a threading.Event with an attached reason
    '''
    TIMED_OUT = 'timed out'
    CLEARED = 'Cleared'
    KODI_ABORT = 'Kodi Abort'
    SHUTDOWN = 'Shutdown'
    RUN_STATE_CHANGE = 'Run State Changed'

    def __init__(self):
        self._event = threading.Event()
        self._reason: Union[str, None] = None

    def getReason(self):
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
