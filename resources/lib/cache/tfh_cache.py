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


class TFHCache:
    """

    """
    UNINITIALIZED_STATE = 'uninitialized_state'
    lock = threading.RLock()
    _logger = None
    _cached_trailers: Dict[str, MovieType] = {}
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
        cls.load_cache()

    @classmethod
    def logger(cls):
        #  type: () -> LazyLogger
        """

        :return:
        """
        return cls._logger

    @classmethod
    def save_cache(cls, flush: bool = False) -> None:
        """
        :param flush:
        :return:
        """
        with cls.lock:
            if (not flush and
                    (cls._unsaved_trailer_changes < 50)
                    and
                    (datetime.datetime.now() - cls._last_saved_trailer_timestamp)
                    < datetime.timedelta(minutes=5)):
                return

            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json')

                path = xbmcvfs.validatePath(path)
                tmp_path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json.tmp')

                tmp_path = xbmcvfs.validatePath(tmp_path)
                parent_dir, file_name = os.path.split(path)
                if not os.path.exists(parent_dir):
                    DiskUtils.create_path_if_needed(parent_dir)

                Monitor.throw_exception_if_abort_requested()
                with io.open(tmp_path, mode='at', newline=None,
                             encoding='utf-8', ) as cacheFile:
                    json_text = json.dumps(cls._cached_trailers,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           default=TFHCache.abort_checker,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._unsaved_trailer_changes = 0

                try:
                    os.replace(tmp_path, path)
                except OSError:
                    cls._logger.exception(f'Failed to replace missing trailer'
                                          f' information cache: {path}')
            except IOError as e:
                TFHCache.logger().exception('')
            except Exception as e:
                TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()

    @classmethod
    def load_cache(cls) -> None:
        """

        :return: True if cache is full and no further discovery needed
        """
        with cls.lock:
            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json')
                path = xbmcvfs.validatePath(path)

                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)

                if os.path.exists(path):
                    with io.open(path, mode='rt', newline=None,
                                                encoding='utf-8') as cacheFile:
                        cls._cached_trailers = json.load(
                            cacheFile,
                            object_handler=TFHCache.abort_checker,
                            encoding='utf-8')
                        cls.last_saved_movie_timestamp = None
                        cls._unsaved_trailer_changes = 0
                else:
                    cls._cached_trailers = dict()

            except IOError as e:
                TFHCache.logger().exception('')
            except JSONDecodeError as e:
                os.remove(path)
            except Exception as e:
                TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()
        return

    @classmethod
    def add_trailers(cls, trailers: Dict[str, MovieType], flush=False) -> None:

        with cls.lock:
            for key, trailer in trailers.items():
                cls._cached_trailers[key] = trailer
                cls._unsaved_trailer_changes += 1

            cls.save_cache(flush=flush)

    @classmethod
    def add_trailer(cls, trailer: MovieType, flush=False) -> None:
        with cls.lock:
            key = trailer[Movie.TFH_ID]
            cls._cached_trailers[key] = trailer
            cls._unsaved_trailer_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def get_cached_trailer(cls, trailer_id: str) -> MovieType:

        return cls._cached_trailers.get(trailer_id)

    @classmethod
    def get_cached_trailers(cls) -> Dict[str, MovieType]:
        return cls._cached_trailers.copy()

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        return dct


TFHCache.class_init()
