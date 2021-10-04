# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''
import sys

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
            cls.logger.enter(f'Adding movie: {movie.get_title()} '
                             f'len: '
                             f'{len(cls._buffer)} cursor: {cls._cursor}')
        duplicate = False
        a_movie: AbstractMovie
        for a_movie in cls._buffer:
            if ((a_movie.get_title() == movie.get_title())
                    and (a_movie.get_year() == movie.get_year())):
                duplicate = True
                break

        if duplicate:
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.logger.debug_extra_verbose(f'Not adding duplicate movie to history: '
                                               f'movie.get_title()')
                cls.dump_history()
            return

        cls._buffer.append(movie)

        # If buffer is over-full, correct
        if len(cls._buffer) > HistoryList.MAX_HISTORY:
            # Delete oldest entry
            del cls._buffer[0]
            # Adjust cursor index
            # Note that even if other events have altered cursor before we
            # have chance to adjust, it will still point to the whatever trailer
            # was or is being played. In the worst case, where we somehow
            # managed to back up to play MAX_HISTORY times before playing the next
            # trailer, the cursor will go negative, but get_next_trailer accounts
            # for this and will set it to 0.

            cls._cursor -= 1
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.dump_history()

    @classmethod
    def dump_history(cls) -> None:
        if cls.logger.isEnabledFor(LazyLogger.DISABLED):
            i: int = 0
            for a_movie in cls._buffer:
                cls.logger.debug_extra_verbose(f'index: {i} movie: {a_movie.get_title()}')
                i += 1

            cls.logger.debug_extra_verbose(f'len: {len(cls._buffer)} '
                                           f'cursor: {cls._cursor}')


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
            cls.logger.enter(f'len: {len(cls._buffer)} cursor: {cls._cursor}')

        movie: AbstractMovie = None

        try:
            # cursor points to currently playing movie or -1
            cls._cursor -= 1
            if cls._cursor < 0:
                cls._cursor = -1
                raise HistoryEmpty()

            # Check should not be needed
            if cls._cursor > len(cls._buffer) - 1:
                cls._cursor = len(cls._buffer) - 1

            movie = cls._buffer[cls._cursor]
        except HistoryEmpty:
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.logger.debug_extra_verbose(f'HistoryEmpty')
            reraise(*sys.exc_info())

        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            title: str = 'None'
            if movie is not None:
                title = movie.get_title()
            cls.logger.exit(f'movie: {title} len: '
                            f'{len(cls._buffer)} cursor: {cls._cursor}')
        return movie

    @classmethod
    def get_next_trailer(cls) -> AbstractMovie:
        """
        Play the next trailer in the history buffer.
        :return: The next trailer in the buffer or None, if there is none
                 (which causes external code to add another trailer from the
                 backend)
        """
        # cursor points to currently playing
        # movie or -1

        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls.logger.enter(f'len: {len(cls._buffer)} cursor: {cls._cursor}')

        movie: AbstractMovie = None
        if len(cls._buffer) == 0:
            cls._cursor = -1
            # return movie  # None

        elif (cls._cursor + 1) > len(cls._buffer) - 1:
            # return movie  # None
            pass

        else:
            cls._cursor += 1  # Advance only when we know it will work!
            movie = cls._buffer[cls._cursor]

        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            title: str = 'None'
            if movie is not None:
                title = movie.get_title()

            cls.logger.exit(f'movie: {title} len: '
                            f'{len(cls._buffer)} cursor: {cls._cursor}')
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
