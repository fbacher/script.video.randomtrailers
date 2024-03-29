# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import datetime

import io
import simplejson as json
from cache.json_cache_helper import JsonCacheHelper
from simplejson import JSONDecodeError
import os
import threading

import xbmcvfs
from common.imports import *

from common.debug_utils import Debug
from common.logger import LazyLogger
from common.monitor import Monitor
from common.movie import TFHMovie
from common.movie_constants import MovieField, MovieType
from common.settings import Settings
from common.disk_utils import DiskUtils
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
    CACHE_COMPLETE = "CACHE_COMPLETE"
    INCOMPLETE_CREATION_DATE_STR = '1900:01:01'

    # Saving the single .json file is expensive.
    #
    # MAX_UNSAVED_CHANGES and MIN_MINUTES_BETWEEN_SAVES both limit how
    # often the cache is saved to disk.
    #
    # By far, most cache activity occurs when the cache data expires and
    # must be downloaded from TFH. (See Settings.get_tfh_cache_expiration_days)
    # Cache expiration is most likely detected at startup.
    #
    # After the cache is created (from data downloaded from TFH), changes
    # to the cache tend to be infrequent, only as trailers are played. The
    # only exception is that at startup, a small number of trailers (about 3)
    # are prepared for playing and loaded into a cache.
    #
    # Here, a large MAX_UNSAVED_CHANGES value causes it to be ignored since
    # it should be very rare that that many changes can occur prior to
    # MIN_MINUTES_BETWEEN_SAVES expires.
    #
    # A special cache entry, INDEX_CREATION_DATE, is used to determine
    # if the cache was fully downloaded and saved. This entry also
    # determines if the cache is expired.
    #
    # If changes to the cache are not saved, the only consequence is
    # that something must be rediscovered. Updates to this cache is
    # primarily to save the TMDb_id corresponding to a TFH trailer,or
    # the fact that the TMDb_id could not be discovered.

    MAX_UNSAVED_CHANGES: int = 10000
    MIN_MINUTES_BETWEEN_SAVES: int = 5

    _initialized = threading.Event()
    lock = threading.RLock()
    _logger: LazyLogger = None
    _cached_movies: Dict[str, TFHMovie] = {}
    _last_saved_movie_timestamp = datetime.datetime.now()
    _tfh_json_cache = JsonCacheHelper.get_json_cache_for_source(
        source=MovieField.TFH_SOURCE)

    # Does NOT capture changes to the entries, only to the addition or
    # removal of the entries.

    _unsaved_changes: int = 0

    # Cache is marked with timestamp of last update of movie ids from TFH
    # Also marked whether the cache was completely updated.

    _time_of_index_creation = datetime.datetime(2000, 1, 1)  # expired
    _cache_complete = False

    @classmethod
    def class_init(cls) -> None:
        """
        :return:
        """
        cls._logger = module_logger.getChild(type(cls).__name__)
        if Settings.is_include_tfh_trailers():
            cls.load_cache()
        else:
            cls._logger.debug_extra_verbose('TFH not enabled')

    @classmethod
    def logger(cls) -> LazyLogger:
        """

        :return:
        """
        cls._initialized.wait()
        return cls._logger

    @classmethod
    def save_cache(cls, flush: bool = False, complete: bool = None) -> None:
        """
        :param flush:
        :param complete:
        :return:

        """
        cls._initialized.wait()
        with cls.lock:
            seconds_since_last_save: float
            seconds_since_last_save = (datetime.datetime.now() -
                                    cls._last_saved_movie_timestamp).total_seconds()
            minutes_since_last_save: int = int(seconds_since_last_save / 60)
            do_flush = False
            if (flush or
                    (cls._unsaved_changes > cls.MAX_UNSAVED_CHANGES)
                    or (minutes_since_last_save > cls.MIN_MINUTES_BETWEEN_SAVES)):
                do_flush = True
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    delta = int((datetime.datetime.now() -
                                cls._last_saved_movie_timestamp).total_seconds() / 60)
                    cls._logger.debug_extra_verbose(f'flush: {flush} '
                                                    f'complete: {complete} '
                                                    f'changes: {cls._unsaved_changes} '
                                                    f'time: {delta}' )
            if not do_flush:
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
                with io.open(tmp_path, mode='wt', newline=None,
                             encoding='utf-8', ) as cacheFile:

                    cls._logger.debug(f'complete: {complete} cache_complete: '
                                      f'{cls._cache_complete}')
                    if (complete is None and cls._cache_complete) or complete:
                        cls._cache_complete = True
                        cls._logger.debug(f'complete2: {complete} cache_complete: '
                                          f'{cls._cache_complete}')
                        cls._set_creation_date()

                    creation_date_str = datetime.datetime.strftime(
                        cls._time_of_index_creation, '%Y:%m:%d')

                    dummy_tfh_movie: TFHMovie
                    dummy_tfh_movie = TFHMovie(movie_id=cls.INDEX_CREATION_DATE)
                    dummy_tfh_movie.set_title('cache complete marker')
                    dummy_tfh_movie.set_property(cls.INDEX_CREATION_DATE,
                                                 creation_date_str)
                    cls._logger.debug(f'complete3: {complete} cache_complete: '
                                      f'{cls._cache_complete}')
                    dummy_tfh_movie.set_property(cls.CACHE_COMPLETE, cls._cache_complete)

                    movie: TFHMovie

                    #
                    # Don't save more fields than we need, slows down
                    # load/save operations.
                    #

                    temp_movies: Dict[str, TFHMovie] = {}

                    for movie in cls._cached_movies.values():
                        try:
                            temp_movie: TFHMovie = TFHMovie(movie_id=movie.get_id())
                            temp_movie.set_cached(True)
                            temp_movie.set_tfh_id(movie.get_id())
                            temp_movie.set_plot(movie.get_plot())  # Very likely empty
                            temp_movie.set_title(movie.get_title())
                            temp_movie.set_trailer_path(movie.get_trailer_path())
                            temp_movie.set_trailer_type(movie.get_trailer_type())
                            temp_movie.set_tfh_title(movie.get_tfh_title())
                            findable: bool = movie.is_tmdb_id_findable()
                            #
                            # Only set when NOT findable.
                            #
                            if not findable:
                                temp_movie.set_tmdb_id_findable(findable)

                            tmdb_id: int = movie.get_tmdb_id()
                            if tmdb_id is not None:
                                temp_movie.set_tmdb_id(tmdb_id)
                            temp_movies[movie.get_id()] = temp_movie
                        except Exception as e:
                            a = 1

                    temp_movies[cls.INDEX_CREATION_DATE] = dummy_tfh_movie

                    json_text = json.dumps(temp_movies,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           default=TFHCache.encoder,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    del temp_movies

                    cls._last_saved_movie_timestamp = datetime.datetime.now()
                    cls._unsaved_changes = 0

                try:
                    os.replace(tmp_path, path)
                except OSError:
                    cls._logger.exception(f'Failed to replace missing movie'
                                          f' information cache: {path}')
            except IOError as e:
                cls._logger.exception('')
            except Exception as e:
                cls._logger.exception('')

        Monitor.throw_exception_if_abort_requested()

    @classmethod
    def load_cache(cls) -> None:
        """

        :return: True if cache is full and no further discovery needed
        """

        with cls.lock:
            cls._initialized.set()
            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json')
                path = xbmcvfs.validatePath(path)

                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)

                if os.path.exists(path):
                    with io.open(path, mode='rt', newline=None,
                                 encoding='utf-8') as cacheFile:
                        cls._cached_movies = json.load(
                            cacheFile,
                            object_hook=TFHCache.decoder)

                    movie: TFHMovie
                    movie_ids_to_delete: List[str] = []
                    #
                    # Read and delete INDEX_CREATION_DATE entry
                    # to set state of the cache
                    #
                    cls._logger.debug(f'entries: {len(cls._cached_movies)}')
                    cls.load_creation_date()
                    for key, movie in cls._cached_movies.items():
                        if not isinstance(movie, TFHMovie):
                            movie_ids_to_delete.append(movie.get_id())
                        elif not movie.is_sane(MovieField.TFH_SKELETAL_MOVIE):
                            movie_ids_to_delete.append(movie.get_id())

                    if len(movie_ids_to_delete) > 0:
                        cls.remove_movies(movie_ids_to_delete, flush=True)

                    cls._last_saved_movie_timestamp = datetime.datetime.now()
                    cls._unsaved_changes = 0
                else:
                    cls._cached_movies = dict()
                    # Set to an old time so that cache is expired
                    cls._time_of_index_creation = datetime.datetime(2000, 1, 1)

            except IOError as e:
                cls._logger.exception('')
            except JSONDecodeError as e:
                os.remove(path)
                cls._logger.exception('')
            except Exception as e:
                cls._logger.exception('')

        Monitor.throw_exception_if_abort_requested()
        return

    @classmethod
    def load_creation_date(cls) -> None:
        # Loads the last time the index was created from a cached entry.
        # If no cached entry with the timestamp exists, set it to now.

        cls._logger.enter()
        try:
            creation_date = None
            creation_date_movie: TFHMovie = cls._cached_movies.get(cls.INDEX_CREATION_DATE,
                                                                   None)
            if creation_date_movie is not None:
                creation_date_entry: MovieType = creation_date_movie.get_as_movie_type()

            # Debug.dump_json(text='TFH INDEX_CREATION_DATE',
            #                 data=creation_date_entry,
            #                 log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)
            # cls._logger.debug(f'creation_date_entry: {creation_date_entry}')
            if creation_date_entry is not None:
                creation_date = creation_date_entry.get(cls.INDEX_CREATION_DATE,
                                                        None)
                cls._cache_complete = creation_date_entry.get(cls.CACHE_COMPLETE, False)
                x = None
                if creation_date is not None:
                    x = Utils.strptime(creation_date, '%Y:%m:%d')
            cls._logger.debug(f'creation_date: {creation_date} '
                              f'creation_date_entry: {creation_date_entry} '
                              f'x: {x}')

            cls._logger.debug(f'cache_complete: {cls._cache_complete} '
                              f' creation_date: {creation_date} '
                              f'x: {x:%Y-%m-%d %H:%M}')
            if creation_date is None:
                cls._set_creation_date()
                cls._cache_complete = False
                return
            else:
                # Remove dummy entry from cache
                del cls._cached_movies[cls.INDEX_CREATION_DATE]

            # Just to be consistent, all cached_trailer entries are TFHMovie (i.e. Dict)
            # So, get the actual timestamp from it

            cls._time_of_index_creation = Utils.strptime(creation_date, '%Y:%m:%d')
        except Exception:
            cls._logger.exception()
        return

    @classmethod
    def _set_creation_date(cls) -> None:
        cls._time_of_index_creation = datetime.datetime.now()

    @classmethod
    def get_creation_date(cls) -> datetime.datetime:
        return cls._time_of_index_creation

    @classmethod
    def is_complete(cls) -> bool:
        return cls._cache_complete

    @classmethod
    def add_movies(cls, movies: Dict[str, TFHMovie],
                   total: int = None, flush: bool = False) -> None:
        cls._initialized.wait()
        with cls.lock:
            for key, movie in movies.items():
                if not movie.is_sane(MovieField.TFH_SKELETAL_MOVIE):
                    cls._logger.debug(f'TFH movie not sane: {movie.get_title}')
                cls._cached_movies[key] = movie
                tmdb_id: int = movie.get_tmdb_id()
                if tmdb_id is not None:
                    cls._tfh_json_cache.add_item(key, str(movie.get_tmdb_id()))

                cls._unsaved_changes += 1
                cls.save_cache(flush=flush)

    @classmethod
    def add_movie(cls, movie: TFHMovie, total: int = None, flush=False) -> None:
        if not movie.is_sane(MovieField.TFH_SKELETAL_MOVIE):
            cls._logger.debug(f'TFH movie not sane: {movie.get_title}')
        cls._initialized.wait()
        with cls.lock:
            key = movie.get_id()
            cls._cached_movies[key] = movie
            tmdb_id: int = movie.get_tmdb_id()
            if tmdb_id is not None:
                cls._tfh_json_cache.add_item(key, str(movie.get_tmdb_id()))

            cls._unsaved_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def remove_movies(cls, movie_ids: List[str], flush: bool = False) -> None:
        cls._initialized.wait()
        with cls.lock:
            for movie_id in movie_ids:
                if movie_id in cls._cached_movies:
                    del cls._cached_movies[movie_id]
                    cls._unsaved_changes += 1

            cls.save_cache(flush=flush)

    @classmethod
    def update_movie(cls, movie: TFHMovie,
                       flush=False) -> None:
        """
            Nearly identical (for now) to add_movie.

            Typically, due to shallow_copy of get_cached_trailers, the
            movie is already in the _cached_trailers map. It is important
            to bump the unsaved_trailer_changes count.

        :param movie:
        :param flush:
        :return:
        """
        cls._initialized.wait()
        with cls.lock:
            key = movie.get_id()
            cls._cached_movies[key] = movie
            tmdb_id: int = movie.get_tmdb_id()
            if tmdb_id is not None:
                cls._tfh_json_cache.add_item(key, str(movie.get_tmdb_id()))

            cls._unsaved_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def get_cached_movie(cls, movie_id: str) -> TFHMovie:
        cls._initialized.wait()
        with cls.lock:
            return cls._cached_movies.get(movie_id)

    @classmethod
    def get_cached_movies(cls) -> Dict[str, TFHMovie]:
        cls._initialized.wait()
        with cls.lock:
            return cls._cached_movies.copy()

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        return dct

    @staticmethod
    def encoder(dct: TFHMovie) -> MovieType:
        Monitor.throw_exception_if_abort_requested()
        if isinstance(dct, TFHMovie):
            return dct.get_as_movie_type()
        return dct

    @staticmethod
    def decoder(dct: MovieType) -> Union[TFHMovie, Dict[str, Any]]:
        try:
            Monitor.throw_exception_if_abort_requested()
            # if len(dct.values()) > 0:
            #     for value in dct.values():
            #         if isinstance(value, TFHMovie):
            #             return dct
            #         break
            # Debug.dump_json(text='decoder1', data=dct,
            #                 log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)

            if MovieField.TFH_ID in dct:
                tfh_id: str = dct.get(MovieField.TFH_ID)
                movie = TFHMovie(movie_id=tfh_id, movie_info=dct)
                return movie

        except Exception as e:
            TFHCache._logger.exception()
        return dct


TFHCache.class_init()
