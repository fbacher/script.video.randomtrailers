# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""
from pathlib import Path

from common.imports import *

import datetime
import io
import simplejson as json
from common.movie import AbstractMovieId, TMDbMovieId, TMDbMovie
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


class BaseTrailerIndex:
    """
    Tracks some useful information about movies, particularly about remote trailers.

    - Whether a movie has a trailer or not
      - If trailer is local (either in movie database or in a cache)
      - If a remote trailer is known to exist
    - The TMDbId of the movie (where trailers frequently come from)
    - The LibraryId of the movie (if it is for a movie in the database)

    There are separate subclasses for each movie type (Library, TMDb, etc.), which
    is done to aid in garbage collection of trailers: we can determine live references
    to each trailer. Instances of this class track each movie instance.

    BaseReverseIndexCache has a similar function for tracking the live
    references to .json files.
    """

    CACHE_PATH_DIR: str = os.path.join(Settings.get_remote_db_cache_path(),
                                       'index')
    _lock = threading.RLock()
    _last_saved = datetime.datetime(year=1900, month=1, day=1)
    _parameters = None
    _unsaved_changes: int = 0
    _logger = None

    _cache: Dict[str, AbstractMovieId] = {}
    _cache_loaded: bool = False
    _cache_path: Path = None

    @classmethod
    def class_init(cls, cache_name: str) -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        try:
            cls._cache_path = Path(f'{cls.CACHE_PATH_DIR}/{cache_name}.json')
        except Exception:
            cls._logger.exception()

    @classmethod
    def add(cls, abstract_movie_id: AbstractMovieId, flush: bool = False) -> None:
        """

        :param abstract_movie_id:
        :param flush:
        :return:
         """
        cls._logger.debug(f'movie_id: {abstract_movie_id}')

        with cls._lock:
            try:
                cls.load_cache()
                if isinstance(abstract_movie_id, TMDbMovie):
                    cls._logger.debug(f'Converting to TMDBMovie')
                    movie = abstract_movie_id.get_as_movie_id_type()
                    cls._logger.debug(f'Converted to: {type(abstract_movie_id)}')
                cls._cache[abstract_movie_id.get_id()] = abstract_movie_id
                cls._unsaved_changes += 1
                cls.save_cache(flush=flush)  # If needed
            except Exception:
                cls._logger.exception()

    @classmethod
    def remove(cls, abstract_movie_id: AbstractMovieId, flush: bool = False) -> None:
        """
        Remove the TMDbMovieId with the given tmdb_id from the
        cached and persisted entries.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param abstract_movie_id:
        :param flush:
        :return:
         """
        with cls._lock:
            try:
                cls.load_cache()
                try:
                    movie_id: str = abstract_movie_id.get_id()
                    if movie_id in cls._cache:
                        del cls._cache[movie_id]
                        cls._unsaved_changes += 1
                except KeyError:
                    pass

                cls.save_cache(flush=flush)  # If needed
            except Exception:
                cls._logger.exception()

    @classmethod
    def get(cls, movie_id: str) -> AbstractMovieId:
        """
        Return AbstractMovieId identified by movie_id

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param movie_id:

        :return:
        """
        with cls._lock:
            try:
                cls.load_cache()
                return cls._cache.get(movie_id, None)
            except Exception:
                cls._logger.exception()

    @classmethod
    def get_all(cls) -> List[AbstractMovieId]:
        with cls._lock:
            try:
                cls.load_cache()
                values: List[AbstractMovieId] = []
                x: ValuesView = cls._cache.values()
                values.extend(x)
                return values
            except Exception:
                cls._logger.exception()

    @classmethod
    def get_all_with_local_trailers(cls) -> List[AbstractMovieId]:
        with cls._lock:
            try:
                ids_with_local_trailers: List[AbstractMovieId] = []
                cls.load_cache()
                abstract_movie_id: AbstractMovieId
                for abstract_movie_id in cls._cache.values():
                    if abstract_movie_id.has_local_trailer():
                        ids_with_local_trailers.append(abstract_movie_id)
                return ids_with_local_trailers
            except Exception:
                cls._logger.exception()

    @classmethod
    def get_all_with_non_local_trailers(cls) -> List[AbstractMovieId]:
        with cls._lock:
            try:
                ids_with_trailers: List[AbstractMovieId] = []
                cls.load_cache()
                abstract_movie_id: AbstractMovieId
                for abstract_movie_id in cls._cache.values():
                    if (abstract_movie_id.get_has_trailer() and
                            not abstract_movie_id.has_local_trailer()):
                        ids_with_trailers.append(abstract_movie_id)
                return ids_with_trailers
            except Exception:
                cls._logger.exception()

    @classmethod
    def get_all_with_no_known_trailers(cls) -> List[AbstractMovieId]:
        with cls._lock:
            try:
                ids_without_trailers: List[AbstractMovieId] = []
                cls.load_cache()
                abstract_movie_id: AbstractMovieId
                for abstract_movie_id in cls._cache.values():
                    if not abstract_movie_id.get_has_trailer():
                        ids_without_trailers.append(abstract_movie_id)
                return ids_without_trailers
            except Exception:
                cls._logger.exception()

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            try:
                cls._cache.clear()
                cls.save_cache(flush=True)
            except Exception:
                cls._logger.exception()

    @classmethod
    def load_cache(cls) -> None:
        """
        Loads the cache of TMDb Ids which are known to have trailers.

        :return:
        """
        try:
            if cls._cache_loaded:
                return

            parent_dir, file_name = os.path.split(cls._cache_path)
            DiskUtils.create_path_if_needed(parent_dir)

            with cls._lock:
                if os.path.exists(cls._cache_path):
                    with io.open(cls._cache_path, mode='rt', newline=None,
                                 encoding='utf-8') as cache_file:
                        temp_cache: Dict[str, Dict[str, str]] = json.load(
                            cache_file, encoding='utf-8')
                        new_cache: Dict[str, AbstractMovieId] = {}
                        for data in temp_cache.values():
                            try:
                                movie_id = AbstractMovieId.de_serialize(data)
                                new_cache[movie_id.get_id()] = movie_id
                            except Exception:
                                cls._logger.exception()

                        cls._cache = new_cache
                        cls._last_saved = datetime.datetime.now()
                        cls._unsaved_changes = 0
                else:
                    cls._cache.clear()

                cls._cache_loaded = True

            Monitor.throw_exception_if_abort_requested()

        except AbortException:
            reraise(*sys.exc_info())
        except IOError as e:
            cls._logger.exception('')
        except JSONDecodeError as e:
            os.remove(cls._cache_path)
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def save_cache(cls, flush: bool = False) -> None:
        """
        :param flush:
        :return:
        """
        flush = True
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
                cls._logger.debug(f'saving cache {cls._cache_path}')
                parent_dir, file_name = os.path.split(cls._cache_path)
                DiskUtils.create_path_if_needed(parent_dir)
                tmp_path: Path = Path(str(cls._cache_path) + '.tmp')
                tmp_path = Path(xbmcvfs.validatePath(tmp_path.as_posix()))
                tmp_cache: Dict[str, Dict[str, str]] = {}
                for movie in cls._cache.values():
                    tmp_cache[movie.get_id()] = movie.serialize()

                with cls._lock, io.open(tmp_path, mode='wt', newline=None,
                                        encoding='utf-8') as cache_file:
                    # Can create reverse_cache from cache
                    json_text = json.dumps(tmp_cache,
                                           ensure_ascii=False,
                                           indent=3, sort_keys=True)
                    cache_file.write(json_text)
                    cache_file.flush()
                    cls._last_saved = datetime.datetime.now()
                    cls._unsaved_changes = 0

                try:
                    os.replace(tmp_path, cls._cache_path)
                except OSError:
                    cls._logger.exception(f'Failed to replace missing movie'
                                          f' information cache: {cls._cache_path}')

                Monitor.throw_exception_if_abort_requested()
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                cls._logger.exception()
            except Exception as e:
                cls._logger.exception()


BaseTrailerIndex.class_init(cache_name='Dummy_cache_name')