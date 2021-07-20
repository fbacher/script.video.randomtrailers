# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''


from common.imports import *
from common.logger import LazyLogger
from common.movie import AbstractMovie

from frontend.history_empty import HistoryEmpty

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class HistoryList:
    """

    """
    MAX_HISTORY: int = 20
    logger: LazyLogger = None
    _buffer: List[AbstractMovie] = []
    _cursor: int = -1

    @classmethod
    def class_init(cls) -> None:
        """

        """
        cls.logger = module_logger.getChild(cls.__class__.__name__)
        cls._buffer: List[AbstractMovie] = []
        cls._cursor: int = -1

    @classmethod
    def append(cls, movie: AbstractMovie) -> None:
        """

        :param movie:
        :return:
        """
        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls.logger.enter('movie', movie.get_title(), 'len(buffer):',
                               len(cls._buffer), 'cursor:', cls._cursor)
        cls._buffer.append(movie)
        if len(cls._buffer) > HistoryList.MAX_HISTORY:
            # Delete oldest entry
            del cls._buffer[0]
        cls._cursor = len(cls._buffer) - 1
        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls.logger.exit('movie', movie.get_title(), 'len(buffer):',
                            len(cls._buffer), 'cursor:', cls._cursor)

    @classmethod
    def has_previous_trailer(cls) -> bool:
        has_previous = True
        if cls._cursor < 1:
            has_previous = False
        return has_previous

    @classmethod
    def get_previous_trailer(cls) -> AbstractMovie:
        """

        :return:
        """
        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
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

        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls.logger.exit('movie', movie.get_title(), 'len(buffer):',
                            len(cls._buffer), 'cursor:', cls._cursor)
        return movie

    @classmethod
    def get_next_trailer(cls) -> AbstractMovie:
        """
        Play the next trailer in the history buffer.
        :return: The next trailer in the buffer or None, if there are none.
        """
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.enter('len(buffer):',
                             len(cls._buffer), 'cursor:',
                             cls._cursor)  # cursor points to currently playing
                                           # movie or -1
        cls._cursor += 1
        if cls._cursor <= -1:
            cls._cursor = 0
        if cls._cursor > len(cls._buffer) - 1:
            movie = None
            title = 'None'
            cls._cursor = len(cls._buffer) - 1
        else:
            movie = cls._buffer[cls._cursor]
            title = movie.get_title()
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            cls.logger.exit('movie', title, 'len(buffer):',
                            len(cls._buffer), 'cursor:', cls._cursor)
        return movie

    @classmethod
    def remove(cls, movie: AbstractMovie) -> None:
        try:
            i = cls._buffer.index(movie)
            del cls._buffer[i]
            if cls._cursor > len(cls._buffer) - 1:
                cls._cursor = len(cls._buffer) - 1
        except Exception as e:
            pass # Does not exist in list


HistoryList.class_init()
