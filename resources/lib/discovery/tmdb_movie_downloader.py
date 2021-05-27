# -*- coding: utf-8 -*-
"""
Created on 4/15/21

@author: Frank Feuerbacher
"""

import sys
import simplejson as json

from common.movie import TMDbMovie
from common.movie_constants import MovieField
from common.exceptions import AbortException
from common.imports import *
from common.settings import Settings
from common.logger import LazyLogger
from cache.cache import Cache
from cache.tmdb_cache_index import CacheIndex
from cache.trailer_unavailable_cache import (TrailerUnavailableCache)
from discovery.utils.parse_tmdb import ParseTMDb

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TMDbMovieDownloader:
    _logger: LazyLogger = None

    @classmethod
    def class_init(cls):
        cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_tmdb_movie(cls,
                       movie_title: str,
                       tmdb_id: Union[int, str],
                       source: str,
                       ignore_failures: bool = False,
                       library_id: str = None
                       ) -> (List[int], TMDbMovie):
        """
            Called in two situations:
                1) When a local movie does not have any movie information
                2) When a TMDB search for multiple movies is used, which does NOT return
                    detail information, including movie info.

            Given the movieId from TMDB, query TMDB for details and manufacture
            a movie entry based on the results. The movie itself will be a Youtube
            url.
        :param self:
        :param movie_title:
        :param tmdb_id:
        :param source: Not always TMDb. Comes from movie requiring this 
                       call. Ex: TFH movies get their detail info from
                       TMDb, so source will be TFH.
        :param ignore_failures:
        :param library_id:
        :return:
        """

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
            CacheIndex.remove_unprocessed_movies(tmdb_id_int)
            rejection_reasons.append(MovieField.REJECTED_NO_TRAILER)
            if not ignore_failures:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    cls._logger.exit(
                        'No trailer found for movie:', movie_title)
                return rejection_reasons, None

        # Query The Movie DB for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        rejection_reasons, tmdb_result = cls._query_tmdb_for_movie(movie_title,
                                                                   tmdb_id_str,
                                                                   source,
                                                                   ignore_failures=False,
                                                                   library_id=library_id)
        if tmdb_result is None:
            return rejection_reasons, None

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

        tmdb_parser = ParseTMDb(tmdb_result, lib_id)
        tmdb_parser.get_movie().set_id(tmdb_id_str)
        movie_title = tmdb_parser.parse_title()
        try:
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
            votes: int = tmdb_parser.parse_votes() # Number of people who voted
            genre_names: List[str] = tmdb_parser.parse_genre_names()
            tmdb_genre_ids: List[str] = tmdb_parser.parse_genre_ids()
            keyword_names: List[str] = tmdb_parser.parse_keyword_names()
            tmdb_keyword_ids: List[str] = tmdb_parser.parse_keyword_ids()
            original_language: str = tmdb_parser.parse_original_language()
            original_title: str = tmdb_parser.parse_original_title()

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(
                f'Error getting info for tmdb_id: {tmdb_id_str}')
            try:
                if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                    json_text = json.dumps(
                        tmdb_result, indent=3, sort_keys=True)
                    cls._logger.debug_extra_verbose(json_text)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.error('failed to get Json data')

        movie: TMDbMovie = tmdb_parser.get_movie()
        cls._logger.exit(f'Finished processing movie: {movie_title}'
                         f' year:{movie.get_year()} movie returned: {not movie is None}')

        return rejection_reasons, movie

    @classmethod
    def _query_tmdb_for_movie(cls,
                              movie_title: str,
                              tmdb_id_str: str,
                              source: str,
                              ignore_failures: bool = False,
                              library_id: str = None
                              ) -> (List[int], TMDbMovie):
        rejection_reasons: List[int] = []

        query_data: Dict[str, str] = {
            'append_to_response': 'credits,releases,keywords,videos,alternative_titles',
            'language': Settings.get_lang_iso_639_1(),
            'api_key': Settings.get_tmdb_api_key()
        }

        url: str = 'http://api.themoviedb.org/3/movie/' + tmdb_id_str

        tmdb_result: MovieType = None
        dump_msg: str = 'tmdb_id: ' + tmdb_id_str
        try:
            cache_id: str
            if library_id is not None:
                cache_id = library_id
            else:
                cache_id = tmdb_id_str

            status_code: int
            status_code, tmdb_result = Cache.get_cached_json(
                url, movie_id=cache_id, error_msg=movie_title, source=source,
                params=query_data, dump_results=False, dump_msg=dump_msg)
            if status_code == 0:
                s_code = tmdb_result.get('status_code', None)
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
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            cls._logger.exception('Error processing movie: ', movie_title)
            rejection_reasons.append(MovieField.REJECTED_FAIL)
            if ignore_failures:
                return rejection_reasons, None
            return rejection_reasons, None

        return rejection_reasons, tmdb_result


TMDbMovieDownloader.class_init()
