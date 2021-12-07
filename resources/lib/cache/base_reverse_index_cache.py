# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""

from common.imports import *

import datetime
import io
import simplejson as json
from simplejson import (JSONDecodeError)
import os
import sys
import threading

import xbmcvfs

from common.imports import *
from common.constants import Constants
from common.exceptions import AbortException
from common.logger import LazyLogger
from common.monitor import Monitor
from common.settings import Settings
from common.disk_utils import DiskUtils

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class BaseReverseIndexCache:

    CACHE_PATH: str
    _lock = threading.RLock()
    _last_saved = datetime.datetime(year=1900, month=1, day=1)
    _parameters = None
    _unsaved_changes: int = 0
    _logger = None

    _cache: Dict[str, str] = {}
    _cache_loaded: bool = False
    _reverse_cache: Dict[str, str] = {}

    @classmethod
    def class_init(cls, cache_name: str) -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', f'{cache_name}.json')
        cls.CACHE_PATH = xbmcvfs.validatePath(path)

    @classmethod
    def add_item(cls, item_id: str, reverse_id: str, flush: bool = False) -> None:
        """

        :param item_id:
        :param reverse_id:
        :param flush:
        :return:

        TODO: Currently only supports mapping to one other database, TMDb.
              Can easily add more by passing an additional argument,
              database_name. Then store remote database_ids in a list where
              the indexes are constant for a remote_database across all
              of these caches.
         """
        # cls._logger.debug(f'item_id: {item_id} reverse_id: {reverse_id}')
        if item_id is None or reverse_id is None:
            return

        with cls._lock:
            cls.load_cache()
            if item_id not in cls._cache:
                cls._cache[item_id] = reverse_id
                cls._reverse_cache[reverse_id] = item_id
                cls._unsaved_changes += 1
                cls.save_cache(flush=flush)  # If needed

    @classmethod
    def remove_item(cls, item_id: str, flush: bool = False) -> None:
        """
        Remove the TMDbMovieId with the given tmdb_id from the
        cached and persisted entries.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param item_id:
        :param flush:
        :return:
         """
        with cls._lock:
            cls.load_cache()
            try:
                reverse_id: str = cls._cache.get(item_id, None)
                if reverse_id is not None:
                    del cls._cache[item_id]
                    del cls._reverse_cache[reverse_id]

                    cls._unsaved_changes += 1
            except KeyError:
                pass

            cls.save_cache(flush=flush)  # If needed

    @classmethod
    def get_item(cls, item_id: str) -> str:
        """
        Return all TMDbMovieIds that are known to have trailers.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :return:
        """
        with cls._lock:
            cls.load_cache()
            return cls._cache.get(item_id, None)

    @classmethod
    def get_reverse_item(cls, reverse_id: str) -> Any:
        """
        Return all TMDbMovieIds that are known to have trailers.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :return:
        """
        with cls._lock:
            cls.load_cache()
            return cls._cache.get(reverse_id, None)

    @classmethod
    def get_all_ids(cls) -> KeysView[str]:
        with cls._lock:
            cls.load_cache()
            return cls._cache.keys()

    @classmethod
    def get_all_reverse_ids(cls) -> KeysView[str]:
        with cls._lock:
            cls.load_cache()
            return cls._reverse_cache.keys()

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._cache.clear()
            cls._reverse_cache.clear()
            cls.save_cache(flush=True)

    @classmethod
    def load_cache(cls) -> None:
        """
        Loads the cache of TMDb Ids which are known to have trailers.

        :return:
        """
        try:
            if cls._cache_loaded:
                return

            parent_dir, file_name = os.path.split(cls.CACHE_PATH)
            DiskUtils.create_path_if_needed(parent_dir)

            with cls._lock:
                if os.path.exists(cls.CACHE_PATH):
                    with io.open(cls.CACHE_PATH, mode='rt', newline=None,
                                           encoding='utf-8') as cache_file:
                        temp_cache: Dict[str, str] = json.load(
                            cache_file, encoding='utf-8')  # object_hook=cls.datetime_parser)
                        cls._cache = temp_cache
                        cls._last_saved = datetime.datetime.now()
                        cls._unsaved_changes = 0
                    cls._reverse_cache.clear()
                    for key, value in cls._cache.items():
                        cls._reverse_cache[value] = key
                else:
                    cls._cache.clear()
                    cls._reverse_cache.clear()

            Monitor.throw_exception_if_abort_requested()

        except AbortException:
            reraise(*sys.exc_info())
        except IOError as e:
            cls._logger().exception('')
        except JSONDecodeError as e:
            os.remove(cls.CACHE_PATH)
        except Exception as e:
            cls._logger().exception('')

    @classmethod
    def save_cache(cls, flush: bool = False) -> None:
        """
        :param flush:
        :return:
        """
        with cls._lock:
            if not cls._cache_loaded:
                return

            if (not flush and
                    (cls._unsaved_changes <
                     Constants.TRAILER_CACHE_FLUSH_UPDATES)
                    and
                    (datetime.datetime.now() - cls._last_saved) <
                    datetime.timedelta(minutes=5)):
                return

            try:
                cls._logger.debug(f'saving cache {cls.CACHE_PATH}')
                parent_dir, file_name = os.path.split(cls.CACHE_PATH)
                DiskUtils.create_path_if_needed(parent_dir)
                tmp_path = cls.CACHE_PATH + '.tmp'
                tmp_path = xbmcvfs.validatePath(tmp_path)

                with cls._lock, io.open(tmp_path, mode='wt', newline=None,
                                        encoding='utf-8') as cache_file:
                    # Can create reverse_cache from cache
                    json_text = json.dumps(cls._cache,
                                           ensure_ascii=False,
                                           # default=CacheIndex.handler,
                                           indent=3, sort_keys=True)
                    cache_file.write(json_text)
                    cache_file.flush()
                    cls._last_saved = datetime.datetime.now()
                    cls._unsaved_changes = 0

                try:
                    os.replace(tmp_path, cls.CACHE_PATH)
                except OSError:
                    cls._logger.exception(f'Failed to replace missing movie'
                                          f' information cache: {cls.CACHE_PATH}')

                Monitor.throw_exception_if_abort_requested()
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                cls._logger().exception('')
            except Exception as e:
                cls._logger().exception('')
