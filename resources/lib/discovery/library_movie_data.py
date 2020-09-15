# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *

from common.constants import Constants, Movie
from discovery.abstract_movie_data import AbstractMovieData


# noinspection Annotator,PyArgumentList
class LibraryMovieData(AbstractMovieData):
    """

    """

    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__(movie_source=Movie.LIBRARY_SOURCE)
        self.start_trailer_fetchers()


class LibraryNoTrailerMovieData(AbstractMovieData):
    """

    """

    def __init__(self):
        # type: () -> None
        """


        """
        super().__init__(movie_source=Movie.LIBRARY_NO_TRAILER)
        self.start_trailer_fetchers()


class LibraryURLMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source=''):
        # type: (str) -> None
        """

        :param movie_source:

        """
        super().__init__(movie_source=Movie.LIBRARY_URL_TRAILER)
        self.start_trailer_fetchers()
