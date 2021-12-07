# -*- coding: utf-8 -*-
"""
Created on 4/15/21

@author: Frank Feuerbacher
"""

import sys
from datetime import datetime

import simplejson as json
from backend.backend_constants import TMDbConstants
from backend.json_utils_basic import JsonUtilsBasic, JsonReturnCode, Result
from cache.tmdb_trailer_index import TMDbTrailerIndex
from common.monitor import Monitor

from common.movie import TMDbMovie, AbstractMovie, AbstractMovieId
from common.movie_constants import MovieField
from common.exceptions import AbortException, CommunicationException
from common.imports import *
from common.settings import Settings
from common.logger import LazyLogger
from cache.cache import Cache
from cache.tmdb_cache_index import CacheIndex
from cache.trailer_unavailable_cache import (TrailerUnavailableCache)
from diagnostics.statistics import Statistics
from discovery.utils.parse_tmdb import ParseTMDb

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TMDbMovieDownloader:
    _logger: LazyLogger = None

    @classmethod
    def class_init(cls):
        cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_tmdb_movie(cls,
                       movie: Union[AbstractMovie, AbstractMovieId],
                       ignore_failures: bool = False
                       ) -> (List[int], TMDbMovie):
        """
            Called in three situations:
                1) When a local movie does not have any movie information
                2) When a local movie is missing trailer info and the Settings are
                   configured to search TMDb for the trailer
                3) When a TMDb search for multiple movies is used, which does NOT return
                    detail information, including movie info.

            Given the movieId from TMDb, query TMDb for details and manufacture
            a movie entry based on the results. The trailer itself will be a Youtube
            or Vinmeo url.
        :param cls:
        :param movie:
        :param ignore_failures:
        :return:
        """

        movie_title: str = movie.get_title()
        tmdb_id: Union[int, str] = movie.get_tmdb_id()
        library_id: str = None
        if movie.get_library_id() is not None:
            library_id = str(movie.get_library_id())

        tmdb_movie: TMDbMovie
        rejection_reasons: List[int] = []
        if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            cls._logger.debug_verbose('title:', movie_title, 'tmdb_id:', tmdb_id,
                                      'library_id:', library_id, 'ignore_failures:',
                                      ignore_failures)

        if tmdb_id is None:
            rejection_reasons.append(MovieField.REJECTED_NO_TMDB_ID)
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                cls._logger.exit(
                    'No tmdb_id for movie:', movie_title)
            return rejection_reasons, None

        tmdb_id_str = str(tmdb_id)
        tmdb_id_int = int(tmdb_id)
        del tmdb_id
        if TrailerUnavailableCache.is_tmdb_id_missing_trailer(tmdb_id_int):
            CacheIndex.remove_unprocessed_movie(tmdb_id_int)
            rejection_reasons.append(MovieField.REJECTED_NO_TRAILER)
            if not ignore_failures:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    cls._logger.exit(
                        'No trailer found for movie:', movie_title)
                return rejection_reasons, None

        # Query The Movie Db for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        rejection_reasons, tmdb_movie = cls._query_cache_for_movie(movie,
                                                                   ignore_failures=False)
        if tmdb_movie is None:
            rejection_reasons, tmdb_movie = cls._query_tmdb_for_movie(movie,
                                                                      ignore_failures=
                                                                      False)
        if tmdb_movie is None:
            return rejection_reasons, None
        else:
            # Add or update info
            # At this point we know that there is a trailer, but we don't know
            # if there is a local copy

            TMDbTrailerIndex.add(tmdb_movie)

        # release_date TMDB key is different from Kodi's

        # Passed title can be junk:
        # TFH titles are all caps, or otherwise wonky: use TMDb's title
        # When only tmdb-id is known, then title is junk

        lib_id: int = None
        try:
            if library_id is not None:
                lib_id = int(library_id)
        except ValueError:
            cls._logger.debug(f'Library id should be a positive integer: {library_id} '
                              f'movie: {movie_title}')
        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(
                f'Error getting info for tmdb_id: {tmdb_id_str}')

        cls._logger.exit(f'Finished processing movie: {movie_title}'
                         f' year:{tmdb_movie.get_year()} movie returned: '
                         f'{not tmdb_movie is None}')

        return rejection_reasons, tmdb_movie

    @classmethod
    def _query_cache_for_movie(cls,
                               movie: Union[AbstractMovie, AbstractMovieId],
                               ignore_failures: bool = False,
                               ) -> (List[int], TMDbMovie):
        movie_title: str = movie.get_title()
        tmdb_id_str: str = str(movie.get_tmdb_id())
        library_id: str = None
        if movie.get_library_id() is not None:
            library_id = str(movie.get_library_id())
        rejection_reasons: List[int] = []

        tmdb_movie: TMDbMovie = None
        try:
            status_code: int
            status_code, tmdb_movie = Cache.get_cached_tmdb_movie(
                tmdb_id=tmdb_id_str, error_msg=movie_title)
            if status_code != 0:
                rejection_reasons.append(MovieField.REJECTED_FAIL)
                if tmdb_movie is None:
                    rejection_reasons.append(MovieField.REJECTED_NOT_IN_CACHE)

                cls._logger.debug_verbose('Error getting TMDB data for:', movie_title,
                                          'status:', status_code)
                return rejection_reasons, None

            # TODO: Remove Temp Patch to convert previous cache format

            if isinstance(tmdb_movie, TMDbMovie):
                dict_obj = tmdb_movie.get_as_movie_type()
            else:
                dict_obj = tmdb_movie
                
            if MovieField.DISCOVERY_STATE not in dict_obj.keys():
                # Old format, raw data from TMDb. Convert to our format

                tmdb_raw_data: MovieType = dict_obj
                tmdb_movie = cls.parse_tmdb_movie(tmdb_raw_data, library_id)
                if tmdb_movie is None:
                    cls._logger.exception('Error parsing movie: ', movie_title)
                    rejection_reasons.append(MovieField.REJECTED_FAIL)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            cls._logger.exception('Error processing movie: ', movie_title)
            rejection_reasons.append(MovieField.REJECTED_FAIL)
            if ignore_failures:
                return rejection_reasons, None
            return rejection_reasons, None

        return rejection_reasons, tmdb_movie

    @classmethod
    def _query_tmdb_for_movie(cls,
                              movie: Union[AbstractMovie, AbstractMovieId],
                              ignore_failures: bool = False) -> (List[int], TMDbMovie):
        rejection_reasons: List[int] = []
        movie_title = movie.get_title()
        tmdb_id_str: str = str(movie.get_tmdb_id())
        library_id: str = None
        if movie.get_library_id() is not None:
            library_id = str(movie.get_library_id())

        query_data: Dict[str, str] = {
            'append_to_response': 'credits,releases,keywords,videos,alternative_titles',
            'language': Settings.get_lang_iso_639_1(),
            'api_key': Settings.get_tmdb_api_key()
        }

        url: str = f'{TMDbConstants.DISCOVER_TRAILER_URL}{tmdb_id_str}'

        tmdb_movie: TMDbMovie = None
        dump_msg: str = 'tmdb_id: ' + tmdb_id_str
        try:
            status_code: int
            status_code, tmdb_raw_data = cls.query_tmdb(url,
                                                        error_msg=movie_title,
                                                        params=query_data,
                                                        dump_results=False,
                                                        dump_msg=dump_msg)
            if status_code == 0:
                s_code = tmdb_raw_data.get('status_code', None)
                if s_code is not None:
                    status_code = s_code
            if status_code != 0:
                rejection_reasons.append(MovieField.REJECTED_FAIL)
                if ignore_failures:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(
                            f'Ignore_failures getting TMDB data for: {movie_title}')
                    return rejection_reasons, None
                cls._logger.debug_verbose('Error getting TMDB data for:', movie_title,
                                          'status:', status_code)
                return rejection_reasons, None

            tmdb_movie = cls.parse_tmdb_movie(tmdb_raw_data, library_id)
            if tmdb_movie is None:
                cls._logger.exception('Error processing movie: ', movie_title)
                rejection_reasons.append(MovieField.REJECTED_FAIL)
            else:
                Cache.write_tmdb_cache_json(tmdb_movie=tmdb_movie, library_id=library_id)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            cls._logger.exception('Error processing movie: ', movie_title)
            rejection_reasons.append(MovieField.REJECTED_FAIL)
            if ignore_failures:
                return rejection_reasons, None
            return rejection_reasons, None

        return rejection_reasons, tmdb_movie

    @classmethod
    def parse_tmdb_movie(cls, tmdb_raw_data: MovieType,
                         library_id: str) -> TMDbMovie:
        movie: TMDbMovie = None
        library_id_int = None
        tmdb_id_str = ''
        if library_id is not None:
            library_id_int = int(library_id)

        try:
            tmdb_parser = ParseTMDb(tmdb_raw_data, library_id_int)
            tmdb_id_str: str = str(tmdb_parser.parse_id())
            tmdb_parser.get_movie().set_id(tmdb_id_str)
            movie_title = tmdb_parser.parse_title()
            tmdb_parser.parse_trailer()
            year: int = tmdb_parser.parse_year()
            certification: str = tmdb_parser.parse_certification()
            fanart: str = tmdb_parser.parse_fanart()
            thumbnail: str = tmdb_parser.parse_thumbnail()
            plot: str = tmdb_parser.parse_plot()
            runtime: int = tmdb_parser.parse_runtime()

            studios: List[str] = tmdb_parser.parse_studios()
            actors: List[str] = tmdb_parser.parse_actors()
            directors: List[str] = tmdb_parser.parse_directors()
            writers: List[str] = tmdb_parser.parse_writers()
            rating: float = tmdb_parser.parse_vote_average()  # avg rating on TMDb, scale 0 - 10
            votes: int = tmdb_parser.parse_votes()  # Number of people who voted
            genre_names: List[str] = tmdb_parser.parse_genre_names()
            tmdb_genre_ids: List[str] = tmdb_parser.parse_genre_ids()
            keyword_names: List[str] = tmdb_parser.parse_keyword_names()
            tmdb_keyword_ids: List[str] = tmdb_parser.parse_keyword_ids()
            original_language: str = tmdb_parser.parse_original_language()
            original_title: str = tmdb_parser.parse_original_title()
            discovery_state = tmdb_parser.get_discovery_state()
            movie = tmdb_parser.get_movie()

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(
                f'Error getting info for tmdb_id: {tmdb_id_str}')
            try:
                if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                    json_text = json.dumps(
                        tmdb_raw_data, indent=3, sort_keys=True)
                    cls._logger.debug_extra_verbose(json_text)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.error('failed to get Json data')

        return movie

    @classmethod
    def query_tmdb(cls, url: str,
                   error_msg: Union[str, int, None] = None,
                   dump_results: bool = False,
                   dump_msg: str = '',
                   headers: Union[dict, None] = None,
                   params: Union[dict, None] = None,
                   timeout: float = 3.0
                   ) -> (int, MovieType):
        """
            Query TMDb for detail data on specified movie id

        :param url:
        :param error_msg:
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

        movie_data: MovieType = None
        status = 0
        finished = False
        delay = 0.5
        retries: int = 3
        while not finished:
            try:
                retries -= 1
                if retries < 0:
                    finished = True  # Not again!

                result: Result
                result = JsonUtilsBasic.get_json(url,
                                                 dump_results=dump_results,
                                                 dump_msg=dump_msg,
                                                 headers=headers,
                                                 error_msg=error_msg,
                                                 params=params,
                                                 timeout=timeout)
                s_code = result.get_api_status_code()
                if s_code is not None:
                    cls._logger.debug(f'api status: {s_code}')

                status_code: JsonReturnCode = result.get_rc()
                if status_code == JsonReturnCode.OK:
                    finished = True
                    status = 0
                    movie_data = result.get_data()
                    if movie_data is None:
                        cls._logger.debug_extra_verbose(f'Status OK but data is None '
                                                        f'Skipping {error_msg}')

                if status_code in (JsonReturnCode.FAILURE_NO_RETRY,
                                   JsonReturnCode.UNKNOWN_ERROR):
                    cls._logger.debug_extra_verbose(f'{error_msg} TMDb call'
                                                    f' {status_code.name}')
                    status = -1
                    finished = True

                if status_code == JsonReturnCode.RETRY:
                    status = -2
                    cls._logger.debug_extra_verbose(f'{error_msg} TMDb call failed RETRY')
                    raise CommunicationException()

            except CommunicationException as e:
                Monitor.throw_exception_if_abort_requested(timeout=delay)
                delay += delay

        return status, movie_data


TMDbMovieDownloader.class_init()
