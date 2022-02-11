# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""
import glob
from pathlib import Path

from cache.base_trailer_index import BaseTrailerIndex
from cache.cache import Cache

import datetime
from common.movie import (AbstractMovieId, TMDbMovieId, TMDbMovie, LibraryMovieId,
                          LibraryMovie)
import threading
from common.imports import *
from common.logger import *


module_logger = BasicLogger.get_module_logger(module_path=__file__)


class LibraryTrailerIndex(BaseTrailerIndex):

    CACHE_NAME: str = 'library_trailer_index'

    _lock = threading.RLock()
    _last_saved = datetime.datetime(year=1900, month=1, day=1)
    _parameters = None
    _unsaved_changes: int = 0
    _logger = None

    _cache: Dict[str, LibraryMovieId] = {}
    _cache_loaded: bool = False
    _cache_path: Path = None
    _first_use: bool = True

    @classmethod
    def class_init(cls, cache_name: str = 'dummy') -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        super().class_init(cache_name=cls.CACHE_NAME)

    @classmethod
    def add(cls, movie: Union[LibraryMovieId, LibraryMovie], flush: bool = False) -> None:
        """

        :param movie:
        :param flush:
        :return:
         """
        # cls._logger.debug(f'item_id: {item_id} reverse_id: {reverse_id}')
        if cls._logger.isEnabledFor(DISABLED):
            cls._logger.debug(f'library id: {movie.get_library_id()} '
                              f'tmdb id: {movie.get_tmdb_id()} type: {type(movie)} '
                              f'has_local: '
                              f'{movie.has_local_trailer()} '
                              f'trailer: {movie.get_trailer_path()}')

        if isinstance(movie, LibraryMovie):
            # cls._logger.debug(f'Converting to LibraryMovie')
            movie = movie.get_as_movie_id_type()
            # cls._logger.debug(f'Converted to: {type(movie)}')

        if cls._first_use:
            cls.check_local_trailer_entries()

        super().add(movie, flush)

    @classmethod
    def remove(cls, movie: Union[LibraryMovieId, LibraryMovie],
               flush: bool = False) -> None:
        """
        Remove the LibraryMovieId with the given library_id from the
        cached and persisted entries.

        As trailers from the Library are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param movie:
        :param flush:
        :return:
         """

        # cls._logger.debug(f'movie: {movie.get_library_id()} type: {type(movie)}')
        if isinstance(movie, LibraryMovie):
            # cls._logger.debug(f'Converting to LibraryMovie')
            movie = movie.get_as_movie_id_type()
            # cls._logger.debug(f'Converted to: {type(movie)}')
        super().remove(movie, flush)

    @classmethod
    def get(cls, movie_id: str) -> LibraryMovieId:
        """
        Return AbstractMovieId identified by movie_id

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param movie_id:

        :return:
        """
        movie: AbstractMovieId = super().get(movie_id)
        movie: LibraryMovieId
        return movie

    @classmethod
    def get_all(cls) -> List[LibraryMovieId]:
        values: List[AbstractMovieId] = super().get_all()
        values: List[LibraryMovieId]
        return values

    @classmethod
    def check_local_trailer_entries(cls) -> bool:
        """
        Scans the index entries to see has_local_trailers is in agreement
        with what is actually in the cache. In addition, if a movie has a
        trailer in the cache, then get_has_trailer must be True. Discrepancies
        are corrected.

        """
        changed: bool = False
        values: List[LibraryMovieId] = cls.get_all()
        if cls._first_use:
            value: LibraryMovieId
            for value in values:
                trailer_path = Cache.get_trailer_cache_file_path_for_movie_id(
                    movie=value, orig_file_name='*-movie.*', normalized=False)
                cached_trailers = glob.glob(trailer_path)
                if len(cached_trailers) > 0:
                    if not value.has_local_trailer():
                        value.set_local_trailer(True)
                        changed = True
                    if not value.get_has_trailer():
                        value.set_has_trailer(True)
                        changed = True
                else:
                    if value.has_local_trailer():
                        value.set_local_trailer(False)
                        changed = True

        if changed:
            cls.save_cache(flush=True)
        cls._first_use = False
        # cls._logger.debug(f'changed: {changed}')
        return changed

    @classmethod
    def get_all_with_local_trailers(cls) -> List[LibraryMovieId]:
        try:
            values: List[AbstractMovieId] = super().get_all_with_local_trailers()
            # cls._logger.debug(f'# local trailers: {len(values)}')
            values: List[LibraryMovieId]
            return values
        except Exception:
            cls._logger.exception(msg='')

    @classmethod
    def get_all_with_non_local_trailers(cls) -> List[LibraryMovieId]:
        try:
            values: List[AbstractMovieId] = super().get_all_with_non_local_trailers()
            # cls._logger.debug(f'# local trailers: {len(values)}')
            values: List[LibraryMovieId]
            return values
        except Exception:
            cls._logger.exception(msg='')

    @classmethod
    def get_all_with_no_known_trailers(cls) -> List[LibraryMovieId]:
        try:
            values: List[AbstractMovieId] = super().get_all_with_no_known_trailers()
            # cls._logger.debug(f'# no known trailers: {len(values)}')
            values: List[LibraryMovieId]
            return values
        except Exception:
            cls._logger.exception(msg='')

    @classmethod
    def clear(cls) -> None:
        super().clear()


LibraryTrailerIndex.class_init()
