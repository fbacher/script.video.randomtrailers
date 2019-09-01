# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
# dummy screensaver will set screen to black and go fullscreen if windowed
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *
import logging
from logging import *

from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException, ShutdownException
from common.logger import (Logger, LazyLogger, Trace, MyHandler, MyFilter)
from common.watchdog import WatchDog
from screensaver.screensaver_bridge import ScreensaverBridge
from kodi_six import xbmc, xbmcgui, xbmcaddon, utils

import sys


REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log('Trying to attach to debugger', xbmc.LOGDEBUG)
        # if module_logger.isEnabledFor(Logger.DEBUG):
        #     module_logger.debug('Python path:', utils.py2_decode(sys.path))
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
        except Exception as e:
            xbmc.log(
                ' Looks like remote debugger was not started prior to plugin start', xbmc.LOGDEBUG)

    except ImportError:
        msg = 'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except BaseException:
        xbmc.log('Exception occurred Waiting on Debug connection', xbmc.LOGDEBUG)


if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('screensaver')
else:
    module_logger = LazyLogger.get_addon_module_logger()

addon = xbmcaddon.Addon()
do_fullscreen = addon.getSetting('do_fullscreen')

try:

    if __name__ == '__main__':
        if xbmc.Player().isPlaying():
            exit(0)
        current_dialog_id = xbmcgui.getCurrentWindowDialogId()
        current_window_id = xbmcgui.getCurrentWindowId()
        _monitor = Monitor.get_instance()
        Trace.enable_all()
        WatchDog.create()

        # Using _waitForAbort instead of waiting for shutdown to
        # cause Monitor to query Kodi for Abort on the main thread.
        # If this is not done, then Kodi will get constipated
        # sending/receiving events to plugins.

        _monitor._waitForAbort(timeout=0.01)

        _monitor.set_startup_complete()

        if module_logger.isEnabledFor(Logger.DEBUG):
            module_logger.debug('CurrentDialogId, CurrentWindowId:', current_dialog_id,
                                current_window_id)

        screen_saver_bridge = ScreensaverBridge.get_instance()
        message_received = screen_saver_bridge.request_activate_screensaver()

        _monitor._waitForAbort(timeout=0.01)

        if not message_received:
            if module_logger.isEnabledFor(Logger.DEBUG):
                module_logger.debug('About to start randomtrailers')

            cmd = '{"jsonrpc": "2.0", "method": "Addons.ExecuteAddon", \
                "params": {"addonid": "script.video.randomtrailers",\
                "params": "screensaver" }, "id": 1}'
            json_text = xbmc.executeJSONRPC(cmd)
            _monitor._waitForAbort(timeout=0.01)

            if module_logger.isEnabledFor(Logger.DEBUG):
                module_logger.debug('Got back from starting randomtrailers')

        # xbmc.sleep(500)
        WatchDog.shutdown(traceback=False)
        _monitor._waitForAbort(timeout=0.01)
        screen_saver_bridge.delete_instance()
        _monitor._waitForAbort(timeout=0.01)
        del screen_saver_bridge

except (AbortException, ShutdownException):
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
