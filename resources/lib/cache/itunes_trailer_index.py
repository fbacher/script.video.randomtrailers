# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""
import datetime
import threading
from pathlib import Path

from cache.base_trailer_index import BaseTrailerIndex
from common.imports import *
from common.logger import LazyLogger
from common.movie import ITunesMovieId, ITunesMovie, AbstractMovieId, ITunesMovieId, \
    ITunesMovie

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ITunesTrailerIndex(BaseTrailerIndex):

    CACHE_NAME: str = 'itunes_trailer_index'

    _lock = threading.RLock()
    _last_saved = datetime.datetime(year=1900, month=1, day=1)
    _parameters = None
    _unsaved_changes: int = 0
    _logger = None

    _cache: Dict[str, ITunesMovieId] = {}
    _cache_loaded: bool = False
    _cache_path: Path = None

    @classmethod
    def class_init(cls, cache_name: str = 'dummy') -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        super().class_init(cache_name=cls.CACHE_NAME)

    @classmethod
    def add(cls, movie: Union[ITunesMovieId, ITunesMovie], flush: bool = False) -> None:
        """

        :param movie:
        :param flush:
        :return:
         """
        # cls._logger.debug(f'item_id: {item_id} reverse_id: {reverse_id}')

        cls._logger.debug(f'movie: {movie.get_id()} type: {type(movie)} '
                          f'class: {type(movie).__name__} has_local: '
                          f'{movie.has_local_trailer()} '
                          f'trailer: {movie.get_has_trailer()}')

        if isinstance(movie, ITunesMovie):
            cls._logger.debug(f'Converting to ITunesMovie')
            movie = movie.get_as_movie_id_type()
            cls._logger.debug(f'Converted to: {type(movie)}')

        super().add(movie, flush)

    @classmethod
    def remove(cls, movie_id: ITunesMovieId, flush: bool = False) -> None:
        """
        Remove the ITunesMovieId with the given itunes_id from the
        cached and persisted entries.

        As trailers from iTunes are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param movie_id:
        :param flush:
        :return:
         """

        cls._logger.debug(f'movie: {movie_id.get_id()} type: {type(movie_id)}')

        super().remove(movie_id, flush)

    @classmethod
    def get(cls, movie_id: str) -> ITunesMovieId:
        """
        Return AbstractMovieId identified by movie_id

        As trailers from iTunes are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param movie_id:

        :return:
        """
        cls._logger.debug(f'movie_id: {movie_id}')

        movie: AbstractMovieId = super().get(movie_id)
        movie: ITunesMovieId
        cls._logger.debug(f'movie: {movie}')
        return movie

    @classmethod
    def get_all(cls) -> List[ITunesMovieId]:
        values: List[AbstractMovieId] = super().get_all()
        values: List[ITunesMovieId]
        return values

    @classmethod
    def get_all_with_local_trailers(cls) -> List[ITunesMovieId]:
        try:
            values: List[AbstractMovieId] = super().get_all_with_local_trailers()
            cls._logger.debug(f'# local trailers: {len(values)}')
            values: List[ITunesMovieId]
            return values
        except Exception:
            cls._logger.exception()

    @classmethod
    def get_all_with_non_local_trailers(cls) -> List[ITunesMovieId]:
        try:
            values: List[AbstractMovieId] = super().get_all_with_non_local_trailers()
            cls._logger.debug(f'# non-local trailers: {len(values)}')
            values: List[ITunesMovieId]
            return values
        except Exception:
            cls._logger.exception()

    @classmethod
    def get_all_with_no_known_trailers(cls) -> List[ITunesMovieId]:
        try:
            values: List[AbstractMovieId] = super().get_all_with_no_known_trailers()
            cls._logger.debug(f'# no known trailers: {len(values)}')
            values: List[ITunesMovieId]
            return values
        except Exception:
            cls._logger.exception()

    @classmethod
    def clear(cls) -> None:
        super().clear()


ITunesTrailerIndex.class_init()