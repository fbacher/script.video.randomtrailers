# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.constants import Movie
from discovery.abstract_movie_data import AbstractMovieData


class LibraryMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = Movie.LIBRARY_SOURCE) -> None:
        """

        """
        super().__init__(movie_source=Movie.LIBRARY_SOURCE)
        self.start_trailer_fetchers()


class LibraryNoTrailerMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = Movie.LIBRARY_NO_TRAILER) -> None:
        """


        """
        super().__init__(movie_source=Movie.LIBRARY_NO_TRAILER)
        self.start_trailer_fetchers()


class LibraryURLMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = Movie.LIBRARY_URL_TRAILER) -> None:
        """

        :param movie_source:

        """
        super().__init__(movie_source=Movie.LIBRARY_URL_TRAILER)
        self.start_trailer_fetchers()
