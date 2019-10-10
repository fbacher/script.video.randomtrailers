# -*- coding: utf-8 -*-

"""
Created on Mar 17, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import sys
import datetime
import threading
import six

from .constants import (Constants)
from .logger import (LazyLogger, Logger, Trace, log_entry)
from .debug_utils import Debug
from .exceptions import AbortException, ShutdownException
from .monitor import Monitor

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.watchdog')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class WatchDog(threading.Thread):
    """

    """

    # TODO:- Cleanup, eliminate deathIsNigh

    # Must use _threads_to_watch_lock object to access!
    _completed_shutdown_phase1 = None
    _death_is_nigh = None
    _threads_to_watch = []
    _threads_to_watch_lock = threading.RLock()
    _logger = None
    _reaper_thread = None
    _watch_dog_thread = None

    @classmethod
    def create(cls):
        # type: () -> None
        """

        :return:
        """
        cls._logger = module_logger.getChild('WatchDog')
        cls._reaper_thread = None
        cls._death_is_nigh = threading.Event()
        cls._completed_shutdown_phase1 = threading.Event()

        cls._watch_dog_thread = WatchDog(False)
        cls._watch_dog_thread.start()
        cls._create_reaper()

    @classmethod
    def _create_reaper(cls):
        # type: () -> None
        """

        :return:
        """
        cls._reaper_thread = WatchDog(True)
        cls._reaper_thread.start()

    @classmethod
    def register_thread(cls, thread):
        # type: (threading.Thread) -> None
        """

        :param thread:
        :return:
        """
        with cls._threads_to_watch_lock:
            cls._threads_to_watch.append(thread)

    @classmethod
    def class__init__(cls, thread_reaper):
        # type: (bool) -> None
        """

        :param thread_reaper:
        """
        if thread_reaper:
            thread_name = type(cls).__name__ + '_threadReaper'
        else:
            thread_name = type(cls).__name__

        cls._time_to_shutdown = None
        super().__init__(group=None, target=None,
                         name=thread_name,
                         args=(), kwargs=None, verbose=None)

    def run(self):
        # type: () -> None
        """

        :return:
        """
        try:
            if self is WatchDog._reaper_thread:
                self.reap_dead_threads()
            else:
                self.wait_for_death_signal()
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception):
            WatchDog._logger.exception('')


    @classmethod
    def reap_dead_threads(cls):
        # type: () -> None
        """
            While waiting for shutdown, reap any zombie threads
        """
        cls._logger.enter()
        Monitor.wait_for_startup_complete()
        cls._logger.debug('StartupComplete')
        #
        # During normal operation, check for threads to harvest every 5
        # minutes, but during shutdown, check continuously
        while not Monitor.wait_for_shutdown(3000):
            try:
                cls.join_with_completed_threads(0.01, reaper_thread=True)
            except (AbortException, ShutdownException):
                six.reraise(*sys.exc_info())
            except (Exception) as e:
                cls._logger.exception('')

        cls._logger.exit('wait_for_shutdown complete')

        # Run once after shutdown received

        try:
            cls.join_with_completed_threads(0.01, reaper_thread=True)
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            cls._logger.exception('')

    @classmethod
    def wait_for_death_signal(cls):
        # type: () -> None
        """

        :return:
        """
        Monitor.wait_for_shutdown()

        cls._time_to_shutdown = datetime.datetime.now()
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('WatchDog: Shutting Down!')

        with cls._threads_to_watch_lock:
            for aThread in cls._threads_to_watch:
                try:
                    if cls._logger.isEnabledFor(Logger.DEBUG):
                        cls._logger.debug('WatchDog stopping',
                                               aThread.getName())
                    thread = threading.Thread(
                        target=aThread.shutdown_thread,
                        name='cls.shutdown')
                    thread.start()

                except (Exception) as e:
                    cls._logger.exception('')

        try:
            if cls._logger.isEnabledFor(Logger.DEBUG):
                cls._logger.debug('WatchDog: _death_is_nigh!')
            death_time = 2.5

            if cls._reaper_thread is not None:
                if cls._reaper_thread.isAlive():
                    cls._reaper_thread.join(death_time)
                if cls._reaper_thread.isAlive():
                    cls._death_is_nigh.set()  # Force exit

                if cls._reaper_thread.isAlive():
                    cls._reaper_thread.join(0.1)
                if cls._reaper_thread.isAlive():
                    cls._logger.error('FAILED to Join with reaperThread')
                else:
                    if cls._logger.isEnabledFor(Logger.DEBUG):
                        cls._logger.debug('Joined with reaperThread')

                cls._reaper_thread = None

                duration = datetime.datetime.now() - cls._time_to_shutdown
                if cls._logger.isEnabledFor(Logger.DEBUG):
                    cls._logger.debug('Waited ' + str(duration.seconds),
                                           'seconds to exit after shutdown request.')
        except (Exception) as e:
            cls._logger.exception('')

        cls._completed_shutdown_phase1.set()

    @classmethod
    def join_with_completed_threads(cls, delay, reaper_thread=True):
        # type: (Union[float, int], bool) -> int
        """

        :param delay:
        :param reaper_thread:
        :return:
        """
        if cls._logger.isEnabledFor(Logger.DEBUG):
            cls._logger.debug('Enter reaper_thread:', reaper_thread)

        reaped = 0
        with cls._threads_to_watch_lock:
            for aThread in cls._threads_to_watch:
                try:
                    # Bug out
                    if cls._death_is_nigh.isSet():
                        break

                    if aThread.isAlive():
                        if Monitor.is_shutdown_requested():
                            if cls._logger.isEnabledFor(Logger.DEBUG):
                                cls._logger.debug('Watchdog joining with ' +
                                                       aThread.getName())
                        aThread.join(delay)
                    if not aThread.isAlive():
                        cls._threads_to_watch.remove(aThread)
                        if cls._logger.isEnabledFor(Logger.DEBUG):
                            cls._logger.debug('Thread: ' + aThread.getName() +
                                                   ' REAPED.')

                except (Exception) as e:
                    cls._logger.exception('')
            remaining = int(len(cls._threads_to_watch))

        if reaper_thread or reaped > 0:
            if cls._logger.isEnabledFor(Logger.DEBUG):
                cls._logger.debug(str(reaped) + ' threads REAPed: ' +
                                       str(remaining) + ' threads remaining', trace=Trace.TRACE)
        return remaining

    @classmethod
    def shutdown(cls, traceback=True):
        # type: (bool) -> None
        """

        :return:
        """
        try:
            Monitor.shutdown_requested()
        except (Exception):
            pass

        # Debug.dump_all_threads()

        cls._completed_shutdown_phase1.wait()
        # Debug.dump_all_threads()
        with cls._threads_to_watch_lock:
            try:
                if cls._watch_dog_thread is not None:
                    if cls._watch_dog_thread.isAlive():
                        cls._logger.debug(
                            'Attempting to join with WatchDogThread')
                        cls._watch_dog_thread.join()
                        if cls._logger.isEnabledFor(Logger.DEBUG):
                            cls._logger.debug('watchDogThread joined')
                        cls._watch_dog_thread = None
            except (Exception) as e:
                cls._logger.exception('')

        Monitor.shutdownThread()
        if traceback:
            Debug.dump_all_threads()
        del cls._threads_to_watch
        del cls._threads_to_watch_lock

        del cls._reaper_thread
        del cls._watch_dog_thread

        del cls._death_is_nigh
        del cls._completed_shutdown_phase1
        try:
            cls._logger.exit()
        except (Exception):
            pass

        try:
            del cls._logger
        except (Exception):
            pass
