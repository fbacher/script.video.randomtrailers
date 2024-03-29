# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *
from common.movie_constants import MovieField
from discovery.abstract_movie_data import AbstractMovieData
from discovery.itunes_trailer_fetcher import ITunesTrailerFetcher
from discovery.trailer_fetcher_interface import TrailerFetcherInterface


class ItunesMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source: str = MovieField.ITUNES_SOURCE) -> None:
        """

        """

        super().__init__(trailer_fetcher_class=ITunesTrailerFetcher,
                         movie_source=MovieField.ITUNES_SOURCE)
        self.start_trailer_fetchers()
