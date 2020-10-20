'''
Created on Dec 3, 2019

@author: fbacher
'''
# -*- coding: utf-8 -*-

import os

from common.constants import Constants, Movie
from common.imports import *
from common.logger import (LazyLogger)
from common.settings import Settings
from common.disk_utils import DiskUtils

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TrailerCache:
    """
    Manages the optional cache for movie trailers. Also manages the cache
    for trailers which have had their volume normalized.
    """

    _logger = None

    @classmethod
    def config_logger(cls):
        #  type: () -> LazyLogger
        """

        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)

        return cls._logger

    @classmethod
    def is_more_discovery_needed(cls, movie: MovieType) -> bool:
        if movie[Movie.DISCOVERY_STATE] <= Movie.DISCOVERY_COMPLETE:
            return False

        more_discovery_needed = False
        title = movie[Movie.TITLE]
        try:
            normalized_trailer_path = movie.get(Movie.NORMALIZED_TRAILER)
            if normalized_trailer_path is None:
                normalized_trailer_path = ''
            cached_trailer_path = movie.get(Movie.CACHED_TRAILER)
            if cached_trailer_path is None:
                cached_trailer_path = ''

            if DiskUtils.is_url(movie.get(Movie.TRAILER, '')):
                # Remote Trailer

                if Settings.is_normalize_volume_of_downloaded_trailers():
                    try:
                        if not os.path.exists(normalized_trailer_path):
                            cls._logger.debug(
                                f'title: {title} does not exist: '
                                f'{normalized_trailer_path}')
                            movie[Movie.NORMALIZED_TRAILER] = None
                            more_discovery_needed = True
                    except Exception as e:
                        cls._logger.log_exception(e)

                elif Settings.is_use_trailer_cache():
                    try:
                        if not os.path.exists(cached_trailer_path):
                            cls._logger.debug(
                                f'title: {title} does not exist: '
                                f'{cached_trailer_path}')
                            movie[Movie.CACHED_TRAILER] = None
                            movie[Movie.NORMALIZED_TRAILER] = None
                            more_discovery_needed = True
                    except Exception as e:
                        cls._logger.log_exception(e)
            elif Settings.is_normalize_volume_of_local_trailers():
                # Local trailer
                try:
                    if not os.path.exists(normalized_trailer_path):
                        cls._logger.debug(
                            f'title: {title} does not exist: '
                            f'{normalized_trailer_path}')
                        movie[Movie.NORMALIZED_TRAILER] = None
                        more_discovery_needed = True
                except Exception as e:
                    cls._logger.log_exception(e)

        except Exception as e:
            cls._logger.log_exception()

        if more_discovery_needed:
            movie[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_COMPLETE
            cls._logger.debug(f'More discovery needed: {title}')

        return more_discovery_needed


TrailerCache.config_logger()
