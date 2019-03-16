'''
Created on Feb 19, 2019

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
from common.exceptions import AbortException, ShutdownException
from settings import Settings
from backend import backend_constants
from common.logger import Logger, Trace

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


class Monitor(xbmc.Monitor):

    _singleton = None

    def __init__(self):
        super(Monitor, self).__init__(args=(), kwargs=None)
        self._logger = Logger(self.__class__.__name__)
        self._screenSaverListeners = []
        self._settingsChangedListeners = []
        self._shutdownListeners = []
        self._abortListeners = []

        #
        # These events are prioritized:
        #
        # _waitForAbortThread waits until a Kodi Abort occurs,
        # once it happens it will set the lower priority events:
        # shutDownEvent, startupCompleteEvent, pluginExitEvent and
        # screenSaverEvent. This is done so that anything waiting on
        # them will stop waiting. They should be sure to check why they
        # woke up, in case they need to take more drastic action.
        #
        # The same scheme is used for _waitForShutdownThread,
        # waitForStartupComplete,
        # onScreensaverActivated, onScreensaverDeactivated

        self.shutDownEvent = threading.Event()
        self.startupCompleteEvent = threading.Event()
        self.pluginExitEvent = threading.Event()
        self.screenSaverEvent = threading.Event()

        self._shutdownThread = threading.Thread(
            target=self._waitForShutdownThread, name='Monitor.waitForShutdown')

        self._abortThread = threading.Thread(
            target=self._waitForAbortThread, name='Monitor.waitForAbort')
        self._shutdownThread.start()
        self._abortThread.start()

    def shutdownThread(self):
        finished = True
        while not finished:
            finished = True
            if self._abortThread.isAlive():
                finished = False
                self._abortThread.join(0.1)
            if self._shutdownThread.isAlive():
                finished = False
                self._shutdownThread.join(0.1)

    @staticmethod
    def getInstance():
        if Monitor._singleton is None:
            Monitor._singleton = Monitor()

        return Monitor._singleton

    def _waitForShutdownThread(self):
        localLogger = self._logger.getMethodLogger(u'_waitForShutdownThread')
        Trace.log(localLogger.getMsgPrefix(), trace=Trace.TRACE_MONITOR)
        self.shutDownEvent.wait()
        localLogger.debug(u'got shutDownEvent')
        Trace.log(localLogger.getMsgPrefix(),
                  u'got shutDownEvent', trace=Trace.TRACE_MONITOR)

        # Force wakeup
        self.startupCompleteEvent.set()
        localLogger.debug(u'set startupCompleteEvent')
        Trace.log(localLogger.getMsgPrefix(),
                  u'set startupCompleteEvent', trace=Trace.TRACE_MONITOR)

        Trace.log(localLogger.getMsgPrefix(),
                  u'SHUTDOWN', trace=Trace.TRACE_MONITOR)

    def _waitForAbortThread(self):
        localLogger = self._logger.getMethodLogger(u'_waitForAbortThread')
        abort = self.waitForAbort(1)
        while not abort:
            if self.shutDownEvent.isSet():
                break
            abort = self.waitForAbort(1)

        Trace.log(localLogger.getMsgPrefix(), u'waitForAbort:', abort, u'shutDownEvent:',
                  self.shutDownEvent.isSet(), trace=Trace.TRACE_MONITOR)
        Trace.log(localLogger.getMsgPrefix(),
                  u'setting shutDownEvent', trace=Trace.TRACE_MONITOR)
        self.shutDownEvent.set()
        Trace.log(localLogger.getMsgPrefix(),
                  u'joining with self._shutdownThread', trace=Trace.TRACE_MONITOR)
        if self._shutdownThread.isAlive():
            self._shutdownThread.join(0.25)
        Trace.log(localLogger.getMsgPrefix(),
                  u'Joined with _shutdownThread', Trace.TRACE_MONITOR)
        localLogger.exit()

    def registerScreensaverListener(self, listener):
        self._screenSaverListeners.append(listener)

    def unRegisterScreensaverListener(self, listener):
        self._screenSaverListeners.remove(listener)

    def registerSettingsChangedListener(self, listener):
        self._settingsChangedListeners.append(listener)

    def unRegisterSettingsChangedListener(self, listener):
        self._settingsChangedListeners.remove(listener)

    def registerShutdownListener(self, listener):
        self._shutdownListeners.append(listener)

    def unRegisterShutdownListener(self, listener):
        self._shutdownListeners.remove(listener)

    def registerAbortListener(self, listener):
        self._abortListeners.append(listener)

    def unRegisterAbortListener(self, listener):
        self._abortListeners.remove(listener)

    def informAbortListeners(self, activated=True):
        for listener in self. _abortListeners:
            listener.onAbortEvent()

    def informShutdownListeners(self, activated=True):
        for listener in self._shutdownListeners:
            listener.onShutdownEvent()

    def informScreensaverListeners(self, activated=True):
        for listener in self._screenSaverListeners:
            if activated:
                listener.onScreensaverActivated()
            else:
                listener.onScreensaverDeactivated()

    def onSettingsChanged(self):
        # type: () -> None
        """
        onSettingsChanged method. 

        Will be called when addon settings are changed 
        """
        return super(Monitor, self).onSettingsChanged()

    def onScreensaverActivated(self):
        # type: () -> None
        """
        onScreensaverActivated method. 

        Will be called when screensaver kicks in 
        """
        self.informScreensaverListeners(activated=True)

        return super(Monitor, self).onScreensaverActivated()

    def onScreensaverDeactivated(self):
        # type: () -> None
        """
        onScreensaverDeactivated method. 

        Will be called when screensaver goes off 
        """
        self.informScreensaverListeners(activated=False)

        return super(Monitor, self).onScreensaverDeactivated()

    def onDPMSActivated(self):
        # type: () -> None
        """
        onDPMSActivated method. 

        Will be called when energysaving/DPMS gets active 
        """
        return super(Monitor, self).onDPMSActivated()

    def onDPMSDeactivated(self):
        # type: () -> None
        """
        onDPMSDeactivated method. 

        Will be called when energysaving/DPMS is turned off 
        """
        return super(Monitor, self).onDPMSDeactivated()

    def onScanStarted(self, library):
        # type: (str_type) -> None
        """
        onScanStarted method. 

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library is being scanned

        New function added.
        """
        return super(Monitor, self).onScanStarted(library)

    def onScanFinished(self, library):
        # type: (str_type) -> None
        """
        onScanFinished method. 

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library has been scanned

        New function added.
        """
        return super(Monitor, self).onScanFinished(library)

    def onCleanStarted(self, library):
        # type: (str_type) -> None
        """
        onCleanStarted method.

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library has been cleaned

        New function added.
        """
        return super(Monitor, self).onCleanStarted(library)

    def onCleanFinished(self, library):
        # type: (str_type) -> None
        """
        onCleanFinished method. 

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library has been finished

        New function added.
        """
        return super(Monitor, self).onCleanFinished(library)

    def onNotification(self, sender, method, data):
        # type: (str_type, str_type, str_type) -> None
        """
        onNotification method. 

        :param sender: Sender of the notification 
        :param method: Name of the notification 
        :param data: JSON-encoded data of the notification

        Will be called when Kodi receives or sends a notification

        New function added.
        """
        return super(Monitor, self).onNotification(sender, method, data)

    def waitForAbort(self, timeout=None):
        # type: (float) -> bool
        """
        Wait for Abort 

        Block until abort is requested, or until timeout occurs. If an abort
        requested have already been made, return immediately.

        :param timeout: [opt] float - timeout in seconds. Default: no timeout.
        :return: True when abort have been requested,
            False if a timeout is given and the operation times out.

        New function added. 
        """
        if timeout is None:
            abort = super(Monitor, self).waitForAbort()
        # Appears to be bug in waitForAbort(0), waits forever
        elif timeout == 0:
            abort = self.abortRequested()
        else:
            abort = super(Monitor, self).waitForAbort(float(timeout))
        if abort:
            localLogger = self._logger.getMethodLogger(u'waitForAbort')
            Trace.log(localLogger.getMsgPrefix(),
                      u'SYSTEM ABORT received', trace=Trace.TRACE_MONITOR)

    def abortRequested(self):
        # type: () -> bool
        """
        Returns True if abort has been requested. 

        :return: True if requested

        New function added. 
        """
        return super(Monitor, self).abortRequested()

    def shutDownRequested(self):
        localLogger = self._logger.getMethodLogger(u'shutDownRequested')
        self.shutDownEvent.set()
        Trace.log(localLogger.getMsgPrefix(),
                  u'shutDownEvent set', trace=Trace.TRACE_MONITOR)
        if self._abortThread.isAlive():
            self._abortThread.join(0.1)
            if not self._abortThread.isAlive():
                Trace.log(localLogger.getMsgPrefix(),
                          u'Joined with _abortThread', trace=Trace.TRACE_MONITOR)

    def isShutdownRequested(self):
        return self.shutDownEvent.isSet()

    def waitForShutdown(self, timeout=None):
        #localLogger = self._logger.getMethodLogger(u'waitForShutdown')
        shutdown = self.shutDownEvent.wait(timeout=timeout)
        #localLogger.debug(u'waitForShutdown:', result)
        if shutdown:
            localLogger = self._logger.getMethodLogger(u'waitForShutdown')
            Trace.log(localLogger.getMsgPrefix(),
                      u'Application SHUTDOWN received', trace=Trace.TRACE_MONITOR)
        return shutdown

    def setStartupComplete(self):
        localLogger = self._logger.getMethodLogger(u'setStartupComplete')
        self.startupCompleteEvent.set()
        Trace.log(localLogger.getMsgPrefix(),
                  u'startupCompleteEvent set', trace=Trace.TRACE_MONITOR)

    def isStartupComplete(self):
        return self.startupCompleteEvent.isSet()

    def waitForStartupComplete(self, timeout=None):
        state = self.startupCompleteEvent.wait(timeout=timeout)
        if state:
            localLogger = self._logger.getMethodLogger(
                u'waitForStartupComplete')
            Trace.log(localLogger.getMsgPrefix(),
                      u'startupCompleteEvent was set', trace=Trace.TRACE_MONITOR)

    @staticmethod
    def throwExceptionIfAbortRequested(timeout=0):
        if Monitor.getInstance().waitForAbort(timeout=timeout):
            localLogger = Monitor.getInstance()._logger.getMethodLogger(
                u'throwExceptionIfAbortRequested')
            Trace.log(localLogger.getMsgPrefix(),
                      u'waitForAbort was set', trace=Trace.TRACE_MONITOR)
            raise AbortException()

    @staticmethod
    def throwExceptionIfShutdownRequested(timeout=0):
        if Monitor.getInstance().waitForShutdown(timeout=timeout):
            localLogger = Monitor.getInstance()._logger.getMethodLogger(
                u'throwExceptoinIfShutdownRequested')
            Trace.log(localLogger.getMsgPrefix(),
                      u'waitForShutdown was set', trace=Trace.TRACE_MONITOR)
            raise ShutdownException()
