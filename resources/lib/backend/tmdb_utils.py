# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

from math import sqrt
import re
import sys


from common.imports import *

from common.constants import Constants, Movie
from common.exceptions import AbortException, CommunicationException
from common.minimal_monitor import MinimalMonitor
from common.settings import Settings
from common.logger import (LazyLogger)
from backend.movie_entry_utils import (MovieEntryUtils)

from common.rating import WorldCertifications
from backend.json_utils import JsonUtils
from backend.json_utils_basic import (JsonUtilsBasic)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TMDBMatcher:
    FILTER_TITLE_PATTERN = re.compile(r'(?:(?:the)|(?:a) )(.*)(?:[?!:-]?)')

    _logger: LazyLogger = None

    class CandidateMovie:
        _logger: LazyLogger = None

        def __init__(self, tmdb_movie: [Dict[str, Any]],
                     tmdb_title: str,
                     tmdb_year: str,
                     tmdb_language: str,
                     tmdb_id: str,
                     runtime_seconds: int) -> None:
            clz = type(self)
            if clz._logger is None:
                clz._logger = module_logger.getChild(clz.__name__)

            self._movie: [Dict[str, Any]] = tmdb_movie
            self._title: str = tmdb_title
            self._year:str = tmdb_year
            self._language: str = tmdb_language
            self._runtime_seconds: int = runtime_seconds
            self._tmdb_id: str = tmdb_id
            self._lower_title: str = self._title.lower()
            self._score: int = 0

        def score(self, movie_title: str, movie_year: Union[str, None],
                  movie_tmdb_id: str = None, runtime_seconds: int = 0) -> None:

            # Score tmdb movie:
            #  Highest score if movie title, year and original language match
            #  perfectly
            #       (When searching for match of TFH movie, there is no date)
            #
            #  Second highest score if all but original language matches
            #
            #  Third score if title, original language match perfectly
            #
            #  Fourth score if title nearly matches and year and original language
            #  match perfectly
            #
            #  Fifth score if title nearly matches, year matches but not language
            #
            #  Sixth score if title nearly matches and original language matches
            #
            #  Seventh score

            clz = type(self)
            try:
                score = 0
                lower_movie_title = movie_title.lower()
                if lower_movie_title == self._lower_title:
                    score = 1000
                else:
                    #
                    # Perhaps there is a erroneous leading prefix, such as: 'The'
                    #
                    filtered_tmdb_title = re.sub(TMDBMatcher.FILTER_TITLE_PATTERN,
                                                 r'\1', self._lower_title)
                    filtered_movie_title = re.sub(TMDBMatcher.FILTER_TITLE_PATTERN,
                                                  r'\1', lower_movie_title)
                    if filtered_tmdb_title == lower_movie_title:
                        score = 900
                    elif self._lower_title == filtered_movie_title:
                        score = 900

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            f'tmdb_title: {self._lower_title}'
                            f' filtered: {filtered_tmdb_title}'
                            f' movie_title: {lower_movie_title}'
                            f' filtered: {filtered_movie_title}'
                            f' score: {score}')

                # Check if within a year of expected year
                if movie_year is not None:
                    if abs(int(movie_year) - int(self._year)) < 2:
                        score += 500

                if self._language == Settings.get_lang_iso_639_1():
                    score += 10

                if runtime_seconds > 0 and self._runtime_seconds > 0:
                    # Movie duration may be off a bit
                    time_delta = abs(runtime_seconds - self._runtime_seconds)

                    # Non-linear penalty for more error

                    score += 250 * (sqrt(runtime_seconds ** 2 - time_delta ** 2) /
                                    runtime_seconds)
                else:
                    if self._runtime_seconds >= 50 * 60:  # Avoid movies < 50 minutes
                        score += 50

                self._score = score

            except AbortException:
                reraise(*sys.exc_info())

            except Exception as e:
                clz._logger.exception(e)

        def get_score(self) -> int:
            return self._score

        def get_movie(self) -> MovieType:
            return self._movie

    def __init__(self, title: str, year: Union[str, None],
                 runtime_seconds: int) -> None:
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__name__)

        self._title_to_match: str = title
        self._year_to_match: Union[str, None] = year
        self._runtime_seconds_to_match: int = runtime_seconds
        self.candidate_movies: List[clz.CandidateMovie] = []

        data = {
            'api_key': Settings.get_tmdb_api_key(),
            'page': '1',
            'query': title,
            'language': Settings.get_lang_iso_639_1()
        }

        if year is not None:
            data['primary_release_year'] = year

        try:
            include_adult = 'false'

            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            adult_certification = certifications.get_certification('dummy', True)
            if certifications.filter(adult_certification):
                include_adult = 'true'
            data['include_adult'] = include_adult
            data['append_to_response'] = 'alternative_titles'

            url = 'https://api.themoviedb.org/3/search/movie'
            finished = False
            delay = 0.5
            _info_string: Dict[str, Any] = None
            attempts: int = 0
            while not finished:
                attempts += 1
                try:
                    status_code, _info_string = \
                        JsonUtilsBasic.get_json(url, params=data,
                                                dump_msg='get_tmdb_id_from_title_year',
                                                dump_results=True,
                                                error_msg=title +
                                                f' ({year})')
                    if status_code == 0:
                        finished = True
                    else:
                        raise CommunicationException()
                except CommunicationException as e:
                    if attempts > 10:  # 5 seconds
                        reraise(*sys.exc_info())
                    else:
                        MinimalMonitor.throw_exception_if_abort_requested(timeout=delay)
                        delay += delay

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    f'Getting TMDB movie for title: {title} year: {year} '
                    f'runtime: {runtime_seconds}')

            if _info_string is not None:
                results = _info_string.get('results', [])
                if len(results) > 1:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            f'Got multiple matching movies: {title} '
                            f'year: {year} runtime: {runtime_seconds}')

                # TODO: Improve. Create best trailer function from get_tmdb_trailer
                # TODO: find best trailer_id

                current_language = Settings.get_lang_iso_639_1()

                for movie in results:
                    release_date = movie.get('release_date', '')  # 1932-04-22
                    tmdb_year = release_date[:-6]
                    movie[Movie.YEAR] = tmdb_year
                    tmdb_title = movie.get('title', '')
                    tmdb_id = movie.get('id', None)
                    tmdb_language = movie.get('original_language')
                    runtime_minutes = movie.get(Movie.RUNTIME, 0)
                    runtime_seconds = int(runtime_minutes * 60)

                    titles = movie.get('alternative_titles', {'titles': []})
                    alt_titles = []
                    for title in titles['titles']:
                        alt_title = (title['title'], title['iso_3166_1'])
                        alt_titles.append(alt_title)

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            f'Matching Movie date: {tmdb_year}'
                            f' tmdb_title: {tmdb_title}'
                            f' lang: {tmdb_language}'
                            f' current_lang: {current_language}')

                    self._add(movie, tmdb_title, tmdb_year,
                              tmdb_language, tmdb_id, runtime_seconds)

        except (AbortException, CommunicationException):
            reraise(*sys.exc_info())

        except Exception as e:
            clz._logger.exception(e)

    def _add(self,
             tmdb_movie: MovieType,
             tmdb_title: str,
             tmdb_year: str,
             tmdb_language: str,
             tmdb_id: str,
             runtime_seconds: int = 0) -> None:
        clz = type(self)

        candidate = clz.CandidateMovie(tmdb_movie, tmdb_title, tmdb_year,
                                       tmdb_language, tmdb_id,
                                       runtime_seconds=runtime_seconds)
        self.candidate_movies.append(candidate)
        candidate.score(self._title_to_match,
                        self._year_to_match,
                        runtime_seconds=self._runtime_seconds_to_match)

    def get_best_score(self) -> (Union[MovieType, None], int):
        clz = type(self)

        best_match = None
        best_score = 0
        for candidate in self.candidate_movies:
            if candidate.get_score() > best_score:
                best_score = candidate.get_score()
                best_match = candidate.get_movie()

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            title = 'Not Found'
            if best_match is not None:
                title = best_match[Movie.TITLE]

            clz._logger.debug_extra_verbose(f'Best match: score: {best_score}'
                                            f' title: {title}')
        return best_match, best_score


