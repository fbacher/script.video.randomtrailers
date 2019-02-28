# monitors onScreensaverActivated event and checks guisettings.xml for plugin.video.randomtrailers.
# if found it will launch plugin.video.randomtrailers which will show trailers.
# this gets around Kodi killing a screensaver 5 seconds after
# onScreensaverDeactivate

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
from common.rt_constants import Movie
from common.logger import Logger, Trace, logEntry, logExit, logEntryExit
from common.debug_utils import Debug
from common.exceptions import AbortException, ShutdownException
from common.monitor import Monitor
import common.kodi_thread as kodi_thread
from settings import Settings
from backend import backend_constants

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


logger = Logger(u'service')


def isTrailerScreensaver():
    pguisettings = xbmc.translatePath(os.path.join(
        u'special://userdata', 'guisettings.xml')).decode(u'utf-8')
    logger.debug(pguisettings)
    name = '<mode>script.video.randomtrailers</mode>'
    if name in file(pguisettings, "r").read():
        logger.debug(u'found script.video.randomtrailers in guisettings.html')
        return True
    else:
        logger.debug(
            u'did not find script.video.randomtrailers in guisettings.html')
        return False


class MyMonitor(Monitor):

    _singletonInstance = None

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)

        super(MyMonitor, self).__init__()
        self._shutDownEvent = threading.Event()
        self._thread = threading.Thread(
            target=self._waitForAbortThread, name='Service Monitor')
        self._logger = Logger(self.__class__.__name__)

        self._thread.start()

    @staticmethod
    def getInstance():
        if MyMonitor._singleton is None:
            MyMonitor._singleton = MyMonitor()

        return MyMonitor._singleton

    def onScreensaverActivated(self):
        if isTrailerScreensaver():
            xbmc.executebuiltin(
                'xbmc.RunScript("script.video.randomtrailers","no_genre")')

    def _waitForAbortThread(self):
        localLogger = self._logger.getMethodLogger(
            u'_waitForAbortThread')
        #Trace.log(localLogger.getMsgPrefix(), trace=Trace.TRACE)
        self.waitForAbort()
        self.shutDownEvent.set()
        localLogger.debug(u'ABORT', trace=Trace.TRACE)

    def waitForShutdownEvent(self):
        localLogger = self._logger.getMethodLogger(
            u'waitForShutdownEvent')
        self.shutDownEvent.wait()
        localLogger.debug(u'SHUTDOWN received')
        self._thread.join(0.01)  # Won't join if abort hasn't occurred


try:
    logger.enter()
    logger.debug(u'randomtrailers.service waiting for shutdown')
    MyMonitor.getInstance().waitForShutdown()
    logger.debug(u'randomtrailers.service stopping Player')
    xbmc.Player().stop
    logger.exit()
except:
    logger.logException()
