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

REMOTE_DEBUG: bool = False

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
            xbmc.log('back_end_service trying to attach to debugger',
                     xbmc.LOGDEBUG)
            addons_path = os.path.join(pydevd_addon_path, 'lib')
            sys.path.append(addons_path)
            # xbmc.log('sys.path appended to', xbmc.LOGDEBUG)
            # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
            # console
            try:
                pydevd.settrace('localhost', stdoutToServer=True,
                                stderrToServer=True, suspend=False,
                                wait_for_ready_to_run=True)
            except Exception as e:
                xbmc.log(
                    ' Looks like remote debugger was not started prior to plugin start',
                    xbmc.LOGDEBUG)
        except BaseException:
            xbmc.log('Waiting on Debug connection', xbmc.LOGDEBUG)
    except ImportError:
        REMOTE_DEBUG = False
        msg = 'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        pydevd = 1
    except BaseException:
        xbmc.log('Waiting on Debug connection', xbmc.LOGERROR)

RECEIVER = None
module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

addon = xbmcaddon.Addon()
do_fullscreen = addon.getSetting('do_fullscreen')

try:
    if __name__ == '__main__':
        if xbmc.Player().isPlaying():
            if REMOTE_DEBUG:
                try:
                    pydevd.stoptrace()
                except Exception:
                    pass
            sys.exit(0)
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
