from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from multiprocessing.pool import ThreadPool
from xml.dom import minidom
from kodi65 import addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import Utils
from common.rt_utils import Playlist
from common.exceptions import AbortException, ShutdownException
from common.rt_utils import WatchDog
from common.rt_utils import Trace
from common.logger import Logger, logEntryExit
from common.messages import Messages
from player.advanced_player import AdvancedPlayer
from action_map import Action
from settings import Settings
from backend.api import *
import sys
import datetime
import io
import json
import os
import queue
import random
import re
import requests
import resource
import threading
import time
import traceback
import urllib
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
#import xbmcwsgi
#import xbmcdrm
import string
import action_map


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
        xbmc.log(u'Trying to attach to debugger', xbmc.LOGDEBUG)
        Debug.myLog(u'Python path: ' + unicode(sys.path), xbmc.LOGDEBUG)
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
        Debug.logException(u'Waiting on Debug connection')

logger = Logger(u'random_trailer_ui')

# TODO: Move to ui_utils


def getTitleFont():
    localLogger = logger.getMethodLogger(u'getTitleFont')
    localLogger.debug(u'In randomtrailer.getTitleFont')
    title_font = 'font13'
    base_size = 20
    multiplier = 1
    skin_dir = xbmc.translatePath("special://skin/")
    list_dir = os.listdir(skin_dir)
    fonts = []
    fontxml_path = u''
    font_xml = u''
    for item in list_dir:
        item = os.path.join(skin_dir, item)
        if os.path.isdir(item):
            font_xml = os.path.join(item, "Font.xml")
        if os.path.exists(font_xml):
            fontxml_path = font_xml
            break
    theDom = minidom.parse(fontxml_path)
    fontlist = theDom.getElementsByTagName('font')
    for font in fontlist:
        name = font.getElementsByTagName('name')[0].childNodes[0].nodeValue
        size = font.getElementsByTagName('size')[0].childNodes[0].nodeValue
        fonts.append({'name': name, 'size': float(size)})
    fonts = sorted(fonts, key=lambda k: k[u'size'])
    for f in fonts:
        if f[u'name'] == 'font13':
            multiplier = f[u'size'] / base_size
            break
    for f in fonts:
        if f[u'size'] >= 38 * multiplier:
            title_font = f[u'name']
            break
    return title_font


def configureSettings():
    '''
        Allow Settings to be modified inside of addon
    '''

    localLogger = logger.getMethodLogger(u'promptForGenre')
    localLogger.debug(u'In randomtrailer.promptForGenre')
    Constants.ADDON.openSettings()

    return


class BlankWindow(xbmcgui.WindowXML):
    '''
        Ensure a nice black window behind our player and transparent
        TrailerDialog. Keeps the Kodi screen from showing up from time
        to time (between trailers, etc.).
    '''

    def onInit(self):
        pass

    def close(self):
        localLogger = logger.getMethodLogger(u'BlankWindow.close')
        localLogger.enter()
        super(BlankWindow, self).close()

    def show(self):
        localLogger = logger.getMethodLogger(u'BlankWindow.show')
        localLogger.enter()
        super(BlankWindow, self).show()

# TODO: Get rid of this


TRACE_STRING = u'TRACE_EVENT '


class BaseWindow():

    '''
        A transparent window (all WindowDialogs are transparent) to contain
        our listeners and Title display. 
    '''

    def addToPlaylist(self, playListId, trailer):
        localLogger = self._logger.getMethodLogger(u'addToPlayList')
        _playlistMap = {xbmcgui.REMOTE_1:
                        Playlist.PLAYLIST_PREFIX + u'1' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_2:
                        Playlist.PLAYLIST_PREFIX + u'2' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_3:
                        Playlist.PLAYLIST_PREFIX + u'3' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_4:
                        Playlist.PLAYLIST_PREFIX + u'4' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_5:
                        Playlist.PLAYLIST_PREFIX + u'5' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_6:
                        Playlist.PLAYLIST_PREFIX + u'6' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_7:
                        Playlist.PLAYLIST_PREFIX + u'7' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_8:
                        Playlist.PLAYLIST_PREFIX + u'8' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_9:
                        Playlist.PLAYLIST_PREFIX + u'9' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_0:
                        Playlist.PLAYLIST_PREFIX + u'10' + Playlist.PLAYLIST_SUFFIX}
        playlistFile = _playlistMap.get(playListId, None)
        if playlistFile is None:
            localLogger.error(
                u'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.getPlaylist(playlistFile).recordPlayedTrailer(trailer)

    def notifyUser(self, msg):
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'notifyUser')
        localLogger.debug(msg)

    def playMovie(self, trailer):
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'playMovie')
        localLogger.debug(u'Playing movie at user request:',
                          trailer[Movie.TITLE])

    def getTitleString(self, trailer):
        title = u'[B]' + trailer[Movie.DETAIL_TITLE] + u'[/B]'
        title2 = trailer[Movie.DETAIL_TITLE]
        return title


class ReasonEvent():
    '''
        Provides a threading.Event with an attached reason
    '''
    TIMED_OUT = u'timed out'
    CLEARED = u'Cleared'
    KODI_ABORT = u'Kodi Abort'
    SHUTDOWN = u'Shutdown'
    APPLICATION_EXIT = u'Application Exit'
    SCREENSAVER_ACTIVATED = u'Screensaver activated'
    SCREENSAVER_DEACTIVATED = u'Screensaver de-activated'

    def __init__(self):
        self._event = threading.Event()

    def getReason(self):
        return self._reason

    def set(self, reason):
        self._reason = reason
        self._event.set()

    def clear(self):
        self._reason = ReasonEvent.CLEARED
        self._event.clear()

    def wait(self, timeout=None):
        self._reason = ReasonEvent.TIMED_OUT
        self._event.wait(timeout)


class ScreensaverState():
    ACTIVATED = u'screensaver activated'
    DEACTIVATED = u'screensaver de-activated'

    _instance = None

    def __init__(self):
        self.state = None

    @staticmethod
    def getInstance():
        if ScreensaverState._instance is None:
            ScreensaverState._instance = ScreensaverState()
        return ScreensaverState._instance

    def setState(self, state):
        self.state = state

    def getState(self):
        return self.state


