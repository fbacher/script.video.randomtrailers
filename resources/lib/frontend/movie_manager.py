# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import datetime
import sys
import threading
import queue
import six

from kodi_six import xbmc, xbmcgui

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException, LogicError
from common.logger import (Logger, LazyLogger, Trace, log_entry_exit)
from common.messages import Messages
from common.monitor import Monitor
from frontend.front_end_bridge import FrontendBridge, FrontendBridgeStatus
from common.settings import Settings
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
from frontend.history_list import HistoryList
from frontend.history_empty import HistoryEmpty

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger(
    ).getChild('frontend.movie_manager')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class MovieStatus(FrontendBridgeStatus):
    PREVIOUS_MOVIE = 'PREVIOUS_MOVIE'
    NEXT_MOVIE = 'NEXT_MOVIE'

class MovieManager(object):

    OPEN_CURTAIN = True
    CLOSE_CURTAIN = False

    def __init__(self):
        # type: () -> None
        """
        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        super().__init__()
        self._movie_history = None
        self._play_open_curtain_next = None
        self._play_close_curtain_next = None
        self._movie_history = HistoryList()
        self._movie_history_cursor = None
        self.front_end_bridge = FrontendBridge.get_instance()
        self._play_open_curtain_next = Settings.get_show_curtains()
        self._play_next_trailer = False
        self._play_previous_trailer = False
        self._thread = None
        self._queuedMovie = None
        self._pre_fetched_trailer_queue = queue.Queue(2)
        self.fetched_event = threading.Event()
        self.pre_fetch_trailer()

    def get_next_trailer(self):
        # type: () -> (TextType, MovieType)
        """

        :return:
        """
        trailer = None
        status = None
        prefetched = False
        if self._play_open_curtain_next:
            status = MovieStatus.OK
            trailer = {Movie.SOURCE: 'curtain',
                       Movie.TITLE: 'openCurtain',
                       Movie.TRAILER: Settings.get_open_curtain_path()}
            self._play_open_curtain_next = False
        elif self._play_close_curtain_next:
            status = MovieStatus.OK
            trailer = {Movie.SOURCE: 'curtain',
                       Movie.TITLE: 'closeCurtain',
                       Movie.TRAILER: Settings.get_close_curtain_path()}
            self._play_close_curtain_next = False
        elif self._play_previous_trailer:
            status = MovieStatus.PREVIOUS_MOVIE
            self._play_previous_trailer = False
            try:
                trailer = self._movie_history.get_previous_movie()
            except (HistoryEmpty):
                six.reraise(*sys.exc_info())
        elif self._play_next_trailer:
            status = MovieStatus.NEXT_MOVIE
            self._play_next_trailer = False
            trailer = self._movie_history.get_next_movie()
            if trailer is None:
                trailer = self._pre_fetched_trailer_queue.get()
                self._movie_history.append(trailer)
        else:
            status = MovieStatus.OK
            trailer = self._movie_history.get_next_movie()
            if trailer is None:
                trailer = self._pre_fetched_trailer_queue.get()
                self._movie_history.append(trailer)

        title = None
        if trailer is not None:
            title = trailer.get(Movie.TITLE)
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.exit('status:', status, 'trailer', title)

        return status, trailer

    def pre_fetch_trailer(self):
        self._thread = threading.Thread(
            target=self._pre_fetch_trailer, name='Pre-Fetch trailer')
        self._thread.start()

    def _pre_fetch_trailer(self):
        while not Monitor.is_shutdown_requested():
            status, trailer = self.front_end_bridge.get_next_trailer()
            if trailer is not None:
                added = False
                while not added:
                    try:
                        self._pre_fetched_trailer_queue.put(trailer, timeout=0.1)
                        added = True
                    except queue.Full:
                        if Monitor.wait_for_shutdown(timeout=1.0):
                            break

    # Put trailer in recent history. If full, delete oldest
    # entry. User can traverse backwards through shown
    # trailers

    def play_previous_trailer(self):
        # type: () -> None
        """

        :return:
        """

        # TODO: probably not needed
        self._logger.enter()
        self._play_previous_trailer = True

    def play_next_trailer(self):
        # type: () -> None
        """

        :return:
        """

        # TODO: probably not needed
        self._logger.enter()
        self._play_next_trailer = True

    def play_curtain_next(self, curtain_type):
        if curtain_type == MovieManager.OPEN_CURTAIN:
            self._play_open_curtain_next = True
            self._play_close_curtain_next = False
        elif curtain_type == MovieManager.CLOSE_CURTAIN:
            self._play_open_curtain_next = False
            self._play_close_curtain_next = True
        else:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Must specify OPEN or CLOSE curtain')
            raise LogicError()
