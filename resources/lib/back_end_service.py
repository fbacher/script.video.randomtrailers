# -*- coding: utf-8 -*-

"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""

from common.python_debugger import PythonDebugger
from common.critical_settings import CriticalSettings
CriticalSettings.set_plugin_name('backend')
REMOTE_DEBUG: bool = False
if REMOTE_DEBUG:
    PythonDebugger.enable('randomtrailers.backend')

from common.logger import LazyLogger

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

import sys
import threading
import xbmc
from common.exceptions import AbortException
from common.minimal_monitor import MinimalMonitor
from common.imports import *


def exit_randomtrailers():
    if PythonDebugger.is_enabled():
        PythonDebugger.disable()
    sys.exit(0)


class MainThreadLoop:
    """
        Kodi's Monitor class has some quirks in it that strongly favors creating
        it from the main thread as well as calling xbmc.sleep/xbmc.wait_for_abort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.wait_for_abort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """

    profiler = None
    # _callableTasks = Queue(maxsize=0)

    @classmethod
    def event_processing_loop(cls) -> None:
        """

        :return:
        """
        try:
            # Cheat and start the back_end_bridge here, although this method
            # should just be a loop.

            worker_thread_initialized = False
            bridge_initialized = False

            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            if REMOTE_DEBUG:
                start_backend_count_down = 2.0 / initial_timeout
            else:
                start_backend_count_down = 0.0
            i = 0
            timeout = initial_timeout

            # Using real_waitForAbort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not MinimalMonitor.real_waitForAbort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 0.10

                if start_backend_count_down > 0:
                    start_backend_count_down -= 1.0
                else:
                    if not worker_thread_initialized:
                        worker_thread_initialized = True
                        cls.start_backend_worker_thread()

                    if not bridge_initialized:
                        bridge_initialized = True
                        cls.start_back_end_bridge()

            MinimalMonitor.throw_exception_if_abort_requested(timeout=timeout)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            # xbmc.log('xbmc.log Exception: ' + str(e), xbmc.LOGERROR)
            module_logger.exception(e, lazy_logger=True)

    @classmethod
    def start_back_end_bridge(cls) -> None:
        from backend.back_end_bridge import BackendBridge
        from discovery.playable_trailer_service import PlayableTrailerService
        BackendBridge(PlayableTrailerService())

    @classmethod
    def start_backend_worker_thread(cls) -> None:
        try:
            import backend_service_worker
            thread = threading.Thread(
                target=backend_service_worker.startup_non_main_thread,
                name='back_end_service.startup_non_main_thread')
            thread.start()
        except Exception as e:
            xbmc.log('Exception: ' + str(e), xbmc.LOGERROR)
            # module_logger# .exception('')


def bootstrap_random_trailers() -> None:
    """
    First function called at startup.

    Note this means that this is running on the main thread

    :return:
    """

    try:
        # xbmc.log('Starting event processing loop', xbmc.LOGDEBUG)

        MainThreadLoop.event_processing_loop()
    except AbortException as e:
        pass
    except Exception as e:
        xbmc.log('Exception: ' + str(e), xbmc.LOGERROR)
        # module_logger.exception('')
    finally:
        exit_randomtrailers()


def bootstrap_unit_test() -> None:
    from test.backend_test_suite import (BackendTestSuite)
    # module_logger.enter()
    suite = BackendTestSuite()
    suite.run_suite()


if __name__ == '__main__':
    try:
        MinimalMonitor.real_waitForAbort(0.1)  # Sometimes thread name is not set
        threading.current_thread().name = 'RandomTrailers backend'
        threading.current_thread().setName('RandomTrailers backend main')
        run_random_trailers = True
        argc = len(sys.argv) - 1
        is_unit_test = False
        for arg in sys.argv[1:]:
            if arg == 'unittest':
                is_unit_test = True
                run_random_trailers = False
        if run_random_trailers:

            # This will NOT return until exiting plugin

            bootstrap_random_trailers()
            profile = False
            if profile:
                import cProfile
                MainThreadLoop.profiler = cProfile.Profile()
                MainThreadLoop.profiler.runcall(bootstrap_random_trailers)
        elif is_unit_test:
            bootstrap_unit_test()
    except AbortException:
        pass  # Die, Die, Die
    finally:
        exit
