# -*- coding: utf-8 -*-
"""
Created on 6/2/21

@author: Frank Feuerbacher
"""
import random
import threading

from common.imports import *
from common.movie import AbstractMovie


class RecentTrailerHistory:

    MAXIMUM_HISTORY: Final[int] = 20
    _trailer_history: Final[List[AbstractMovie]] = []
    _lock: Final[threading.RLock] = threading.RLock()

    @classmethod
    def __class_init__(cls) -> None:
        pass

    @classmethod
    def get_trailer(cls) -> AbstractMovie:
        with cls._lock:
            if len(cls._trailer_history) == 0:
                return None

            index: int = random.randint(0, len(cls._trailer_history) - 1)
            return cls._trailer_history[index]

    @classmethod
    def add_trailer(cls, movie: AbstractMovie) -> None:
        with cls._lock:
            cls._trailer_history.append(movie)
            if len(cls._trailer_history) > cls.MAXIMUM_HISTORY:
                del cls._trailer_history[0]

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