class ScreensaverManager:
    '''
        Catches events and relays to listeners
    '''

    _instance = None

    def __init__(self):
        ScreensaverManager._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._screensaverState = ScreensaverState.getInstance()
        self._screensaverStateChanged = threading.Event()
        self._screenSaverListeners = []
        self._screensaverInactiveEvent = threading.Event()
        self._launchedAsScreenSaver = None
        self._screensaverActiveEvent = threading.Event()
        self._monitor = Monitor.getInstance()
        self._monitor.registerScreensaverListener(self)
        self._monitor.registerShutdownListener(self)
        self._monitor.registerAbortListener(self)

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        self._checkForIdle = threading.Event()
        self._idleMonitor = threading.Thread(
            target=self.restartScreensaverOnIdle, name=u'Screensaver on Idle')
        self._idleMonitor.start()

    @staticmethod
    def getInstance():
        if ScreensaverManager._instance is None:
            ScreensaverManager._instance = ScreensaverManager()
        localLogger = ScreensaverManager._logger.getMethodLogger(
            u'getInstance')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)
        return ScreensaverManager._instance

    def registerScreensaverListener(self, listener):
        self._screenSaverListeners.append(listener)

    def unRegisterScreensaverListener(self, listener):
        self._screenSaverListeners.remove(listener)

    # Kodi is not calling these in our situation.

    def onScreensaverActivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverActivated')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)

        self._screensaverInactiveEvent.clear()
        self._screensaverActiveEvent.set()
        self._screensaverState.setState(ScreensaverState.ACTIVATED)
        self._screensaverStateChanged.set()
        self._checkForIdle.clear()
        self.informScreensaverListeners(activated=True)

    def onScreensaverDeactivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverDeactivated')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)

        self._screensaverInactiveEvent.set()
        self._screensaverActiveEvent.clear()
        self._screensaverState.setState(ScreensaverState.DEACTIVATED)

        # Causes an idle checking thread to resume

        self._checkForIdle.set()
        self._screensaverStateChanged.set()
        self.informScreensaverListeners(activated=False)

    def onShutdownEvent(self):
        localLogger = self._logger.getMethodLogger(u'onShutdownEvent')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)

        # Make sure that restartScreensaverOnIdle thread can exit

        self._checkForIdle.set()
        self._screensaverStateChanged.set()

        # Set these events so that the code will fall-through
        # and check for AbortandShutdown

        self._screensaverInactiveEvent.set()
        self._screensaverActiveEvent.set()

    def onAbortEvent(self):
        localLogger = self._logger.getMethodLogger(u'onAbortEvent')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)

        # Make sure that restartScreensaverOnIdle thread can exit

        self._checkForIdle.set()
        self._screensaverStateChanged.set()

        # Set these events so that the code will fall-through
        # and check for AbortandShutdown

        self._screensaverInactiveEvent.set()
        self._screensaverActiveEvent.set()

    def informScreensaverListeners(self, activated=True):
        localLogger = self._logger.getMethodLogger(
            u'informScreensaverListeners')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        for listener in self._screenSaverListeners:
            if activated:
                listener.onScreensaverActivated()
            else:
                listener.onScreensaverDeactivated()

    def getScreensaverState(self):
        localLogger = self._logger.getMethodLogger(
            u'getScreensaverState')
        localLogger.trace(
            u'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)
        return self._screensaverState

    def isScreensaverActivated(self):
        localLogger = self._logger.getMethodLogger(
            u'isScreensaverActivated')
        localLogger.trace(
            u'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)
        return self._screensaverState.getState() == ScreensaverState.ACTIVATED

    def isScreensaverDeactivated(self):
        localLogger = self._logger.getMethodLogger(
            u'isScreensaverDeactivated')
        localLogger.trace(
            u'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)
        return self._screensaverState.getState() == ScreensaverState.DEACTIVATED

    def isLaunchedAsScreensaver(self):
        return self._launchedAsScreenSaver

    def setLaunchedAsScreensaver(self, launchedAsScreensaver):
        self._launchedAsScreenSaver = launchedAsScreensaver

    def waitForScreensaverActive(self, timeout=None):
        '''
            Block until this plugin is active as a screen saver

            Note that when a plugin is not running as a 
            screen saver, then it will not exit until Kodi
            shuts down.

            Raises an AbortException or ShutdownException 
            when those conditions exist.
        '''
        self._screensaverActiveEvent.wait(timeout)
        self._monitor.throwExceptionIfAbortRequested(timeout=0)
        self._monitor.throwExceptionIfShutdownRequested(timeout=0)

    def waitForScreensaverInactive(self, timeout=None):
        '''
            Block until this plugin is active as a screen saver

            Note that when a plugin is not running as a 
            screen saver, then it will not exit until Kodi
            shuts down.

            Raises an AbortException or ShutdownException 
            when those conditions exist.
        '''
        self._screensaverInactiveEvent.wait(timeout=timeout)
        self._monitor.throwExceptionIfAbortRequested(timeout=0)
        self._monitor.throwExceptionIfShutdownRequested(timeout=0)

    def restartScreensaverOnIdle(self):
        try:
            localLogger = self._logger.getMethodLogger(
                u'restartScreensaverOnIdle')
            localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
            finished = False
            while not finished:

                # Block when screen saver is activated or not in screen saver
                # mode

                self._checkForIdle.wait()
                if xbmc.Player().isPlaying():
                    continue

                # If idle for x seconds, then reactivate the screen saver. Kodi's
                # getGlobalIdleTime considers our player as idle whether it is
                # playing something or not.

                idle = False
                startScreensaverAfterIdleSeconds = Settings.getIdleTimeout()
                waitTime = startScreensaverAfterIdleSeconds
                while not idle:
                    Monitor.getInstance().throwExceptionIfShutdownRequested(waitTime)

                    idleTime = xbmc.getGlobalIdleTime()
                    if idleTime < waitTime:
                        waitTime = startScreensaverAfterIdleSeconds - idleTime
                    else:
                        idle = True

                # Just in case the user started doing something while we
                # were waiting for the inner time-out loop

                if Monitor.getInstance().isShutdownRequested():
                    return

                if not self._checkForIdle.isSet() or xbmc.Player().isPlaying():
                    continue

                self.onScreensaverActivated()

        except (AbortException, ShutdownException) as e:
            pass
        except Exception:
            Logger.logException(e)

# TODO: Put this in separate file


class TrailerDialog(xbmcgui.WindowXMLDialog, BaseWindow):
    '''
        Note that the underlying 'script-trailer-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    '''

    def __init__(self, *args, **kwargs):
        super(TrailerDialog, self).__init__(*args, **kwargs)
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._exitDialog = False
        self._player = kwargs[u'player']
        self._player.setCallBacks(onShowInfo=self)
        self._numberOfTrailersToPlay = kwargs[u'numberOfTrailersToPlay']
        self._screensaverManager = ScreensaverManager.getInstance()
        self._screensaverManager.registerScreensaverListener(self)
        self._runningAsScreensaver = kwargs.get(u'screensaver', False)
        screenSaverstate = ScreensaverState.getInstance()
        if self._screensaverManager.isLaunchedAsScreensaver():
            screenSaverstate.setState(ScreensaverState.ACTIVATED)

        self._control = None
        self._source = None
        self._trailer = None
        self._lock = threading.RLock()
        self._longTrailerKiller = None
        self._messages = Messages.getInstance()
        self._viewedPlaylist = Playlist.getPlaylist(
            Playlist.VIEWED_PLAYLIST_FILE)
        self._infoDialogController = None
        self._thread = None
        self._pause = threading.Event()
        self._waitEvent = ReasonEvent()
        monitor = Monitor.getInstance()
        monitor.registerScreensaverListener(self)
        monitor.registerShutdownListener(self)
        monitor.registerAbortListener(self)

        self._shutdown = False
        self._abort = False

    def onInit(self):
        localLogger = self._logger.getMethodLogger(u'onInit')
        localLogger.enter()

        if self._infoDialogController is None:
            self._infoDialogController = InfoDialogController(
                kwargs={u'trailerDialog': self})

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        if self._thread is None:
            self._thread = threading.Thread(
                target=self.playTrailers, name=u'TrailerDialog')
            self._thread.start()

    def playTrailers(self):
        localLogger = self._logger.getMethodLogger(u'playTrailers')

        localLogger.debug(u' WindowID: ' +
                          str(xbmcgui.getCurrentWindowId()))

        windowstring = Utils.getKodiJSON(
            '{"jsonrpc":"2.0","method":"GUI.GetProperties",\
            "params":{"properties":["currentwindow"]},"id":1}')
        localLogger.debug('Trailer_Window_id = ' +
                          str(windowstring[u'result'][u'currentwindow'][u'id']))
        localLogger.debug(u' about to get TrailerManager.iterator')

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
        windowHeight = self.getHeight()
        windowWidth = self.getWidth()
        localLogger.debug(u'Window Dimensions: ' + str(windowHeight) +
                          u' H  x ' + str(windowWidth) + u' W')

        self.setBriefInfoVisibility(False)
        limitTrailersToPlay = True
        if self._numberOfTrailersToPlay == 0:
            limitTrailersToPlay = False

        trailerManager = BaseTrailerManager.getInstance()
        trailerIterator = iter(trailerManager)
        self._trailer = next(trailerIterator)
        try:

            # Main trailer playing loop

            while self._trailer is not None and not Monitor.getInstance().isShutdownRequested():
                localLogger.debug(u' got trailer to play: ' +
                                  self._trailer.get(Movie.TRAILER))

                # Make sure that any previously playing video is finished

                if self._infoDialogController is not None:
                    self._infoDialogController.dismissInfoDialog()

                TrailerDialog.trailer = self._trailer

                # Our event listeners will stop the player, as appropriate.

                self._player.waitForIsNotPlayingVideo()

                self._source = self._trailer.get(Movie.SOURCE)
                showInfoDialog = False
                self._viewedPlaylist.recordPlayedTrailer(self._trailer)

                if (Settings.getTimeToDisplayDetailInfo() > 0
                        and self._source != Movie.FOLDER_SOURCE):
                    showInfoDialog = True

                self.showMovieInfo(showDetailInfo=showInfoDialog,
                                   showBriefInfo=Settings.getShowTrailerTitle())

                # Play Trailer

                if not Monitor.getInstance().isShutdownRequested():
                    localLogger.debug(u' About to play: ' +
                                      self._trailer.get(Movie.TRAILER))
                    self._player.play(self._trailer.get(
                        Movie.TRAILER).encode(u'utf-8'), windowed=False)

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

                if not self._player.waitForIsPlayingVideo(timeout=5.0):
                    # Timed out
                    localLogger.debug(u'Timed out Waiting for Player.')

                try:
                    if showInfoDialog:
                        # InfoDialogController will unpause after the
                        # the prescribed time

                        self._player.pausePlay()

                    trailerTotalTime = self._player.getTotalTime()
                    maxPlayTime = Settings.getMaxTrailerLength()
                    if trailerTotalTime > maxPlayTime:
                        self.startLongTrailerKiller(maxPlayTime)
                except (AbortException, ShutdownException):
                    raise sys.exc_info()
                except Exception as e:
                    localLogger.logException()

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

                self._player.waitForIsNotPlayingVideo()
                self.cancelLongPlayingTrailerKiller()

                # Again, we rely on our listeners to  stop this display, as
                # appropriate
                if Settings.getShowTrailerTitle():
                    localLogger.debug(u'About to Hide Brief Info')
                    self.setBriefInfoVisibility(False)

                if self._exitDialog:
                    break

                screenSaverState = self.getScreensaverState().getState()
                if screenSaverState == ScreensaverState.DEACTIVATED:
                    # Block until unpaused
                    self.blockPlayingTrailers()

                if limitTrailersToPlay:
                    self._numberOfTrailersToPlay -= 1
                    if self._numberOfTrailersToPlay < 1:
                        break
                self._trailer = next(trailerIterator)

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            localLogger.logException()
        finally:
            localLogger.debug(u'About to close TrailerDialog')
            localLogger.debug(u'About to stop xbmc.Player')
            self._player.stop()
            self.cancelLongPlayingTrailerKiller()
            localLogger.debug(u'Stopped xbmc.Player')

            self.close()
            localLogger.debug(u'Closed TrailerDialog')
            self.shutdown()
            return self._exitDialog

    def doModal(self):
        localLogger = self._logger.getMethodLogger(u'doModal')
        localLogger.enter()

        # In case playing was paused due to screensaver deactivated
        # and now it is being reactivated.

        self.unBlockPlayingTrailers()
        super(TrailerDialog, self).doModal()
        localLogger.exit()
        return self._exitDialog

    def show(self):
        localLogger = self._logger.getMethodLogger(u'show')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)

        super(TrailerDialog, self).show()

    def close(self):
        localLogger = self._logger.getMethodLogger(u'close')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)

        super(TrailerDialog, self).close()

    def blockPlayingTrailers(self):
        '''
            Used to block the main trailer playing loop when the screensaver
            is not active.
        '''
        localLogger = self._logger.getMethodLogger(u'blockPlayingTrailers')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)
        self.close()
        self._pause.clear()
        self._pause.wait()
        localLogger.trace(u'Exiting', trace=Trace.TRACE_SCREENSAVER)

    def unBlockPlayingTrailers(self):
        '''
            Unblocks the main trailer playing loop when the screensaver
            is active.
        '''
        localLogger = self._logger.getMethodLogger(u'unBlockPlayingTrailers')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)
        self._pause.set()

    def exitRandomTrailers(self):
        localLogger = self._logger.getMethodLogger(u'exitRandomTrailers')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._exitDialog = True
        self.killLongPlayingTrailer(informUser=False)
        self._waitEvent.set(ReasonEvent.APPLICATION_EXIT)

    def onScreensaverActivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverActivated')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)

        self._waitEvent.set(ReasonEvent.SCREENSAVER_ACTIVATED)

    def onScreensaverDeactivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverDeactivated')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)

        # Stop showing Movie details
        # getScreensaverState already returns correct info

        self._infoDialogController.dismissInfoDialog(
            reason=u'screensaver deactivated')
        self.close()
        self.killLongPlayingTrailer(informUser=False)

        self._waitEvent.set(ReasonEvent.SCREENSAVER_DEACTIVATED)
        localLogger.trace(u'after setting SCREENSAVER_DEACTIVATED',
                          trace=Trace.TRACE_SCREENSAVER)

    def getScreensaverState(self):
        localLogger = self._logger.getMethodLogger(u'getScreensaverState')
        state = self._screensaverManager.getScreensaverState()
        localLogger.trace(u'state:', state.getState(),
                          trace=Trace.TRACE_SCREENSAVER)
        return state

    def onShutdownEvent(self):
        localLogger = self._logger.getMethodLogger(u'onShutdownEvent')
        localLogger.enter()
        self._shutdown = True
        self._waitEvent.set(ReasonEvent.SHUTDOWN)

    def onAbortEvent(self):
        localLogger = self._logger.getMethodLogger(u'onAbortEvent')
        localLogger.enter()
        self._abort = True
        self._waitEvent.set(ReasonEvent.KODI_ABORT)

    # TODO: put this in own class

    def startLongTrailerKiller(self, maxPlayTime):
        localLogger = self._logger.getMethodLogger(
            u'startLongTrailerKiller')
        localLogger.trace(u'waiting on lock', trace=Trace.TRACE_UI_CONTROLLER)
        with self._lock:
            localLogger.trace(u'got lock, maxPlayTime:',
                              maxPlayTime,
                              trace=Trace.TRACE_UI_CONTROLLER)
            self._longTrailerKiller = None
            if not Monitor.getInstance().isShutdownRequested():
                if maxPlayTime > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                    maxPlayTime -= Constants.MAX_PLAY_TIME_WARNING_TIME
                    localLogger.trace(u'adjusted maxPlayTime:',  maxPlayTime,
                                      trace=Trace.TRACE_UI_CONTROLLER)
                self._longTrailerKiller = threading.Timer(maxPlayTime,
                                                          self.killLongPlayingTrailer)
                self._longTrailerKiller.setName(u'TrailerKiller')
                self._longTrailerKiller.start()

    def killLongPlayingTrailer(self, informUser=True):
        try:
            localLogger = self._logger.getMethodLogger(
                u'killLongPlayingTrailer')
            localLogger.enter()
            localLogger.trace(u'Now Killing',
                              trace=Trace.TRACE_UI_CONTROLLER)

            if informUser:
                self.getTitleControl().setLabel(self._messages.getMsg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))
                self.setBriefInfoVisibility(True)

                # Wait unless interrupted by screen saver inactive, abort

                self._screensaverManager.waitForScreensaverInactive(
                    timeout=Constants.MAX_PLAY_TIME_WARNING_TIME)
            self.setBriefInfoVisibility(False)
            self._player.stop()

            with self._lock:
                self._longTrailerKiller = None
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            Logger.logException(e)

        localLogger.trace(u'exit', trace=Trace.TRACE_SCREENSAVER)

    def cancelLongPlayingTrailerKiller(self):
        localLogger = self._logger.getMethodLogger(
            u'cancelLongPlayingTrailerKiller')
        localLogger.trace(u'enter, waiting on lock',
                          trace=[Trace.TRACE_SCREENSAVER,
                                 Trace.TRACE_UI_CONTROLLER])
        with self._lock:
            if self._longTrailerKiller is not None:
                self._longTrailerKiller.cancel()

    '''
        Callback method from InfoDialog to inform us that it has closed, most
        likely from a timeout. But it could be due to user action.
    '''

    def onInfoDialogClosed(self, reason=u''):
        localLogger = self._logger.getMethodLogger(u'onInfoDialogClosed')
        localLogger.trace(u'reason:', reason, trace=Trace.TRACE_SCREENSAVER)
        stillPlayingTrailers = not Monitor.getInstance().isShutdownRequested()
        screenSaverState = self.getScreensaverState().getState()
        if screenSaverState == ScreensaverState.DEACTIVATED:
            stillPlayingTrailers = False

        if stillPlayingTrailers:
            self._player.resumePlay()
            if Settings.getShowTrailerTitle():
                localLogger.debug(u'About to show Brief Info')
                self.setBriefInfoVisibility(True)

        localLogger.trace(u'exiting', trace=[
                          Trace.TRACE_SCREENSAVER, Trace.TRACE])

    def playNextTrailer(self):
        localLogger = self._logger.getMethodLogger(u'playNextTrailer')
        localLogger.enter()
        if self._infoDialogController is not None:
            self._infoDialogController.dismissInfoDialog()

        self.cancelLongPlayingTrailerKiller()
        self._player.stop()
        localLogger.trace(u'Finished playing old trailer',
                          trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self):
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u'Do not use.')
        return

    def onBack(self, actionId):
        localLogger = self._logger.getMethodLogger(u'onBack')

        localLogger.trace(u'actionId:', str(actionId), trace=Trace.TRACE)

    def onFocus(self, controlId):
        localLogger = self._logger.getMethodLogger(u'onFocus')
        localLogger.debug(u' controlId:' + controlId)

    def onDeinitWindow(self, windowId):
        localLogger = self._logger.getMethodLogger(u'onDeinitWindow')
        localLogger.debug(u'windowId:', windowId)

    def onShowInfo(self):
        localLogger = self._logger.getMethodLogger(u'onShowInfo')
        localLogger.trace(trace=Trace.TRACE)
        self.showDetailedInfo(fromUserRequest=True)

    def onAction(self, action):
        '''
            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next trailer
            ACTION_MOVE_RIGHT -> Skip to next trailer

            PREVIOUS_MENU -> Exit Random Trailer script
                or stop Screensaver
            NAV_BACK -> Exit Random Trailer Script
                or stop screensaver

            PAUSE -> Toggle Play/Pause playing trailer
            PLAY -> Toggle Play/Pause playing trailer

            ENTER -> Play movie for current trailer (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato 
        '''

        localLogger = self._logger.getMethodLogger(u'onAction')

        localLogger.trace(u'Action.id:', str(action.getId()),
                          u'Action.buttonCode:',
                          str(action.getButtonCode()), trace=Trace.TRACE)

        actionMapper = Action.getInstance()
        matches = actionMapper.getKeyIDInfo(action)

        for line in matches:
            localLogger.debug(line)

        actionId = action.getId()
        buttonCode = action.getButtonCode()

        # These return empty string if not found
        actionKey = actionMapper.getActionIDInfo(action)
        remoteButton = actionMapper.getRemoteKeyButtonInfo(action)
        remoteKeyId = actionMapper.getRemoteKeyIDInfo(action)

        # Returns found buttonCode, or u'key_' +  actionButton
        actionButton = actionMapper.getButtonCodeId(action)

        separator = u''
        key = u''
        if actionKey != u'':
            key = actionKey
            separator = u', '
        if remoteButton != u'':
            key = key + separator + remoteButton
            separator = u', '
        if remoteKeyId != u'':
            key = key + separator + remoteKeyId
        if key == u'':
            key = actionButton

        localLogger.debug(u'Key found:', key)

        if actionId == xbmcgui.ACTION_SHOW_INFO or buttonCode == 61513:
            localLogger.debug(key, u'Closing dialog')

            if self._infoDialogController is not None:
                self._infoDialogController.dismissInfoDialog()

        elif (actionId == xbmcgui.ACTION_STOP or actionId == xbmcgui.ACTION_MOVE_RIGHT):
            localLogger.debug(key, u'Play next trailer at user\'s request')
            self.playNextTrailer()

        #
        # PAUSE/PLAY is handled by native player
        #
        elif actionId == xbmcgui.ACTION_QUEUE_ITEM:
            localLogger.debug(key, u'Queue to couch potato')
            strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                self._trailer[Movie.TITLE]
            xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

        elif (actionId == xbmcgui.ACTION_PREVIOUS_MENU
              or actionId == xbmcgui.ACTION_NAV_BACK):
            localLogger.trace(u'Exit application',
                              trace=Trace.TRACE_SCREENSAVER)
            localLogger.debug(key, u'Exiting RandomTrailers at user request')
            if not ScreensaverManager.getInstance().isLaunchedAsScreensaver():
                self.exitRandomTrailers()
            else:
                self._screensaverManager.onScreensaverDeactivated()

        elif actionId == xbmcgui.ACTION_ENTER:
            localLogger.debug(key, u'Play Movie')
            localLogger.debug(u'Playing movie for currently playing trailer.')
            movieFile = self._trailer[Movie.FILE]
            if movieFile == u'':
                self.notifyUser(u'Movie not available for playing trailer')
            else:
                self.playMovie(self._trailer)

        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing trailer

        elif (actionId == xbmcgui.REMOTE_1 or
              actionId == xbmcgui.REMOTE_2 or
              actionId == xbmcgui.REMOTE_3 or
              actionId == xbmcgui.REMOTE_4 or
              actionId == xbmcgui.REMOTE_5 or
              actionId == xbmcgui.REMOTE_6 or
              actionId == xbmcgui.REMOTE_7 or
              actionId == xbmcgui.REMOTE_8 or
              actionId == xbmcgui.REMOTE_9 or
                actionId == xbmcgui.REMOTE_0):
            localLogger.debug(key)
            self.addToPlaylist(actionId, self._trailer)

    def showMovieInfo(self, showDetailInfo=False, showBriefInfo=False):
        if showDetailInfo:
            self.setBriefInfoVisibility(False)
            self.showDetailedInfo()
        #
        # You can have both showInfoDialog (movie details screen
        # shown prior to playing trailer) as well as the
        # simple ShowTrailerTitle while the trailer is playing.
        #
        if showBriefInfo:
            title = self.getTitleString(self._trailer)
            self.getTitleControl().setLabel(title)
            if not showDetailInfo:
                self.setBriefInfoVisibility(True)
            else:
                # Show it after detailInfo is dismissed
                pass

    def setBriefInfoVisibility(self, visible):
        self.getTitleControl().setVisible(visible)

    @logEntryExit
    def showDetailedInfo(self, fromUserRequest=False):
        localLogger = self._logger.getMethodLogger(u'showDetailedInfo')

        if (self._infoDialogController.getInfoDialog() is not None
                and self._source != Movie.SOURCE):
            localLogger.debug(TRACE_STRING + u'about to showDetailedInfo')
            displaySeconds = Settings.getTimeToDisplayDetailInfo()
            if fromUserRequest:
                displaySeconds = 0
            else:  # TODO: I suspect the pause below belongs in the if fromUserRequest
                self._player.pausePlay()

            self._infoDialogController.show(self._trailer, displaySeconds)

    def getTitleControl(self, text=u''):
        localLogger = self._logger.getMethodLogger(u'getTitleControl')
        if self._control is None:
            textColor = u'0xFFFFFFFF'  # White
            shadowColor = u'0x00000000'  # Black
            disabledColor = u'0x0000000'  # Won't matter, screen will be invisible
            xPos = 20
            yPos = 20
            width = 680
            height = 20
            font = u'font13'
            XBFONT_LEFT = 0x00000000
            XBFONT_RIGHT = 0x00000001
            XBFONT_CENTER_X = 0x00000002
            XBFONT_CENTER_Y = 0x00000004
            XBFONT_TRUNCATED = 0x00000008
            XBFONT_JUSTIFIED = 0x00000010
            alignment = XBFONT_CENTER_Y
            hasPath = False
            angle = 0
            self._control = xbmcgui.ControlLabel(xPos, yPos, width, height,
                                                 text, font, textColor,
                                                 disabledColor, alignment,
                                                 hasPath, angle)
            self.addControl(self._control)
            localLogger.exit()

        return self._control

    def shutdown(self):
        localLogger = self._logger.getMethodLogger(u'shutdown')
        localLogger.enter()
        self.close()
        self._player.setCallBacks(onShowInfo=None)
        self._numberOfTrailersToPlay = 0
        if Monitor.getInstance().isShutdownRequested():
            self._player = None
            self._control = None
            self._source = None
            self._trailer = None
            self._viewedPlaylist = None
            self._infoDialogController = None


