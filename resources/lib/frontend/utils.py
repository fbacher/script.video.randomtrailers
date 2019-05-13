# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: fbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                                 TextType, DEVELOPMENT, RESOURCE_LIB)
from common.constants import Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace
from common.monitor import Monitor
from common.settings import Settings
from player.player_container import PlayerContainer

import threading
from kodi_six import xbmc, xbmcgui


class ReasonEvent(object):
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


class ScreensaverState(object):
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


class ScreenSaverException(Exception):
    pass


class ScreensaverManager(object):
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
        self._is_screen_saver = None
        self._screensaverActiveEvent = threading.Event()
        self._monitor = Monitor.getInstance()
        self._monitor.registerScreensaverListener(self)
        self._monitor.registerShutdownListener(self)
        self._monitor.registerAbortListener(self)

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        self._checkForIdle = threading.Event()
        self._checkForIdle.set()
        self._isAddonActive = True
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
        if not PlayerContainer.getInstance().getPlayer().isActivated():
            PlayerContainer.getInstance.useDummyPlayer()

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
        if not self.isLaunchedAsScreensaver():
            raise ScreenSaverException()

        return self._screensaverState.getState() == ScreensaverState.ACTIVATED

    def isScreensaverDeactivated(self):
        localLogger = self._logger.getMethodLogger(
            u'isScreensaverDeactivated')
        localLogger.trace(
            u'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)

        if not self.isLaunchedAsScreensaver():
            raise ScreenSaverException()
        return self._screensaverState.getState() == ScreensaverState.DEACTIVATED

    def isLaunchedAsScreensaver(self):
        return self._is_screen_saver

    def wakeup(self, is_screen_saver):

        # May be transitioning to a screensaver, or perhaps
        # this invocation was not as a screensaver, but we already are one

        if not self._is_screen_saver:
            self._is_screen_saver = is_screen_saver

        # TODO: resolve how screensaver mode is handled. Is script re-launced
        # each time, or is it made dormant and re-awakened?
        #
        # If a screen saver, then wait for idle period,
        # otherwise, wake up immediately
        # if self._is_screen_saver:
        #    self._checkForIdle.set()
        # else:
        self._checkForIdle.clear()

    def isAddonActive(self):
        return self._isAddonActive

    def setAddonActive(self, isActive):
        self._isAddonActive = isActive

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
        self._monitor.throwExceptionIfShutdownRequested(delay=0)

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
        self._monitor.throwExceptionIfShutdownRequested(delay=0)

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

                # Can wait on monitored event
                if xbmc.Player().isPlaying():
                    Monitor.getInstance().throwExceptionIfShutdownRequested(delay=0.5)
                    continue

                # If idle for x seconds, then reactivate the screen saver. Kodi's
                # getGlobalIdleTime considers our player as idle whether it is
                # playing something or not.

                idle = False
                startScreensaverAfterIdleSeconds = Settings.getIdleTimeout()
                waitTime = startScreensaverAfterIdleSeconds
                while not idle:
                    Monitor.getInstance().throwExceptionIfShutdownRequested(delay=waitTime)

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
        except (Exception) as e:
            Logger.logException(e)


class BaseWindow(object):

    '''
        A transparent window (all WindowDialogs are transparent) to contain
        our listeners and Title display.
    '''

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)

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

        self.exitRandomTrailers()
        listItem = xbmcgui.ListItem(label=trailer[Movie.TITLE],
                                    thumbnailImage=trailer[Movie.THUMBNAIL],
                                    path=trailer[Movie.FILE])
        listItem.setInfo(type=u'video',
                         infoLabels={u'genre': trailer[Movie.GENRE],
                                     u'path': trailer[Movie.FILE],
                                     u'plot': trailer[Movie.PLOT]})
        listItem.setProperty(u'isPlayable', u'true')

        xbmc.Player.play(trailer[Movie.FILE].encode(u'utf-8'), listitem=listItem,
                         windowed=False)
        #"PlayMedia(media[,isdir][,1],[playoffset=xx])"
        #command = 'XBMC.NotifyAll({0}.SIGNAL,{1},{2})'.format(source_id, signal,_encodeData(data))
        # xbmc.executebuiltin(command)

    def getTitleString(self, trailer):
        title = u'[B]' + trailer[Movie.DETAIL_TITLE] + u'[/B]'
        title2 = trailer[Movie.DETAIL_TITLE]
        return title
