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


from kodi_six import xbmc, xbmcgui

from kodi65 import addon
from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException, ShutdownException
from common.watchdog import WatchDog
from common.settings import Settings
from common.front_end_bridge import FrontendBridge
from common.logger import Logger, Trace
from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, DEVELOPMENT, RESOURCE_LIB)

import sys
import random_trailers_ui
import queue

logger = Logger(u'random_trailers_main')
logger.setAddonName(u'script.video.randomtrailers')


REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        localLogger = logger.getMethodLogger(u'Debugger startup')
        localLogger.debug(u'Trying to attach to debugger')
        localLogger.debug(u'Python path: ' + unicode(sys.path))
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

    except ImportError:
        msg = u'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except BaseException:
        localLogger.logException(u'Waiting on Debug connection')

RECEIVER = None


class MainThreadLoop(object):
    '''
        Kodi's Monitor class has some quirks in it that strongly favor creating
        it from the main thread as well as callng xbmc.sleep/xbmc.waitForAbort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.waitForAbort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    '''

    _singleton = None

    def __init__(self, is_screensaver):
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._monitor = Monitor.getInstance()
        Trace.enableAll()
        WatchDog.create()
        self._front_end_bridge = None
        self._screen_saver_manager = None
        self._advanced_player = None
        self._is_screensaver = is_screensaver

        # Calls that need to be performed on the main thread

        self._callableTasks = queue.Queue(maxsize=0)
        MainThreadLoop._singleton = self

    @staticmethod
    def getInstance(self):
        if MainThreadLoop._singleton is None:
            logger = Logger(u'MainThreadLoop.getInstance')
            logger.error(u'Not yet initialized')
            return None

        return MainThreadLoop._singleton

    def startup(self):
        localLogger = self._logger.getMethodLogger(u'startup')
        localLogger.enter()
        currentDialogId = xbmcgui.getCurrentWindowDialogId()
        currentWindowId = xbmcgui.getCurrentWindowId()
        localLogger.debug(u'CurrentDialogId, CurrentWindowId:', currentDialogId,
                          currentWindowId)

        self._front_end_bridge = FrontendBridge.getInstance()
        if not self._is_screensaver and Settings.promptForSettings():
            self.configureSettings()

        self._front_end_bridge .notifySettingsChanged()
        self._startUI = random_trailers_ui.StartUI(self._is_screensaver)
        self._startUI.start()
        self._monitor.setStartupComplete()
        self.eventProcessingLoop()

    def eventProcessingLoop(self):
        localLogger = self._logger.getMethodLogger(u'eventProcessingLoop')
        localLogger.enter()

        try:
            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout
            while not self._monitor.waitForShutdown(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 1.0

                try:
                    task = self._callableTasks.get(block=False)
                    self.run_task(task)
                except (queue.Empty):
                    pass

        except (Exception) as e:
            localLogger.logException(e)
        finally:
            monitor = Monitor.getInstance()
            if monitor is not None and monitor.isShutdownRequested():
                localLogger.debug(
                    u'*********************** SHUTDOWN MAIN **************')
            WatchDog.shutdown()

    def runOnMainThread(self, callable_class):
        self._callableTasks.put(callable_class)

    def run_task(self, callable_class):
        localLogger = self._logger.getMethodLogger(u'run_task')
        localLogger.enter()
        try:
            callable_class()
        except (AbortException, ShutdownException) as e:
            pass
        except (Exception) as e:
            localLogger.logException(e)

    def configureSettings(self):
        '''
            Allow Settings to be modified inside of addon
        '''

        localLogger = self._logger.getMethodLogger(u'promptForGenre')
        localLogger.enter()
        Constants.FRONTEND_ADDON.openSettings()

        return


def bootstrap():
    try:
        logger = Logger(u'random_trailers_main')
        Logger.setAddonName(addon.ID)
        localLogger = logger.getMethodLogger(u'bootstrap')

        argc = len(sys.argv) - 1
        is_screensaver = False
        for arg in sys.argv[1:]:
            if arg == u'screensaver':
                is_screensaver = True

        currentDialogId = xbmcgui.getCurrentWindowDialogId()
        currentWindowId = xbmcgui.getCurrentWindowId()
        localLogger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                          u' ' + str(currentWindowId))

        mainLoop = MainThreadLoop(is_screensaver)
        mainLoop.startup()

        # Logger can be unusable during shutdown

        xbmc.log(u'Exiting plugin', xbmc.LOGDEBUG)

    except (AbortException, ShutdownException) as e:
        pass
    except (Exception) as e:
        Logger.logException(e)
    finally:
        if REMOTE_DBG:
            try:
                pydevd.stoptrace()
            except (Exception) as e:
                pass
        exit(0)


if __name__ == '__main__':
    bootstrap()
