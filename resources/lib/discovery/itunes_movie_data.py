# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *
from common.movie_constants import MovieField
from discovery.abstract_movie_data import AbstractMovieData


class ItunesMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = MovieField.ITUNES_SOURCE) -> None:
        """

        """

        super().__init__(movie_source=MovieField.ITUNES_SOURCE)
        self.start_trailer_fetchers()
