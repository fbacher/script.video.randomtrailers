# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: fbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

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
        ScreensaverManager._logger = Logger(self.__class__.__name__)
        local_logger = self._logger.get_method_logger('__init__')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._screensaverState = ScreensaverState.getInstance()
        self._screensaverStateChanged = threading.Event()
        self._screenSaverListeners = []
        self._screensaverInactiveEvent = threading.Event()
        self._is_screen_saver = None
        self._screensaverActiveEvent = threading.Event()
        self._monitor = Monitor.get_instance()
        self._monitor.register_shutdown_listener(self.on_shutdown_event)
        self._monitor.register_abort_listener(self.on_abort_event)

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

    @staticmethod
    def get_instance():
        if ScreensaverManager._instance is None:
            ScreensaverManager._instance = ScreensaverManager()
        local_logger = ScreensaverManager._logger.get_method_logger(
            'get_instance')
        local_logger.trace('enter', trace=Trace.TRACE_SCREENSAVER)
        return ScreensaverManager._instance

    def on_shutdown_event(self):
        local_logger = self._logger.get_method_logger('on_shutdown_event')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)

        # Make sure that restartScreensaverOnIdle thread can exit

        self._screensaverStateChanged.set()

        # Set these events so that the code will fall-through
        # and check for AbortandShutdown

        self._screensaverInactiveEvent.set()
        self._screensaverActiveEvent.set()

    def on_abort_event(self):
        self.on_shutdown_event()

    def inform_screensaver_listeners(self, activated=True):
        local_logger = self._logger.get_method_logger(
            'inform_screensaver_listeners')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        for listener in self._screenSaverListeners:
            if activated:
                listener.onScreensaverActivated()
            else:
                listener.onScreensaverDeactivated()

    def get_screensaver_state(self):
        local_logger = self._logger.get_method_logger(
            'get_screensaver_state')
        local_logger.trace(
            'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)
        return self._screensaverState

    def isScreensaverActivated(self):
        local_logger = self._logger.get_method_logger(
            'isScreensaverActivated')
        local_logger.trace(
            'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)
        if not self.is_launched_as_screensaver():
            raise ScreenSaverException()

        return self._screensaverState.getState() == ScreensaverState.ACTIVATED

    def isScreensaverDeactivated(self):
        local_logger = self._logger.get_method_logger(
            'isScreensaverDeactivated')
        local_logger.trace(
            'state:', self._screensaverState.getState(), trace=Trace.TRACE_SCREENSAVER)

        if not self.is_launched_as_screensaver():
            raise ScreenSaverException()
        return self._screensaverState.getState() == ScreensaverState.DEACTIVATED

    def is_launched_as_screensaver(self):
        return self._is_screen_saver

    # def wakeup(self, is_screen_saver):

        # May be transitioning to a screensaver, or perhaps
        # this invocation was not as a screensaver, but we already are one

        # if not self._is_screen_saver:
        #    self._is_screen_saver = is_screen_saver

        # TODO: resolve how screensaver mode is handled. Is script re-launced
        # each time, or is it made dormant and re-awakened?
        #
        # If a screen saver, then wait for idle period,
        # otherwise, wake up immediately
        # if self._is_screen_saver:
        #    self._checkForIdle.set()
        # else:
        # self._checkForIdle.clear()

    # def isAddonActive(self):
    #    return self._isAddonActive

    # def setAddonActive(self, isActive):
    #    self._isAddonActive = isActive

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
        self._monitor.throw_exception_if_abort_requested(timeout=0)
        self._monitor.throw_exception_if_shutdown_requested(delay=0)

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
        self._monitor.throw_exception_if_abort_requested(timeout=0)
        self._monitor.throw_exception_if_shutdown_requested(delay=0)

class BaseWindow(object):

    '''
        A transparent window (all WindowDialogs are transparent) to contain
        our listeners and Title display.
    '''

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)

    def add_to_playlist(self, playListId, trailer):
        local_logger = self._logger.get_method_logger('addToPlayList')
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
            local_logger.error(
                'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.getPlaylist(playlist_file).recordPlayedTrailer(trailer)

    def notifyUser(self, msg):
        # TODO: Supply code
        local_logger = self._logger.get_method_logger('notifyUser')
        local_logger.debug(msg)

    def play_movie(self, trailer):
        # TODO: Supply code
        local_logger = self._logger.get_method_logger('queue_movie')
        local_logger.debug('Playing movie at user request:',
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
