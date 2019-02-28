# dummy screensaver will set screen to black and go fullscreen if windowed


from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from multiprocessing.pool import ThreadPool
from kodi65 import addon
from kodi65 import utils
from six.moves.urllib.parse import urlparse

from common.rt_constants import Constants
from common.exceptions import AbortException, ShutdownException
from settings import Settings
from backend import backend_constants
from common.logger import Logger, Trace
from common.monitor import Monitor

import sys
import datetime
import io
import json
import os
import queue
import random
import re
import requests
import resource
import threading
import time
import traceback
import urllib
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
import xbmcdrm
import string

addon = xbmcaddon.Addon()
logger = Logger(u'screensaver')

do_fullscreen = addon.getSetting('do_fullscreen')


class MyMonitor(Monitor):

    '''
        Create monitor that provides a means to wait on
        either an abort from Kodi or screen saver deactivate.

        Both abort and screen ScreensaverDeactivate events sets
        _shutDownEvent. External callers wait on this event.
    '''

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)

        super(MyMonitor, self).__init__()
        self._shutDownEvent = threading.Event()
        self._thread = threading.Thread(
            target=self._waitForAbortThread, name='Service Monitor')

        self._thread.start()

    def _waitForAbortThread(self):
        localLogger = self._logger.getMethodLogger(
            u'_waitForAbortThread')
        #Trace.log(localLogger.getMsgPrefix(), trace=Trace.TRACE)
        self.waitForAbort()
        self.shutDownEvent.set()
        localLogger.debug(u'SHUTDOWN', trace=Trace.TRACE)

    def onScreensaverDeactivated(self):
        self.shutDownEvent.set()

    def waitForShutdownEvent(self):
        localLogger = self._logger.getMethodLogger(
            u'waitForShutdownEvent')
        self.shutDownEvent.wait()
        localLogger.debug(u'ShutdownEvent received')
        self._thread.join(0.05)


try:
    if __name__ == '__main__':
        if do_fullscreen == 'true':
            if not xbmc.getCondVisibility("System.IsFullscreen"):
                xbmc.executebuiltin('xbmc.Action(togglefullscreen)')

    monitor = MyMonitor()
    monitor.waitForShutdownEvent()
except:
    logger.logException()
