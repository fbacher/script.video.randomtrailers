# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from cache.tmdb_cache_index import CacheIndex
from common.imports import *
from common.movie import TMDbMovie, AbstractMovie, TMDbMovieId, BaseMovie
from common.movie_constants import MovieField, MovieType
from discovery.abstract_movie_data import AbstractMovieData
from discovery.tmdb_trailer_fetcher import TMDbTrailerFetcher
from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from .__init__ import *


class TMDbMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source: str = MovieField.TMDB_SOURCE) -> None:
        """

        """
        super().__init__(trailer_fetcher_class=TMDbTrailerFetcher,
                         movie_source=MovieField.TMDB_SOURCE)
        self.start_trailer_fetchers()

    def add_to_discovered_trailers(self,
                                   movies: Union[MovieType,
                                                 List[MovieType]]) -> None:
        """

        :param movies:
        :return:
        """

        super().add_to_discovered_movies(movies)

    def remove_discovered_movie(self, movie: TMDbMovie) -> None:
        with self._discovered_movies_lock:
            super().remove_discovered_movie(movie)
            CacheIndex.remove_unprocessed_movie(movie)

    def purge_rediscoverable_data(self, movie: TMDbMovie) -> TMDbMovieId:
        """
        Replace fully populated cached entry with light-weight entry.
        Data can easily be rediscovered from locally cached data.

        :param movie:
        :return:
        """
        if isinstance(movie, TMDbMovie):
            with self._discovered_movies_lock:
                # super().remove_discovered_movie(movie)
                tmdb_movie_id: TMDbMovieId = movie.get_as_movie_id_type()
                super().replace(tmdb_movie_id)

        return tmdb_movie_id


