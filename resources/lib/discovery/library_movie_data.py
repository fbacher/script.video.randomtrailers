# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *
from common.movie import LibraryMovieId, LibraryMovie
from common.movie_constants import MovieField
from discovery.abstract_movie_data import AbstractMovieData
from discovery.library_movie_trailer_fetcher import LibraryMovieTrailerFetcher
from discovery.library_no_trailer_fetcher import LibraryNoTrailerTrailerFetcher
from discovery.library_url_trailer_fetcher import LibraryURLTrailerFetcher
from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from .__init__ import *


class LibraryMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source: str = None) -> None:
        """

        """
        super().__init__(trailer_fetcher_class=LibraryMovieTrailerFetcher,
                         movie_source=MovieField.LIBRARY_SOURCE)
        self.start_trailer_fetchers()

    def purge_rediscoverable_data(self, movie: LibraryMovie) -> LibraryMovieId:
        """
        Replace fully populated cached entry with light-weight entry.
        Data can easily be rediscovered from locally cached data.

        :param movie:
        :return:
        """
        if isinstance(movie, LibraryMovie):
            with self._discovered_movies_lock:
                # super().remove_discovered_movie(movie)
                movie_id: LibraryMovieId = movie.get_as_movie_id_type()
                super().replace(movie_id)

        return movie_id


class LibraryNoTrailerMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source: str = None) -> None:
        """


        """
        super().__init__(trailer_fetcher_class=LibraryNoTrailerTrailerFetcher,
                         movie_source=MovieField.LIBRARY_NO_TRAILER)
        self.start_trailer_fetchers()

    def purge_rediscoverable_data(self, movie: LibraryMovie) -> LibraryMovieId:
        """
        Replace fully populated cached entry with light-weight entry.
        Data can easily be rediscovered from locally cached data.

        :param movie:
        :return:
        """
        if isinstance(movie, LibraryMovie):
            with self._discovered_movies_lock:
                # super().remove_discovered_movie(movie)
                movie_id: LibraryMovieId = movie.get_as_movie_id_type()
                super().replace(movie_id)

        return movie_id


class LibraryURLMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source: str = None) -> None:
        """

        :param movie_source:

        """
        super().__init__(trailer_fetcher_class=LibraryURLTrailerFetcher,
                         movie_source=MovieField.LIBRARY_URL_TRAILER)
        self.start_trailer_fetchers()

    def purge_rediscoverable_data(self, movie: LibraryMovie) -> LibraryMovieId:
        """
        Replace fully populated cached entry with light-weight entry.
        Data can easily be rediscovered from locally cached data.

        :param movie:
        :return:
        """
        if isinstance(movie, LibraryMovie):
            with self._discovered_movies_lock:
                # super().remove_discovered_movie(movie)
                movie_id: LibraryMovieId = movie.get_as_movie_id_type()
                super().replace(movie_id)

        return movie_id
