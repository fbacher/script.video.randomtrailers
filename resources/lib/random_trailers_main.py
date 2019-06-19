# -*- coding: utf-8 -*-

'''
Created on Feb 12, 2019

@author: Frank Feuerbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)


from kodi_six import xbmc, xbmcgui, utils

from kodi65 import addon
from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException, ShutdownException
from common.watchdog import WatchDog
from common.settings import Settings
from frontend.front_end_bridge import FrontendBridge
from common.logger import Logger, Trace
from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, DEVELOPMENT, RESOURCE_LIB)

import sys
from frontend import random_trailers_ui
import queue

logger = Logger(u'random_trailers_main')
logger.set_addon_name(u'script.video.randomtrailers')


REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        logger.debug(u'Trying to attach to debugger')
        logger.debug(u'Python path:', utils.py2_decode(sys.path))
        # os.environ["DEBUG_CLIENT_SERVER_TRANSLATION"] = "True"
        # os.environ[u'PATHS_FROM_ECLIPSE_TO_PYTON'] =\
        #    u'/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py:' +\
        #    u'/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py'

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
        sys.path.append(u'/home/fbacher/.kodi/addons/script.module.pydevd/lib/pydevd.py'
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
                u' Looks like remote debugger was not started prior to plugin start', xbmc.LOGDEBUG)

    except (ImportError):
        msg = u'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except (BaseException):
        logger.log_exception(msg=u'Waiting on Debug connection')

RECEIVER = None


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

    def __init__(self, is_screensaver):
        # type: (bool) -> None
        """

        :param is_screensaver:
        """
        self._logger = Logger(self.__class__.__name__)
        local_monitor = self._logger.get_method_logger(u'__init__')
        local_monitor.enter()
        self._monitor = Monitor.get_instance()
        Trace.enable_all()
        WatchDog.create()
        self._front_end_bridge = None
        self._advanced_player = None
        self._is_screensaver = is_screensaver
        self._start_ui = None

        # Calls that need to be performed on the main thread

        self._callableTasks = queue.Queue(maxsize=0)
        MainThreadLoop._singleton = self

    @staticmethod
    def get_instance(self):
        # type: () -> MainThreadLoop
        """

        :param self:
        :return:
        """
        if MainThreadLoop._singleton is None:
            MainThreadLoop.logger = Logger(u'MainThreadLoop.get_instance')
            MainThreadLoop.logger.error(u'Not yet initialized')
            return None

        return MainThreadLoop._singleton

    def startup(self):
        # type: () -> None
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(u'startup')
        local_logger.enter()
        current_dialog_id = xbmcgui.getCurrentWindowDialogId()
        current_window_id = xbmcgui.getCurrentWindowId()
        local_logger.debug(u'CurrentDialogId, CurrentWindowId:', current_dialog_id,
                          current_window_id)

        self._front_end_bridge = FrontendBridge.get_instance()
        if not self._is_screensaver and Settings.prompt_for_settings():
            self.configure_settings()

        Monitor.get_instance().register_settings_changed_listener(
            Settings.on_settings_changed)
        self._front_end_bridge .notify_settings_changed()
        self._start_ui = random_trailers_ui.StartUI()
        self._start_ui.start()
        self._monitor.set_startup_complete()
        self.event_processing_loop()

    def event_processing_loop(self):
        # type: () -> None
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(u'event_processing_loop')
        local_logger.enter()

        try:
            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout
            while not self._monitor.wait_for_shutdown(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 1.0

                try:
                    task = self._callableTasks.get(block=False)
                    self.run_task(task)
                except (queue.Empty):
                    pass

        except (Exception) as e:
            local_logger.log_exception(e)
        finally:
            monitor = Monitor.get_instance()
            if monitor is not None and monitor.is_shutdown_requested():
                local_logger.debug(
                    u'*********************** SHUTDOWN MAIN **************')
            WatchDog.shutdown()

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
        local_logger = self._logger.get_method_logger(u'run_task')
        local_logger.enter()
        try:
            callable_class()
        except (AbortException, ShutdownException) as e:
            pass
        except (Exception) as e:
            local_logger.log_exception(e)

    def configure_settings(self):
        # type: () -> None
        """
            Allow Settings to be modified inside of addon
        """

        local_monitor = self._logger.get_method_logger(u'promptForGenre')
        local_monitor.enter()
        Constants.FRONTEND_ADDON.openSettings()

        return


def bootstrap():
    # type: () -> None
    """

    :return:
    """
    try:
        logger = Logger(u'random_trailers_main')
        Logger.set_addon_name(addon.ID)
        local_logger = logger.get_method_logger(u'bootstrap')

        # TODO: need quick exit if backend is not running

        argc = len(sys.argv) - 1
        is_screensaver = False
        for arg in sys.argv[1:]:
            if arg == u'screensaver':
                is_screensaver = True

        current_dialog_id = xbmcgui.getCurrentWindowDialogId()
        current_window_id = xbmcgui.getCurrentWindowId()
        local_logger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(current_dialog_id) +
                          u' ' + str(current_window_id))

        main_loop = MainThreadLoop(is_screensaver)
        main_loop.startup()

        # Logger can be unusable during shutdown

        local_logger.exit(u'Exiting plugin' )

    except (AbortException, ShutdownException) as e:
        pass
    except (Exception) as e:
        Logger.log_exception(e)
    finally:
        if REMOTE_DBG:
            try:
                pydevd.stoptrace()
            except (Exception) as e:
                pass
        exit(0)


if __name__ == '__main__':
    bootstrap()
