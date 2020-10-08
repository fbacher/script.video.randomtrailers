# -*- coding: utf-8 -*-

"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""

import os
import io
import sys

import xbmc
import xbmcaddon


import stat
import threading
from queue import Queue, Empty
from common.imports import *
from backend.back_end_bridge import BackendBridge
from common.constants import Constants
from common.exceptions import AbortException
from common.monitor import Monitor
from common.settings import Settings
from backend.api import load_trailers
from common.logger import (LazyLogger)

from discovery.playable_trailer_service import PlayableTrailerService
from cache.cache_manager import CacheManager


REMOTE_DEBUG: bool = True

pydevd_addon_path = None
try:
    pydevd_addon_path = xbmcaddon.Addon(
        'script.module.pydevd').getAddonInfo('path')
except Exception:
    xbmc.log('Debugger disabled, script.module.pydevd NOT installed',
             xbmc.LOGDEBUG)
    REMOTE_DEBUG = False

if REMOTE_DEBUG:
    try:
        import pydevd

        # Note, besides having script.module.pydevd installed, pydevd
        # must also be on path of IDE runtime. Should be same versions!
        try:
            xbmc.log('back_end_service trying to attach to debugger',
                     xbmc.LOGDEBUG)
            addons_path = os.path.join(pydevd_addon_path, 'lib')
            sys.path.append(addons_path)
            # xbmc.log('sys.path appended to', xbmc.LOGDEBUG)
            # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
            # console
            try:
                pydevd.settrace('localhost', stdoutToServer=True,
                                stderrToServer=True, suspend=False,
                                wait_for_ready_to_run=True)
            except Exception as e:
                xbmc.log(
                    ' Looks like remote debugger was not started prior to plugin start',
                    xbmc.LOGDEBUG)
                REMOTE_DEBUG = False
        except BaseException:
            xbmc.log('Waiting on Debug connection', xbmc.LOGDEBUG)
            REMOTE_DEBUG = False
    except ImportError:
        REMOTE_DEBUG = False
        msg = 'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        pydevd = 1
    except BaseException:
        xbmc.log('Waiting on Debug connection', xbmc.LOGERROR)
        REMOTE_DEBUG = False

RECEIVER = None
module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MainThreadLoop(object):
    """
        Kodi's Monitor class has some quirks in it that strongly favors creating
        it from the main thread as well as calling xbmc.sleep/xbmc.wait_for_abort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.wait_for_abort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """

    _singleton = None
    profiler = None
    _logger = None

    def __init__(self):
        # type: () -> None
        """

        """

        type(self)._logger = module_logger.getChild(
            self.__class__.__name__)

        # Calls that need to be performed on the main thread

        self._callableTasks = Queue(maxsize=0)
        MainThreadLoop._singleton = self

    @staticmethod
    def get_instance():
        # type: () -> MainThreadLoop
        """

        :return:
        """

        if MainThreadLoop._singleton is None:
            MainThreadLoop()

        return MainThreadLoop._singleton

    def event_processing_loop(self):
        # type: () -> None
        """

        :return:
        """
        try:
            # Cheat and start the back_end_bridge here, although this method
            # should just be a loop.

            self.start_back_end_bridge()

            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout

            # Using _wait_for_abort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not Monitor._wait_for_abort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 0.10

                try:
                    task = self._callableTasks.get(block=False)
                    self.run_task(task)
                except Empty as e:
                    pass

            Monitor.throw_exception_if_abort_requested(timeout=timeout)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            type(self)._logger.exception('')

    def start_back_end_bridge(self):
        BackendBridge(PlayableTrailerService())

    def run_on_main_thread(self, callable_class):
        # type: (Callable[[None], None]) -> None
        """

        :param callable_class:
        :return:
        """
        self._callableTasks.put(callable_class)

    def run_task(self, callable_class):
        # type: (Optional[Callable[[None], None]]) -> None
        """

        :param callable_class:
        :return:
        """
        if type(self)._logger.isEnabledFor(LazyLogger.DEBUG):
            type(self)._logger.debug('%s', 'Enter', lazy_logger=False)
        try:
            callable_class()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            type(self)._logger.exception('')


def profiler_thread():
    # type: () -> None

    finished = False
    try:
        num = 0
        while not finished:
            num += 1
            MainThreadLoop.profiler.enable()
            f = io.open('/tmp/profile_' + str(num), mode='wb')
            import pstats
            stats = pstats.Stats(
                MainThreadLoop.profiler, stream=f)

            Monitor.throw_exception_if_abort_requested(timeout=5 * 60)
            MainThreadLoop.profiler.create_stats()
            stats.print_stats()
            f.close()
    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        module_logger.exception('')


def startup_non_main_thread():
    # type: () -> None
    """

    :return:
    """
    if module_logger.isEnabledFor(LazyLogger.DEBUG):
        module_logger.debug('%s', 'Enter', lazy_logger=False)

    Settings.save_settings()
    Monitor.register_settings_changed_listener(
        Settings.on_settings_changed)
    Monitor.register_settings_changed_listener(
        LazyLogger.on_settings_changed)
    try:
        Settings.get_locale()
    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        pass
    load_trailers()

    # Start the periodic garbage collector

    CacheManager.get_instance().start_cache_garbage_collection_thread()
    Monitor.register_settings_changed_listener(load_trailers)


def bootstrap_random_trailers():
    # type: () -> None
    """
    First function called at startup.

    Note this means that this is running on the main thread

    :return:
    """

    try:
        if MainThreadLoop.profiler is not None:
            MainThreadLoop.profiler.enable()
            thread = threading.Thread(
                target=profiler_thread,
                name='back_end_service.profiler_thread')
            thread.start()

        main_loop = MainThreadLoop.get_instance()
        try:
            thread = threading.Thread(
                target=startup_non_main_thread,
                name='back_end_service.startup_main_thread')
            thread.start()
        except Exception:
            module_logger.exception('')

        main_loop.event_processing_loop()

    except AbortException as e:
        pass
    except Exception as e:
        module_logger.exception('')
    finally:
        if REMOTE_DEBUG:
            try:
                pydevd.stoptrace()
            except Exception:
                pass
        sys.exit(0)


def post_install():
    #
    # Ensure execute permission
    pass


def bootstrap_unit_test():
    from test.backend_test_suite import (BackendTestSuite)
    module_logger.enter()
    suite = BackendTestSuite()
    suite.run_suite()


if __name__ == '__main__':
    try:
        run_random_trailers = True
        argc = len(sys.argv) - 1
        is_unit_test = False
        for arg in sys.argv[1:]:
            if arg == 'unittest':
                is_unit_test = True
                run_random_trailers = False
        if run_random_trailers:
            post_install()
            profile = False
            if profile:
                import cProfile
                MainThreadLoop.profiler = cProfile.Profile()
                MainThreadLoop.profiler.runcall(bootstrap_random_trailers)
            else:
                bootstrap_random_trailers()
        elif is_unit_test:
            bootstrap_unit_test()
    except AbortException:
        pass  # Die, Die, Die
    finally:
        if REMOTE_DEBUG:
            try:
                pydevd.stoptrace()
            except Exception:
                pass
        sys.exit(0)
