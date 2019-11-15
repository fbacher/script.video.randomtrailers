# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

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
from kodi_six import utils

from common.development_tools import (Any, Dict, Union,
                                      TextType, MovieType)
from common.constants import Constants, Movie
from common.logger import (Logger, LazyLogger)
from common.exceptions import (
    TrailerIdException)
from common.messages import Messages
from backend.movie_entry_utils import (MovieEntryUtils)
from common.settings import Settings
from backend import backend_constants
from common.disk_utils import DiskUtils
from backend.json_utils_basic import (JsonUtilsBasic)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'cache.cache')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class Cache(object):
    """
    Caching of requests to external sites is done to reduce
    aggregate traffic to these sites for local and remote
    performance reasons.

    In addition, the size of the caches are maintained.
    The user selects how large the caches can
    grown using several different metrics and these classes enforce
    it.

    TODO: Need to add delete of old cache when switching locations, or when
        disabling cache.

        Suggest adding hidden setting to record old cache location(s). Remove
        from settings once actually removed.

    """
    _logger = module_logger.getChild('Cache')
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._garbage_collector_thread = None
        self._garbage_collection_done_event = threading.Event()
        self._messages = Messages.get_instance()
        self._initial_run = True

    @staticmethod
    def get_instance():
        # type: () -> Cache
        """
            Returns the singleton instance of Cache

        :return:
        """
        if Cache._instance is None:
            Cache._instance = Cache()
        return Cache._instance

    @staticmethod
    def get_cached_json(url,  # type; TextType
                        movie_id=None,  # type: Union[TextType, int, None]
                        error_msg=None,  # type: Union[TextType, int, None]
                        source=None,  # type: Union[TextType, None]
                        dump_results=False,  # type: bool
                        dump_msg='',  # type: TextType
                        headers=None,  # type: Union[dict, None]
                        params=None,  # type: Union[dict, None]
                        timeout=3.0  # type: int
                        ):
        # type: (...) -> (int, TextType)
        """
            Attempt to get cached JSON movie information before using the JSON calls
            to get it remotely.

            Any information not in the cache will be placed into it after successfully
            reading it.
        :param url:
        :param movie_id:
        :param error_msg:
        :param source:
        :param dump_results:
        :param dump_msg:
        :param headers:
        :param params:
        :param timeout:
        :return:
        """

        if headers is None:
            headers = {}

        if params is None:
            params = {}

        trailer_data = None
        status = 0
        if source is None or source not in Movie.LIB_TMDB_ITUNES_SOURCES:
            Cache._logger.error('Invalid source:', source)

        if Settings.is_use_tmdb_cache():
            start = datetime.datetime.now()
            trailer_data = Cache.read_tmdb_cache_json(
                movie_id, source, error_msg=error_msg)
            status = 0
            stop = datetime.datetime.now()
            read_time = stop - start
            if Cache._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
                Cache._logger.debug_extra_verbose('json cache read time:',
                                                  read_time.microseconds / 10000,
                                                  'ms')
            if trailer_data is not None:
                trailer_data[Movie.CACHED] = True

        if trailer_data is None:
            status, trailer_data = JsonUtilsBasic.get_json(url, dump_results=dump_results,
                                                           dump_msg=dump_msg,
                                                           headers=headers,
                                                           error_msg=error_msg, params=params,
                                                           timeout=timeout)
            if (
                    status == 0 or status == 200) and trailer_data is not None and \
                    Settings.is_use_tmdb_cache():
                Cache.write_tmdb_cache_json(movie_id, source, trailer_data)

        return status, trailer_data

    @staticmethod
    def read_tmdb_cache_json(movie_id,  # type: Union[int, TextType]
                             source,  # type: TextType
                             error_msg=''  # type: TextType
                             ):
        # type: (...) ->  Union[MovieType, None]
        """
            Attempts to read TMDB detail data for a specific movie
            from local cache.
        :param movie_id: TMDB movie ID
        :param source: Source database that caused this request (local,
                       TMDB, iTunes)
        :param error_msg: Supplies additional text to display on error.
                          Typically a movie title
        :return: MovieType containing cached data, or None if not found
        """

        trailer = None
        movie_id = str(movie_id)
        exception_occurred = False
        path = None

        try:
            path = Cache.get_json_cache_file_path_for_movie_id(movie_id, source,
                                                               error_msg=error_msg)
            if not os.path.exists(path):
                if Cache._logger.isEnabledFor(Logger.DEBUG):
                    Cache._logger.debug('cache file not found for:', error_msg,
                                        'id:', movie_id, 'source:', source)
                return None

            if not os.access(path, os.R_OK):
                messages = Messages.get_instance()
                Cache._logger.error(messages.get_msg(
                    Messages.CAN_NOT_READ_FILE) % path)
                return None

            file_mod_time = datetime.datetime.fromtimestamp(
                os.path.getmtime(path))
            if file_mod_time < Constants.CACHE_FILE_EXPIRED_TIME:
                if Cache._logger.isEnabledFor(Logger.DEBUG):
                    Cache._logger.debug('cache file EXPIRED for:', error_msg,
                                        'id:', movie_id, 'source:', source)
                return None

            with io.open(path, mode='rt', newline=None, encoding='utf-8') as cacheFile:
                trailer = json.load(cacheFile, encoding='utf-8')
            trailer[Movie.CACHED] = True
        except (IOError) as e:
            Cache._logger.exception('')
            trailer = None
            exception_occurred = True
        except (Exception) as e:
            Cache._logger.exception('')
            trailer = None
            exception_occurred = True

        try:
            # Blow away bad cache file
            if exception_occurred and path is not None:
                os.remove(path)
        except (Exception) as e:
            Cache._logger.exception('Trying to delete bad cache file.')
        return trailer

    @staticmethod
    def write_tmdb_cache_json(movie_id,  # type: Union[TextType, int]
                              source,  # type: TextType
                              trailer  # type: MovieType
                              ):
        # type: (...) -> None
        """
            Write the given movie information into the cache as JSON
        """
        try:
            if source is None or source not in Movie.LIB_TMDB_ITUNES_SOURCES:
                Cache._logger.error('Invalid source:', source)
            start = datetime.datetime.now()
            movie_id = str(movie_id)
            path = Cache.get_json_cache_file_path_for_movie_id(
                movie_id, source)
            parent_dir, file_name = os.path.split(path)
            if not os.path.exists(parent_dir):
                DiskUtils.create_path_if_needed(parent_dir)

            if os.path.exists(path) and not os.access(path, os.W_OK):
                messages = Messages.get_instance()
                Cache._logger.error(messages.get_msg(
                    Messages.CAN_NOT_WRITE_FILE) % path)
                return None
            with io.open(path, mode='wt', newline=None,
                         encoding='utf-8', ) as cacheFile:
                json_text = utils.py2_decode(json.dumps(trailer,
                                                        encoding='utf-8',
                                                        ensure_ascii=False,
                                                        indent=3, sort_keys=True))
                cacheFile.write(json_text)
                cacheFile.flush()
                stop = datetime.datetime.now()
                write_time = stop - start
                if Cache._logger.isEnabledFor(Logger.DEBUG):
                    Cache._logger.debug('json cache write time:',
                                        write_time.microseconds / 10000, 'ms')
        except (Exception) as e:
            Cache._logger.exception('')

    @staticmethod
    def get_video_id(trailer):
        # type: (MovieType) -> TextType
        """
            Gets the unique id to use in the cache for the given movie.

            Acts as a wrapper around generate_unique_id_from_source

        :param trailer:
        :return:
        :raise TrailerIdException:
        """
        movie_id = None
        try:
            source = trailer[Movie.SOURCE]
            valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                             Movie.ITUNES_SOURCE, Movie.TFH_SOURCE]
            if source in valid_sources:
                if source == Movie.LIBRARY_SOURCE:
                    movie_id = trailer[Movie.MOVIEID]
                elif source == Movie.TMDB_SOURCE:
                    movie_id = MovieEntryUtils.get_tmdb_id(trailer)
                elif source == Movie.TFH_SOURCE:
                    movie_id = trailer[Movie.TFH_ID]

                elif source == Movie.ITUNES_SOURCE:
                    # Apple doesn't provide ID, use TMDB ID instead.

                    movie_id = MovieEntryUtils.get_tmdb_id(trailer)

                    if movie_id is None:
                        if Cache._logger.isEnabledFor(Logger.DEBUG):
                            Cache._logger.debug('TMDBid is None for ITunes movie:',
                                                trailer[Movie.TITLE])
                if movie_id is not None:
                    movie_id = Cache.generate_unique_id_from_source(movie_id,
                                                                    source)
        except (TrailerIdException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            Cache._logger.exception('')
        return movie_id

    @staticmethod
    def generate_unique_id_from_source(movie_id,  # type: Union[int, TextType]
                                       source,  # type: TextType
                                       error_msg=''  # type: TextType
                                       ):
        # type: (...) ->  Union[MovieType, None]
        """
            Every query is from TMDB, so we could always use the TMDBId
            as the key, However, library entries don't have to have
            the TMDBId, so to avoid cost of queying TMDB for it, we
            simply use a cache file by kodi library id.

            TODO: consider storing TMDBID in database and always using TMDBID

        :param movie_id:
        :param source:
        :param error_msg: Optional text to add to error message. Typically
                            movie title
        :return:TextType: a unique id for the given movie.Typically it is
            the TMDBId for the movie with a prefix indicating the source
            of the request (t_ for TMDB, no prefix for local database and
                            a_ for Apple/iTunes).
        """
        valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                         Movie.ITUNES_SOURCE, Movie.TFH_SOURCE]
        unique_id = None
        if source not in valid_sources:
            if Cache._logger.isEnabledFor(Logger.DEBUG):
                Cache._logger.debug('Unsupported source:', source, 'movie_id:',
                                    movie_id, error_msg)

        if source == Movie.LIBRARY_SOURCE:
            unique_id = str(movie_id)
        elif source == Movie.TMDB_SOURCE:
            unique_id = (backend_constants.TMDB_TRAILER_CACHE_FILE_PREFIX +
                         str(movie_id))
        elif source == Movie.TFH_SOURCE:
            unique_id = str(backend_constants.TFH_TRAILER_CACHE_FILE_PREFIX +
                            str(movie_id))
        elif source == Movie.ITUNES_SOURCE:
            unique_id = (backend_constants.APPLE_TRAILER_CACHE_FILE_PREFIX +
                         str(movie_id))

        return unique_id

    @staticmethod
    def get_json_cache_file_path_for_movie_id(movie_id,  # type: Union[int, TextType]
                                              source,  # type: TextType
                                              error_msg=''  # type: TextType
                                              ):
        # type: (...) -> Union[TextType, None]
        """
            Returns the path for a cache JSON file for the given movie_id
            and source.

        :param movie_id:
        :param source:
        :param error_msg: Optional text to add to any error message.
                    Typically a movie title.
        :return:
        """
        try:
            prefix = Cache.generate_unique_id_from_source(movie_id, source,
                                                          error_msg=error_msg)
            if Cache._logger.isEnabledFor(Logger.DEBUG):
                Cache._logger.debug('movie_id:', movie_id, 'source:', source,
                                    'prefix:', prefix)
            #
            # To reduce clutter, put cached data into a folder named after the
            # SOURCE and first character of the id
            #
            # For local library entries, just use the first digit from the
            # numeric id.

            if source == Movie.LIBRARY_SOURCE:
                folder = prefix[0]
            elif source == Movie.TMDB_SOURCE:
                #
                # For TMDB entries, the numeric TMDB id is prefaced with:
                # "tmdb_". Use a folder named "t" + first digit of TMDBID
                #
                x = prefix.split('_', 1)
                folder = 't' + x[1][0]
            elif source == Movie.TFH_SOURCE:
                #
                # For TFH entries, the numeric TFH id is prefaced with:
                # "tfh_". Use a folder named "h" + first digit of TFH
                #
                x = prefix.split('_', 1)
                folder = 'h' + x[1][0]
            elif source == Movie.ITUNES_SOURCE:
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
                Cache._logger.error('Unexpected source:', source,
                                    'movie_id:', movie_id)
                return None

            cache_file = prefix + '.json'
            path = os.path.join(Settings.get_remote_db_cache_path(),
                                folder, cache_file)
            path = xbmc.validatePath(path)

            return path
        except (Exception) as e:
            Cache._logger.exception('')
        return None

    @staticmethod
    def is_trailer_from_cache(path):
        #  type: (TextType) -> bool
        """

        :param path:
        :return:
        """
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        if path.startswith(cache_path_prefix):
            return True
        return False

    @staticmethod
    def get_trailer_cache_file_path_for_movie_id(trailer, orig_file_name,
                                                 normalized):
        # type: (Dict[TextType, Any], TextType, bool) -> Union[TextType, None]
        """
            Generates the path for a file in the cache
            for a trailer for given movie.

        :param trailer:
        :param orig_file_name:
        :param normalized:
        :return:
        """
        path = None
        movie_id = None
        source = None
        try:
            valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                             Movie.ITUNES_SOURCE, Movie.TFH_SOURCE]
            if trailer[Movie.SOURCE] in valid_sources:
                movie_id = Cache.get_video_id(trailer)
                source = trailer[Movie.SOURCE]
            else:
                if Cache._logger.isEnabledFor(Logger.DEBUG):
                    Cache._logger.debug('Not valid video source title:',
                                        trailer[Movie.TITLE],
                                        'source:', trailer[Movie.SOURCE])

            if movie_id is not None:

                # movie_id may begin with an '_'.

                prefix = movie_id + '_'
                folder = None
                if source == Movie.LIBRARY_SOURCE:
                    folder = movie_id[0]
                elif source == Movie.TMDB_SOURCE:
                    x = prefix.split('_', 1)
                    folder = 't' + x[1][0]
                elif source == Movie.TFH_SOURCE:
                    x = prefix.split('_', 1)
                    folder = 'h' + x[1][0]
                elif source == Movie.ITUNES_SOURCE:
                    x = prefix.split('_', 1)
                    folder = 'a' + movie_id[1][0]

                # Possible that trailer was downloaded into cache

                orig_file_name = re.sub(
                    r'^' + re.escape(prefix), '', orig_file_name)

                if normalized:
                    if 'normalized_' in orig_file_name:
                        Cache._logger.error('Already normalized:',
                                            trailer.get(
                                                Movie.TITLE, 'no title'),
                                            'orig_file_name:', orig_file_name)
                        file_name = prefix + orig_file_name
                    else:
                        file_name = prefix + 'normalized_' + orig_file_name
                else:
                    file_name = prefix + orig_file_name

                path = os.path.join(Settings.get_downloaded_trailer_cache_path(),
                                    folder, file_name)
                # Should not be needed
                path = xbmc.validatePath(path)

        except (Exception) as e:
            title = trailer.get(Movie.TITLE, 'no title')
            Cache._logger.exception('title:', title)

            path = None

        if Cache._logger.isEnabledFor(Logger.DEBUG):
            Cache._logger.debug('Path:', path)
        return path
