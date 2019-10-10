# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.constants import (Constants, Movie)
from common.development_tools import (Callable, TextType)
from discovery.abstract_movie_data import AbstractMovieData


# noinspection Annotator,PyArgumentList
class FolderMovieData(AbstractMovieData):
    """

    """

    def __init__(self, movie_source=''):
        # type: (TextType) -> None
        """

        :param movie_source:

        """
        super().__init__(movie_source=Movie.FOLDER_SOURCE)
        self.start_trailer_fetchers()
