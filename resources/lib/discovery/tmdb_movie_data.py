# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from backend.movie_entry_utils import MovieEntryUtils
from cache.tmdb_cache_index import CacheIndex
# from cache.unprocessed_tmdb_page_data import UnprocessedTMDbPages
from common.imports import *
from common.movie import TMDbMovie, AbstractMovie, TMDbMovieId, BaseMovie
from common.movie_constants import MovieField, MovieType
from discovery.abstract_movie_data import AbstractMovieData


class TMDBMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = MovieField.TMDB_SOURCE) -> None:
        """

        """
        super().__init__(movie_source=MovieField.TMDB_SOURCE)
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

    def purge_rediscoverable_data(self, movie: TMDbMovie) -> None:
        """
        Replace fully populated cached entry with light-weight entry.
        Data can easily be rediscovered from locally cached data.

        :param movie:
        :return:
        """
        cached_movie: BaseMovie = self.get_by_id(movie.get_id())
        if cached_movie is None:
            return 
        
        tmdb_movie_id: TMDbMovieId = movie.get_as_movie_id_type()
        if isinstance(cached_movie, TMDbMovie):
            with self._discovered_movies_lock:
                # super().remove_discovered_movie(movie)
                super().replace(tmdb_movie_id)

