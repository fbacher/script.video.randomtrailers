# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, MovieType, DEVELOPMENT, RESOURCE_LIB)
import sys
import threading

import six

from kodi_six import xbmc, xbmcgui

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException, LogicError
from common.logger import Logger, Trace, log_entry_exit
from common.messages import Messages
from common.monitor import Monitor
from frontend.front_end_bridge import FrontendBridge, FrontendBridgeStatus
from action_map import Action
from common.settings import Settings
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
from frontend.history_list import HistoryList
from frontend.history_empty import HistoryEmpty

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState

class MovieStatus(FrontendBridgeStatus):
     PREVIOUS_MOVIE = u'PREVIOUS_MOVIE'


class MovieManager(object):

    OPEN_CURTAIN = True
    CLOSE_CURTAIN = False

    def __init__(self):
        # type: () -> None
        """
        """
        self._logger = Logger(self.__class__.__name__)
        local_logger = self._logger.get_method_logger(u'__init__')
        super().__init__()
        self._movie_history = None
        self._play_open_curtain_next = None
        self._play_close_curtain_next = None
        self._movie_history = HistoryList()
        self._movie_history_cursor = None
        self.front_end_bridge = FrontendBridge.get_instance()
        self._play_open_curtain_next = Settings.get_show_curtains()
        self._play_previous_trailer = False
        self._queuedMovie = None

    def get_next_trailer(self):
        # type: () -> (TextType, MovieType)
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(u'get_next_trailer')

        if self._play_open_curtain_next:
            status = MovieStatus.OK
            trailer = {Movie.SOURCE: u'curtain',
                       Movie.TITLE: u'openCurtain',
                       Movie.TRAILER: Settings.get_open_curtain_path()}
            self._play_open_curtain_next = False
        elif self._play_close_curtain_next:
            status = MovieStatus.OK
            trailer = {Movie.SOURCE: u'curtain',
                       Movie.TITLE: u'closeCurtain',
                       Movie.TRAILER: Settings.get_close_curtain_path()}
            self._play_close_curtain_next = False
        elif self._play_previous_trailer:
            status = MovieStatus.PREVIOUS_MOVIE
            self._play_previous_trailer = False
            try:
                trailer = self._movie_history.getPreviousMovie()
            except (HistoryEmpty):
                six.reraise(*sys.exc_info())
        else:
            status, trailer = self.front_end_bridge.get_next_trailer()
            if trailer is not None:
                # Put trailer in recent history. If full, delete oldest
                # entry. User can traverse backwards through shown
                # trailers

                self._movie_history.append(trailer)

        title = None
        if trailer is not None:
            title = trailer.get(Movie.TITLE)
        local_logger.exit(u'status:', status, u'trailer', title)

        return status, trailer

    def play_previous_trailer(self):
        # type: () -> None
        """

        :return:
        """

        # TODO: probably not needed
        local_logger = self._logger.get_method_logger(u'play_previous_trailer')
        local_logger.enter()
        self._play_previous_trailer = True


    def play_curtain_next(self, curtainType):
        local_logger = self._logger.get_method_logger(u'play_curtain_next')

        if curtainType == MovieManager.OPEN_CURTAIN:
            self._play_open_curtain_next = True
            self._play_close_curtain_next = False
        elif curtainType == MovieManager.CLOSE_CURTAIN:
            self._play_open_curtain_next = False
            self._play_close_curtain_next = True
        else:
            local_logger.debug(u'Must specify OPEN or CLOSE curtain')
            raise LogicError()
