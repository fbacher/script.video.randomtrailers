# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher

"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import copy
import datetime
import os
import threading

from kodi_six import xbmc

from .constants import Constants
from .critical_settings import CriticalSettings
from .exceptions import AbortException, ShutdownException
from .logger import (Logger, LazyLogger, Trace)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.monitor')
else:
    module_logger = LazyLogger.get_addon_module_logger()


# noinspection
# Annotator,Annotator,Annotator,Annotator,PyArgumentList,PyArgumentList
# noinspection Annotator
class Monitor(xbmc.Monitor):
    """
        Provides a number of customizations to xbmc.monitor
    """
    startup_complete_event = None
    _monitor_changes_in_settings_thread = None
    _shutdown = False
    _shutdown_received = None
    _logger = None
    _xbmc_monitor = None
    _screen_saver_listeners = None
    _screen_saver_listener_lock = None
    _settings_changed_listeners = None
    _settings_changed_listener_lock = None
    _shutdown_listeners = None
    _shutdown_listener_lock = None
    _abort_listeners = None
    _abort_listener_lock = None
    _abort_or_shutdown_event_received = None
    _abort_received = None

    @classmethod
    def class_init_(cls):
        # type;() -> None
        """

        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)
            cls._logger.enter()
            # Weird problems with recursion if we make requests to the super

            Monitor._xbmc_monitor = xbmc.Monitor()
            _monitor_changes_in_settings_thread = None
            cls._screen_saver_listeners = []
            cls._screen_saver_listener_lock = threading.RLock()
            cls._settings_changed_listeners = []
            cls._settings_changed_listener_lock = threading.RLock()
            cls._shutdown_listeners = []
            cls._shutdown_listener_lock = threading.RLock()
            cls._abort_listeners = []
            cls._abort_listener_lock = threading.RLock()
            cls._abort_or_shutdown_event_received = threading.Event()
            cls._abort_received = threading.Event()

            #
            # These events are prioritized:
            #
            # _wait_for_abort_thread waits until a Kodi Abort occurs,
            # once it happens it will set the lower priority events:
            # shutdown_event and startup_complete_event. This is done so that
            # anything waiting on
            # them will stop waiting. They should be sure to check why they
            # woke up, in case they need to take more drastic action.
            #
            # The same scheme is used for wait_for_startup_complete,
            # onScreensaverActivated, onScreensaverDeactivated

            cls._shutdown_received = threading.Event()
            cls.startup_complete_event = threading.Event()

            # noinspection PyTypeChecker
            cls._monitor_changes_in_settings_thread = threading.Thread(
                target=cls._monitor_changes_in_settings,
                name='monitorSettingsChanges')
            cls._monitor_changes_in_settings_thread.start()

    @classmethod
    def shutdownThread(cls):
        # type: () -> None
        """

        :return:
        """
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('Trying to shutdown abort_thread')
        Monitor._shutdown = True

        finished = False
        if cls._monitor_changes_in_settings_thread.isAlive():
            cls._monitor_changes_in_settings_thread.join(0.5)

    @classmethod
    def get_instance(cls):
        # type: () -> Monitor
        """

        :return:
        """
        return cls

    @classmethod
    def _monitor_changes_in_settings(cls):
        # type: () -> None
        """

        :return:
        """
        cls._logger.enter()
        start_time = datetime.datetime.now()
        settings_path = os.path.join(
            Constants.FRONTEND_DATA_PATH, 'settings.xml')
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('settings_path:', settings_path)

        while not cls.wait_for_shutdown(timeout=60.0):
            # noinspection PyRedundantParentheses
            try:
                fileStat = os.stat(settings_path)
                modTime = datetime.datetime.fromtimestamp(
                    fileStat.st_mtime)
                if cls._logger.isEnabledFor(Logger.DEBUG):
                    cls._logger.debug('start_time:', start_time.strftime(
                        '%A, %d %B %Y %I:%M%p'), 'modTime:', modTime.strftime(
                        '%A, %d %B %Y %I:%M%p'))
            except (Exception) as e:
                cls._logger.debug("Failed to read settings.xml")
                modTime = start_time

            if modTime > start_time:
                start_time = datetime.datetime.now()
                if cls._logger.isEnabledFor(Logger.DEBUG):
                    cls._logger.debug('Settings Changed!')
                cls.onSettingsChanged()

    @classmethod
    def register_screensaver_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._screen_saver_listener_lock:
            cls._screen_saver_listeners.append(listener)

    @classmethod
    def unregister_screensaver_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._screen_saver_listener_lock:
            cls._screen_saver_listeners.remove(listener)

    @classmethod
    def register_settings_changed_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('Adding listener:', listener.__name__, '.',
                              listener.__name__)

        with cls._settings_changed_listener_lock:
            cls._settings_changed_listeners.append(listener)

    @classmethod
    def unregister_settings_changed_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._settings_changed_listener_lock:
            cls._settings_changed_listeners.remove(listener)

    @classmethod
    def register_shutdown_listener(cls, listener):
        # type: (Callable[[Union[Any, None]], Union[Any, None]]) -> None
        """

        :param listener:
        :return:
        """
        with cls._shutdown_listener_lock:
            cls._shutdown_listeners.append(listener)

    @classmethod
    def unregister_shutdown_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._shutdown_listener_lock:
            cls._shutdown_listeners.remove(listener)

    @classmethod
    def register_abort_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._abort_listener_lock:
            cls._abort_listeners.append(listener)

    @classmethod
    def unregister_abort_listener(cls, listener):
        # type: (Callable[[None], None]) -> None
        """

        :param listener:
        :return:
        """
        with cls._abort_listener_lock:
            cls._abort_listeners.remove(listener)

    @classmethod
    def inform_abort_listeners(cls):
        # type: () ->None
        """

        :return:
        """
        with cls._abort_listener_lock:
            listeners_copy = copy.copy(cls._abort_listeners)
            del cls._abort_listeners[:]

        for listener in listeners_copy:
            # noinspection PyTypeChecker
            thread = threading.Thread(
                target=listener.on_abort_event, name='Monitor.inform_abort_listeners')
            thread.start()

    @classmethod
    def inform_settings_changed_listeners(cls):
        # type: () -> None
        """

        :return:
        """
        with cls._settings_changed_listener_lock:
            listeners = copy.copy(cls._settings_changed_listeners)

        for listener in listeners:
            if cls._logger.isEnabledFor(Logger.DEBUG):
                cls._logger.debug('Notifying listener:', listener.__name__)
            thread = threading.Thread(
                target=listener, name='Monitor.inform:' + listener.__name__)
            thread.start()

    @classmethod
    def inform_shutdown_listeners(cls):
        # type: () -> None
        """

        :return:
        """
        with cls._shutdown_listener_lock:
            listeners = copy.copy(cls._shutdown_listeners)
            del cls._shutdown_listeners[:]

        # TODO: Change to not use fixed method name

        for listener in listeners:
            # noinspection PyTypeChecker
            thread = threading.Thread(
                target=listener,  # .on_shutdown_event,
                name='Monitor.inform_shutdown_listeners')
            thread.start()

    @classmethod
    def inform_screensaver_listeners(cls, activated=True):
        # type () -> None
        """

        :param activated:
        :return:
        """
        with cls._screen_saver_listener_lock:
            listeners_copy = copy.copy(cls._screen_saver_listeners)

        for listener in listeners_copy:
            # noinspection PyTypeChecker
            thread = threading.Thread(
                target=listener, name='Monitor.inform_screensaver_listeners',
                args=(activated,))
            thread.start()

    @classmethod
    def onSettingsChanged(cls):
        # type: () -> None
        """
        on_settings_changed method.

        Will be called when addon settings are changed

        :return:
        """
        cls._logger.enter()
        cls.inform_settings_changed_listeners()

    @classmethod
    def onScreensaverActivated(cls):
        # type: () -> None
        """
        onScreensaverActivated method.

        Will be called when screensaver kicks in

        :return:
        """
        cls._logger.enter()
        cls.inform_screensaver_listeners(activated=True)

        # return super().onScreensaverActivated()

    @classmethod
    def onScreensaverDeactivated(cls):
        # type: () -> None
        """
        onScreensaverDeactivated method.

        Will be called when screensaver goes off

        :return:
        """
        cls._logger.enter()
        cls.inform_screensaver_listeners(activated=False)

        # return super().onScreensaverDeactivated()

    @classmethod
    def onDPMSActivated(cls):
        # type: () -> None
        """
        onDPMSActivated method.

        Will be called when energysaving/DPMS gets active

        :return:
        """
        # return super().onDPMSActivated()

    @classmethod
    def onDPMSDeactivated(cls):
        # type: () -> None
        """
        onDPMSDeactivated method.

        Will be called when energysaving/DPMS is turned off

        :return:
        """
        # return super().onDPMSDeactivated()

    @classmethod
    def onScanStarted(cls, library):
        # type: (TextType) -> None
        """
        onScanStarted method.

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library is being scanned

        New function added.

        :return:
        """
        # return super().onScanStarted(library)

    @classmethod
    def onScanFinished(cls, library):
        # type: (TextType) -> None
        """
        onScanFinished method.

        :param library: Video / music as string

        Will be called when library clean has ended and return video or music
        to indicate which library has been scanned

        New function added.

        :return:
        """
        # return super().onScanFinished(library)

    @classmethod
    def onCleanStarted(cls, library):
        # type: (TextType) -> None
        """
        onCleanStarted method.

        :param library: Video / music as string
        :return:

        Will be called when library clean has ended and return video or music
        to indicate which library has been cleaned

        New function added.
        """
        # return super().onCleanStarted(library)

    @classmethod
    def onCleanFinished(cls, library):
        # type: (TextType) -> None
        """
        onCleanFinished method.

        :param library: Video / music as string
        :return:

        Will be called when library clean has ended and return video or music
        to indicate which library has been finished

        New function added.
        """
        # return super().onCleanFinished(library)

    @classmethod
    def onNotification(cls, sender, method, data):
        # type: (TextType, TextType, TextType) -> None
        """
        onNotification method.

        :param sender: Sender of the notification
        :param method: Name of the notification
        :param data: JSON-encoded data of the notification

        :return:

        Will be called when Kodi receives or sends a notification

        New function added.
        """
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('sender:', sender, 'method:', method)

    @classmethod
    def _waitForAbort(cls, timeout=None):
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
        abort = False
        if not cls._abort_received.isSet():
            abort = None
            if timeout is None:  # Wait forever
                finished = False
                while not finished:
                    abort = cls._xbmc_monitor().waitForAbort(timeout=0.10)
                    if abort:
                        cls._abort_or_shutdown_event_received.set()
                        cls._abort_received.set()
                        break
                    if cls._shutdown_received.isSet():
                        break

            # Appears to be bug in waitForAbort(0), waits forever
            elif timeout == 0:  # No wait
                abort = cls.is_abort_requested()
                if abort:
                    cls._set_abort_or_shutdown_event()
                    cls._abort_received.set()
            else:
                timeout_arg = float(timeout)

                # Was getting recursive calls here.Somehow.
                #abort = super().waitForAbort(timeout=timeout_arg)

                abort = cls._xbmc_monitor.waitForAbort(timeout=timeout_arg)
                if abort:
                    cls._set_abort_or_shutdown_event()
                    cls._abort_received.set()

            if abort:
                if cls._logger.isEnabledFor(Logger.DEBUG):
                    cls._logger.debug(
                        'SYSTEM ABORT received', trace=Trace.TRACE_MONITOR)

            elif cls._shutdown_received.isSet():
                if cls._logger.isEnabledFor(Logger.DEBUG):
                    cls._logger.debug('ABORT NOT received, but SHUTDOWN event already',
                                      'received', trace=Trace.TRACE_MONITOR)
            if abort:
                cls.inform_abort_listeners()

        else:
            #    return cls.is_abort_requested()
            pass

        return abort

    @classmethod
    def waitForAbort(cls, timeout=None):
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
        return cls._abort_received.wait(timeout=timeout)

    @classmethod
    def abortRequested(cls):
        # type: () -> None
        """

        :return:
        """
        super().abortRequested()

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
    def shutdown_requested(cls):
        # type: () -> None
        """
        Puts plugin into shutdown-requested state.

        :return:
        """
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.enter()
        if not cls._shutdown_received.isSet():
            cls._shutdown_received.set()
            cls._set_abort_or_shutdown_event()
            cls.inform_shutdown_listeners()
            if cls._logger.isEnabledFor(Logger.DEBUG):
                cls._logger.debug(
                    'shutdown_event set', trace=Trace.TRACE_MONITOR)

            if CriticalSettings.is_debug_enabled:
                LazyLogger.dump_stack('shutdown_requested')
        else:
            if CriticalSettings.is_debug_enabled:
                cls._logger.debug('Shutdown already set.')

    @classmethod
    def is_shutdown_requested(cls):
        # type: () -> bool
        """

        :return:
        """
        return cls._shutdown_received.isSet()

    @classmethod
    def wait_for_shutdown(cls, timeout=None):
        # type (float) -> bool
        """
            Waits a maximum of timeout seconds until shutdown (or abort) is set.
            If timeout = 0, then returns the current shutdown state.
            if timeout = None, then wait forever until shutdown (or abort) is set.
            Otherwise, wait a maximum a maximum of the specified time in seconds.

        :param timeout:
        :return:
        """

        is_set = cls._abort_or_shutdown_event_received.wait(timeout=timeout)
        return is_set

    @classmethod
    def _set_abort_or_shutdown_event(cls):
        # type: () -> None
        """

        :return:
        """

        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('Setting _abort_or_shutdown_event_received')
        cls._abort_or_shutdown_event_received.set()

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
        is_set = cls.startup_complete_event.wait(timeout=timeout)

        if is_set:
            cls._logger.debug(
                'startup_complete_event was set', trace=Trace.TRACE_MONITOR)

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

    @classmethod
    def throw_exception_if_shutdown_requested(cls, delay=0):
        # type: (float) -> None
        """
            Throws a ShutdownException if shutdown has been set or an
            AbortException if Abort has been set within the specified time period.

            If timeout = 0, then immediately returns without exception if
             shutdwown (or abort) is not set, or with an Exception if it
             is set.
            if timeout = None, then wait forever until shutdown (or abort) is set.
            Otherwise, wait a maximum of the specified time in seconds.

        :param delay:
        :return:
        """
        if cls._abort_or_shutdown_event_received.wait(timeout=delay):
            if cls._abort_received.isSet():
                raise AbortException()
            cls._logger.debug(
                'wait_for_shutdown was set', trace=Trace.TRACE_MONITOR)
            raise ShutdownException()


# Initialize class:
#
Monitor.class_init_()
