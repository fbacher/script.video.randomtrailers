# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: fbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.constants import (Constants, Movie)
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import (Logger, LazyLogger, Trace)
from common.monitor import Monitor
from common.settings import Settings
from player.player_container import PlayerContainer

import threading
from kodi_six import xbmc, xbmcgui

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('frontend.utils')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class ReasonEvent(object):
    '''
        Provides a threading.Event with an attached reason
    '''
    TIMED_OUT = 'timed out'
    CLEARED = 'Cleared'
    KODI_ABORT = 'Kodi Abort'
    SHUTDOWN = 'Shutdown'
    RUN_STATE_CHANGE = 'Run State Changed'

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
    ACTIVATED = 'screensaver activated'
    DEACTIVATED = 'screensaver de-activated'

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
        ScreensaverManager._logger = module_logger.getChild(self.__class__.__name__)
        # self._screensaverState = ScreensaverState.getInstance()
        self._screensaverStateChanged = threading.Event()
        self._screenSaverListeners = []
        self._is_screen_saver = None
        self._screensaverActiveEvent = threading.Event()
        self._monitor = Monitor.get_instance()

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

    @staticmethod
    def get_instance():
        if ScreensaverManager._instance is None:
            ScreensaverManager._instance = ScreensaverManager()
        if ScreensaverManager._logger.isEnabledFor(Logger.DEBUG):
            ScreensaverManager._logger.debug('enter', trace=Trace.TRACE_SCREENSAVER)
        return ScreensaverManager._instance

    def inform_screensaver_listeners(self, activated=True):
        if ScreensaverManager._logger.isEnabledFor(Logger.DEBUG):
            ScreensaverManager._logger.debug(trace=Trace.TRACE_SCREENSAVER)
        for listener in self._screenSaverListeners:
            if activated:
                listener.onScreensaverActivated()
            else:
                listener.onScreensaverDeactivated()

    def get_screensaver_state(self):
        if ScreensaverManager._logger.isEnabledFor(Logger.DEBUG):
            ScreensaverManager._logger.debug(
                'state:', self._screensaverState.getState(),
                trace=Trace.TRACE_SCREENSAVER)
        return self._screensaverState

    def isScreensaverActivated(self):
        if ScreensaverManager._logger.isEnabledFor(Logger.DEBUG):
            ScreensaverManager._logger.debug(
                'state:', self._screensaverState.getState(),
                trace=Trace.TRACE_SCREENSAVER)
        if not self.is_launched_as_screensaver():
            raise ScreenSaverException()

        return self._screensaverState.getState() == ScreensaverState.ACTIVATED

    def isScreensaverDeactivated(self):
        if ScreensaverManager._logger.isEnabledFor(Logger.DEBUG):
            ScreensaverManager._logger.debug(
                'state:', self._screensaverState.getState(),
                trace=Trace.TRACE_SCREENSAVER)

        if not self.is_launched_as_screensaver():
            raise ScreenSaverException()
        return self._screensaverState.getState() == ScreensaverState.DEACTIVATED

    def is_launched_as_screensaver(self):
        return self._is_screen_saver

class BaseWindow(object):

    '''
        A transparent window (all WindowDialogs are transparent) to contain
        our listeners and Title display.
    '''

    def __init__(self):
        self._logger = module_logger.getChild(self.__class__.__name__)

    def add_to_playlist(self, playListId, trailer):
        _playlistMap = {xbmcgui.REMOTE_1:
                        Playlist.PLAYLIST_PREFIX + '1' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_2:
                        Playlist.PLAYLIST_PREFIX + '2' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_3:
                        Playlist.PLAYLIST_PREFIX + '3' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_4:
                        Playlist.PLAYLIST_PREFIX + '4' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_5:
                        Playlist.PLAYLIST_PREFIX + '5' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_6:
                        Playlist.PLAYLIST_PREFIX + '6' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_7:
                        Playlist.PLAYLIST_PREFIX + '7' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_8:
                        Playlist.PLAYLIST_PREFIX + '8' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_9:
                        Playlist.PLAYLIST_PREFIX + '9' + Playlist.PLAYLIST_SUFFIX,
                        xbmcgui.REMOTE_0:
                        Playlist.PLAYLIST_PREFIX + '10' + Playlist.PLAYLIST_SUFFIX}
        playlist_file = _playlistMap.get(playListId, None)
        if playlist_file is None:
            self._logger.error(
                'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.getPlaylist(playlist_file).recordPlayedTrailer(trailer)

    def notifyUser(self, msg):
        # TODO: Supply code
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(msg)

    def play_movie(self, trailer):
        # TODO: Supply code
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Playing movie at user request:',
                          trailer[Movie.TITLE])

        self.exitRandomTrailers()
        listItem = xbmcgui.ListItem(label=trailer[Movie.TITLE],
                                    thumbnailImage=trailer[Movie.THUMBNAIL],
                                    path=trailer[Movie.FILE])
        listItem.setInfo(type='video',
                         infoLabels={'genre': trailer[Movie.GENRE],
                                     'path': trailer[Movie.FILE],
                                     'plot': trailer[Movie.PLOT]})
        listItem.setProperty('isPlayable', 'true')

        xbmc.Player.play(trailer[Movie.FILE].encode('utf-8'), listitem=listItem,
                         windowed=False)
        #"PlayMedia(media[,isdir][,1],[playoffset=xx])"
        #command = 'XBMC.NotifyAll({0}.SIGNAL,{1},{2})'.format(source_id, signal,_encodeData(data))
        # xbmc.executebuiltin(command)

    def getTitleString(self, trailer):
        title = '[B]' + trailer[Movie.DETAIL_TITLE] + '[/B]'
        title2 = trailer[Movie.DETAIL_TITLE]
        return title
