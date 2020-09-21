# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from backend.movie_entry_utils import MovieEntryUtils
from cache.cache_index import CacheIndex
from common.imports import *
from common.constants import (Constants, Movie)
from discovery.abstract_movie_data import AbstractMovieData


# noinspection Annotator,PyArgumentList
class TMDBMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source=''):
        # type: (str) -> None
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

    def get_number_of_movies_with_trailers(self):
        # type: () -> int
        """

        :return:
        """
        movies_with_trailers = 0
        for movie in self._discovered_trailers.get_trailers():
            if movie[Movie.DISCOVERY_STATE] >= Movie.DISCOVERY_COMPLETE:
                movies_with_trailers += 1

        return movies_with_trailers

    def remove_discovered_movie(self, movie):
        with self._discovered_trailers_lock:
            super().remove_discovered_movie(movie)
            tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
            CacheIndex.remove_unprocessed_movie(int(tmdb_id))
