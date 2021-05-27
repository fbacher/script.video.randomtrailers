# -*- coding: utf-8 -*-

"""
Created on Mar 4, 2019

@author: Frank Feuerbacher
"""

from common.imports import *

from common.settings import Settings


class TmdbSettings:
    """

    """
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

    @classmethod
    def get_rating_limit_string_from_setting(cls) -> str:
        """

        :return:
        """
        rating_limit = Settings.get_rating_limit_setting()
        # return TmdbSettings._rating_limit_string_for_setting[rating_limit]
        return 'R'

    @classmethod
    def get_trailer_type(cls) -> str:
        """

        :return:
        """
        tmdb_trailer_type = Settings.get_tmdb_trailer_type()
        return TmdbSettings._trailer_type_string_for_setting_map[tmdb_trailer_type]
