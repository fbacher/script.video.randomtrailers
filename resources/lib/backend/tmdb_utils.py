# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import os
import sys

from common.imports import *

from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.settings import Settings
from common.logger import (LazyLogger)
from backend.movie_entry_utils import (MovieEntryUtils)

from common.rating import WorldCertifications
from backend.json_utils import JsonUtils
from backend.json_utils_basic import (JsonUtilsBasic)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TMDBUtils(object):
    """


    """
    kodi_data_for_tmdb_id = None
    _logger = None

    def __init__(self,
                 kodi_id,  # type: int
                 tmdb_id,  # type int
                 kodi_file  # type str
                 ):

        self._kodi_id = kodi_id
        self._tmdb_id = tmdb_id
        self._kodi_file = kodi_file

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_kodi_id(self):
        # type: () -> int

        return self._kodi_id

    def get_kodi_file(self):
        # type() -> str
        """

        :return:
        """
        return self._kodi_file

    def get_tmdb_id(self):
        # type: () -> int
        """

        :return:
        """
        return self._tmdb_id

    @classmethod
    def load_cache(cls):
        # type () -> None
        """

        :return:
        """
        if cls.kodi_data_for_tmdb_id is not None:
            return

        cls._logger = module_logger.getChild(type(cls).__name__)

        cls.kodi_data_for_tmdb_id = {}

        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", \
                    "params": {\
                    "properties": \
                        ["title", "year", "uniqueid", "file"]}, "id": 1}'

        query_result = JsonUtils.get_kodi_json(
            query, dump_results=False)
        result_field = query_result.get('result', None)

        number_of_tmdb_id_entries = 0
        if result_field is not None:
            for movie in result_field.get('movies', []):
                title = movie[Movie.TITLE]
                kodi_id = movie['movieid']
                kodi_file = movie[Movie.FILE]
                year = movie['year']
                tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
                if tmdb_id is None:
                    tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                        title, year)
                if tmdb_id is not None:
                    number_of_tmdb_id_entries += 1
                    entry = TMDBUtils(kodi_id, tmdb_id, kodi_file)
                    TMDBUtils.kodi_data_for_tmdb_id[tmdb_id] = entry

    @classmethod
    def get_kodi_id_for_tmdb_id(cls, tmdb_id):
        # type: (int) -> str
        """

        :param tmdb_id:
        :return:
        """
        cls.load_cache()
        entry = cls.kodi_data_for_tmdb_id.get(tmdb_id)
        kodi_id = None
        if entry is not None:
            kodi_id = entry.get_kodi_id()
        return kodi_id

    @classmethod
    def get_movie_by_tmdb_id(cls, tmdb_id):
        # type: (int) -> TMDBUtils
        """

        :param tmdb_id:
        :return:
        """
        cls.load_cache()
        entry = cls.kodi_data_for_tmdb_id.get(tmdb_id)
        return entry

    @staticmethod
    def get_tmdb_id_from_title_year(title: str, year: int) -> int:
        """

        :param title:
        :param year:
        :return:
        """
        tmdb_id = None
        try:
            year = int(year)
            tmdb_id = TMDBUtils._get_tmdb_id_from_title_year(title, year)
            if tmdb_id is None:
                tmdb_id = TMDBUtils._get_tmdb_id_from_title_year(
                    title, year + 1)
            if tmdb_id is None:
                tmdb_id = TMDBUtils._get_tmdb_id_from_title_year(
                    title, year - 1)

        except AbortException:
            reraise(*sys.exc_info())

        except Exception:
            TMDBUtils._logger.exception('Error finding tmdb_id for movie:', title,
                                        'year:', year)

        return tmdb_id

    @staticmethod
    def _get_tmdb_id_from_title_year(title: str, year: int) -> Optional[int]:
        """
            When we don't have a trailer for a movie, we can
            see if TMDB has one.
        :param title:
        :param year:
        :return:
        """
        year_str = str(year)
        found_movie = None
        trailer_id = None
        data = {}
        data['api_key'] = Settings.get_tmdb_api_key()
        data['page'] = '1'
        data['query'] = title
        data['language'] = Settings.get_lang_iso_639_1()
        data['primary_release_year'] = year

        try:
            include_adult = 'false'

            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            adult_certification = certifications.get_certification('dummy', True)
            if certifications.filter(adult_certification):
                include_adult = 'true'
            data['include_adult'] = include_adult

            url = 'https://api.themoviedb.org/3/search/movie'
            status_code, _info_string = \
                JsonUtilsBasic.get_json(url, params=data,
                                        dump_msg='get_tmdb_id_from_title_year',
                                        dump_results=True,
                                        error_msg=title +
                                                  ' (' + year_str + ')')
            if _info_string is not None:
                results = _info_string.get('results', [])
                if len(results) > 1:
                    if TMDBUtils._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        TMDBUtils._logger.debug_extra_verbose(
                            'Got multiple matching movies:',
                            title,
                            'year:', year)

                # TODO: Improve. Create best trailer function from get_tmdb_trailer
                # TODO: find best trailer_id

                matches = []
                current_language = Settings.get_lang_iso_639_1()
                movie = None
                for movie in results:
                    release_date = movie.get('release_date', '')  # 1932-04-22
                    found_year = release_date[:-6]
                    found_title = movie.get('title', '')

                    if (found_title.lower() == title.lower()
                            and found_year == year_str
                            and movie.get('original_language') == current_language):
                        matches.append(movie)

                # TODO: Consider close match heuristics.

                if len(matches) == 1:
                    found_movie = matches[0]
                elif len(matches) > 1:
                    if TMDBUtils._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        TMDBUtils._logger.debug_extra_verbose(
                            'More than one matching movie in same year choosing first '
                            'one matching current language.',
                            'Num choices:', len(matches))
                    found_movie = matches[0]

                if movie is None:
                    if TMDBUtils._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        TMDBUtils._logger.debug_extra_verbose('Could not find movie:',
                                                              title, 'year:', year,
                                                              'at TMDB. found',
                                                              len(results), 'candidates')
                    for a_movie in results:
                        release_date = a_movie.get(
                            'release_date', '')  # 1932-04-22
                        found_year = release_date[:-6]
                        found_title = a_movie.get('title', '')
                        tmdb_id = a_movie.get('id', None)
                        if TMDBUtils._logger.isEnabledFor(LazyLogger.DISABLED):
                            TMDBUtils._logger.debug_extra_verbose('found:', found_title,
                                                                  '(', found_year, ')',
                                                                  'tmdb id:', tmdb_id)
                        tmdb_data = MovieEntryUtils.get_alternate_titles(
                            title, tmdb_id)
                        for alt_title, country in tmdb_data['alt_titles']:
                            if alt_title.lower() == title.lower():
                                found_movie = tmdb_data  # Not actually in "movie" format
                                break
            else:
                if TMDBUtils._logger.isEnabledFor(LazyLogger.INFO):
                    TMDBUtils._logger.info('Could not find movie:', title, 'year:', year,
                                            'at TMDB. found no candidates')
        except AbortException:
            reraise(*sys.exc_info())

        except Exception:
            TMDBUtils._logger.exception('')

        tmdb_id = None
        if found_movie is not None:
            tmdb_id = found_movie.get('id', None)
        if tmdb_id is None:
            return None
        return int(tmdb_id)

TMDBUtils.class_init()