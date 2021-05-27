# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *
from common.movie_constants import MovieField
from discovery.abstract_movie_data import AbstractMovieData


class LibraryMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = MovieField.LIBRARY_SOURCE) -> None:
        """

        """
        super().__init__(movie_source=MovieField.LIBRARY_SOURCE)
        self.start_trailer_fetchers()


class LibraryNoTrailerMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = MovieField.LIBRARY_NO_TRAILER) -> None:
        """


        """
        super().__init__(movie_source=MovieField.LIBRARY_NO_TRAILER)
        self.start_trailer_fetchers()


class LibraryURLMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = MovieField.LIBRARY_URL_TRAILER) -> None:
        """

        :param movie_source:

        """
        super().__init__(movie_source=MovieField.LIBRARY_URL_TRAILER)
        self.start_trailer_fetchers()
