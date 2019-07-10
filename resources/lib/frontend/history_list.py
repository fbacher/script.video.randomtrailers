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
from common.logger import Logger, Trace
from common.messages import Messages
from common.monitor import Monitor

from frontend.history_empty import HistoryEmpty


class HistoryList(object):
    """

    """
    MAX_HISTORY = 20

    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__()
        self._logger = Logger(self.__class__.__name__)
        local_logger = self._logger.get_method_logger('__init__')
        self._buffer = []  # type: List[MovieType]
        self._cursor = int(0)  # type: int

    def append(self, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        local_logger = self._logger.get_method_logger('append')
        local_logger.enter('movie', movie[Movie.TITLE], 'len(buffer):',
                        len(self._buffer), 'cursor:', self._cursor)
        if len(self._buffer) > HistoryList.MAX_HISTORY:
            # Delete oldest entry
            del self._buffer[0]
        self._buffer.append(movie)
        self._cursor = len(self._buffer) - 1

    def getPreviousMovie(self):
        # type: () -> MovieType
        """

        :return:
        """
        local_logger = self._logger.get_method_logger('getPreviousMovie')
        local_logger.debug('cursor:', self._cursor)
        if self._cursor == -1:
            movie = None
            raise HistoryEmpty()
        else:
            movie = self._buffer[self._cursor]
            self._cursor -= 1

        return movie
