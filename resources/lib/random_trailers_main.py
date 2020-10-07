# -*- coding: utf-8 -*-

'''
Created on Feb 12, 2019

@author: Frank Feuerbacher
'''

import threading
import queue
import os
import sys

import xbmc
import xbmcaddon

from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException
from common.imports import *
from common.settings import Settings
from frontend.front_end_bridge import FrontendBridge
from common.logger import (LazyLogger, Trace)

from frontend import random_trailers_ui

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
            xbmc.log('front-end trying to attach to debugger', xbmc.LOGDEBUG)
            addons_path = os.path.join(Constants.ADDON_PATH, '..',
                                       'script.module.pydevd', 'lib')

            sys.path.append(addons_path)
            # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
            # console
            try:
                pydevd.settrace('localhost', stdoutToServer=True,
                                stderrToServer=True, suspend=False)
            except Exception as e:
                xbmc.log(
                    ' Looks like remote debugger was not started prior to plugin start',
                    xbmc.LOGDEBUG)
        except BaseException:
            xbmc.log('Waiting on Debug connection', xbmc.LOGDEBUG)
    except ImportError:
        REMOTE_DEBUG = False
        pydevd = 1

RECEIVER = None
xbmc.log('__file__:' + __file__ + 'module:' + __name__, xbmc.LOGDEBUG)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MainThreadLoop(object):
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

            # Using _wait_for_abort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not Monitor._wait_for_abort(timeout=timeout):
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
            if REMOTE_DEBUG:
                try:
                    pydevd.stoptrace()
                except Exception:
                    pass
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(e)

    @classmethod
    def ui_thread_runner(cls):
        try:
            cls._start_ui = random_trailers_ui.StartUI(cls._is_screensaver)
            cls._start_ui.start()
        except AbortException:
            if REMOTE_DEBUG:
                try:
                    pydevd.stoptrace()
                except Exception:
                    pass
                    pass  # Thread to die
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
        if REMOTE_DEBUG:
            try:
                pydevd.stoptrace()
            except Exception:
                pass
        sys.exit(0)


def bootstrap_unit_test():
    pass


if __name__ == '__main__':  # TODO: need quick exit if backend is not running
    if xbmc.Player().isPlaying():
        if REMOTE_DEBUG:
            try:
                pydevd.stoptrace()
            except Exception:
                pass
        sys.exit(0)
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

    if REMOTE_DEBUG:
        try:
            pydevd.stoptrace()
        except Exception:
            pass
    sys.exit(0)
