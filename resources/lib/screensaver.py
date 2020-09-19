# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
# dummy screensaver will set screen to black and go fullscreen if windowed

import os
import sys

import xbmc
import xbmcaddon

from common.constants import Constants
from common.exceptions import AbortException
from common.imports import *
from common.monitor import Monitor
from common.logger import (LazyLogger, Trace)
from screensaver.screensaver_bridge import ScreensaverBridge

REMOTE_DEBUG: bool = True

if REMOTE_DEBUG:
    try:
        import pydevd

        # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
        try:
            xbmc.log('Trying to attach to debugger', xbmc.LOGDEBUG)
            '''
                If the server (your python process) has the structure
                    /user/projects/my_project/src/package/module1.py

                and the client has:
                    c:\my_project\src\package\module1.py

                the PATHS_FROM_ECLIPSE_TO_PYTHON would have to be:
                    PATHS_FROM_ECLIPSE_TO_PYTHON = \
                          [(r'c:\my_project\src', r'/user/projects/my_project/src')
                # with the addon script.module.pydevd, only use `import pydevd`
                # import pysrc.pydevd as pydevd
            '''
            addons_path = os.path.join(Constants.ADDON_PATH, '..',
                                       'script.module.pydevd', 'lib', 'pydevd.py')

            sys.path.append(addons_path)
            # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
            # console
            try:
                pydevd.settrace('localhost', stdoutToServer=True,
                                stderrToServer=True)
            except AbortException:
                exit(0)
            except Exception as e:
                xbmc.log(
                    ' Looks like remote debugger was not started prior to plugin start',
                    xbmc.LOGDEBUG)
        except BaseException:
            xbmc.log('Waiting on Debug connection', xbmc.LOGDEBUG)
    except ImportError:
        REMOTE_DEBUG = False
        pydevd = None

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

addon = xbmcaddon.Addon()
do_fullscreen = addon.getSetting('do_fullscreen')

try:
    if __name__ == '__main__':
        if xbmc.Player().isPlaying():
            exit(0)
        _monitor = Monitor
        Trace.enable_all()

        # Using wait_for_abort to
        # cause Monitor to query Kodi for Abort on the main thread.
        # If this is not done, then Kodi will get constipated
        # sending/receiving events to plugins.

        _monitor.wait_for_abort(timeout=0.01)
        _monitor.set_startup_complete()
        ScreensaverBridge()  # Initialize
        message_received = ScreensaverBridge.request_activate_screensaver()

        _monitor.wait_for_abort(timeout=0.01)

        if not message_received:
            if module_logger.isEnabledFor(LazyLogger.DEBUG):
                module_logger.debug('About to start randomtrailers')

            cmd = '{"jsonrpc": "2.0", "method": "Addons.ExecuteAddon", \
                "params": {"addonid": "script.video.randomtrailers",\
                "params": "screensaver" }, "id": 1}'
            json_text = xbmc.executeJSONRPC(cmd)
            _monitor.wait_for_abort(timeout=0.01)

            if module_logger.isEnabledFor(LazyLogger.DEBUG):
                module_logger.debug('Got back from starting randomtrailers')

        _monitor.wait_for_abort(timeout=0.01)
        ScreensaverBridge.delete_instance()
        _monitor.wait_for_abort(timeout=0.01)

except AbortException:
    pass
except Exception as e:
    module_logger.exception('')
finally:
    if REMOTE_DEBUG:
        try:
            pydevd.stoptrace()
        except Exception as e:
            pass
exit(0)