class InfoDialogController(threading.Thread):
    def __init__(self,  group=None, target=None, name=None,
                 args=(), kwargs={}, verbose=None):
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._trailerDialog = kwargs.get(u'trailerDialog', None)

        name = u'InfoDialogController'
        super(InfoDialogController, self).__init__(group, target, name,
                                                   args, kwargs, verbose)
        WatchDog.registerThread(self)
        self._showTrailerEvent = threading.Event()
        self._infoDialog = InfoDialog(u'script-DialogVideoInfo.xml',
                                      Constants.ADDON_PATH, u'Default', u'720p',
                                      controller=self)
        self._timer = None
        self.start()

    def run(self):
        try:
            localLogger = self._logger.getMethodLogger(u'run')

            while not Monitor.getInstance().isShutdownRequested():
                localLogger.debug(u'waiting')
                self._showTrailerEvent.wait()
                if Monitor.getInstance().isShutdownRequested():
                    break

                localLogger.debug(u'About to show')
                self._showTrailerEvent.clear()
                self._infoDialog.setTrailer(self._trailer)
                self._infoDialog.doModal()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def show(self, trailer, displaySeconds=0):
        localLogger = self._logger.getMethodLogger(u'show')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._infoDialog.close()
        self._trailer = trailer
        self._showTrailerEvent.set()
        self._infoDialog.setTrailer(self._trailer)
        if displaySeconds == 0:
            # One year
            displaySeconds = 365 * 24 * 60 * 60

        self._timer = None
        if not Monitor.getInstance().isShutdownRequested():
            self._timer = threading.Timer(displaySeconds,
                                          self.dismissInfoDialog, kwargs={u'reason': u'timeout'})
            self._timer.setName(u'InfoDialogTimer')
            self._timer.start()

    def dismissInfoDialog(self, reason=u''):
        localLogger = self._logger.getMethodLogger(u'dismissInfoDialog')
        localLogger.enter()
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        if self._timer:
            self._timer.cancel()
        if self._infoDialog is not None:
            self._infoDialog.close()
        if self._trailerDialog is not None:
            self._trailerDialog.onInfoDialogClosed(reason=reason)

    def exitRandomTrailers(self):
        pass

    def playNextTrailer(self):
        self._trailerDialog.playNextTrailer()

    # Not to be called from InfoDialogController thread
    def shutdownThread(self):
        localLogger = self._logger.getMethodLogger(u'shutdown')
        localLogger.enter()
        try:
            self.dismissInfoDialog(u'SHUTDOWN')
            if self._infoDialog is not None:
                del self._infoDialog
                self._infoDialog = None
            if self._showTrailerEvent is not None:
                self._showTrailerEvent.set()
            if self._timer is not None:
                del self._timer
                self._timer = None
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def getInfoDialog(self):
        return self._infoDialog


