# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *
from common.movie_constants import MovieField
from discovery.abstract_movie_data import AbstractMovieData
from discovery.folder_trailer_fetcher import FolderTrailerFetcher
from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from .__init__ import *


class FolderMovieData(AbstractMovieData):
    """

    """

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface] = None,
                 movie_source=MovieField.FOLDER_SOURCE) -> None:
        """

        :param movie_source:

        """
        super().__init__(trailer_fetcher_class=FolderTrailerFetcher,
                         movie_source=MovieField.FOLDER_SOURCE)
        self.start_trailer_fetchers()
