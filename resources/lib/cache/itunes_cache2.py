# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import sys
import datetime
import io
import simplejson as json
import os
import re
import threading

import xbmcvfs

from common.imports import *
from common.logger import LazyLogger
from common.exceptions import (AbortException, CommunicationException,
                               TrailerIdException)
from common.messages import Messages
from common.monitor import Monitor
from backend.movie_entry_utils import (MovieEntryUtils)
from common.movie import AbstractMovie, ITunesMovie
from common.movie_constants import MovieField, MovieType
from common.settings import Settings
from backend import backend_constants
from common.disk_utils import DiskUtils
from diagnostics.statistics import Statistics

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ITunesCache:
    """
    Caching of requests to external sites is done to reduce
    aggregate traffic to these sites for local and remote
    performance reasons.

    In addition, the size of the caches are maintained.
    The user selects how large the caches can
    grow using several different metrics and these classes enforce
    it.

    TODO: Need to add delete of old cache when switching locations, or when
        disabling cache.

        Suggest adding hidden setting to record old cache location(s). Remove
        from settings once actually removed.

    """
    _logger = module_logger.getChild('ITunesCache')
    _instance = None

    def __init__(self) -> None:
        """

        """
        self._garbage_collector_thread = None
        self._garbage_collection_done_event = threading.Event()
        self._messages = Messages
        self._initial_run = True

    @classmethod
    def get_cached_itunes_movie(cls,
                                itunes_id: Union[str, int, None] = None,
                                source: str = None,
                                error_msg: Union[str, int, None] = None
                                ) -> (int, ITunesMovie):
        """
            Attempt to get cached JSON movie information before using the JSON calls
            to get it remotely.

            Any information not in the cache will be placed into it after successfully
            reading it.
        :param itunes_id:
        :param source:
        :param error_msg:
        :return:
        """

        itunes_movie: ITunesMovie = None
        status = 0

        if Settings.is_use_tmdb_cache():
            start = datetime.datetime.now()
            itunes_movie = ITunesCache.read_tmdb_cache_json(itunes_id,
                                                            source=source,
                                                            error_msg=error_msg)
            status = 0
            stop = datetime.datetime.now()
            read_time = stop - start
            Statistics.add_json_read_time(int(read_time.microseconds / 10000))

        if itunes_movie is None and status == 0:
            status = -1

        return status, itunes_movie

    @classmethod
    def read_tmdb_cache_json(cls, itunes_id: Union[int, str],
                             source: str = None,
                             error_msg: str = ''
                             ) -> Union[ITunesMovie, None]:
        """
            Attempts to read TMDB detail data for a specific movie
            from local cache.
        :param itunes_id: TMDB movie ID
        :param source: database source of the movie that needs tmdb data.
                       Ex: library, TMDb, TFH. Used to segregate the cached files
                       to aid garbage collection, etc.
        :param error_msg: Supplies additional text to display on error.
                          Typically a movie title
        :return: AbstractMovie containing cached data, or None if not found

        TODO: For ALL remote json/movie requests, need return code to
        indicate whether communication is down or not. Don't want to purge
        everything just because network is down.

        """

        itunes_id = str(itunes_id)
        exception_occurred = False
        path: str = None
        itunes_movie: ITunesMovie = None
        try:
            # Keep cached files from the source the data/trailer comes from
            path = ITunesCache.get_json_cache_file_path_for_movie_id(itunes_id, source,
                                                               error_msg=error_msg)
            if path is None or not os.path.exists(path):
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'cache file not found for: '
                                                    f'{error_msg} '
                                                    f'itunes_id: {itunes_id} '
                                                    f'path: {path}')
                return None

            if not os.access(path, os.R_OK):
                messages = Messages
                cls._logger.warning(messages.get_msg(
                    Messages.CAN_NOT_READ_FILE) % path)
                return None

            file_mod_time = datetime.datetime.fromtimestamp(
                os.path.getmtime(path))
            now = datetime.datetime.now()
            expiration_time = now - datetime.timedelta(
                Settings.get_expire_trailer_cache_days())

            if file_mod_time < expiration_time:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose('cache file EXPIRED for:', error_msg,
                                                    'itunes_id:', itunes_id,
                                                    'path:', path)
                return None

            Monitor.throw_exception_if_abort_requested()
            with io.open(path, mode='rt', newline=None, encoding='utf-8') as cacheFile:
                try:
                    serializable: MovieType = json.load(cacheFile, encoding='utf-8')
                    serializable[MovieField.CACHED] = True
                    
                    #  TODO: Get rid of this HACK
                    
                    if serializable.get(MovieField.CLASS, '') == ITunesMovie.__name__:                          
                        itunes_movie = ITunesMovie.de_serialize(serializable)
                    else:
                        # serializeable is raw data from TMDb. Must be parsed
                        # by caller (HACK)

                        tmdb_raw_data: MovieType = serializable
                        from discovery.itunes_movie_downloader import ITunesMovieDownloader

                        itunes_movie = ITunesMovieDownloader.parse_itunes_movie(tmdb_raw_data,
                                                                          None,
                                                                          source=source)
                        if (itunes_movie is None and cls._logger.isEnabledFor(
                                LazyLogger.DEBUG_EXTRA_VERBOSE)):
                            cls._logger.debug_extra_verbose(
                                f'Error parsing movie: {error_msg}')

                except Exception as e:
                    cls._logger.exception(e)
                    cls._logger.debug_extra_verbose(
                        'Failing json:', path,  cacheFile)
                    exception_occurred = True
                    itunes_movie = None
        except AbortException:
            reraise(*sys.exc_info())
        except IOError as e:
            cls._logger.exception('')
            itunes_movie = None
            exception_occurred = True
        except Exception as e:
            cls._logger.exception('')
            itunes_movie = None
            exception_occurred = True

        try:
            # Blow away bad cache file
            if exception_occurred and path is not None:
                os.remove(path)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('Trying to delete bad cache file.')
        return itunes_movie

    @classmethod
    def write_tmdb_cache_json(cls, itunes_movie: ITunesMovie, source: str) -> None:
        """
            Write the given movie information into the cache as JSON

            Due to the small size of these files, will not check for
            AbortException during write nor save old version of file.

           Source is the movie database needing this info from TMDb. Used to
           simplify managing the cached files (deletion, etc.).
        """

        itunes_id_str = itunes_movie.get_id()
        source_id_str = itunes_movie.get_source_id()

        try:
            if source is None or source not in MovieField.LIB_TMDB_ITUNES_TFH_SOURCES:
                cls._logger.debug('Invalid source:', source)
            path = ITunesCache.get_json_cache_file_path_for_movie_id(
                itunes_id_str, source)
            parent_dir, file_name = os.path.split(path)
            if not os.path.exists(parent_dir):
                DiskUtils.create_path_if_needed(parent_dir)

            if os.path.exists(path) and not os.access(path, os.W_OK):
                messages = Messages
                cls._logger.error(messages.get_msg(
                    Messages.CAN_NOT_WRITE_FILE) % path)
                return None
            # temp_movie = {}

            #  TODO: Move cache serialize logic into ITunesMovie

            itunes_movie.set_cached(True)
            serializable: MovieType = itunes_movie.get_serializable()

            Monitor.throw_exception_if_abort_requested()
            with io.open(path, mode='wt', newline=None,
                         encoding='utf-8', ) as cache_file:
                json_text = json.dumps(serializable,
                                       ensure_ascii=False,
                                       indent=3, sort_keys=True)
                cache_file.write(json_text)
                cache_file.flush()
                json_cache = JsonITunesCacheHelper.get_json_cache_for_source(source)
                json_cache.add_item(source_id_str, itunes_id_str)
                # del temp_movie
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(f'itunes_id: {itunes_id_str} source: {source}')

    @classmethod
    def get_tmdb_video_id(cls, movie: AbstractMovie) -> str:
        """
            Gets the unique id to use in the cache for the given movie.
            Used for movies which have data from TMDb (
            detail info, etc.) Here we keep the .json file stored according to
            it's itunes_id.

            For trailers, we would keep the cached trailer according to where the data
            comes from.

            Acts as a wrapper around generate_unique_id_from_source

        :param movie:
        :return:
        :raise movieIdException:
        """
        itunes_id = None
        try:
            source = movie.get_source()
            itunes_id = movie.get_id()

            if itunes_id is None:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    cls._logger.debug_verbose(f'TMDBid is None: for: {movie.get_title()} '
                                              f'source: {movie.get_source()}')

            if itunes_id is not None:
                itunes_id = ITunesCache.generate_unique_id_from_source(itunes_id, source)
        except AbortException:
            reraise(*sys.exc_info())
        except TrailerIdException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
        return itunes_id

    @classmethod
    def get_trailer_id(cls, movie: AbstractMovie) -> str:
        """
            TODO: Track down users and modify according to source of data.

            Gets the unique id to use in the trailer cache for the given movie.

            Acts as a wrapper around generate_unique_id_from_source

        :param movie:
        :return:
        :raise movieIdException:
        """
        movie_id = None
        try:
            source = movie.get_source()
            movie_id = movie.get_id()

            if source == MovieField.ITUNES_SOURCE:
                # We only need id for iTunes for generating a key
                # for cached trailers. We could simply use a hash of the
                # title (or the title itself), but instead, since we
                # get additional info from TMDb, we use the TMDb Id.
                #
                #  TODO:  This is a wart. Probably should bite bullet and
                #  generate it from title + year, etc. from the beginning.
                #  It is ugly to leave the field empty so long.

                movie_id = MovieEntryUtils.get_itunes_id(movie)

                if movie_id is None:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        cls._logger.debug_verbose('TMDBid is None for ITunes movie:',
                                                  movie.get_title())
            if movie_id is not None:
                movie_id = ITunesCache.generate_unique_id_from_source(movie_id, source)
        except AbortException:
            reraise(*sys.exc_info())
        except TrailerIdException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
        return movie_id

    @classmethod
    def generate_unique_id_from_source(cls, movie_id: Union[int, str],
                                       source: str,
                                       error_msg: str = ""
                                       ) -> str:
        """
        :param movie_id:
        :param source:
        :param error_msg: Optional text to add to error message. Typically
                            movie title
        :return:str: a unique id for the given movie. Typically it is
            the TMDBId for the movie with a prefix indicating the source
            of the request (t_ for TMDB, no prefix for local database and
                            a_ for Apple/iTunes).
        """
        valid_sources = [MovieField.LIBRARY_SOURCE, MovieField.TMDB_SOURCE,
                         MovieField.ITUNES_SOURCE, MovieField.TFH_SOURCE]
        unique_id = None
        if source not in valid_sources:
            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug('Unsupported source:', source, 'itunes_id:',
                                  movie_id, error_msg)

        if source == MovieField.LIBRARY_SOURCE:
            unique_id = str(movie_id)
        elif source == MovieField.TMDB_SOURCE:
            unique_id = (backend_constants.TMDB_TRAILER_CACHE_FILE_PREFIX +
                         str(movie_id))
        elif source == MovieField.TFH_SOURCE:
            unique_id = str(backend_constants.TFH_TRAILER_CACHE_FILE_PREFIX +
                            str(movie_id))
        elif source == MovieField.ITUNES_SOURCE:
            unique_id = (backend_constants.APPLE_TRAILER_CACHE_FILE_PREFIX +
                         str(movie_id))

        return unique_id

    @classmethod
    def get_json_cache_file_path_for_movie_id(cls, movie_id: Union[int, str],
                                              source: str,
                                              error_msg: str = ''
                                              ) -> Union[str, None]:
        """
            Returns the path for a cache JSON file for the given itunes_id
            and source.

        :param movie_id:
        :param source:
        :param error_msg: Optional text to add to any error message.
                    Typically a movie title.
        :return:
        """
        try:
            # All JSON files from TMDb stay in TMDb directory
            source = MovieField.TMDB_SOURCE
            prefix = ITunesCache.generate_unique_id_from_source(movie_id, source,
                                                          error_msg=error_msg)
            # if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            #     cls._logger.debug('itunes_id:', itunes_id, 'source:', source,
            #                        'prefix:', prefix)
            #
            # To reduce clutter, put cached data into a folder named after the
            # SOURCE and first character of the id
            #
            # For local library entries, just use the first digit from the
            # numeric id.

            if source == MovieField.LIBRARY_SOURCE:
                folder = prefix[0]
            elif source == MovieField.TMDB_SOURCE:
                #
                # For TMDB entries, the numeric TMDB id is prefaced with:
                # "tmdb_". Use a folder named "t" + first digit of TMDBID
                #
                x = prefix.split('_', 1)
                folder = 't' + x[1][0]
            elif source == MovieField.TFH_SOURCE:
                #
                # For TFH entries, the numeric TFH id is prefaced with:
                # "tfh_". Use a folder named "h" + first digit of TFH
                #
                x = prefix.split('_', 1)
                folder = 'h' + x[1][0]
            elif source == MovieField.ITUNES_SOURCE:
                #
                # For ITunes entries, Apple does not supply an ID, so we
                # use the TMDB ID instead if we can find it. (A lot of these are
                # for very new or unreleased movies.)
                #
                # The TMDB id here is prefaced with: "appl_". Use a folder named
                # "a" + first digit of TMDBID.

                x = prefix.split('_', 1)
                folder = 'a' + x[1][0]
            else:
                cls._logger.debug('Unexpected source:', source,
                                  'itunes_id:', movie_id)
                return None

            cache_file = prefix + '.json'
            path = os.path.join(Settings.get_remote_db_cache_path(),
                                folder, cache_file)
            path = xbmcvfs.validatePath(path)

            return path
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
        return None

    @classmethod
    def is_trailer_from_cache(cls, path: str) -> bool:
        """

        :param path:
        :return:
        """
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        if path.startswith(cache_path_prefix):
            return True
        return False

    @classmethod
    def get_trailer_cache_file_path_for_movie_id(cls, movie: AbstractMovie,
                                                 orig_file_name: str,
                                                 normalized: bool) -> str:
        """
            Generates the path for a file in the cache
            for a movie for given movie.

        :param movie:
        :param orig_file_name:
        :param normalized:
        :return:
        """
        path = ''
        movie_id = None
        source = None
        try:
            if movie.get_source() in MovieField.LIB_TMDB_ITUNES_TFH_SOURCES:
                movie_id = ITunesCache.get_tmdb_video_id(movie)
                source = movie.get_source()
            else:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                    cls._logger.debug('Not valid video source title:',
                                      movie.get_title(),
                                      'source:', movie.get_source())

            if movie_id is not None:

                # itunes_id may begin with an '_'.

                prefix = movie_id + '_'
                folder = None
                if source == MovieField.LIBRARY_SOURCE:
                    folder = movie_id[0]
                elif source == MovieField.TMDB_SOURCE:
                    x = prefix.split('_', 1)
                    folder = 't' + x[1][0]
                elif source == MovieField.TFH_SOURCE:
                    x = prefix.split('_', 1)
                    folder = 'h' + x[1][0]
                elif source == MovieField.ITUNES_SOURCE:
                    x = prefix.split('_', 1)
                    folder = 'a' + movie_id[1][0]

                # Possible that movie was downloaded into cache

                orig_file_name = re.sub(
                    r'^' + re.escape(prefix), '', orig_file_name)

                if normalized:
                    if 'normalized_' in orig_file_name:
                        cls._logger.debug('Already normalized:',
                                          movie.get_title(),
                                          'orig_file_name:', orig_file_name)
                        file_name = prefix + orig_file_name
                    else:
                        file_name = prefix + 'normalized_' + orig_file_name
                else:
                    file_name = prefix + orig_file_name

                path = os.path.join(Settings.get_downloaded_trailer_cache_path(),
                                    folder, file_name)
                # Should not be needed
                path = xbmcvfs.validatePath(path)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            title = movie.get_title()
            cls._logger.exception('title:', title)

            path = ''

        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.debug_extra_verbose('Path:', path)
        return path
