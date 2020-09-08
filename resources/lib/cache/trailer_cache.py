'''
Created on Dec 3, 2019

@author: fbacher
'''
# -*- coding: utf-8 -*-

from common.imports import *

import sys
import datetime
import io
import simplejson as json
import os
import re

import threading
import six

import xbmc

from common.constants import Constants, Movie
from common.logger import (LazyLogger)
from common.exceptions import (AbortException, TrailerIdException)
from common.messages import Messages
from backend.movie_entry_utils import (MovieEntryUtils)
from common.settings import Settings
from backend import backend_constants
from common.disk_utils import DiskUtils
from backend.json_utils_basic import (JsonUtilsBasic)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TrailerCache(object):
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
    def validate_cached_files(cls,
                              movie  # type: MovieType
                              ):
        cache_file_missing = False
        normalized_file_missing = False

        if movie.get(Movie.CACHED_TRAILER, "") != "":
            try:
                if not os.path.exists(movie[Movie.CACHED_TRAILER]):
                    movie[Movie.CACHED_TRAILER] = None
                    cache_file_missing = True
            except Exception:
                cls._logger.error('Movie:', movie[Movie.TITLE],
                                  'cached_trailer:', movie[Movie.CACHED_TRAILER])
                movie[Movie.CACHED_TRAILER] = None
                cache_file_missing = True

        if movie.get(Movie.NORMALIZED_TRAILER, "") != "":
            try:
                if not os.path.exists(movie[Movie.NORMALIZED_TRAILER]):
                    movie[Movie.NORMALIZED_TRAILER] = None
                    normalized_file_missing = True
            except Exception:
                cls._logger.error('Movie:', movie[Movie.TITLE],
                                  'normalized_trailer:', movie[Movie.NORMALIZED_TRAILER])
                movie[Movie.NORMALIZED_TRAILER] = None
                normalized_file_missing = True

        if (cache_file_missing and normalized_file_missing
                and movie[Movie.DISCOVERY_STATE] > Movie.DISCOVERY_COMPLETE):
            movie[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_COMPLETE


TrailerCache.config_logger()