class InfoDialog(BaseWindow, xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super(InfoDialog, self).__init__(*args, **kwargs)
        # get the optional data and add it to a variable you can use elsewhere
        # in your script
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._titleControl = None
        self._trailer = None
        self._screensaverManager = ScreensaverManager.getInstance()

        self._controller = kwargs.get(u'controller', None)

    def onInit(self):
        try:
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            localLogger = self._logger.getMethodLogger(u'onInit')
            localLogger.enter()
            localLogger.debug(TRACE_STRING)

            control = self.getControl(38001)
            thumbnail = self._trailer[Movie.THUMBNAIL]
            control.setImage(thumbnail)

            self.getControl(38003).setImage(self._trailer[Movie.FANART])

            title_font = getTitleFont()
            titleString = u'title not set'
            if self._trailer is not None:
                titleString = self.getTitleString(self._trailer)
            if self._titleControl is None:
                self._titleControl = xbmcgui.ControlLabel(
                    x=10, y=40, width=760, height=40, label=titleString,
                    font=title_font)
                self.addControl(self._titleControl)
            else:
                self._titleControl.setLabel(titleString)

            title = self.getControl(38002)
            title.setAnimations(
                [('windowclose', 'effect=fade end=0 time=1000')])

            movieDirectors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movieDirectors)

            movieActors = self._trailer[Movie.DETAIL_ACTORS]
            self.getControl(38006).setLabel(movieActors)

            movieDirectors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movieDirectors)

            movieWriters = self._trailer[Movie.DETAIL_WRITERS]
            self.getControl(38007).setLabel(movieWriters)

            plot = self._trailer[Movie.PLOT]
            self.getControl(38009).setText(plot)

            movieStudios = self._trailer[Movie.DETAIL_STUDIOS]
            self.getControl(38010).setLabel(movieStudios)

            label = (self._trailer[Movie.DETAIL_RUNTIME] + u' - ' +
                     self._trailer[Movie.DETAIL_GENRES])
            self.getControl(38011).setLabel(label)

            imgRating = self._trailer[Movie.DETAIL_RATING_IMAGE]
            self.getControl(38013).setImage(imgRating)
            localLogger.exit()
            localLogger.debug(TRACE_STRING + u'exiting')

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)
        finally:
            pass

    def doModal(self):
        localLogger = self._logger.getMethodLogger(u'doModal')
        localLogger.enter()
        super(InfoDialog, self).doModal()

    def setTrailer(self, trailer):
        localLogger = self._logger.getMethodLogger(u'setTrailer')
        localLogger.enter()
        localLogger.debug(TRACE_STRING)
        self._trailer = trailer
        try:
            if self._titleControl is None:
                localLogger.debug(u'titleControl not set')
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)
        finally:
            pass

    def dismiss(self, reason=u''):
        self._controller.dismissInfoDialog(reason)

    #
    # Does not appear to work

    def getFocus(self, control):
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u' DO NOT USE.')
        return
        result = super(InfoDialog, self).getFocus(control)
        localLogger.debug(u' result:' + result)
        return result

    def setFocus(self, control):
        localLogger = self._logger.getMethodLogger(u'setFocus')
        try:
            localLogger.enter()
            super(InfoDialog, self).setFocus(control)
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def setFocusId(self, controlId):
        localLogger = self._logger.getMethodLogger(u'setFocusId')
        try:
            result = super(InfoDialog, self).setFocusId(controlId)
            localLogger.debug(u' result:', result)
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def onClick(self, controlId):
        localLogger = self._logger.getMethodLogger(u'onClick')
        localLogger.debug(u' controlID: ', str(controlId))

    def onBack(self, actionId):
        localLogger = self._logger.getMethodLogger(u'onBack')

        localLogger.debug(u'actionId: ', str(actionId))

    def onControl(self, control):
        localLogger = self._logger.getMethodLogger(u'onControl')

        localLogger.debug(u'controlId: ' + str(control.getId()))

    def onFocus(self, controlId):
        localLogger = self._logger.getMethodLogger(u'onFocus')
        localLogger.debug(u' controlId:' + controlId)

    def onDeinitWindow(self, windowId):
        localLogger = self._logger.getMethodLogger(u'onDeinitWindow')
        localLogger.debug(u'windowId:', windowId)

    def onAction(self, action):
        '''
            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next trailer
            ACTION_MOVE_RIGHT -> Skip to next trailer

            PREVIOUS_MENU -> Exit Random Trailer script
                or stop Screensaver
            NAV_BACK -> Exit Random Trailer Script
                or stop screensaver

            PAUSE -> Toggle Play/Pause playing trailer
            PLAY -> Toggle Play/Pause playing trailer

            ENTER -> Play movie for current trailer (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato 
        '''

        localLogger = self._logger.getMethodLogger(u'onAction')

        localLogger.trace(u' Action.id: ' +
                          str(action.getId()) + u' Action.buttonCode: ' +
                          str(action.getButtonCode()), trace=Trace.TRACE)

        try:
            actionMapper = Action.getInstance()
            matches = actionMapper.getKeyIDInfo(action)

            for line in matches:
                localLogger.debug(line)

            actionId = action.getId()
            buttonCode = action.getButtonCode()

            # These return empty string if not found
            actionKey = actionMapper.getActionIDInfo(action)
            remoteButton = actionMapper.getRemoteKeyButtonInfo(action)
            remoteKeyId = actionMapper.getRemoteKeyIDInfo(action)

            # Returns found buttonCode, or u'key_' +  actionButton
            actionButton = actionMapper.getButtonCodeId(action)

            separator = u''
            key = u''
            if actionKey != u'':
                key = actionKey
                separator = u', '
            if remoteButton != u'':
                key = key + separator + remoteButton
                separator = u', '
            if remoteKeyId != u'':
                key = key + separator + remoteKeyId
            if key == u'':
                key = actionButton

            localLogger.debug(u'Key found:', key)

            #
            # In full-screen xbmc.player.play mode, then the player also reacts to
            # SHOW_INFO. But not in Windowed mode.
            #

            if actionId == xbmcgui.ACTION_SHOW_INFO or buttonCode == 61513:
                localLogger.debug(key, u'Closing dialog')
                self.close()
                self.dismiss(reason=u'Dismiss Info')

            elif (actionId == xbmcgui.ACTION_STOP or actionId == xbmcgui.ACTION_MOVE_RIGHT):
                localLogger.debug(key, u'Play next trailer at user\'s request')
                self.playNextTrailer()        #

            # If full-screen xbmc.player.play mode, then PAUSE/PLAY is handled by
            # native player. But in Windowed mode, it is not.
            #
            elif actionId == xbmcgui.ACTION_QUEUE_ITEM:
                localLogger.debug(key, u'Queue to couch potato')
                strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                    self._trailer[Movie.TITLE]
                xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

            elif (actionId == xbmcgui.ACTION_PREVIOUS_MENU
                  or actionId == xbmcgui.ACTION_NAV_BACK):
                localLogger.debug(
                    key, u'Exiting RandomTrailers at user request')
            if not self._screensaverManager.isLaunchedAsScreensaver():
                self.exitRandomTrailers()
            else:
                self._screensaverManager.onScreensaverDeactivated()

            if actionId == xbmcgui.ACTION_ENTER:
                localLogger.debug(key, u'Play Movie')
                localLogger.debug(
                    u'Playing movie for currently playing trailer.')
                movieFile = self._trailer[Movie.FILE]
                if movieFile == u'':
                    self.notifyUser(u'Movie not available for playing trailer')
                else:
                    self.playMovie(self._trailer)

            # From IR remote as well as keyboard
            # Close InfoDialog and resume playing trailer

            elif (actionId == xbmcgui.REMOTE_1 or
                  actionId == xbmcgui.REMOTE_2 or
                  actionId == xbmcgui.REMOTE_3 or
                  actionId == xbmcgui.REMOTE_4 or
                  actionId == xbmcgui.REMOTE_5 or
                  actionId == xbmcgui.REMOTE_6 or
                  actionId == xbmcgui.REMOTE_7 or
                  actionId == xbmcgui.REMOTE_8 or
                  actionId == xbmcgui.REMOTE_9 or
                    actionId == xbmcgui.REMOTE_0):
                localLogger.debug(key)
                self.addToPlaylist(actionId, self._trailer)
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def exitRandomTrailers(self):
        self.dismiss(reason=u'User exit')
        self._controller.exitRandomTrailers()


