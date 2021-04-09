# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *

from common.constants import (Constants, Movie)
from discovery.abstract_movie_data import AbstractMovieData


class FolderMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source: str = Movie.FOLDER_SOURCE) -> None:
        """

        :param movie_source:

        """
        super().__init__(movie_source=Movie.FOLDER_SOURCE)
        self.start_trailer_fetchers()
