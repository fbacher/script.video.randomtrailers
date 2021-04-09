# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
from common.minimal_monitor import MinimalMonitor
from common.python_debugger import PythonDebugger
REMOTE_DEBUG: bool = False
if REMOTE_DEBUG:
    PythonDebugger.enable('randomtrailers.screensaver')

import sys

import xbmc
import xbmcaddon

from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import (LazyLogger, Trace)


module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)

addon = xbmcaddon.Addon()
do_fullscreen = addon.getSetting('do_fullscreen')


def exit_randomtrailers():
    try:
        if PythonDebugger.is_enabled():
            PythonDebugger.disable()
        sys.exit(0)
    except Exception as e:
        xbmc.log('Exception occurred exiting ' + str(e), xbmc.LOGDEBUG)
        pass


try:
    if __name__ == '__main__':
        if xbmc.Player().isPlaying():
            exit_randomtrailers()

        _monitor = MinimalMonitor
        # Trace.enable_all()

        # Using wait_for_abort to
        # cause Monitor to query Kodi for Abort on the main thread.
        # If this is not done, then Kodi will get constipated
        # sending/receiving events to plugins.

        _monitor.throw_exception_if_abort_requested(timeout=0.01)

        message_received = False
        if not message_received:
            if module_logger.isEnabledFor(LazyLogger.DEBUG):
                module_logger.debug('About to start randomtrailers as screensaver')

            cmd = '{"jsonrpc": "2.0", "method": "Addons.ExecuteAddon", \
                "params": {"addonid": "script.video.randomtrailers",\
                "params": "screensaver" }, "id": 1}'
            json_text = xbmc.executeJSONRPC(cmd)
            _monitor.throw_exception_if_abort_requested(timeout=0.01)

    MinimalMonitor.abort_requested()
    while not MinimalMonitor.real_waitForAbort(timeout=0.1):
        pass

except AbortException:
    pass
except Exception as e:
    xbmc.log('Exception occurred exiting2 ' + str(e), xbmc.LOGDEBUG)
    module_logger.exception('')
finally:
    exit_randomtrailers()
