# -*- coding: utf-8 -*-
"""
Created on 6/2/21

@author: Frank Feuerbacher
"""
import random
import threading

from common.imports import *
from common.logger import LazyLogger
from common.movie import AbstractMovie


module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class RecentTrailerHistory:

    MAXIMUM_HISTORY: Final[int] = 20

    logger: LazyLogger = None

    _trailer_history: Final[List[AbstractMovie]] = []
    _lock: Final[threading.RLock] = threading.RLock()

    @classmethod
    def __class_init__(cls) -> None:
        cls.logger = module_logger.getChild(f'{cls.__name__}')

    @classmethod
    def get_trailer(cls) -> AbstractMovie:
        with cls._lock:
            if len(cls._trailer_history) == 0:
                return None

            index: int = random.randint(0, len(cls._trailer_history) - 1)
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.logger.debug_extra_verbose(f'len: {len(cls._trailer_history)} '
                                               f'getting: {cls._trailer_history[index].get_title()}')
            return cls._trailer_history[index]

    @classmethod
    def add_trailer(cls, movie: AbstractMovie) -> None:
        with cls._lock:
            cls._trailer_history.append(movie)
            if cls.logger.isEnabledFor(LazyLogger.DISABLED):
                cls.logger.debug_extra_verbose(f'adding: {movie.get_title()}')
            if len(cls._trailer_history) > cls.MAXIMUM_HISTORY:
                del cls._trailer_history[0]
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(f'history[0]:'
                                                   f'{cls._trailer_history[0].get_title()}')

    @classmethod
    def get_number_of_trailers(cls) -> int:
        return len(cls._trailer_history)


class RecentlyPlayedTrailers:

    @classmethod
    def __class_init__(cls):
        pass

    @classmethod
    def get_recently_played(cls) -> AbstractMovie:
        return RecentTrailerHistory.get_trailer()

    @classmethod
    def add_played_trailer(cls, movie: AbstractMovie) -> None:
        return RecentTrailerHistory.add_trailer(movie)

    @classmethod
    def get_number_of_trailers(cls) -> int:
        return RecentTrailerHistory.get_number_of_trailers()


RecentTrailerHistory.__class_init__()