class TMDBUtils:
    """


    """
    kodi_data_for_tmdb_id = None
    _logger = None

    def __init__(self,
                 kodi_id: int,
                 tmdb_id: int,
                 kodi_file: str
                 ) -> None:

        self._kodi_id = kodi_id
        self._tmdb_id = tmdb_id
        self._kodi_file = kodi_file

    @classmethod
    def class_init(cls) -> None:
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_kodi_id(self) -> int:

        return self._kodi_id

    def get_kodi_file(self) -> str:
        """

        :return:
        """
        return self._kodi_file

    def get_tmdb_id(self) -> int:
        """

        :return:
        """
        return self._tmdb_id

    @classmethod
    def load_cache(cls) -> None:
        """
        Loads kodi-id and tmdb-id for ENTIRE database for every entry with tmdb-id.
        This cache is not saved and is loaded on first query.

        TODO: Change to query database for entry with tmdb-id on demand. May not
              be possible to do cheaply.

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
            communication_error_count: int = 0
            for movie in result_field.get('movies', []):
                title = movie[Movie.TITLE]
                kodi_id = movie[Movie.MOVIEID]
                kodi_file = movie[Movie.FILE]
                year = movie[Movie.YEAR]
                tmdb_id = MovieEntryUtils.get_tmdb_id(movie)

                # If we can't talk to TMDb we just won't get the tmdb_id
                # this time around.

                if tmdb_id is None and communication_error_count < 5:
                    try:
                        tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                            title, year)
                    except CommunicationException:
                        communication_error_count += 1

                if tmdb_id is not None:
                    number_of_tmdb_id_entries += 1
                    entry = TMDBUtils(kodi_id, tmdb_id, kodi_file)
                    TMDBUtils.kodi_data_for_tmdb_id[tmdb_id] = entry

    @classmethod
    def get_kodi_id_for_tmdb_id(cls, tmdb_id: int) -> str:
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
    def get_movie_by_tmdb_id(cls, tmdb_id: int) -> ForwardRef('TMDBUtils'):
        """

        :param tmdb_id:
        :return:
        """
        entry: TMDBUtils
        try:
            cls.load_cache()
            entry = cls.kodi_data_for_tmdb_id.get(tmdb_id)
        except (AbortException, CommunicationException):
            pass

        except Exception:
            cls._logger.exception()


        return entry

    @staticmethod
    def get_tmdb_id_from_title_year(title: str, year: Union[int, str],
                                    runtime_seconds: int = 0) -> int:
        """

        :param title:
        :param year:
        :param runtime_seconds:
        :return:
        """
        tmdb_id = None
        try:
            if year is not None:
                year = int(year)
            tmdb_id = TMDBUtils._get_tmdb_id_from_title_year(title, year,
                                                             runtime_seconds=
                                                             runtime_seconds)
            if tmdb_id is None and year is not None:
                tmdb_id = TMDBUtils._get_tmdb_id_from_title_year(
                    title, year + 1, runtime_seconds=runtime_seconds)
            if tmdb_id is None and year is not None:
                tmdb_id = TMDBUtils._get_tmdb_id_from_title_year(
                    title, year - 1, runtime_seconds=runtime_seconds)

        except (AbortException, CommunicationException):
            reraise(*sys.exc_info())

        except Exception:
            TMDBUtils._logger.exception('Error finding tmdb_id for movie:', title,
                                        'year:', year)

        return tmdb_id

    @staticmethod
    def _get_tmdb_id_from_title_year(title: str, year: int,
                                     runtime_seconds: int = 0) -> Optional[int]:
        """
            When we don't have a trailer for a movie, we can
            see if TMDB has one.
        :param title:
        :param year:
        :param runtime_seconds:
        :return:
        """
        year_str = None
        if year is not None:
            year_str = str(year)

        best_match = None
        try:
            matcher = TMDBMatcher(title, year_str, runtime_seconds)
            best_match, best_score = matcher.get_best_score()

        except (AbortException, CommunicationException):
            reraise(*sys.exc_info())

        except Exception:
            TMDBUtils._logger.exception('')

        tmdb_id = None
        if best_match is not None:
            tmdb_id = best_match.get('id', None)
        if tmdb_id is None:
            return None
        return int(tmdb_id)


TMDBUtils.class_init()
