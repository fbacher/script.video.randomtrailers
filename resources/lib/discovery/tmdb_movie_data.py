# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from backend.movie_entry_utils import MovieEntryUtils
from cache.tmdb_cache_index import CacheIndex
from common.imports import *
from common.constants import Movie
from discovery.abstract_movie_data import AbstractMovieData


class TMDBMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = Movie.TMDB_SOURCE) -> None:
        """

        """
        super().__init__(movie_source=Movie.TMDB_SOURCE)
        self.start_trailer_fetchers()

    def add_to_discovered_trailers(self,
                                   movies: Union[MovieType,
                                                 List[MovieType]]) -> None:
        """

        :param movies:
        :return:
        """

        super().add_to_discovered_trailers(movies)

    def remove_discovered_movie(self, movie: MovieType) -> None:
        with self._discovered_trailers_lock:
            super().remove_discovered_movie(movie)
            tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
            CacheIndex.remove_unprocessed_movies(int(tmdb_id))
