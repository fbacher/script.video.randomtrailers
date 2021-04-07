# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from common.imports import *

import datetime
import dateutil.parser
import io
import simplejson as json
from simplejson import (JSONDecodeError)
import os
import sys
import threading

import xbmcvfs

from diagnostics.statistics import (Statistics)
from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.logger import (LazyLogger)
from common.monitor import Monitor
from common.settings import Settings
from common.disk_utils import DiskUtils

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection PyRedundantParentheses
class TrailerUnavailableCache:
    """

    """
    _logger = module_logger.getChild('TrailerUnavailableCache')
    _loaded = False
    _all_missing_tmdb_trailers = dict()
    _all_missing_library_trailers = dict()
    lock = threading.RLock()
    library_last_save = datetime.datetime.now()
    library_unsaved_changes = 0
    tmdb_last_save = datetime.datetime.now()
    tmdb_unsaved_changes = 0

    @classmethod
    def add_missing_tmdb_trailer(cls,
                                 tmdb_id=None,  # type: int
                                 library_id=None,  # type: Optional[int]
                                 title=None,  # type: str
                                 year=None,  # type: int
                                 source=None  # type str
                                 ):
        # type (...) -> None
        """

        :param tmdb_id:
        :param library_id:
        :param title:
        :param year:
        :param source:
        :return:
        """
        values = {Movie.UNIQUE_ID_TMDB: tmdb_id,
                  'timestamp': datetime.date.today()
                  }
        if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            values[Movie.MOVIEID] = library_id
            values[Movie.TITLE] = title
            values[Movie.YEAR] = year
            values[Movie.SOURCE] = source

        cls.abort_on_shutdown()
        with cls.lock:
            cls.load_cache_if_needed()
            if tmdb_id not in cls._all_missing_tmdb_trailers:
                cls._all_missing_tmdb_trailers[tmdb_id] = values
                cls.tmdb_cache_changed()

        Statistics.add_missing_tmdb_trailer()

    @classmethod
    def add_missing_library_trailer(cls,
                                    tmdb_id: int = None,
                                    library_id: int = None,
                                    title: str = None,
                                    year: int = None,
                                    source: str = None
                                    ):
        # type (...) -> None
        """

        :param tmdb_id:
        :param library_id:
        :param title:
        :param year:
        :param source:
        :return:
        """

        values = {
            Movie.MOVIEID: library_id,
            'timestamp': datetime.date.today()
        }

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            values[Movie.UNIQUE_ID_TMDB] = tmdb_id
            values[Movie.TITLE] = title
            values[Movie.YEAR] = year
            values[Movie.SOURCE] = source

        cls.abort_on_shutdown()
        with cls.lock:
            cls.load_cache_if_needed()
            if tmdb_id not in TrailerUnavailableCache._all_missing_library_trailers:
                cls._all_missing_library_trailers[tmdb_id] = values
                cls.library_cache_changed()
                Statistics.add_missing_library_trailer()

    @classmethod
    def is_library_id_missing_trailer(cls,
                                      library_id):
        # type: (int) -> Union[bool, None]
        """

        :param library_id:
        :return:
        """
        cls.abort_on_shutdown()
        with cls.lock:
            cls.load_cache_if_needed()
            if library_id not in cls._all_missing_library_trailers:
                entry = None
            else:
                entry = cls._all_missing_library_trailers[library_id]
                elapsed = datetime.date.today() - entry['timestamp']
                elapsed_days = elapsed.days
                if elapsed_days > Settings.get_expire_remote_db_trailer_check_days():
                    del cls._all_missing_library_trailers[library_id]
                    entry = None
                    cls.library_cache_changed()

        if entry is None:
            Statistics.add_missing_library_id_cache_miss()
        else:
            Statistics.add_missing_library_id_cache_hit()

        return entry

    @classmethod
    def library_cache_changed(cls, flush=False):
        # type: (bool) -> None
        """

        :return:
        """
        cls.library_unsaved_changes += 1
        if cls.library_last_save is None:
            cls.library_last_save = datetime.datetime.now()

        if flush or (cls.library_unsaved_changes >
                     Constants.TRAILER_CACHE_FLUSH_UPDATES) or (
                (datetime.datetime.now() - cls.library_last_save)
                > datetime.timedelta(seconds=Constants.TRAILER_CACHE_FLUSH_SECONDS)):
            cls.save_cache()

    @classmethod
    def is_tmdb_id_missing_trailer(cls,
                                   tmdb_id):
        # type: (int) -> Union[bool, None]
        """

        :param tmdb_id:
        :return:
        """
        cls.abort_on_shutdown()
        with cls.lock:
            cls.load_cache_if_needed()
            if tmdb_id not in cls._all_missing_tmdb_trailers:
                return None
            entry = cls._all_missing_tmdb_trailers[tmdb_id]

            elapsed_time = datetime.date.today() - entry['timestamp']
            elapsed_days = elapsed_time.days
            if elapsed_days > Settings.get_expire_remote_db_trailer_check_days():
                del cls._all_missing_tmdb_trailers[tmdb_id]
                entry = None
                cls.tmdb_cache_changed()

        if entry is None:
            Statistics.add_missing_tmdb_id_cache_miss()
        else:
            Statistics.add_missing_tmdb_cache_hit()

        return entry

    @classmethod
    def tmdb_cache_changed(cls, flush=False):
        # type: (bool) -> None
        """

        :return:
        """
        #
        # TODO: There are several issues here:
        #
        # tmdb_unsaved_changes and last save can be changed here, outside of
        # the lock, while save_cache is in process of writing cache. In which
        # save_cache will reset tmdb_unsaved_changes and tmdb_last_save AFTER
        # we have exited.
        #
        # Also there are issues with multiple threads waiting on lock during
        # a shutdown.
        #
        # Also, if the cache is large, it can take time to write AND it
        # is more vulnerable to corruption, particularly at shutdown.
        #
        # Problems likely in other cache modules.
        #
        # Suggest using object_hook argument on json operations coupled with
        # write to temp file, then rename.  See json_utils_basic.

        with cls.lock:
            cls.tmdb_unsaved_changes += 1
            if cls.tmdb_last_save is None:
                cls.tmdb_last_save = datetime.datetime.now()

            if flush or (cls.tmdb_unsaved_changes >
                         Constants.TRAILER_CACHE_FLUSH_UPDATES) or (
                    (datetime.datetime.now() - cls.tmdb_last_save)
                    > datetime.timedelta(seconds=Constants.TRAILER_CACHE_FLUSH_SECONDS)):
                cls.save_cache()

    @classmethod
    def abort_on_shutdown(cls, ignore_shutdown=False):
        if ignore_shutdown:
            return
        Monitor.throw_exception_if_abort_requested()

    @classmethod
    def save_cache(cls, ignore_shutdown=False) -> None:
        """

        :return:
        """
        cls.abort_on_shutdown(ignore_shutdown=ignore_shutdown)
        with cls.lock:
            cls.load_cache_if_needed()
            if cls.tmdb_unsaved_changes == 0 and cls.library_unsaved_changes == 0:
                return
            if cls.tmdb_unsaved_changes > 0:
                entries_to_delete = []
                for key, entry in cls._all_missing_tmdb_trailers.items():
                    elapsed_time = datetime.date.today() - entry['timestamp']
                    elapsed_days = elapsed_time.days
                    if elapsed_days > Settings.get_expire_remote_db_trailer_check_days():
                        if entry[Movie.UNIQUE_ID_TMDB] in cls._all_missing_tmdb_trailers:
                            entries_to_delete.append(
                                entry[Movie.UNIQUE_ID_TMDB])
                for entry_to_delete in entries_to_delete:
                    del cls._all_missing_tmdb_trailers[entry_to_delete]

                cls.abort_on_shutdown(ignore_shutdown=ignore_shutdown)
                try:
                    path = os.path.join(Settings.get_remote_db_cache_path(),
                                        'index', 'missing_tmdb_trailers.json')
                    temp_path = os.path.join(Settings.get_remote_db_cache_path(),
                                        'index', 'missing_tmdb_trailers.json.temp')

                    # path = path.encode('utf-8')
                    path = xbmcvfs.validatePath(path)
                    temp_path = xbmcvfs.validatePath(temp_path)

                    parent_dir, file_name = os.path.split(temp_path)
                    if not os.path.exists(parent_dir):
                        DiskUtils.create_path_if_needed(parent_dir)

                    with io.open(temp_path, mode='wt', newline=None,
                                 encoding='utf-8', ) as cacheFile:
                        json_text = \
                            json.dumps(cls._all_missing_tmdb_trailers,
                                       encoding='utf-8',
                                       ensure_ascii=False,
                                       default=TrailerUnavailableCache.handler,
                                       indent=3, sort_keys=True)
                        cacheFile.write(json_text)
                        cacheFile.flush()
                    try:
                        os.replace(temp_path, path)
                    except OSError:
                        cls._logger.exception(f'Failed to replace index of movies'
                                              f' missing trailers cache: {path}')

                    cls.tmdb_last_save = datetime.datetime.now()
                    cls.tmdb_unsaved_changes = 0
                except AbortException:
                    reraise(*sys.exc_info())
                except IOError as e:
                    cls._logger.exception('')
                except Exception as e:
                    cls._logger.exception('')
                finally:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

            cls.abort_on_shutdown(ignore_shutdown=ignore_shutdown)
            if cls.library_unsaved_changes > 0:
                entries_to_delete = []

                for key, entry in cls._all_missing_library_trailers.items():
                    elapsed_time = datetime.date.today() - entry['timestamp']
                    elapsed_days = elapsed_time.days
                    if elapsed_days > Settings.get_expire_remote_db_trailer_check_days():
                        if entry[Movie.MOVIEID] in cls._all_missing_library_trailers:
                            entries_to_delete.append(entry[Movie.MOVIEID])

                for entry_to_delete in entries_to_delete:
                    del cls._all_missing_library_trailers[entry_to_delete]

                cls.abort_on_shutdown(ignore_shutdown=ignore_shutdown)
                try:

                    path = os.path.join(Settings.get_remote_db_cache_path(),
                                        'index', 'missing_library_trailers.json')
                    temp_path = os.path.join(Settings.get_remote_db_cache_path(),
                                        'index', 'missing_library_trailers.json.temp')
                    # path = path.encode('utf-8')
                    path = xbmcvfs.validatePath(path)
                    temp_path = xbmcvfs.validatePath(temp_path)

                    parent_dir, file_name = os.path.split(path)
                    if not os.path.exists(parent_dir):
                        DiskUtils.create_path_if_needed(parent_dir)

                    with io.open(temp_path, mode='wt', newline=None,
                                 encoding='utf-8', ) as cacheFile:

                        # TODO: Need ability to interrupt when ABORT. Object_handler
                        # not a valid arg to dumps

                        json_text = \
                            json.dumps(cls._all_missing_library_trailers,
                                       encoding='utf-8',
                                       ensure_ascii=False,
                                       default=TrailerUnavailableCache.handler,
                                       indent=3, sort_keys=True)
                        cacheFile.write(json_text)
                        cacheFile.flush()

                    try:
                        os.replace(temp_path, path)
                    except OSError:
                        cls._logger.exception(f'Failed to replace missing trailer'
                                              f' information cache: {path}')

                    cls.library_last_save = datetime.datetime.now()
                    cls.library_unsaved_changes = 0
                except AbortException:
                    reraise(*sys.exc_info())
                except IOError as e:
                    cls._logger.exception('')
                except Exception as e:
                    cls._logger.exception('')
                finally:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        TrailerUnavailableCache.abort_on_shutdown()
        return dct

    @staticmethod
    def handler(obj):
        # type: (Any) -> Any
        """

        :param obj:
        :return:
        """
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        # else:  # if isinstance(obj, ...):
        #     return json.JSONEncoder.default(self, obj)
        else:
            raise TypeError('Object of type %s with value of %s is not JSON serializable' % (
                type(obj), repr(obj)))

    @staticmethod
    def datetime_parser(dct):
        # type: (Dict[Any]) -> Dict[Any]
        """

        :param dct:
        :return:
        """
        TrailerUnavailableCache.abort_on_shutdown()
        date_string = dct.get('timestamp', None)
        if date_string is not None:
            timestamp = dateutil.parser.parse(date_string)
            dct['timestamp'] = timestamp.date()
            return dct
        else:
            return dct

    @classmethod
    def load_cache_if_needed(cls, force_load: bool = False) -> None:
        """

        :return:
        """
        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'missing_tmdb_trailers.json')
        path = xbmcvfs.validatePath(path)
        cls.abort_on_shutdown()
        with cls.lock:
            if force_load and cls._loaded:
                return
            try:
                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)

                if os.path.exists(path):
                    with io.open(path, mode='rt',
                                           newline=None,
                                           encoding='utf-8') as cacheFile:
                        cls._all_missing_tmdb_trailers = json.load(
                            cacheFile, encoding='utf-8',
                            object_hook=TrailerUnavailableCache.datetime_parser)
                        size = len(cls._all_missing_tmdb_trailers)
                        Statistics.missing_tmdb_trailers_initial_size(size)
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                cls._logger.exception('')
            except JSONDecodeError as e:
                os.remove(path)
            except Exception as e:
                cls._logger.exception('')

            cls.abort_on_shutdown()
            path = os.path.join(Settings.get_remote_db_cache_path(),
                                'index', 'missing_library_trailers.json')
            path = xbmcvfs.validatePath(path)
            try:
                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)
                if os.path.exists(path):
                    with io.open(path, mode='rt',
                                           newline=None,
                                           encoding='utf-8') as cacheFile:
                        cls._all_missing_library_trailers = json.load(
                            cacheFile, encoding='utf-8',
                            object_hook=TrailerUnavailableCache.datetime_parser)
                        size = len(cls._all_missing_library_trailers)
                        Statistics.missing_library_trailers_initial_size(size)
            except AbortException:
                reraise(*sys.exc_info())
            except JSONDecodeError as e:
                os.remove(path)
            except IOError as e:
                cls._logger.exception('')
            except Exception as e:
                cls._logger.exception('')

        cls._loaded = True
