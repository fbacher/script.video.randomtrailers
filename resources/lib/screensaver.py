# -*- coding: utf-8 -*-

# dummy screensaver will set screen to black and go fullscreen if windowed


from __future__ import print_function, division, absolute_import, unicode_literals

from future import standard_library
standard_library.install_aliases()  # noqa: E402

from builtins import unicode
from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace
from common.watchdog import WatchDog
from common.back_end_bridge import BackEndBridge
from kodi_six import xbmc, xbmcgui, xbmcaddon

import sys

logger = Logger(u'screensaver')
logger.setAddonName(u'screensaver')

REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log(u'Trying to attach to debugger', xbmc.LOGDEBUG)
        logger.debug(u'Python path: ' + unicode(sys.path), xbmc.LOGDEBUG)
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
        logger.logException(u'Waiting on Debug connection')


addon = xbmcaddon.Addon()


do_fullscreen = addon.getSetting('do_fullscreen')


try:
    if __name__ == '__main__':
        currentDialogId = xbmcgui.getCurrentWindowDialogId()
        currentWindowId = xbmcgui.getCurrentWindowId()
        logger = Logger(u'screeensaver')
        Logger.setAddonName(u'screensaver')
        localLogger = logger.getMethodLogger(u'bootstrap')
        _monitor = Monitor.getInstance()
        Trace.enableAll()
        WatchDog.create()
        _monitor.setStartupComplete()

        localLogger.debug(u'CurrentDialogId, CurrentWindowId:', currentDialogId,
                          currentWindowId)

        back_end_bridge = BackEndBridge.getInstance(
            Constants.FRONTEND_SERVICE)
        back_end_bridge.initialize(Constants.FRONTEND_SERVICE)
        messageReceived = back_end_bridge.requestActivateScreensaver()

        if not messageReceived:
            localLogger.debug(u'About to start randomtrailers')
            # command = u'RunScript("script.video.randomtrailers", "screensaver")'
            # xbmc.executebuiltin(command)
            cmd = u'{"jsonrpc": "2.0", "method": "Addons.ExecuteAddon", \
                "params": {"addonid": "script.video.randomtrailers",\
                "params": "screensaver" }, "id": 1}'
            jsonText = xbmc.executeJSONRPC(cmd)
            localLogger.debug(u'Got back from starting randomtrailers')

        WatchDog.shutdown()
        back_end_bridge.delete_instance()
        del back_end_bridge

except (AbortException, ShutdownException):
    pass
except (Exception) as e:
    localLogger.logException(e)
finally:
    if REMOTE_DBG:
        try:
            pydevd.stoptrace()
        except (Exception) as e:
            pass
exit(0)
