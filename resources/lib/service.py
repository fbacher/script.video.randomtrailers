# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
# monitors onScreensaverActivated event and checks guisettings.xml for plugin.video.randomtrailers.
# if found it will launch plugin.video.randomtrailers which will show trailers.
# this gets around Kodi killing a screensaver 5 seconds after
# onScreensaverDeactivate

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from typing import Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence

from common.logger import Logger, Trace
from common.exceptions import AbortException, ShutdownException
from common.monitor import Monitor

import sys
import os
import threading
from kodi_six import xbmc, xbmcgui

# import xbmc
# import xbmcgui

'''
    Rough outline:
        Start separate threads to discover basic information about all selected
        video sources:
            1- library
            2- trailer folders
            3- iTunes
            4- TMDB
            5- (future) IMDB
        Each of the above store the discovered info into separate queues.
        The main function here is to discover the identity of all candidates
        for playing so that a balanced mix of trailers is available for playing
        and random selection. It is important to do this quickly. Additional
        information discovery is performed later, in background threads or
        just before playing the video.

        Immediately after starting the discovery threads, the player
        thread is started. The player thread:
            * Loops playing videos until stopped
            * On each iteration it gets movie a to play from
              TrailerManager's ReadyToPlay queue
            * Listens for events:stop & exit, pause, play, playMovie, showInfo,
              Skip to next trailer, etc.

        TrailerManager holds various queues and lists:
            * Queues for each video source (library, iTunes, etc.) for
                the initial discovery from above
            * Queues for discovering additional information
            * DiscoveredTrailers, a list of all videos after filtering (genre,
                rating, etc). This list grows during initial discovery
            * A small queue (about 5 elements) for each video source so that
                required additional information can be discovered just before
                playing the video. The queues provide enough of a buffer so
                that playing will not be interrupted waiting on discovery
            * The ReadyToPlayQueue which is a small queue containing fully
                discovered trailers and awaiting play. WAs trailers are played
                it is refilled from the small final discovery queues above


'''

REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        _logger = Logger(u'service.RemoteDebug.init')

        _logger.debug(u'Trying to attach to debugger')
        _logger.debug(u'Python path: ' + unicode(sys.path))
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
        Logger.logException(u'Waiting on Debug connection')

logger = Logger(u'service')


def isTrailerScreensaver():
    return True

    pguisettings = xbmc.translatePath(os.path.join(
        u'special://userdata', 'guisettings.xml')).decode(u'utf-8')
    _logger = Logger(u'Service.isTrailerScreensaver')

    _logger.debug(pguisettings)
    name = '<mode>script.video.randomtrailers</mode>'
    if name in file(pguisettings, "r").read():
        _logger.debug(u'found script.video.randomtrailers in guisettings.html')
        return True
    else:
        _logger.debug(
            u'did not find script.video.randomtrailers in guisettings.html')
        return False


class MyMonitor(Monitor):

    _singletonInstance = None

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)

        super().__init__()
        self._shutDownEvent = threading.Event()
        self._thread = threading.Thread(
            target=self._waitForAbortThread, name='Service Monitor')

        self._thread.start()

    @staticmethod
    def getInstance():
        if MyMonitor._singleton is None:
            MyMonitor._singleton = MyMonitor()

        return MyMonitor._singleton

    def onScreensaverActivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverActivated')
        localLogger.debug(u'In onScreenserverActivated')

        if isTrailerScreensaver():
            self._logger.debug(
                u'In onScreenserverActivated isTrailerScreenSaver')
            xbmc.executebuiltin(
                'xbmc.RunScript("script.video.randomtrailers","screensaver")')

    def _waitForAbortThread(self):
        localLogger = self._logger.getMethodLogger(
            u'_waitForAbortThread')
        self.waitForAbort()
        self.shutDownEvent.set()
        localLogger.debug(u'ABORT', trace=Trace.TRACE)

    def waitForShutdownEvent(self):
        localLogger = self._logger.getMethodLogger(
            u'waitForShutdownEvent')
        self.shutDownEvent.wait()
        localLogger.debug(u'SHUTDOWN received')
        self._thread.join(0.01)  # Won't join if abort hasn't occurred


try:
    logger.enter()
    currentDialogId = xbmcgui.getCurrentWindowDialogId()
    currentWindowId = xbmcgui.getCurrentWindowId()
    localLogger = logger.getMethodLogger(u'service')

    if __name__ == '__main__':
        localLogger.debug(u'I am __main__')

    localLogger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                      u' ' + str(currentWindowId))

    shutDownEvent = threading.Event()

    logger.debug(u'randomtrailers.service waiting for shutdown')
    MyMonitor.getInstance().waitForShutdown()
    logger.debug(u'randomtrailers.service stopping Player')
    xbmc.Player().stop
    logger.exit()
except Exception as e:
    logger.logException(e)
