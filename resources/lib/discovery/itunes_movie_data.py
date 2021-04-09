# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from common.constants import Movie
from discovery.abstract_movie_data import AbstractMovieData


class ItunesMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = Movie.ITUNES_SOURCE) -> None:
        """

        """

        super().__init__(movie_source=Movie.ITUNES_SOURCE)
        self.start_trailer_fetchers()
