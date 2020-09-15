# -*- coding: utf-8 -*-

"""
Created on Mar 4, 2019

@author: Frank Feuerbacher
"""

from common.imports import *

#  from common.rating import Rating
from common.settings import Settings


# noinspection PyClassHasNoInit
class TmdbSettings(object):
    """

    """
    _instance = None

    #_rating_limit_string_for_setting = {'0': Rating.RATING_NC_17,
    #                                '1': Rating.RATING_G,
    #                                '2': Rating.RATING_PG,
    #                                '3': Rating.RATING_PG_13,
    #                                '4': Rating.RATING_R,
    #                                '5': Rating.RATING_NC_17}

    _trailer_type_string_for_setting_map = {'0': 'popular',
                                       '1': 'top_rated',
                                       '2': 'upcoming',
                                       '3': 'now_playing',
                                       '4': 'all'}

    _genre_setting_method_for_genre = {}

    @staticmethod
    def get_instance():
        # type: () -> TmdbSettings
        """

        :return:
        """
        if TmdbSettings._instance is None:
            TmdbSettings._instance = TmdbSettings()
        return TmdbSettings._instance

    def get_rating_limit_string_from_setting(self):
        # type: () ->  str
        """

        :return:
        """
        rating_limit = Settings.get_rating_limit_setting()
        # return TmdbSettings._rating_limit_string_for_setting[rating_limit]
        return 'R'

    def get_trailer_type(self):
        # type: () -> str
        """

        :return:
        """
        tmdb_trailer_type = Settings.get_tmdb_trailer_type()
        return TmdbSettings._trailer_type_string_for_setting_map[tmdb_trailer_type]
