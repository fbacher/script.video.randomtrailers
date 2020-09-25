# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher

"""

from common.imports import *

import copy
import datetime
import os
import threading

import xbmc

from common.constants import Constants
from common.critical_settings import CriticalSettings
from common.exceptions import AbortException
from common.logger import (Logger, LazyLogger, Trace)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection
# Annotator,Annotator,Annotator,Annotator,PyArgumentList,PyArgumentList
# noinspection Annotator
class Monitor(xbmc.Monitor):
    """
        Provides a number of customizations to xbmc.monitor
    """
    startup_complete_event = None
    _monitor_changes_in_settings_thread = None
    _logger = None
    _instance = None
    _xbmc_monitor = None
    _screen_saver_listeners = None
    _screen_saver_listener_lock = None
    _settings_changed_listeners = None
    _settings_changed_listener_lock = None
    _abort_listeners = None
    _abort_listener_lock = None
    _abort_listeners_informed = False
    _abort_received = None

    def __init__(self):
        super().__init__()

    @classmethod
    def class_init(cls):
        # type;() -> None
        """

        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)
            cls._instance = Monitor()
            # Weird problems with recursion if we make requests to the super

            cls._xbmc_monitor = xbmc.Monitor()
            cls._screen_saver_listeners = []
            cls._screen_saver_listener_lock = threading.RLock()
            cls._settings_changed_listeners = []
            cls._settings_changed_listener_lock = threading.RLock()
            cls._abort_listeners = []
            cls._abort_listener_lock = threading.RLock()
            cls._abort_listeners_informed = False
            cls._abort_received = threading.Event()

            #
            # These events are prioritized:
            #
            # _wait_for_abort_thread waits until a Kodi Abort occurs,
            # once it happens it will set the lower priority event:
            # startup_complete_event. This is done so that
            # anything waiting on
            # them will stop waiting. They should be sure to check why they
            # woke up, in case they need to take more drastic action.
            #
            # The same scheme is used for wait_for_startup_complete,
            # onScreensaverActivated, onScreensaverDeactivated

            cls.startup_complete_event = threading.Event()

            # noinspection PyTypeChecker
            cls._monitor_changes_in_settings_thread = threading.Thread(
                target=cls._monitor_changes_in_settings,
                name='monitorSettingsChanges')
            cls._monitor_changes_in_settings_thread.start()

    @classmethod
    def _monitor_changes_in_settings(cls):
        # type: () -> None
        """

        :return:
        """
        start_time = datetime.datetime.now()
        settings_path = os.path.join(
            Constants.FRONTEND_DATA_PATH, 'settings.xml')

        # It seems that if multiple xbmc.WaitForAborts are pending, xbmc
        # Does not inform all of them when an abort occurs. So, instead
        # of waiting for 60 seconds per iteration, we wait 0.1 seconds
        # and act when 600 calls has been made. Not exactly 60 seconds, but
        # close enough for this

        iterations = 600
        while not cls._wait_for_abort(timeout=0.1):
            # noinspection PyRedundantParentheses
            iterations -= 1
            if iterations < 0:
                iterations = 600
                try:
                    fileStat = os.stat(settings_path)
                    modTime = datetime.datetime.fromtimestamp(
                        fileStat.st_mtime)
                except Exception as e:
                    cls._logger.debug("Failed to read settings.xml")
                    modTime = start_time

                if modTime > start_time:
                    start_time = datetime.datetime.now()
                    if cls._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                        cls._logger.debug_verbose('Settings Changed!')
                    cls._instance.onSettingsChanged()
                    # Here we go again

    @classmethod
    def register_screensaver_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._screen_saver_listener_lock:
            if not cls.is_abort_requested():
                cls._screen_saver_listeners.append(listener)

    @classmethod
    def unregister_screensaver_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._screen_saver_listener_lock:
            try:
                cls._screen_saver_listeners.remove(listener)
            except ValueError:
                pass

    @classmethod
    def register_settings_changed_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._settings_changed_listener_lock:
            if not cls.is_abort_requested():
                cls._settings_changed_listeners.append(listener)

    @classmethod
    def unregister_settings_changed_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._settings_changed_listener_lock:
            try:
                cls._settings_changed_listeners.remove(listener)
            except ValueError:
                pass

    @classmethod
    def register_abort_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._abort_listener_lock:
            if not cls.is_abort_requested():
                cls._abort_listeners.append(listener)
            else:
                raise AbortException()

    @classmethod
    def unregister_abort_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._abort_listener_lock:
            try:
                cls._abort_listeners.remove(listener)
            except ValueError:
                pass

    @classmethod
    def _inform_abort_listeners(cls):
        # type: () ->None
        """

        :return:
        """
        with cls._abort_listener_lock:
            if cls._abort_listeners_informed:
                return
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                cls._logger.enter()
            listeners_copy = copy.copy(cls._abort_listeners)
            del cls._abort_listeners[:]  # Unregister all
            cls._abort_listeners_informed = True

        for listener in listeners_copy:
            # noinspection PyTypeChecker
            thread = threading.Thread(
                target=listener, name='Monitor._inform_abort_listeners')
            thread.start()

        # cls._inform_settings_changed_listeners()
        cls.startup_complete_event.set()
        #cls._inform_screensaver_listeners()

        with cls._settings_changed_listener_lock:
            del cls._settings_changed_listeners[:]

        with cls._screen_saver_listener_lock:
            del cls._screen_saver_listeners[:]

        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            xbmc.sleep(250)
            from common.debug_utils import Debug
            Debug.dump_all_threads()
            xbmc.sleep(250)
            Debug.dump_all_threads()

    @classmethod
    def _inform_settings_changed_listeners(cls):
        # type: () -> None
        """

        :return:
        """
        with cls._settings_changed_listener_lock:
            listeners = copy.copy(cls._settings_changed_listeners)
            if cls.is_abort_requested():
                del cls._settings_changed_listeners[:]

        for listener in listeners:
            if cls._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                cls._logger.debug_verbose('Notifying listener:', listener.__name__)
            thread = threading.Thread(
                target=listener, name='Monitor.inform:' + listener.__name__)
            thread.start()

    @classmethod
    def _inform_screensaver_listeners(cls, activated=True):
        # type () -> None
        """

        :param activated:
        :return:
        """
        with cls._screen_saver_listener_lock:
            listeners_copy = copy.copy(cls._screen_saver_listeners)
            if cls.is_abort_requested():
                del cls._screen_saver_listeners[:]

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            cls._logger.debug_verbose(f'Screensaver activated: {activated}')
        for listener in listeners_copy:
            # noinspection PyTypeChecker
            thread = threading.Thread(
                target=listener, name='Monitor._inform_screensaver_listeners',
                args=(activated,))
            thread.start()

    def onSettingsChanged(self):
        # type: () -> None
        """
        on_settings_changed method.

        Will be called when addon settings are changed

        :return:
        """
        type(self)._inform_settings_changed_listeners()

    def onScreensaverActivated(self):
        # type: () -> None
        """
        onScreensaverActivated method.

        Will be called when screensaver kicks in

        :return:
        """
        type(self)._inform_screensaver_listeners(activated=True)

        # return super().onScreensaverActivated()

    def onScreensaverDeactivated(self):
        # type: () -> None
        """
        onScreensaverDeactivated method.

        Will be called when screensaver goes off

        :return:
        """
        type(self)._inform_screensaver_listeners(activated=False)

        # return super().onScreensaverDeactivated()

    def onDPMSActivated(self):
        # type: () -> None
        """
        onDPMSActivated method.

        Will be called when energysaving/DPMS gets active

        :return:
        """
        # return super().onDPMSActivated()

    def onDPMSDeactivated(self):
        # type: () -> None
        """
        onDPMSDeactivated method.

        Will be called when energysaving/DPMS is turned off

        :return:
        """
        # return super().onDPMSDeactivated()

    def onScanStarted(self, library):
        # type: (str) -> None
        """
        onScanStarted method.

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library is being scanned

        New function added.

        :return:
        """
        # return super().onScanStarted(library)

    def onScanFinished(self, library):
        # type: (str) -> None
        """
        onScanFinished method.

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library has been scanned

        New function added.

        :return:
        """
        # return super().onScanFinished(library)

    def onCleanStarted(self, library):
        # type: (str) -> None
        """
        onCleanStarted method.

        :param library: Video / music as string
        :return:

        Will be called when library clean has ended and return video or music
        to indicate which library has been cleaned

        New function added.
        """
        # return super().onCleanStarted(library)

    def onCleanFinished(self, library):
        # type: (str) -> None
        """
        onCleanFinished method.

        :param library: Video / music as string
        :return:

        Will be called when library clean has ended and return video or music
        to indicate which library has been finished

        New function added.
        """
        # return super().onCleanFinished(library)

    def onNotification(self, sender, method, data):
        # type: (str, str, str) -> None
        """
        onNotification method.

        :param sender: Sender of the notification
        :param method: Name of the notification
        :param data: JSON-encoded data of the notification

        :return:

        Will be called when Kodi receives or sends a notification
        """
        # if type(self)._logger.isEnabledFor(Logger.DEBUG):
        #    type(self)._logger.debug('sender:', sender, 'method:', method)
        pass

    @classmethod
    def _wait_for_abort(cls, timeout=None):
        # type: (float) -> bool
        """
        Wait for Abort

        Block until abort is requested, or until timeout occurs. If an abort
        requested have already been made, return immediately.

        :param timeout: [opt] float - timeout in seconds.
                        if None: wait forever
                        if 0: check without wait & return
                        if > 0: wait at max wait seconds

        :return: True when abort have been requested,
            False if a timeout is given and the operation times out.

        New function added.
        """
        abort = True
        if not cls._abort_received.isSet():
            abort = False
            if timeout is None:  # Wait forever
                while not abort:
                    abort = cls._instance.waitForAbort(timeout=0.10)
            else:
                timeout_arg = float(timeout)
                if timeout_arg == 0.0:
                    timeout_arg = 0.001  # Otherwise waits forever

                abort = cls._instance.waitForAbort(timeout=timeout_arg)
            if abort:
                cls._abort_received.set()
                if cls._logger.isEnabledFor(Logger.DEBUG):
                    cls._logger.debug(
                        'SYSTEM ABORT received', trace=Trace.TRACE_MONITOR)
                cls._inform_abort_listeners()

        return abort

    def waitForAbort(self, timeout=None):
        # Provides signature of super class (xbmc.Monitor)
        abort = super().waitForAbort(timeout=timeout)
        # _wait_for_abort responsible for notifications
        return abort

    @classmethod
    def wait_for_abort(cls, timeout=None):
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
        abort = cls._abort_received.isSet()
        if not abort:
            abort = cls._instance.waitForAbort(timeout=timeout)

        return abort

    @classmethod
    def abort_requested(cls):
        cls._instance.abortRequested()

    def abortRequested(self):
        # type: () -> None
        """

        :return:
        """
        super().abortRequested()
        type(self)._abort_received.set()

    @classmethod
    def is_abort_requested(cls):
        # type: () -> bool
        """
        Returns True if abort has been requested.

        :return: True if requested

        New function added.
        """
        return cls._abort_received.isSet()

    @classmethod
    def set_startup_complete(cls):
        # type () -> None
        """

        :return:
        """
        cls.startup_complete_event.set()
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug(
                'startup_complete_event set', trace=Trace.TRACE_MONITOR)

    @classmethod
    def is_startup_complete(cls):
        # type: () -> bool
        """

        :return:
        """
        return cls.startup_complete_event.isSet()

    @classmethod
    def wait_for_startup_complete(cls, timeout=None):
        # type: (float) -> bool
        """

        :param timeout:
        :return:
        """
        is_set = False
        approximate_wait_time = 0.0
        while not is_set:
            is_set = cls.startup_complete_event.wait(tmeout=None)
            Monitor.throw_exception_if_abort_requested(timeout=0.1)
            approximate_wait_time += 0.1
            if timeout is not None and approximate_wait_time >= timeout:
                break

        return is_set

    @classmethod
    def throw_exception_if_abort_requested(cls, timeout=0):
        # type: (float) -> None
        """
         Throws an AbortException if Abort has been set within the specified
          time period.

            If timeout = 0, then immediately returns without exception if
             Abort is not set, or with an AbortException if it
             is set.
            if timeout = None, then wait forever until abort is set.
            Otherwise, wait a maximum of the specified time in seconds.
        :param timeout:
        :return:
        """
        if cls._abort_received.wait(timeout=timeout):
            raise AbortException()


# Initialize class:
#
Monitor.class_init()
