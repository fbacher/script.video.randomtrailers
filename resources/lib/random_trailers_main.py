# -*- coding: utf-8 -*-

'''
Created on Feb 12, 2019

@author: Frank Feuerbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import threading
import logging
from logging import *
import queue
import sys


from kodi_six import xbmc, xbmcgui, utils

from kodi65 import addon
from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException, ShutdownException
from common.watchdog import WatchDog
from common.settings import Settings
from frontend.front_end_bridge import FrontendBridge
from common.logger import (Logger, LazyLogger, Trace, MyHandler, MyFilter)
from common.playlist import Playlist

from frontend import random_trailers_ui

REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log('Trying to attach to debugger', xbmc.LOGDEBUG)
        # os.environ["DEBUG_CLIENT_SERVER_TRANSLATION"] = "True"
        # os.environ['PATHS_FROM_ECLIPSE_TO_PYTON'] =\
        #    '/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py:' +\
        #    '/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py'

        '''
            If the server (your python process) has the structure
                /user/projects/my_project/src/package/module1.py
    
            and the client has:
                c:\my_project\src\package\module1.py
    
            the PATHS_FROM_ECLIPSE_TO_PYTHON would have to be:
                PATHS_FROM_ECLIPSE_TO_PYTHON = [(r'c:\my_project\src', r'/user/projects/my_project/src')
            # with the addon script.module.pydevd, only use `import pydevd`
            # import pysrc.pydevd as pydevd
        '''
        sys.path.append('/home/fbacher/.kodi/addons/script.module.pydevd/lib/pydevd.py'
                        )
        import pydevd
        # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
        # console
        try:
            pydevd.settrace('localhost', stdoutToServer=True,
                            stderrToServer=True)
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            xbmc.log(
                ' Looks like remote debugger was not started prior to plugin start', xbmc.LOGDEBUG)

    except (ImportError):
        msg = 'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except (BaseException):
        xbmc.log('Waiting on Debug connection', xbmc.LOGDEBUG)

RECEIVER = None

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('random_trailers_main')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class MainThreadLoop(object):
    """
        Kodi's Monitor class has some quirks in it that strongly favor creating
        it from the main thread as well as callng xbmc.sleep/xbmc.waitForAbort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.waitForAbort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """

    _singleton = None
    _logger = None

    def __init__(self, is_screensaver):
        # type: (bool) -> None
        """

        :param is_screensaver:
        """
        MainThreadLoop._logger = module_logger.getChild(
            self.__class__.__name__)
        if MainThreadLoop._logger.isEnabledFor(Logger.DEBUG):
            MainThreadLoop._logger.enter()
        self._monitor = Monitor.get_instance()
        Trace.enable_all()
        WatchDog.create()
        Settings.save_settings()
        self._front_end_bridge = None
        self._advanced_player = None
        self._is_screensaver = is_screensaver
        self._start_ui = None

        # Calls that need to be performed on the main thread

        self._callableTasks = queue.Queue(maxsize=0)
        MainThreadLoop._singleton = self

    @staticmethod
    def get_instance(is_screensaver):
        # type: (bool) -> MainThreadLoop
        """

        :param self:
        :return:
        """
        if MainThreadLoop._singleton is None:
            MainThreadLoop._singleton = MainThreadLoop(is_screensaver)

        return MainThreadLoop._singleton

    def startup(self):
        # type: () -> None
        """

        :return:
        """
        if MainThreadLoop._logger.isEnabledFor(Logger.DEBUG):
            current_dialog_id = xbmcgui.getCurrentWindowDialogId()
            current_window_id = xbmcgui.getCurrentWindowId()
            MainThreadLoop._logger.debug('CurrentDialogId, CurrentWindowId:',
                                         current_dialog_id,
                                         current_window_id)

        self._front_end_bridge = FrontendBridge.get_instance()
        if not self._is_screensaver and Settings.prompt_for_settings():
            self.configure_settings()
        try:
            thread = threading.Thread(
                target=self.ui_thread_runner,
                name='ui_thread')
            thread.start()
        except (Exception):
            module_logger.exception('')

        self._monitor.set_startup_complete()
        Playlist('junk').get_all_playlists()
        self.event_processing_loop()

    def event_processing_loop(self):
        # type: () -> None
        """

        :return:
        """
        MainThreadLoop._logger.enter()

        try:
            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout

            # Using _waitForAbort instead of waiting for shutdown to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not self._monitor._waitForAbort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 0.10

                try:
                    task = self._callableTasks.get(block=False)
                    self.run_task(task)
                except (queue.Empty):
                    pass

        except (Exception) as e:
            MainThreadLoop._logger.exception('')
        finally:
            monitor = Monitor.get_instance()
            if monitor is not None and monitor.is_shutdown_requested():
                if MainThreadLoop._logger.isEnabledFor(Logger.DEBUG):
                    MainThreadLoop._logger.debug(
                        '*********************** SHUTDOWN MAIN **************')
            WatchDog.shutdown()

    def ui_thread_runner(self):
        try:
            self._start_ui = random_trailers_ui.StartUI(self._is_screensaver)
            self._start_ui.start()
        except (Exception):
            MainThreadLoop._logger.exception()

    def run_on_main_thread(self, callable_class):
        # type: (Callable) -> None
        """

        :param callable_class:
        :return:
        """
        self._callableTasks.put(callable_class)

    def run_task(self, callable_class):
        # type: (Callable) -> None
        """

        :param callable_class:
        :return:
        """
        if MainThreadLoop._logger.isEnabledFor(Logger.DEBUG):
            MainThreadLoop._logger.enter()
        try:
            callable_class()
        except (AbortException, ShutdownException) as e:
            pass
        except (Exception) as e:
            MainThreadLoop._logger.exception('')

    def configure_settings(self):
        # type: () -> None
        """
            Allow Settings to be modified inside of addon
        """

        if MainThreadLoop._logger.isEnabledFor(Logger.DEBUG):
            MainThreadLoop._logger.enter()
        Constants.FRONTEND_ADDON.openSettings()

        return

    def setup_front_end_bridge(self):
        self._front_end_bridge = FrontendBridge.get_instance()


def bootstrap():
    # type: () -> None
    """

    :return:
    """
    try:
        Monitor.get_instance().register_settings_changed_listener(
            Settings.on_settings_changed)
        Monitor.get_instance().register_settings_changed_listener(
            Logger.on_settings_changed)

        # TODO: need quick exit if backend is not running

        argc = len(sys.argv) - 1
        is_screensaver = False
        for arg in sys.argv[1:]:
            if arg == 'screensaver':
                is_screensaver = True

        current_dialog_id = xbmcgui.getCurrentWindowDialogId()
        current_window_id = xbmcgui.getCurrentWindowId()
        if module_logger.isEnabledFor(Logger.DEBUG):
            module_logger.debug('CurrentDialogId, CurrentWindowId:', current_dialog_id,
                                current_window_id)

        mainLoop = MainThreadLoop.get_instance(is_screensaver)
        mainLoop.startup()

        # LazyLogger can be unusable during shutdown

        if module_logger.isEnabledFor(Logger.DEBUG):
            module_logger.exit('Exiting plugin')

    except (AbortException, ShutdownException) as e:
        pass
    except (Exception) as e:
        module_logger.exception('')
    finally:
        if REMOTE_DBG:
            try:
                pydevd.stoptrace()
            except (Exception) as e:
                pass
        exit(0)


if __name__ == '__main__':
    bootstrap()
