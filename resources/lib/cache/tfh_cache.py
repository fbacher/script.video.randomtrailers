# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import datetime
import dateutil.parser

import io
import simplejson as json
from simplejson import (JSONDecodeError)
import os
import sys
import threading

import xbmc
import xbmcvfs
from common.imports import *

from common.constants import (Constants, Movie, RemoteTrailerPreference)
from common.exceptions import AbortException
from common.logger import (Logger, LazyLogger)
from common.messages import (Messages)
from common.monitor import Monitor
from backend.movie_entry_utils import (MovieEntryUtils)
from common.settings import (Settings)
from common.disk_utils import (DiskUtils)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TFHCache(object):
    """

    """
    CACHE_COMPLETE_MARKER = 'CACHE_COMPLETE_MARKER'
    UNINITIALIZED_STATE = 'uninitialized_state'
    lock = threading.RLock()
    _logger = None
    _cache_complete: bool = False
    _cached_trailers: List[MovieType] = list()
    _last_saved_trailer_timestamp = datetime.datetime.now()
    _unsaved_trailer_changes: int = 0

    @classmethod
    def class_init(cls,
                   ):
        # type: (...) -> None
        """
        :return:
        """
        cls._logger = module_logger.getChild(type(cls).__name__)

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
                cls._unsaved_trailer_changes += 1
        else:
            cls._cached_trailers.extend(trailers)
            cls._unsaved_trailer_changes += len(trailers)

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
                                     Movie.MPAA: '',
                                     Movie.ADULT: False
                                     }
            cls._cached_trailers.append(cache_complete_marker)

        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tfh_trailers.json')

        path = xbmcvfs.validatePath(path)
        parent_dir, file_name = os.path.split(path)
        if not os.path.exists(parent_dir):
            DiskUtils.create_path_if_needed(parent_dir)

        with cls.lock:
            try:
                with io.open(path, mode='at', newline=None,
                             encoding='utf-8', ) as cacheFile:
                    json_text = json.dumps(cls._cached_trailers,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._unsaved_trailer_changes = 0
            except IOError as e:
                TFHCache.logger().exception('')
            except Exception as e:
                TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()

    @classmethod
    def load_trailer_cache(cls):
        # type: () -> bool
        """

        :return: True if cache is complete and no further discovery needed
        """
        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tfh_trailers.json')
        path = xbmcvfs.validatePath(path)
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

        except IOError as e:
            TFHCache.logger().exception('')
        except JSONDecodeError as e:
            os.remove(path)
        except Exception as e:
            TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()
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
