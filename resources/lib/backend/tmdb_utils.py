# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
import threading
from math import sqrt
import re
import sys

import simplejson
from cache.base_reverse_index_cache import BaseReverseIndexCache
from cache.json_cache_helper import JsonCacheHelper
from backend.backend_constants import TMDbConstants

from common.imports import *

from common.exceptions import AbortException, CommunicationException
from common.minimal_monitor import MinimalMonitor
from common.movie import LibraryMovie
from common.movie_constants import MovieField, MovieType
from common.settings import Settings
from common.logger import *
from common.certification import WorldCertifications
from backend.json_utils import JsonUtils
from backend.json_utils_basic import (JsonUtilsBasic, JsonReturnCode, Result)
from common.utils import Delay
from discovery.utils.parse_library import ParseLibrary

module_logger = BasicLogger.get_module_logger(module_path=__file__)


class TMDBMatcher:

    #  TODO:  Add ability to convert 20000 to 20,000, etc.

    FILTER_TITLE_PATTERN = re.compile(r'(?:(?:the)|(?:a) )(.*)(?:[?!:-]?)')
    _logger: BasicLogger = None

    class CandidateMovie:
        _logger: BasicLogger = None

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
            self._year: str = tmdb_year
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

                    if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
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
                clz._logger.exception(f'movie_title: {movie_title}')

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

        if year is not None and year != '':
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

            finished = False
            delay = 0.5
            attempts: int = 0
            while not finished:
                attempts += 1
                try:
                    result: Result = \
                        JsonUtilsBasic.get_json(TMDbConstants.SEARCH_URL, params=data,
                                                dump_msg='get_tmdb_id_from_title_year',
                                                dump_results=False,
                                                error_msg=f'{title} ({year})')

                    s_code = result.get_api_status_code()
                    if s_code is not None:
                        clz._logger.debug(f'api status: {s_code}')

                    status_code: JsonReturnCode = result.get_rc()
                    if status_code == JsonReturnCode.OK:
                        finished = True
                        if result.get_data() is None:
                            clz._logger.debug_extra_verbose(f'Status OK but data is None '
                                                            f'Skipping {title}')

                    if status_code == JsonReturnCode.FAILURE_NO_RETRY:
                        clz._logger.debug_extra_verbose(f'{title} TMDb call'
                                                        f' FAILURE_NO_RETRY')
                        finished = True

                    if status_code == JsonReturnCode.UNKNOWN_ERROR:
                        clz._logger.debug_extra_verbose(f'{title} TMDb call'
                                                        f' UNKNOWN_ERROR')
                        finished = True

                    if status_code == JsonReturnCode.RETRY:
                        clz._logger.debug_extra_verbose(f'{title} TMDb call failed RETRY')
                        raise CommunicationException()

                except CommunicationException as e:
                    if attempts > 10:  # 5 seconds
                        reraise(*sys.exc_info())
                    else:
                        MinimalMonitor.throw_exception_if_abort_requested(timeout=delay)
                        delay += delay

            if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    f'Getting TMDB movie for title: {title} year: {year} '
                    f'runtime: {runtime_seconds}')

            if result.get_data() is not None:
                results = result.get_data().get('results', [])
                if len(results) > 1:
                    if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            f'Got multiple matching movies: {title} '
                            f'year: {year} runtime: {runtime_seconds}')

                # TODO: Improve. Create best movie function from get_tmdb_trailer
                # TODO: find best trailer_id

                current_language = Settings.get_lang_iso_639_1()

                for movie in results:
                    tmdb_year: str = movie.get('year', '0')
                    tmdb_title = movie.get('title', '')
                    tmdb_id = movie.get('id', None)
                    tmdb_language = movie.get('original_language')
                    runtime_minutes = movie.get(MovieField.RUNTIME, 0)
                    runtime_seconds = int(runtime_minutes * 60)

                    # TODO: take advantage of alt-titles

                    titles = movie.get('alternative_titles', {'titles': []})
                    alt_titles: List[Tuple[str, str]] = []
                    for title in titles['titles']:
                        alt_title = (title['title'], title['iso_3166_1'])
                        alt_titles.append(alt_title)

                    if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            f'Matching Movie date: {tmdb_year}'
                            f' tmdb_title: {tmdb_title}'
                            f' lang: {tmdb_language}'
                            f' current_lang: {current_language}')

                    self._add(movie, tmdb_title, tmdb_year,
                              tmdb_language, tmdb_id, runtime_seconds)

        except AbortException:
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

        if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            title = f'Not Found: {self._title_to_match}'
            if best_match is not None:
                title = best_match[MovieField.TITLE]

            clz._logger.debug_extra_verbose(f'Best match: score: {best_score}'
                                            f' title: {title}')
        return best_match, best_score


