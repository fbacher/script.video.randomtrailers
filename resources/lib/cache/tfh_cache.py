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
from common.utils import Utils

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TFHCache:
    """
    Trailers From Hell has an index of all of the trailers that they produce.
    We don't rely on the index being static. It is not really searchable.
    When this cache is determined to be expired, the entire index must be
    retrieved and this list recreated.
    """
    UNINITIALIZED_STATE = 'uninitialized_state'
    INDEX_CREATION_DATE = 'INDEX_CREATION_DATE'
    INCOMPLETE_CREATION_DATE_STR = '1900:01:01'
    lock = threading.RLock()
    _logger = None
    _cached_trailers: Dict[str, MovieType] = {}
    _last_saved_trailer_timestamp = datetime.datetime.now()
    _unsaved_trailer_changes: int = 0
    _time_of_index_creation = datetime.datetime(2000, 1, 1)  # expired
    _number_of_trailers_on_site: int = 0

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
    def save_cache(cls, flush: bool = False, complete: bool = False) -> None:
        """
        :param flush:
        :param complete:
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
                    if complete:
                        creation_date_str = datetime.datetime.strftime(
                            cls._time_of_index_creation, '%Y:%m:%d')
                    else:
                        creation_date_str = TFHCache.INCOMPLETE_CREATION_DATE_STR
                    cls._cached_trailers[TFHCache.INDEX_CREATION_DATE] = {
                        TFHCache.INDEX_CREATION_DATE: creation_date_str,
                    }

                    json_text = json.dumps(cls._cached_trailers,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           default=TFHCache.abort_checker,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()

                    # Get rid of dummy entry
                    del cls._cached_trailers['INDEX_CREATION_DATE']
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
                            # object_hook=TFHCache.abort_checker,
                        )
                        cls.last_saved_movie_timestamp = None
                        cls._unsaved_trailer_changes = 0
                        cls.load_creation_date()
                else:
                    cls._cached_trailers = dict()
                    # Set to an old time so that cache is expired
                    cls._time_of_index_creation = datetime.datetime(2000, 1, 1)
                    cls._index_complete = False

            except IOError as e:
                TFHCache.logger().exception('')
            except JSONDecodeError as e:
                os.remove(path)
            except Exception as e:
                TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()
        return

    @classmethod
    def load_creation_date(cls) -> None:
        # Loads the last time the index was created from a cached entry.
        # If no cached entry with the timestamp exists, set it to now.

        creation_date = None
        creation_date_entry = cls._cached_trailers.get('INDEX_CREATION_DATE')
        if creation_date_entry is not None:
            creation_date = creation_date_entry.get('INDEX_CREATION_DATE')
        if creation_date is None:
            cls.set_creation_date()
            return
        else:
            # Remove dummy entry from cache
            del cls._cached_trailers['INDEX_CREATION_DATE']

        # Just to be consistent, all cached_trailer entries are MovieType (i.e. Dict)
        # So, get the actual timestamp from it

        cls._time_of_index_creation = Utils.strptime(creation_date, '%Y:%m:%d')
        return

    @classmethod
    def set_creation_date(cls) -> None:
        cls._time_of_index_creation = datetime.datetime.now()
        cls._index_complete = False

    @classmethod
    def get_creation_date(cls) -> datetime.datetime:
        return cls._time_of_index_creation

    @classmethod
    def add_trailers(cls, trailers: Dict[str, MovieType],
                     total: int = None, flush=False) -> None:

        with cls.lock:
            if total is not None:
                cls._number_of_trailers_on_site = total
            for key, trailer in trailers.items():
                cls._cached_trailers[key] = trailer
                cls._unsaved_trailer_changes += 1
                cls.set_creation_date()

            cls.save_cache(flush=flush)

    @classmethod
    def add_trailer(cls, movie: MovieType, total: int = None, flush=False) -> None:
        with cls.lock:
            key = movie[Movie.TFH_ID]
            if total is not None:
                cls._number_of_trailers_on_site = total
            cls._cached_trailers[key] = movie
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
