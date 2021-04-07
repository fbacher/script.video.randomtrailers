# -*- coding: utf-8 -*-

"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""

from common.python_debugger import PythonDebugger
REMOTE_DEBUG: bool = True
if REMOTE_DEBUG:
    PythonDebugger.enable('randomtrailers.backend')

from common.logger import LazyLogger

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

import sys
import threading
import xbmc
from common.exceptions import AbortException
from common.minimal_monitor import MinimalMonitor
from common.imports import reraise, Callable


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

            xbmc.log('In event_processing_loop', xbmc.LOGDEBUG)

            debugger_initialized = False
            bridge_initialized = False

            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout

            # Using real_waitForAbort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            xbmc.log('Imported Monitor and AbortException', xbmc.LOGDEBUG)


            while not MinimalMonitor.real_waitForAbort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 0.10
                        
                """
                try:
                     task = self._callableTasks.get(block=False)
                     self.run_task(task)
                 except Empty as e:
                     pass
                """

                if not bridge_initialized:
                    bridge_initialized = True
                    cls.start_back_end_bridge()
                    
            MinimalMonitor.throw_exception_if_abort_requested(timeout=timeout)
 

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            pass
            # type(self)._logger.exception('')

    @classmethod
    def start_back_end_bridge(cls) -> None:
        from backend.back_end_bridge import BackendBridge
        from discovery.playable_trailer_service import PlayableTrailerService
        BackendBridge(PlayableTrailerService())

    '''
    @classmethod
    def run_on_main_thread(cls,
                           callable_class: Callable[[None], None] = None) -> None:
        """

        :param callable_class:
        :return:
        """
        cls._callableTasks.put(callable_class)
    '''

    @classmethod
    def run_task(cls,
                 callable_class: Callable[[None], None] = None) -> None:
        """

        :param callable_class:
        :return:
        """
        # if type(self)._logger.isEnabledFor(LazyLogger.DEBUG):
        #    type(self)._logger.debug('%s', 'Enter', lazy_logger=False)
        try:
            callable_class()


        except AbortException:
            pass
            # reraise(*sys.exc_info())
        except Exception:
            pass
            # type(self)._logger.exception('')


def bootstrap_random_trailers() -> None:
    """
    First function called at startup.

    Note this means that this is running on the main thread

    :return:
    """

    xbmc.log('Starting non-main thread', xbmc.LOGDEBUG)
    try:
        try:
            import backend_service_worker
            thread = threading.Thread(
                target=backend_service_worker.startup_non_main_thread,
                name='back_end_service.startup_non_main_thread')
            thread.start()
        except Exception:
            pass
            # module_logger# .exception('')

        xbmc.log('Starting event processing loop', xbmc.LOGDEBUG)

        MainThreadLoop.event_processing_loop()
    except AbortException as e:
        pass
    except Exception as e:
        pass
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
        run_random_trailers = True
        argc = len(sys.argv) - 1
        is_unit_test = False
        for arg in sys.argv[1:]:
            if arg == 'unittest':
                is_unit_test = True
                run_random_trailers = False
        if run_random_trailers:
            xbmc.log('main thread 4', xbmc.LOGDEBUG)

            # This will NOT return until exiting plugin

            bootstrap_random_trailers()

            xbmc.log('main thread 5', xbmc.LOGDEBUG)

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
