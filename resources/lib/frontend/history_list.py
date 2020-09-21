# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''

import sys
import threading
from collections import deque

from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.imports import *
from common.logger import (LazyLogger, Trace)
from common.messages import Messages
from common.monitor import Monitor

from frontend.history_empty import HistoryEmpty

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class HistoryList(object):
    """

    """
    MAX_HISTORY = 20
    logger: LazyLogger = None
    _buffer: List[MovieType] = []
    _cursor: int = int(-1)

    @classmethod
    def class_init(cls):
        # type: () -> None
        """

        """
        cls.logger = module_logger.getChild(cls.__class__.__name__)
        cls._buffer = []  # type: List[MovieType]
        cls._cursor = int(-1)  # type: int

    @classmethod
    def append(cls, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.enter('movie', movie[Movie.TITLE], 'len(buffer):',
                               len(cls._buffer), 'cursor:', cls._cursor)
        cls._buffer.append(movie)
        if len(cls._buffer) > HistoryList.MAX_HISTORY:
            # Delete oldest entry
            del cls._buffer[0]
        cls._cursor = len(cls._buffer) - 1
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.exit('movie', movie[Movie.TITLE], 'len(buffer):',
                             len(cls._buffer), 'cursor:', cls._cursor)

    @classmethod
    def get_previous_movie(cls):
        # type: () -> MovieType
        """

        :return:
        """
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.enter('len(buffer):',
                               len(cls._buffer), 'cursor:', cls._cursor)
        # cursor points to currently playing movie or -1
        cls._cursor -= 1
        if cls._cursor < 0:
            cls._cursor = -1
            movie = None
            raise HistoryEmpty()
        else:
            movie = cls._buffer[cls._cursor]

        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.exit('movie', movie[Movie.TITLE], 'len(buffer):',
                              len(cls._buffer), 'cursor:', cls._cursor)
        return movie

    @classmethod
    def get_next_movie(cls):
        # type: () -> MovieType
        """
        Play the next movie in the history buffer.
        :return: The next movie in the buffer or None, if there are none.
        """
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.enter('len(buffer):',
                               len(cls._buffer), 'cursor:',
                               cls._cursor)  # cursor points to currently playing
            # movie or -1
        cls._cursor += 1
        if cls._cursor <= -1:
            cls._cursor = 0
        if len(cls._buffer) < (cls._cursor + 1):
            movie = None
            title = 'None'
        else:
            movie = cls._buffer[cls._cursor]
            title = movie[Movie.TITLE]
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.exit('movie', title, 'len(buffer):',
                              len(cls._buffer), 'cursor:', cls._cursor)
        return movie

    @classmethod
    def remove(cls, movie):
        try:
            i = cls._buffer.index(movie)
            del cls._buffer[i]
            if cls._cursor >  len(cls._buffer) - 1:
                cls._cursor = len(cls._buffer) - 1
        except Exception as e:
            pass # Does not exist in list


HistoryList.class_init()