def playTrailers(player, blackBackground, runningAsScreensaver=False):
    myTrailerDialog = None
    localLogger = logger.getMethodLogger(u'playTrailers')
    _exit = False
    screenSaverManager = ScreensaverManager.getInstance()

    numberOfTrailersToPlay = Settings.getNumberOfTrailersToPlay()
    if not (_exit or Monitor.getInstance().isShutdownRequested()):
        myTrailerDialog = TrailerDialog(u'script-trailerwindow.xml',
                                        Constants.ADDON_PATH, u'Default',
                                        player=player,
                                        numberOfTrailersToPlay=numberOfTrailersToPlay,
                                        screensaver=runningAsScreensaver)
    GROUP_TRAILERS = False
    if Constants.ADDON.getSetting(u'group_trailers') == u'true':
        GROUP_TRAILERS = True
    GROUP_NUMBER = int(Constants.ADDON.getSetting(u'group_number'))
    trailersInGroup = GROUP_NUMBER
    GROUP_DELAY = Settings.getGroupDelay()
    showOpenCurtain = False  # Already played at startup
    try:
        while not (_exit or Monitor.getInstance().isShutdownRequested()):
            blackBackground.show()

            if showOpenCurtain:
                localLogger.debug(u'Playing OpenCurtain')
                player.play(Settings.getOpenCurtainPath(), windowed=False)
                player.waitForIsNotPlayingVideo()

            # Open curtain before each group

            showOpenCurtain = Settings.getShowCurtains()
            while not Monitor.getInstance().isShutdownRequested():
                Monitor.getInstance().throwExceptionIfShutdownRequested()

                if GROUP_TRAILERS:
                    trailersInGroup = trailersInGroup - 1

                # Play a group of trailers.
                # This will unblock when:
                #    a group has finished playing
                #    screen saver disabled
                #    user request to exit plugin
                #    shutdown/abort

                _exit = myTrailerDialog.doModal()

                # This should not be needed, but....

                player.waitForIsNotPlayingVideo()

                if _exit or screenSaverManager.isScreensaverDeactivated():
                    break

                if not GROUP_TRAILERS:
                    break

                if trailersInGroup == 0:
                    trailersInGroup = GROUP_NUMBER
                    i = GROUP_DELAY
                    while Monitor.getInstance().waitForShutdown(0.500):
                        i = i - 500
                        if i < 0:
                            break

            showCloseCurtain = False
            if _exit or screenSaverManager.isScreensaverDeactivated():
                showCloseCurtain = True
            if Monitor.getInstance().isShutdownRequested():
                showCloseCurtain = False

            if showCloseCurtain:
                if Settings.getShowCurtains():
                    localLogger.debug(u'Playing CloseCurtain')
                    player.play(Settings.getCloseCurtainPath())
                    player.waitForIsNotPlayingVideo()

            blackBackground.close()

            # Block if in screensaver mode and screen saver inactive

            screensaverManager = ScreensaverManager.getInstance()
            if screensaverManager.isLaunchedAsScreensaver():
                screensaverManager.waitForScreensaverActive()

    finally:
        if myTrailerDialog is not None:
            del myTrailerDialog
            myTrailerDialog = None
            localLogger.exit()


