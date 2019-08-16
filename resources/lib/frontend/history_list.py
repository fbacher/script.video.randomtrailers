# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import threading
from collections import deque

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import (Logger, LazyLogger, Trace)
from common.messages import Messages
from common.monitor import Monitor

from frontend.history_empty import HistoryEmpty

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('frontend.history_list')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class HistoryList(object):
    """

    """
    MAX_HISTORY = 20

    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__()
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._buffer = []  # type: List[MovieType]
        self._cursor = int(-1)  # type: int

    def append(self, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        self._logger.enter('movie', movie[Movie.TITLE], 'len(buffer):',
                        len(self._buffer), 'cursor:', self._cursor)
        self._buffer.append(movie)
        if len(self._buffer) > HistoryList.MAX_HISTORY:
            # Delete oldest entry
            del self._buffer[0]
        self._cursor = len(self._buffer) - 1

    def get_previous_movie(self):
        # type: () -> MovieType
        """

        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('cursor:', self._cursor)
        # cursor points to currently playing movie or -1
        self._cursor -= 1
        if self._cursor <= -1:
            self._cursor = -1
            movie = None
            raise HistoryEmpty()
        else:
            movie = self._buffer[self._cursor]

        return movie
