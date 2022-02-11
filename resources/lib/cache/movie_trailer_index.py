# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""

from cache.base_trailer_index import BaseTrailerIndex
from cache.itunes_trailer_index import ITunesTrailerIndex
from cache.library_trailer_index import LibraryTrailerIndex
from cache.tfh_trailer_index import TFHTrailerIndex
from cache.tmdb_trailer_index import TMDbTrailerIndex
from common.imports import *
from common.logger import *
from common.movie import AbstractMovieId, TMDbMovieId, TMDbMovie, AbstractMovie, \
    LibraryMovie, LibraryMovieId, TFHMovieId, ITunesMovieId, TFHMovie, ITunesMovie

module_logger = BasicLogger.get_module_logger(module_path=__file__)


class MovieTrailerIndex(BaseTrailerIndex):
    """
    High-Level generic wrapper to subclasses of BaseTrailerIndex


    """

    _logger: BasicLogger = None

    @classmethod
    def class_init(cls, cache_name: str) -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

    @classmethod
    def get_class_for_type(cls,
                           movie: Union[AbstractMovieId, AbstractMovie]
                           ) -> Type[BaseTrailerIndex]:
        if isinstance(movie, (TMDbMovie, TMDbMovieId)):
            return TMDbTrailerIndex
        if isinstance(movie, (LibraryMovie, LibraryMovieId)):
            return LibraryTrailerIndex
        if isinstance(movie, (TFHMovie, TFHMovieId)):
            return TFHTrailerIndex
        if isinstance(movie, (ITunesMovie, ITunesMovieId)):
            return ITunesTrailerIndex

    @classmethod
    def add(cls, movie: Union[AbstractMovieId, AbstractMovie],
            flush: bool = False) -> None:
        """
        Add the given movie to the cache, after converting it to
        AbstractMovieId type, if necessary.

        :param movie:
        :param flush:
        :return:
         """
        cls.get_class_for_type(movie).add(movie, flush)

    @classmethod
    def remove(cls, movie: Union[AbstractMovieId, AbstractMovie],
            flush: bool = False) -> None:
        """
        Remove the given movie from the cached and persisted entries,
        after converting the movie to AbstractMovieId type, as necessary.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param movie:
        :param flush:
        :return:
         """

        cls.get_class_for_type(movie).remove(movie, flush)


MovieTrailerIndex.class_init(cache_name='Dummy_cache_name2')