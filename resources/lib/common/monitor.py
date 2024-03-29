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
from common.minimal_monitor import MinimalMonitor

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Monitor(MinimalMonitor):
    """
        Provides a number of customizations to xbmc.monitor

        MinimalMonitor exists simply to not drag in logging dependencies
        at startup.
    """
    startup_complete_event: threading.Event = None
    _monitor_changes_in_settings_thread: threading.Thread = None
    _logger: LazyLogger = None
    _screen_saver_listeners: Dict[Callable[[None], None], str] = None
    _screen_saver_listener_lock: threading.RLock = None
    _settings_changed_listeners: Dict[Callable[[None], None], str] = None
    _settings_changed_listener_lock: threading.RLock = None
    _abort_listeners: Dict[Callable[[None], None], str] = None
    _abort_listener_lock: threading.RLock = None
    _abort_listeners_informed: bool = False
    _wait_return_count_map: Dict[str, int] = {}  # thread_id, returns from wait
    _wait_call_count_map: Dict[str, int] = {}  # thread_id, calls to wait

    """
      Can't get rid of __init__
    """
    def __init__(self):
        super().__init__()

    @classmethod
    def class_init(cls) -> None:
        """

        """
        if cls._logger is None:
            cls._logger: LazyLogger = module_logger.getChild(cls.__class__.__name__)
            # Weird problems with recursion if we make requests to the super

            cls._screen_saver_listeners = {}
            cls._screen_saver_listener_lock = threading.RLock()
            cls._settings_changed_listeners = {}
            cls._settings_changed_listener_lock = threading.RLock()
            cls._abort_listeners = {}
            cls._abort_listener_lock = threading.RLock()
            cls._abort_listeners_informed = False

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

            cls.startup_complete_event = threading.Event()
            super().register_abort_callback(cls._inform_abort_listeners)

            cls._monitor_changes_in_settings_thread = threading.Thread(
                target=cls._monitor_changes_in_settings,
                name='_monitor_changes_in_settings')
            cls._monitor_changes_in_settings_thread.start()

    @classmethod
    def _monitor_changes_in_settings(cls) -> None:
        """

        :return:
        """

        last_time_changed: datetime.datetime
        settings_path = os.path.join(
            Constants.FRONTEND_DATA_PATH, 'settings.xml')
        try:
            file_stat = os.stat(settings_path)
            last_time_changed = datetime.datetime.fromtimestamp(file_stat.st_mtime)
        except Exception as e:
            cls._logger.debug("Failed to read settings.xml")
            last_time_changed = datetime.datetime.now()

        # It seems that if multiple xbmc.WaitForAborts are pending, xbmc
        # Does not inform all of them when an abort occurs. So, instead
        # of waiting for 60 seconds per iteration, we wait 0.1 seconds
        # and act when 600 calls has been made. Not exactly 60 seconds, but
        # close enough for this

        thread_name = CriticalSettings.get_plugin_name() + "_monitorSettingsChanges"
        threading.current_thread().setName(thread_name)
        iterations: int = 600

        # We know that settings have not changed when we first start up,
        # so ignore first false change.

        while not cls.wait_for_abort(timeout=0.1):
            iterations -= 1
            if iterations < 0:
                iterations = 600
                try:
                    file_stat = os.stat(settings_path)
                    mod_time: datetime.datetime = datetime.datetime.fromtimestamp(
                        file_stat.st_mtime)
                except Exception as e:
                    cls._logger.debug("Failed to read settings.xml")
                    mod_time: datetime.datetime = datetime.datetime.now()

                # Wait at least a minute after settings changed, just in case there
                # are multiple changes.
                #
                # Note that when settings are changed via kodi config that this
                # will cause a second settings changed event a minute or two
                # after the initial one. However, the Settings code should
                # detect that nothing has actually changed and no harm should be
                # done.

                if last_time_changed == mod_time:
                    continue

                now: datetime.datetime = datetime.datetime.now()

                #
                # Was file modified at least a minute ago?
                #

                delta: datetime.timedelta = now - mod_time

                if delta.total_seconds() > 60:
                    if cls._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                        cls._logger.debug_verbose('Settings Changed!')
                    last_time_changed = mod_time
                    cls.on_settings_changed()

                    # Here we go again

    @classmethod
    def get_listener_name(cls,
                          listener: Callable[[None], None],
                          name: str = None) -> str:
        listener_name: str = 'unknown'
        if name is not None:
            listener_name = name
        elif hasattr(listener, '__name__'):
            try:
                listener_name = listener.__name__
            except:
                pass
        elif hasattr(listener, 'name'):
            try:
                listener_name = listener.name
            except:
                pass

        return listener_name

    @classmethod
    def register_screensaver_listener(cls,
                                      listener: Callable[[None], None],
                                      name: str = None) -> None:
        """

        :param listener:
        :param name:
        :return:
        """
        with cls._screen_saver_listener_lock:
            if not (cls.is_abort_requested()
                    or listener in cls._screen_saver_listeners):
                listener_name = cls.get_listener_name(listener, name)

                cls._screen_saver_listeners[listener] = listener_name

    @classmethod
    def unregister_screensaver_listener(cls,
                                        listener: Callable[[None], None]) -> None:
        """

        :param listener:
        :return:
        """
        with cls._screen_saver_listener_lock:
            try:
                if listener in cls._screen_saver_listeners:
                    del cls._screen_saver_listeners[listener]
            except ValueError:
                pass

    @classmethod
    def register_settings_changed_listener(cls,
                                           listener: Callable[[None], None],
                                           name: str = None) -> None:
        """

        :param name:
        :param listener:
        :return:
        """
        with cls._settings_changed_listener_lock:
            if not (cls.is_abort_requested()
                    or listener in cls._settings_changed_listeners):
                listener_name = cls.get_listener_name(listener, name)

                cls._settings_changed_listeners[listener] = listener_name

    @classmethod
    def unregister_settings_changed_listener(cls,
                                             listener: Callable[[None], None]) -> None:
        """

        :param listener:
        :return:
        """
        with cls._settings_changed_listener_lock:
            try:
                if listener in cls._settings_changed_listeners:
                    del cls._settings_changed_listeners[listener]
            except ValueError:
                pass

    @classmethod
    def register_abort_listener(cls,
                                listener: Callable[[None], None],
                                name: str = None) -> None:
        """

        :param listener:
        :param name:
        :return:
        """
        with cls._abort_listener_lock:
            if not (cls.is_abort_requested()
                    or listener in cls._abort_listeners):
                listener_name = cls.get_listener_name(listener, name)

                cls._abort_listeners[listener] = listener_name
            else:
                raise AbortException()

    @classmethod
    def unregister_abort_listener(cls,
                                  listener: Callable[[None], None]) -> None:
        """

        :param listener:
        :return:
        """
        with cls._abort_listener_lock:
            try:
                if listener in cls._abort_listeners:
                    del cls._abort_listeners[listener]
            except ValueError:
                pass

    @classmethod
    def _inform_abort_listeners(cls) -> None:
        """

        :return:
        """
        with cls._abort_listener_lock:
            if cls._abort_listeners_informed:
                return
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                cls._logger.enter()
            listeners_copy = copy.copy(cls._abort_listeners)
            cls._abort_listeners.clear() # Unregister all
            cls._abort_listeners_informed = True

        for listener, listener_name in listeners_copy.items():
            # noinspection PyTypeChecker
            thread = threading.Thread(
                target=listener, name=listener_name)
            thread.start()

        cls.startup_complete_event.set()

        with cls._settings_changed_listener_lock:
            cls._settings_changed_listeners.clear()

        with cls._screen_saver_listener_lock:
            cls._screen_saver_listeners.clear()

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            from common.debug_utils import Debug
            Debug.dump_all_threads(delay=0.25)
            Debug.dump_all_threads(delay=0.50)

    @classmethod
    def _inform_settings_changed_listeners(cls) -> None:
        """

        :return:
        """
        with cls._settings_changed_listener_lock:
            listeners = copy.copy(cls._settings_changed_listeners)
            if cls.is_abort_requested():
                cls._settings_changed_listeners.clear()

        for listener, listener_name in listeners.items():
            if cls._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                cls._logger.debug_verbose(
                    'Notifying listener:', listener_name)
            thread = threading.Thread(
                target=listener, name='Monitor.inform_' + listener_name)
            thread.start()

    @classmethod
    def _inform_screensaver_listeners(cls,
                                      activated: bool = True) -> None:
        """

        :param activated:
        :return:
        """
        with cls._screen_saver_listener_lock:
            listeners_copy = copy.copy(cls._screen_saver_listeners)
            if cls.is_abort_requested():
                cls._screen_saver_listeners.clear()

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            cls._logger.debug_verbose(f'Screensaver activated: {activated}')
        for listener, listener_name in listeners_copy.items():
            thread = threading.Thread(
                target=listener, name='Monitor._inform_' + listener_name,
                args=(activated,))
            thread.start()

    def onSettingsChanged(self) -> None:
        """
        This method is called by xbmc when any settings have changed.

        Don't rely on xbmc.onSettingsChanged because we want to avoid changes to
        app settings based upon a user's incomplete changes. Instead, rely
        on _monitor_changes_in_settings, which waits a minute after settings.xml
        file is stable before notification.

        Real settings changed notification caused by on_settings_changed method.

        :return:
        """
        # type(self).on_settings_changed()
        pass

    @classmethod
    def on_settings_changed(cls) -> None:
        cls._inform_settings_changed_listeners()

    def onScreensaverActivated(self) -> None:
        """
        onScreensaverActivated method.

        Will be called when screensaver kicks in

        :return:
        """
        type(self)._inform_screensaver_listeners(activated=True)

        # return super().onScreensaverActivated()

    def onScreensaverDeactivated(self) -> None:
        """
        onScreensaverDeactivated method.

        Will be called when screensaver goes off

        :return:
        """
        type(self)._inform_screensaver_listeners(activated=False)

        # return super().onScreensaverDeactivated()

    def onNotification(self, sender: str, method: str, data: str) -> None:
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

    def waitForAbort(self, timeout: float = None) -> bool:
        # Provides signature of super class (xbmc.Monitor)
        #
        # Only real_waitForAbort() calls xbmc.Monitor.waitForAbort, which is
        # called only by back_end_service, front_end_service or screensaver and
        # only from the main thread.
        #
        # WaitForAbort and wait_for_abort depend upon _abort_received

        clz = type(self)
        if timeout is not None and timeout < 0.0:
            timeout = None

        clz.track_wait_call_counts()
        abort = clz._abort_received.wait(timeout=timeout)
        clz.track_wait_return_counts()

        return abort

    @classmethod
    def wait_for_abort(cls, timeout: float = None) -> bool:
        """
        Wait for Abort

        Block until abort is requested, or until timeout occurs. If an abort
        requested have already been made, return immediately.

        :param timeout: [opt] float - timeout in seconds. Default: no timeout.
        :return: True when abort have been requested,
            False if a timeout is given and the operation times out.

        New function added.
        """
        if timeout is not None and timeout < 0.0:
            timeout = None

        cls.track_wait_call_counts()
        abort = False
        while timeout > 0.0:
            poll_delay: float = min(timeout, CriticalSettings.SHORT_POLL_DELAY)
            if CriticalSettings.POLL_MONITOR_WAIT_FOR_ABORT:
                if cls._abort_received.is_set():
                    abort = True
                    break
                cls.real_waitForAbort(timeout=poll_delay)
            else:
                if cls._abort_received.wait(timeout=poll_delay):
                    abort = True
                    break
            timeout -= poll_delay

        cls.track_wait_return_counts()

        return abort

    @classmethod
    def abort_requested(cls) -> None:
        cls._xbmc_monitor.abortRequested()
        cls.set_abort_received()

    def abortRequested(self) -> None:
        """

        :return:
        """
        Monitor.abort_requested()

    @classmethod
    def is_abort_requested(cls) -> bool:
        """
        Returns True if abort has been requested.

        :return: True if requested

        New function added.
        """
        return cls._abort_received.isSet()

    @classmethod
    def set_startup_complete(cls) -> None:
        """

        :return:
        """
        cls.startup_complete_event.set()
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug(
                'startup_complete_event set', trace=Trace.TRACE_MONITOR)

    @classmethod
    def is_startup_complete(cls) -> bool:
        """

        :return:
        """
        return cls.startup_complete_event.isSet()

    @classmethod
    def wait_for_startup_complete(cls, timeout: float = None) -> bool:
        """

        :param timeout:
        :return:
        """
        is_set = False
        approximate_wait_time = 0.0
        while not is_set:
            is_set = cls.startup_complete_event.wait(timeout=None)
            Monitor.throw_exception_if_abort_requested(timeout=0.2)
            approximate_wait_time += 0.2
            if timeout is not None and approximate_wait_time >= timeout:
                break

        return is_set

    @classmethod
    def track_wait_call_counts(cls, thread_name: str = None) -> None:
        if thread_name is None:
            thread_name = threading.current_thread().getName()
        # xbmc.log('track_wait_call_counts thread: ' + thread_name, xbmc.LOGDEBUG)

        if thread_name is None:
            thread_name = threading.current_thread().getName()

        count = cls._wait_call_count_map.get(thread_name, None)
        if count is None:
            count = 1
        else:
            count += 1

        cls._wait_call_count_map[thread_name] = count
        cls.dump_wait_counts()

    @classmethod
    def track_wait_return_counts(cls, thread_name: str = None) -> None:
        if thread_name is None:
            thread_name = threading.current_thread().getName()
        # xbmc.log('track_wait_return_counts thread: ' + thread_name, xbmc.LOGDEBUG)

        if thread_name is None:
            thread_name = threading.current_thread().getName()

        count = cls._wait_return_count_map.get(thread_name, None)
        if count is None:
            count = 1
        else:
            count += 1

        cls._wait_return_count_map[thread_name] = count
        cls.dump_wait_counts()

    @classmethod
    def dump_wait_counts(cls) -> None:
        return

        xbmc.log('Wait Call Map', xbmc.LOGDEBUG)
        for k, v in cls._wait_call_count_map.items():
            xbmc.log(str(k) + ': ' + str(v), xbmc.LOGDEBUG)

        xbmc.log('Wait Return Map', xbmc.LOGDEBUG)
        for k, v in cls._wait_return_count_map.items():
            xbmc.log(str(k) + ': ' + str(v), xbmc.LOGDEBUG)

        from common.debug_utils import Debug
        Debug.dump_all_threads()


# Initialize class:
#
Monitor.class_init()
