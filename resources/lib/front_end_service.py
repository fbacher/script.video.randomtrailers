# -*- coding: utf-8 -*-

'''
Created on Feb 12, 2019

@author: Frank Feuerbacher
'''

from common.python_debugger import PythonDebugger
REMOTE_DEBUG: bool = False
if REMOTE_DEBUG:
    PythonDebugger.enable('randomtrailers.frontend')

import queue
import sys
import threading

import xbmc

from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException
from common.imports import *
from common.settings import Settings
from frontend.front_end_bridge import FrontendBridge
from common.logger import (LazyLogger, Trace)

from frontend import random_trailers_ui


module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

def exit_randomtrailers():
    if PythonDebugger.is_enabled():
        PythonDebugger.disable()
    sys.exit(0)

class MainThreadLoop:
    """
        Kodi's Monitor class has some quirks in it that strongly favor creating
        it from the main thread as well as callng xbmc.sleep/xbmc.wait_for_abort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.wait_for_abort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """
    _advanced_player = None
    _callableTasks = None
    _is_screensaver = None
    _logger = None
    _start_ui = None

    def __init__(self) -> None:
        """

        """
        pass

    @classmethod
    def class_init(cls, screensaver: bool) -> None:
        cls._logger = module_logger.getChild(cls.__name__)
        Trace.enable_all()
        Settings.save_settings()
        cls._advanced_player = None
        cls._is_screensaver = screensaver
        cls._start_ui = None
        cls._callableTasks = queue.Queue(maxsize=0)


    # Calls that need to be performed on the main thread

    @classmethod
    def startup(cls) -> None:
        """

        :return:
        """

        FrontendBridge()  # Initialize
        if not cls._is_screensaver and Settings.prompt_for_settings():
            cls.configure_settings()
        try:
            thread = threading.Thread(target=cls.ui_thread_runner,
                                      name='ui_thread')
            thread.start()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            module_logger.exception('')

        Monitor.set_startup_complete()
        cls.event_processing_loop()

    @classmethod
    def event_processing_loop(cls) -> None:
        """

        :return:
        """
        try:
            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 0.10 seconds

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout

            # Using real_waitForAbort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not Monitor.real_waitForAbort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 0.10

                try:
                    task = cls._callableTasks.get(block=False)
                    cls.run_task(task)
                except queue.Empty:
                    pass

            Monitor.throw_exception_if_abort_requested(timeout=timeout)

        except AbortException:
            if PythonDebugger.is_enabled():
                PythonDebugger.disable()
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(e)

    @classmethod
    def ui_thread_runner(cls):
        try:
            cls._start_ui = random_trailers_ui.StartUI(cls._is_screensaver)
            cls._start_ui.start()
        except AbortException:
            if PythonDebugger.is_enabled():
                PythonDebugger.disable()
        except Exception:
            cls._logger.exception('')

    @classmethod
    def run_on_main_thread(cls, callable_class: Callable) -> None:
        """

        :param callable_class:
        :return:
        """
        cls._callableTasks.put(callable_class)

    @classmethod
    def run_task(cls, callable_class: Callable) -> None:
        """

        :param callable_class:
        :return:
        """
        try:
            callable_class()
        except AbortException:
            pass
        except Exception:
            cls._logger.exception('')

    @classmethod
    def configure_settings(cls) -> None:
        """
            Allow Settings to be modified inside of addon
        """
        Constants.FRONTEND_ADDON.openSettings()

        return


def bootstrap_random_trailers(screensaver: bool) -> None:
    """
    :param screensaver: True when launched as a screensaver
    :return:
    """
    try:
        Monitor.register_settings_changed_listener(
            Settings.on_settings_changed)

        Monitor.register_settings_changed_listener(
            LazyLogger.on_settings_changed)

        MainThreadLoop.class_init(screensaver)
        MainThreadLoop.startup()

        # LazyLogger can be unusable during shutdown

        if module_logger.isEnabledFor(LazyLogger.DEBUG):
            module_logger.exit('Exiting plugin')

    except AbortException:
        pass  # Exit in finally block
    except Exception:
        module_logger.exception('')
    finally:
        exit_randomtrailers()


def bootstrap_unit_test():
    pass


if __name__ == '__main__':  # TODO: need quick exit if backend is not running
    if xbmc.Player().isPlaying():
        exit_randomtrailers()
    run_random_trailers = True
    argc = len(sys.argv) - 1
    is_screensaver = False
    is_unit_test = False
    for arg in sys.argv[1:]:
        if arg == 'screensaver':
            is_screensaver = True
        if arg == 'unittest':
            is_unit_test = True

    if run_random_trailers:
        bootstrap_random_trailers(is_screensaver)
    elif is_unit_test:
        bootstrap_unit_test()

    exit_randomtrailers()
