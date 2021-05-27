'''
Created on Dec 3, 2019

@author: fbacher
'''
# -*- coding: utf-8 -*-

import os

from common.imports import *
from common.logger import (LazyLogger)
from common.movie import BaseMovie, AbstractMovie
from common.movie_constants import MovieField
from common.settings import Settings

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TrailerCache:
    """
    Manages the optional cache for movie trailers. Also manages the cache
    for trailers which have had their volume normalized.
    """

    _logger = None

    @classmethod
    def config_logger(cls) -> LazyLogger:
        """

        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)

        return cls._logger

    @classmethod
    def is_more_discovery_needed(cls, movie: BaseMovie) -> bool:
        if movie.get_discovery_state() <= MovieField.DISCOVERY_COMPLETE:
            return False

        movie: AbstractMovie
        more_discovery_needed: bool = False
        title = movie.get_title()
        try:
            normalized_trailer_path = movie.get_normalized_trailer_path()
            if normalized_trailer_path is None:
                normalized_trailer_path = ''
            cached_trailer_path: str = movie.get_cached_movie()
            if cached_trailer_path is None:
                cached_trailer_path = ''

            if movie.is_trailer_url():
                # Remote Trailer

                if Settings.is_normalize_volume_of_downloaded_trailers():
                    try:
                        if not os.path.exists(normalized_trailer_path):
                            cls._logger.debug(
                                f'title: {title} does not exist: '
                                f'{normalized_trailer_path}')
                            movie.set_normalized_trailer_path('')
                            more_discovery_needed = True
                    except Exception as e:
                        cls._logger.log_exception(e)

                elif Settings.is_use_trailer_cache():
                    try:
                        if not os.path.exists(cached_trailer_path):
                            cls._logger.debug(
                                f'title: {title} does not exist: '
                                f'{cached_trailer_path}')
                            movie.set_cached_trailer('')
                            movie.set_normalized_trailer_path('')
                            more_discovery_needed = True
                    except Exception as e:
                        cls._logger.log_exception(e)
            elif Settings.is_normalize_volume_of_local_trailers():
                # Local movie
                try:
                    if not os.path.exists(normalized_trailer_path):
                        cls._logger.debug(
                            f'title: {title} normalized trailer does not exist: '
                            f'{normalized_trailer_path}')
                        movie.set_normalized_trailer_path('')
                        more_discovery_needed = True
                except Exception as e:
                    cls._logger.log_exception(e)

        except Exception as e:
            cls._logger.log_exception()

        if more_discovery_needed:
            movie.set_discovery_state(MovieField.DISCOVERY_COMPLETE)
            cls._logger.debug(f'More discovery needed: {title}')

        return more_discovery_needed


TrailerCache.config_logger()
