'''
Created on Feb 24, 2019

@author: fbacher
'''
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
from settings import Settings
from backend import backend_constants
import threading
import time


def Timer(*args, **kwargs):
    Timer._logger = Logger(u'kodi_thread.Timer')

    Timer._logger.enter()
    timer = _Timer(args, *kwargs)
    return timer


class _Timer(threading._Timer):
    def __init__(self, interval, function, args=[], kwargs={}):
        self._logger = Logger(self.__class__.__name__)

        ShutdownListener.register(self)
        timer = super(_Timer, self).__init__(interval, function, args, kwargs)
        return timer

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        localLogger.enter()
        ShutdownListener.remove()
        super(_Timer, self).run()

    def cancel(self):
        localLogger = self._logger.getMethodLogger(u'cancel')
        localLogger.enter()
        ShutdownListener.remove()
        super(_Timer, self).cancel()


_sleepLock = threading.RLock()
_sleepers = []


def sleep(seconds):
    event = threading.Event()
    with _sleepLock:
        _sleepers.append(event)
    event.wait(seconds)
    with _sleepLock:
        _sleepers.remove(event)
    Monitor.throwExceptionIfShutdownRequested()


class ShutdownListener():
    _listenerLock = threading.RLock()
    _listeners = []

    def register(self, listener):
        localLogger = self._logger.getMethodLogger(u'register')
        localLogger.enter()
        with ShutdownListener._listenerLock:
            ShutdownListener._listeners.append(listener)

    def unRegister(self, listener):
        localLogger = self._logger.getMethodLogger(u'unRegister')
        localLogger.enter()
        with ShutdownListener._listenerLock:
            ShutdownListener._listeners.remove(listener)

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'.__init__')
        localLogger.enter()
        Monitor.waitForShutdown()
        with _sleepLock:
            for sleeper in _sleepers:
                sleeper.cancel()

        with ShutdownListener._listenerLock:
            for listener in ShutdownListener._listeners:
                listener.cancel()