class TMDbIdForKodiId:
    """
    Contains the kodi_id, kodi movie path and tmdb_id for a kodi movie.

    Used in conjunction with a map to look up the Kodi movie corresponding
    to a TMDbId.
    """

    def __init__(self,
                 kodi_id: int,
                 tmdb_id: int,
                 kodi_file: str,
                 title: str
                 ) -> None:
        self._kodi_id = kodi_id
        self._tmdb_id = tmdb_id
        self._kodi_file = kodi_file
        self._title = title

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

    def get_title(self) -> str:
        return self._title


class TMDBUtils:
    """
        Provides the ability to look up a movie's kodi_id, tmdb_id and movie file path
        using a tmdb-id. This cache is built from local kodi library information.
        For movies that do not include the TMDb_id,

    """
    _logger: BasicLogger = None
    kodi_data_for_tmdb_id: Dict[int, TMDbIdForKodiId] = None  # Must be None!
    _library_json_cache: Type[BaseReverseIndexCache]

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

        cls._library_json_cache = JsonCacheHelper.get_json_cache_for_source(
            MovieField.LIBRARY_SOURCE)

    @classmethod
    def load_cache(cls) -> None:
        """
        Build a bi-directional map of of kodi_id to tmdb_id.

        This can be very expensive, depending upon size of local db as well as
        Setting.get_update_tmdb_id returning True, which causes the tmdb_id of
        library movies to be stored in the kodi library database. It can take
        one or more hours to build the map for a library of over 1,000 movies.

        If get_update_tmdb_id is False, the cache library_json_cache is used
        instead. The cache exists to help manage cached .json files, but can
        also be used for this purpose.

        Because of the expense, building the map in a separate thread is necessary.
        Until it is built, some queries will
        fail, resulting in on-demand queries to TMDb to get ids, or missing the
        relationship. Normally this is not a big deal, the UI won't snow that a
        TMDb movie is also a local movie. In any event, it is not catastrophic
        and will be rectified in a later run.
        """
        if cls.kodi_data_for_tmdb_id is not None:
            return

        loader = threading.Thread(target=cls._load_cache_thread,
                                  name='load kodi-tmdbid map')

        cls.kodi_data_for_tmdb_id = {}
        loader.start()

    @classmethod
    def _load_cache_thread(cls) -> None:

        try:
            cls._load_cache_worker()
        except AbortException:
            pass  # Quietly die

        except Exception:
            cls._logger.exception(msg='')

    @classmethod
    def _load_cache_worker(cls) -> None:
        """
        Loads kodi-id and tmdb-id for ENTIRE database for every entry with tmdb-id.
        The results are optionally saved in the local database. The results are
        also persisted in the cache library_json_cache.json

        :return:
        """

        # Add wait between each movie added = 1.0 + log(# trailers_added * 2)
        # seconds
        # For 1,000 trailers added, the delay is 1.0 + 3.3 = 4.3 seconds
        #
        # The delay does not occur until when the json files are read

        delay = Delay(bias=1.0, call_scale_factor=2.0, scale_factor=1.0)

        query: str = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", \
                     "params": {\
                     "properties": \
                         ["title", "year", "uniqueid", "file"]}, "id": 1}'

        query_result = JsonUtils.get_kodi_json(
            query, dump_results=False)
        result_field = query_result.get('result', None)

        number_of_tmdb_id_entries = 0
        if result_field is not None:
            communication_error_count: int = 0
            for movie_entry in result_field.get('movies', []):
                # Create partially populated LibraryMove to unify access.
                # Remember that it is only partially populated!

                if cls._logger.isEnabledFor(DISABLED):
                    dump: str = simplejson.dumps(movie_entry, indent=3,
                                                 sort_keys=True)
                    cls._logger.debug_extra_verbose(f'Movie DUMP: {dump}')
                # Debug.dump_dictionary(d=movie_entry, level=DEBUG)
                lib_parser = ParseLibrary(movie_entry)
                title: str = lib_parser.parse_title()
                kodi_file: str = lib_parser.parse_movie_path()
                year: int = lib_parser.parse_year()

                lib_parser.parse_unique_ids()

                movie: LibraryMovie = lib_parser.get_movie()
                tmdb_id: int = movie.get_tmdb_id()
                kodi_id: int = movie.get_library_id()
                if cls._logger.isEnabledFor(DISABLED):
                    cls._logger.debug_extra_verbose(f'title: {title} - {movie.get_title()} '
                                                    f'year: {year} - {movie.get_year()} '
                                                    f'tmdb_id: {tmdb_id} kodi-id: {kodi_id}')

                # Movie entries that have not been scraped?

                if title is None or len(title) == 0 or year == 0:
                    cls._logger.debug(
                        f'The movie: {kodi_file} does not appear to be scraped')
                    if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(
                            f'title: {title} - {movie.get_title()} '
                            f'year: {year} - {movie.get_year()} '
                            f'tmdb_id: {tmdb_id} kodi-id: {kodi_id}')
                    continue

                if tmdb_id is None:
                    tmdb_id_str: str = cls._library_json_cache.get_item(str(kodi_id))
                    if tmdb_id_str is not None:
                        tmdb_id = int(tmdb_id_str)

                # If we can't talk to TMDb we just won't get the tmdb_id
                # this time around.

                if tmdb_id is None and communication_error_count < 5:
                    try:
                        delay.delay()
                        tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                            title, year)
                    except CommunicationException:
                        communication_error_count += 1

                if tmdb_id is not None:
                    number_of_tmdb_id_entries += 1
                    entry: TMDbIdForKodiId = TMDbIdForKodiId(kodi_id, tmdb_id,
                                                             kodi_file, title)
                    TMDBUtils.kodi_data_for_tmdb_id[tmdb_id] = entry
                    # cls._logger.debug(f'tmdb_id: {tmdb_id} kodi_id: {kodi_id}')
                    if tmdb_id is not None:
                        cls._library_json_cache.add_item(str(kodi_id), str(tmdb_id))

    @classmethod
    def get_kodi_id_for_tmdb_id(cls, tmdb_id: int) -> int:
        """

        :param tmdb_id:
        :return:
        """
        cls.load_cache()
        entry: TMDbIdForKodiId = cls.kodi_data_for_tmdb_id.get(tmdb_id)
        kodi_id = None
        if entry is not None:
            kodi_id = entry.get_kodi_id()
        return kodi_id

    @classmethod
    def get_movie_by_tmdb_id(cls, tmdb_id: int) -> TMDbIdForKodiId:
        """

        :param tmdb_id:
        :return:
        """
        cls.load_cache()
        entry: TMDbIdForKodiId = cls.kodi_data_for_tmdb_id.get(tmdb_id)
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
        tmdb_id: int = None
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
            TMDBUtils._logger.exception(f'Error finding tmdb_id for movie: {title} '
                                        f'year: {year}')

        return tmdb_id

    @staticmethod
    def _get_tmdb_id_from_title_year(title: str, year: int,
                                     runtime_seconds: int = 0) -> Optional[int]:
        """
            The library may not have the TMDb id's for a movie.
            See if TMDb has one.
        :param title:
        :param year:
        :param runtime_seconds:
        :return:
        """
        year_str = None
        if year is not None and year != 0:
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
