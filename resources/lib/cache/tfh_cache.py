# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import datetime
import dateutil.parser

import io
import simplejson as json
from simplejson import (JSONDecodeError)

import os

import threading

from kodi_six import xbmc, utils

from common.development_tools import (Any, List,
                                      Dict, Union,
                                      TextType, MovieType)
from common.constants import (Constants, Movie, RemoteTrailerPreference)
from common.logger import (Logger, LazyLogger)
from common.messages import (Messages)
from backend.movie_entry_utils import (MovieEntryUtils)
from common.settings import (Settings)
from common.disk_utils import (DiskUtils)
from backend.statistics import (Statistics)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'cache.cache')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class TFHCache(object):
    """

    """
    CACHE_COMPLETE_MARKER = 'CACHE_COMPLETE_MARKER'
    UNINITIALIZED_STATE = 'uninitialized_state'
    lock = threading.RLock()
    _logger = None

    @classmethod
    def class_init(cls,
                   ):
        # type: (...) -> None
        """
        :return:
        """
        cls._logger = module_logger.getChild(cls.__class__.__name__)
        cls._cached_trailers = list()  # type: List[MovieType]
        cls._unsaved_trailer_changes = 0
        cls._last_saved_trailer_timestamp = datetime.datetime.now()
        cls._cache_complete = False

    @classmethod
    def logger(cls):
        #  type: () -> LazyLogger
        """

        :return:
        """
        return cls._logger

    @classmethod
    def save_trailers_to_cache(cls, trailers, flush=False, cache_complete=False):
        # type: (Union[List[MovieType], MovieType], bool, bool) -> None
        """
        :param trailers:
        :param flush:
        :param cache_complete:
        :return:
        """
        if not isinstance(trailers, list):
            if trailers is not None:
                cls._cached_trailers.append(trailers)
        else:
            cls._cached_trailers.extend(trailers)

        cls._unsaved_trailer_changes += len(trailers)
        if cls._unsaved_trailer_changes == 0:
            return

        if (not flush and not cache_complete and
                (cls._unsaved_trailer_changes < 50)
                and
                (datetime.datetime.now() - cls._last_saved_trailer_timestamp)
                < datetime.timedelta(minutes=5)):
            return

        if cache_complete:
            cache_complete_marker = {Movie.SOURCE: Movie.TFH_SOURCE,
                                     Movie.TFH_ID: TFHCache.CACHE_COMPLETE_MARKER,
                                     Movie.TITLE: TFHCache.CACHE_COMPLETE_MARKER,
                                     Movie.YEAR: 0,
                                     Movie.ORIGINAL_LANGUAGE: '',
                                     Movie.TRAILER: TFHCache.CACHE_COMPLETE_MARKER,
                                     Movie.PLOT: TFHCache.CACHE_COMPLETE_MARKER,
                                     Movie.THUMBNAIL: TFHCache.CACHE_COMPLETE_MARKER,
                                     Movie.DISCOVERY_STATE: Movie.NOT_FULLY_DISCOVERED,
                                     Movie.MPAA: ''
                                     }
            cls._cached_trailers.append(cache_complete_marker)

        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tfh_trailers.json')
        path = path.encode('utf-8')
        path = xbmc.validatePath(path)
        parent_dir, file_name = os.path.split(path)
        if not os.path.exists(parent_dir):
            DiskUtils.create_path_if_needed(parent_dir)

        with cls.lock:
            try:
                with io.open(path, mode='at', newline=None,
                             encoding='utf-8', ) as cacheFile:
                    json_text = utils.py2_decode(json.dumps(cls._cached_trailers,
                                                            encoding='utf-8',
                                                            ensure_ascii=False,
                                                            indent=3, sort_keys=True))
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._unsaved_trailer_changes = 0

            except (IOError) as e:
                TFHCache.logger().exception('')
            except (Exception) as e:
                TFHCache.logger().exception('')

    @classmethod
    def load_trailer_cache(cls):
        # type: () -> bool
        """

        :return: True if cache is complete and no further discovery needed
        """
        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tfh_trailers.json')
        path = path.encode('utf-8')
        path = xbmc.validatePath(path)
        try:
            parent_dir, file_name = os.path.split(path)
            DiskUtils.create_path_if_needed(parent_dir)

            if os.path.exists(path):
                with TFHCache.lock, io.open(path, mode='rt', newline=None,
                                            encoding='utf-8') as cacheFile:
                    cls._cached_trailers = json.load(
                        cacheFile, encoding='utf-8')
                    cls.last_saved_movie_timestamp = None
                    cls._unsaved_trailer_changes = 0
            else:
                cls._cached_trailers = list()

        except (IOError) as e:
            TFHCache.logger().exception('')
        except (JSONDecodeError) as e:
            os.remove(path)
        except (Exception) as e:
            TFHCache.logger().exception('')

        cls._cache_complete = False
        for trailer in cls._cached_trailers:
            if trailer[Movie.TFH_ID] == TFHCache.CACHE_COMPLETE_MARKER:
                cls._cache_complete = True
                break

        return cls._cache_complete

    @classmethod
    def get_cached_trailers(cls):
        #  type: () -> List[MovieType]
        """

        :return:
        """

        return cls._cached_trailers


TFHCache.class_init()
