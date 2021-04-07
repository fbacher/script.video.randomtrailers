# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""

from common.python_debugger import PythonDebugger
from back_end_service import exit_randomtrailers
REMOTE_DEBUG: bool = True
if REMOTE_DEBUG:
    PythonDebugger.enable('randomtrailers.screensaver')

import sys

import xbmc
import xbmcaddon

from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import (LazyLogger, Trace)


module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

addon = xbmcaddon.Addon()
do_fullscreen = addon.getSetting('do_fullscreen')

def exit_randomtrailers():
    if PythonDebugger.is_enabled():
        PythonDebugger.disable()
    sys.exit(0)

try:
    if __name__ == '__main__':
        if xbmc.Player().isPlaying():
            exit_randomtrailers()
            
        _monitor = Monitor
        Trace.enable_all()

        # Using wait_for_abort to
        # cause Monitor to query Kodi for Abort on the main thread.
        # If this is not done, then Kodi will get constipated
        # sending/receiving events to plugins.

        _monitor.wait_for_abort(timeout=0.01)
        _monitor.set_startup_complete()

        message_received = False
        if not message_received:
            if module_logger.isEnabledFor(LazyLogger.DEBUG):
                module_logger.debug('About to start randomtrailers screensaver')

            cmd = '{"jsonrpc": "2.0", "method": "Addons.ExecuteAddon", \
                "params": {"addonid": "script.video.randomtrailers",\
                "params": "screensaver" }, "id": 1}'
            json_text = xbmc.executeJSONRPC(cmd)
            _monitor.wait_for_abort(timeout=0.01)

        _monitor.wait_for_abort(timeout=0.01)

except AbortException:
    pass
except Exception as e:
    module_logger.exception('')
finally:
    exit_randomtrailers()