def check_for_xsqueeze():
    localLogger = logger.getMethodLogger(u'check_for_xsqueeze')
    localLogger.enter()
    KEYMAPDESTFILE = os.path.join(xbmc.translatePath(
        u'special://userdata/keymaps'), "xsqueeze.xml")
    if os.path.isfile(KEYMAPDESTFILE):
        return True
    else:
        return False

#
# MAIN program
#

# Don't start if Kodi is busy playing something


def myMain(screensaver=False):
    Logger.setAddonName(Constants.addonName)
    localLogger = logger.getMethodLogger(u'myMain')
    localLogger.debug(u'screensaver:', screensaver)
    localLogger.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

    if screensaver and not Settings.isScreensaverEnabled():
        return
    ScreensaverManager.getInstance().setLaunchedAsScreensaver(screensaver)
    blackBackground = None
    try:

        if not xbmc.Player().isPlaying() and not check_for_xsqueeze():
            localLogger.debug(u'Python path: ' + unicode(sys.path))

            # TODO: Use settings

            Trace.enableAll()
            WatchDog.create()
            currentDialogId = xbmcgui.getCurrentWindowDialogId()
            currentWindowId = xbmcgui.getCurrentWindowId()
            localLogger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                              u' ' + str(currentWindowId))

            blackBackground = BlankWindow(u'script-BlankWindow.xml',
                                          Constants.ADDON_PATH, u'Default')
            localLogger.debug(u'Activating BlankWindow')
            blackBackground.show()

            if Settings.getAdjustVolume():
                muted = xbmc.getCondVisibility("Player.Muted")
                if not muted and Settings.getVolume() == 0:
                    xbmc.executebuiltin(u'xbmc.Mute()')
                else:
                    xbmc.executebuiltin(
                        u'XBMC.SetVolume(' + str(Settings.getVolume()) + ')')

            # See if user wants to restrict trailers to a
            # genre

            if Settings.promptForSettings():
                configureSettings()

            _player = AdvancedPlayer()

            if Settings.getShowCurtains():
                _player.play(Settings.getOpenCurtainPath())

            LoadTrailers()

            # Finish curtain playing before proceeding
            if Settings.getShowCurtains():
                _player.waitForIsPlayingVideo(3)
                _player.waitForIsNotPlayingVideo()
            playTrailers(_player, blackBackground,
                         runningAsScreensaver=screensaver)
            if Settings.getAdjustVolume():
                muted = xbmc.getCondVisibility(u'Player.Muted')

                if muted and Settings.getVolume() == 0:
                    xbmc.executebuiltin('xbmc.Mute()')
                else:
                    currentVolume = xbmc.getInfoLabel(u'Player.Volume')
                    currentVolume = int(
                        (float(currentVolume.split(u' ')[0]) + 60.0) / 60.0 * 100.0)
                    xbmc.executebuiltin(
                        'XBMC.SetVolume(' + str(currentVolume) + ')')

            localLogger.debug(u'Shutting down')
            Playlist.shutdown()
        else:
            localLogger.notice(
                'Exiting Random Trailers Screen Saver Something is playing!!!!!!')
    except AbortException:
        localLogger.error(
            'Exiting Random Trailers Screen Saver due to Kodi Abort!')
    except ShutdownException:
        localLogger.error(
            u'Exiting Random Trailers Screen Saver at addon\'s request')
    except Exception as e:
        localLogger.logException(e)

    finally:
        if Monitor.getInstance().isShutdownRequested():
            localLogger.debug(
                u'*********************** SHUTDOWN MAIN **************')
            WatchDog.shutdown()
            Playlist.shutdown()

        localLogger.debug(u'Stopping xbmc.Player')
        xbmc.Player().stop()
        localLogger.debug(u'Deleting black screen')
        if blackBackground is not None:
            blackBackground.close()
            del blackBackground
        localLogger.exit()
