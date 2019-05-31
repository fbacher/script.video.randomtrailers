# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
# dummy screensaver will set screen to black and go fullscreen if windowed


from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

#from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
#                                                 TextType, DEVELOPMENT, RESOURCE_LIB, resource)
from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace
from common.watchdog import WatchDog
from screensaver.screensaver_bridge import ScreensaverBridge
from kodi_six import xbmc, xbmcgui, xbmcaddon, utils

import sys

logger = Logger(u'screensaver')
logger.set_addon_name(u'script.video.randomtrailers.screensaver')

REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log(u'Trying to attach to debugger', xbmc.LOGDEBUG)
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
        except Exception as e:
            xbmc.log(
                u' Looks like remote debugger was not started prior to plugin start', xbmc.LOGDEBUG)

    except ImportError:
        msg = u'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except BaseException:
        logger.log_exception(u'Waiting on Debug connection')


addon = xbmcaddon.Addon()


do_fullscreen = addon.getSetting('do_fullscreen')

logger = Logger(u'screeensaver')
local_logger = logger.get_method_logger(u'bootstrap')
try:

    if __name__ == '__main__':
        current_dialog_id = xbmcgui.getCurrentWindowDialogId()
        current_window_id = xbmcgui.getCurrentWindowId()
        _monitor = Monitor.get_instance()
        Trace.enable_all()
        WatchDog.create()
        _monitor.set_startup_complete()

        local_logger.debug(u'CurrentDialogId, CurrentWindowId:', current_dialog_id,
                           current_window_id)

        screen_saver_bridge = ScreensaverBridge.get_instance()
        message_received = screen_saver_bridge.request_activate_screensaver()

        if not message_received:
            local_logger.debug(u'About to start randomtrailers')
            # command = u'RunScript("script.video.randomtrailers", "screensaver")'
            # xbmc.executebuiltin(command)
            cmd = u'{"jsonrpc": "2.0", "method": "Addons.ExecuteAddon", \
                "params": {"addonid": "script.video.randomtrailers",\
                "params": "screensaver" }, "id": 1}'
            json_text = xbmc.executeJSONRPC(cmd)
            local_logger.debug(u'Got back from starting randomtrailers')

        WatchDog.shutdown()
        screen_saver_bridge.delete_instance()
        del screen_saver_bridge

except (AbortException, ShutdownException):
    pass
except (Exception) as e:
    local_logger.log_exception(e)
finally:
    if REMOTE_DBG:
        try:
            pydevd.stoptrace()
        except (Exception) as e:
            pass
exit(0)
