# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""
from typing import Type, Union

import xbmc

from cache.base_reverse_index_cache import BaseReverseIndexCache
from cache.itunes_json_cache import ITunesJsonCache
from cache.library_json_cache import LibraryJsonCache
from cache.tfh_json_cache import TFHJsonCache
from cache.tmdb_json_cache import TMDbJsonCache
from common.logger import LazyLogger
from common.movie import AbstractMovie, AbstractMovieId, LibraryMovie, LibraryMovieId, \
    ITunesMovieId, ITunesMovie, TFHMovie, TFHMovieId, TMDbMovie, TMDbMovieId
from common.movie_constants import MovieField

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class JsonCacheHelper:
    _logger: LazyLogger = None

    @classmethod
    def get_json_cache_for_source(cls, source: str) -> Type[BaseReverseIndexCache]:
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        # cls._logger.debug(f'source: {source}')
        # cls._logger.dump_stack(msg=f'source: {source}', xbmc_log_level=xbmc.LOGDEBUG)
        if source == MovieField.LIBRARY_SOURCE:
            return LibraryJsonCache
        elif source == MovieField.TMDB_SOURCE:
            return TMDbJsonCache
        elif source == MovieField.ITUNES_SOURCE:
            return ITunesJsonCache
        elif source == MovieField.TFH_SOURCE:
            return TFHJsonCache
        else:
            raise ValueError(f'Invalid source: {source}')

    @classmethod
    def get_json_cache(cls,
                       movie: Union[AbstractMovie, AbstractMovieId]
                       ) -> Type[BaseReverseIndexCache]:
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        movie_type = type(movie)
        if movie_type in (LibraryMovie, LibraryMovieId):
            return LibraryJsonCache
        elif movie_type in (TMDbMovie, TMDbMovieId):
            return TMDbJsonCache
        elif movie_type in (ITunesMovie, ITunesMovieId):
            return ITunesJsonCache
        elif movie_type in (TFHMovie, TFHMovieId):
            return TFHJsonCache
        else:
            raise ValueError(f'Invalid movie type: {movie_type}')
