# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from common.imports import *
from common.movie_constants import MovieField
from discovery.abstract_movie_data import AbstractMovieData
from discovery.tfh_trailer_fetcher import TFHTrailerFetcher
from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from .__init__ import *


class TFHMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source: str = MovieField.TFH_SOURCE) -> None:
        """

        """
        super().__init__(trailer_fetcher_class=TFHTrailerFetcher,
                         movie_source=MovieField.TFH_SOURCE)
        self.start_trailer_fetchers()
