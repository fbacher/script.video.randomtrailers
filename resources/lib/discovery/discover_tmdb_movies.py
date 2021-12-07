# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import sys
import datetime
from pathlib import Path
from re import Match

import simplejson as json
import xbmcvfs

from backend.backend_constants import TMDbConstants
from cache.cache import Cache
from cache.json_cache_helper import JsonCacheHelper
from cache.tmdb_cache_index import (CachedPage, CacheIndex, CacheParameters,
                                    CachedPagesData)
# from cache.unprocessed_tmdb_page_data import UnprocessedTMDbPages
from cache.tmdb_trailer_index import TMDbTrailerIndex
from cache.trailer_unavailable_cache import TrailerUnavailableCache
from common.constants import Constants, RemoteTrailerPreference
from common.critical_settings import CriticalSettings
from common.debug_utils import Debug
from common.disk_utils import DiskUtils, FindFiles
from common.exceptions import AbortException, CommunicationException, reraise
from common.garbage_collector import GarbageCollector
from common.imports import *
from common.monitor import Monitor
from common.logger import LazyLogger, Trace
from common.movie import TMDbMovieId, BaseMovie, TMDbMoviePageData
from common.movie_constants import MovieField, MovieType
from common.settings import Settings
from common.tmdb_settings import TmdbSettings
from common.utils import Delay

from discovery.restart_discovery_exception import StopDiscoveryException
from backend.genreutils import GenreUtils
from backend.json_utils_basic import JsonUtilsBasic, JsonReturnCode, Result
from common.certification import WorldCertifications
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.utils.tmdb_filter import TMDbFilter
from discovery.tmdb_movie_data import TMDbMovieData
from discovery.utils.parse_tmdb_page_data import ParseTMDbPageData
from gc import garbage

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class DiscoverTmdbMovies(BaseDiscoverMovies):
    """
        TMDB, like iTunes, provides trailers. Query TMDB for trailers
        and manufacture movie entries for them.
    """

    MOVIES_PER_PAGE: Final[int] = 20

    _singleton_instance: ForwardRef('DiscoverTmdbMovies') = None
    logger: LazyLogger = None

    def __init__(self) -> None:
        """

        """
        clz = type(self)
        type(self).logger: LazyLogger = module_logger.getChild(clz.__name__)
        thread_name = 'Discover TMDB'
        kwargs = {MovieField.SOURCE: MovieField.TMDB_SOURCE}

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=kwargs)
        self._movie_data: TMDbMovieData = TMDbMovieData()
        self._select_by_year_range: bool = None
        self._language: str = None
        self._country: str = None
        self._tmdb_api_key: str = None
        self._include_adult: bool = None
        self._filter_genres: bool = None
        self._selected_keywords: str = None
        self._selected_genres: str = None
        self._excluded_genres: str = None
        self._excluded_keywords: str = None
        self._remote_trailer_preference: str = None
        self._vote_comparison: int = None
        self._vote_value: int = None
        self._rating_limit_string: str = None
        self._minimum_year: int = None
        self._maximum_year: int = None
        self._rejected_due_to_year: bool = None
        self._total_pages_read: int = 0
        self._on_filter_failure_purge_json_cache: int = False
        self._rebuild_cache: bool = False
        self._calls_to_delay: int = 0

    def discover_basic_information(self) -> None:
        """
            Starts the discovery thread

        :return:
        """
        clz = type(self)

        self.start()
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug(': started')

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return Settings.is_include_tmdb_trailers()

    def run(self) -> None:
        """
            Thread run method that is started as a result of running
            discover_basic_information

            This method acts as a wrapper around run_worker. This
            wrapper is able to restart discovery and to handle a few
            details after discovery is complete.

        :return: # type: None
        """
        clz = type(self)
        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    self.wait_until_restart_or_shutdown()
                    self.finished_discovery()
                    duration = datetime.datetime.now() - start_time
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz.logger.debug_verbose(f'Time to discover: {duration.seconds} '
                                                 f'seconds',
                                                 trace=Trace.STATS)

                        used_memory: int = self._movie_data.get_size_of()
                        used_mb: float = float(used_memory) / 1000000.0
                        self.logger.debug(f'movie_data size: {used_memory} MB: {used_mb}')
                except StopDiscoveryException:
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz.logger.debug_verbose('Stopping discovery')
                    # self.destroy()
                    finished = True

        except AbortException:
            return  # Let thread die
        except Exception as e:
            clz.logger.exception('')
        finally:
            GarbageCollector.add_thread(self)

    def run_worker(self) -> None:
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return: #type: None
        """
        clz = type(self)

        try:
            self.wait_until_restart_or_shutdown(CriticalSettings.SHORT_POLL_DELAY)
            tmdb_trailer_type = TmdbSettings.get_trailer_type()

            #
            # TMDb accepts iso-639-1 but adding an iso-3166- suffix
            # would be better (en_US)
            #
            self._language = Settings.get_lang_iso_639_1()
            self._country = Settings.get_country_iso_3166_1()
            self._tmdb_api_key = Settings.get_tmdb_api_key()

            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            if certifications is None:
                self._include_adult = False
            else:
                adult_certification = certifications.get_adult_certification()
                self._include_adult = certifications.filter(
                    adult_certification)

            self._selected_keywords = ''
            self._selected_genres = ''
            self._excluded_genres = ''
            self._excluded_keywords = ''
            self._filter_genres = Settings.get_filter_genres()
            if self._filter_genres:
                self._selected_genres = GenreUtils.get_external_genre_ids_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=False, or_operator=True)
                self._selected_keywords = GenreUtils.get_external_keywords_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=False, or_operator=True)
                self._excluded_genres = GenreUtils.get_external_genre_ids_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=True, or_operator=True)
                self._excluded_keywords = GenreUtils.get_external_keywords_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=True, or_operator=True)
            if self._filter_genres:
                # If no actual selections were made, then change to not filter_genres
                # Otherwise, the filter code will not work properly.
                if (self._selected_genres == ''
                        and self._excluded_genres == ''
                        and self._selected_keywords == ''
                        and self._excluded_keywords == ''):
                    self._filter_genres = False

            self._remote_trailer_preference = Settings.get_tmdb_trailer_preference()
            self._vote_comparison, self._vote_value = \
                Settings.get_tmdb_avg_vote_preference()
            self._rating_limit_string = \
                WorldCertifications.get_certification_limit_setting()

            # Trailers may be sparse for old movies. Could implement a max# of trailers,
            # but that is done much later in the pipeline

            if Settings.get_tmdb_include_old_movie_trailers():
                max_pages = Settings.get_tmdb_max_download_movies() / 20
            else:
                max_pages = int(110)

            self.discover_movies(
                max_pages, tmdb_trailer_type=tmdb_trailer_type)
        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

    def discover_movies(self, max_pages: int, tmdb_trailer_type: str = '') -> None:
        """
            Calls configure_search_parameters as many times as appropriate to
            discover movies based on the filters specified by the settings.

        :param max_pages: # type int
                The TMDb API returns movies in pages which contains info for
                about 20 movies. The caller specifies which page to get.
        :param tmdb_trailer_type: # type: str
                Specifies the type of movies to get (popular, recent, etc.)
        :return: # type: None (Lower code uses add_to_discovered_movies).
        """
        clz = type(self)

        try:
            self._rejected_due_to_year = 0

            # Configure search parameters. If parameters have
            # changed then discover one page of movie data from
            # TMDB based on those parameters.

            movies = self.configure_search_parameters(
                                        tmdb_trailer_type=tmdb_trailer_type)
            if self._rebuild_cache:
                self.purge_cache(actually_delete=False)
                # self.purge_cache(actually_delete=True)
            else:
                self.send_cached_movies_to_discovery()

            process_genres: bool
            process_keywords: bool
            pages_in_chunks: int
            genre_finished: bool
            if self._filter_genres:
                if self._selected_genres != '' or self._excluded_genres != '':
                    process_genres = True
                else:
                    process_genres = False

                if self._selected_keywords != '' or self._excluded_keywords != '':
                    process_keywords = True
                else:
                    process_keywords = False

                if process_genres and process_keywords:
                    pages_in_chunk = 5
                else:
                    pages_in_chunk = max_pages

                while process_genres or process_keywords:
                    if process_genres:
                        genre_finished = self.second_phase_discovery(
                            max_pages,
                            pages_in_chunk,
                            tmdb_trailer_type,
                            "genre", additional_movies=movies)
                        del movies[:]
                        if genre_finished:
                            process_genres = False
                    if process_keywords:
                        keyword_finished = self.second_phase_discovery(
                            max_pages,
                            pages_in_chunk,
                            tmdb_trailer_type,
                            "keyword", additional_movies=movies)
                        if keyword_finished:
                            process_keywords = False

            else:
                self.second_phase_discovery(
                    max_pages,
                    max_pages,
                    tmdb_trailer_type,
                    "generic",
                    additional_movies=movies)

            clz.logger.debug_verbose('Completed second phase discovery')
            more_to_get: bool = True
            while more_to_get:
                if self._filter_genres:
                    if self._selected_genres != '' or self._excluded_genres != '':
                        tmdb_search_query = "genre"
                        #
                        # Exit when there are no more pages to process
                        #
                        more_to_get = self.discover_movies_using_search_pages(
                            tmdb_trailer_type,
                            tmdb_search_query=tmdb_search_query)
                    if self._selected_keywords != '' or self._excluded_keywords != '':
                        tmdb_search_query = "keyword"
                        #
                        # Exit when there are no more pages to process
                        #
                        more_to_get = self.discover_movies_using_search_pages(
                            tmdb_trailer_type,
                            tmdb_search_query=tmdb_search_query)
                else:
                    tmdb_search_query = "generic"
                    #
                    # Exit when there are no more pages to process
                    #
                    more_to_get = self.discover_movies_using_search_pages(
                        tmdb_trailer_type,
                        tmdb_search_query=tmdb_search_query)
            clz.logger.debug_verbose(f'Completed creating all search pages')

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception:
            clz.logger.exception('')

    def configure_search_parameters(self,
                                    tmdb_trailer_type: str = ''
                                    ) -> List[TMDbMoviePageData]:
        """
            Performs the critical task of translating complex
            search parameters into multiple groups of API calls
            to carry out the search.

            The most complex queries specify a range of years as well
            as other search criteria.

        :param tmdb_trailer_type: # type: str
                Specifies a trailer-type search parameter
        :return: # type: List[MovieType]
        """
        clz = type(self)
        self.throw_exception_on_forced_to_stop()
        movies: List[TMDbMoviePageData] = []
        '''
        TMDB related settings 
        * indicates saved in search_parameters
        - indicates change does not warrant destroying tmdb cache
        + indicates change does warrant destroying tmdb cache
        
        - TMDB_MAX_NUMBER_OF_TRAILERS,
        - TMDB_MAX_DOWNLOAD_MOVIES
        *- TMDB_ALLOW_FOREIGN_LANGUAGES,
        - TMDB_TRAILER_TYPE,
        -    INCLUDE_TMDB_TRAILERS,
        -    INCLUDE_CLIPS,
        -    INCLUDE_FEATURETTES,
        -    INCLUDE_TEASERS,
        * TMDB_SORT_ORDER,
        * TMDB_VOTE_VALUE,
        * TMDB_VOTE_FILTER,
        *+ TMDB_ENABLE_SELECT_BY_YEAR_RANGE (increase of range not too destructive),
            * TMDB_YEAR_RANGE_MINIMUM or None
            * TMDB_YEAR_RANGE_MAXIMUM or None
        *+ TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        FILTER_GENRES
        * GENREXXX
        * keywords
        * certifications: not-yet-rated, Unknown certification, max_certification
        
        '''
        try:
            self._minimum_year = 0
            self._maximum_year = 0
            self._select_by_year_range = Settings.is_tmdb_select_by_year_range()
            if self._select_by_year_range:
                self._minimum_year = Settings.get_tmdb_minimum_year()
                self._maximum_year = Settings.get_tmdb_maximum_year()

            #
            # Will compare parameters with earlier cached ones. If different,
            # New cache will be initialized. Otherwise, old one loaded.

            current_parameters = CacheParameters({
                # type: List[str]
                'included_genres': self._selected_genres,
                # type: List[str]
                'excluded_genres': self._excluded_genres,
                # type: List[str]
                'included_tags': self._selected_keywords,
                # type: List[str]
                'excluded_tags': self._excluded_keywords,
                'minimum_year': self._minimum_year,  # type: int
                'maximum_year': self._maximum_year,  # type: int
                'remote_trailer_preference': self._remote_trailer_preference,
                'vote_comparison': self._vote_comparison,  # type: int
                'vote_value': self._vote_value,  # type: int
                'rating_limit_string': self._rating_limit_string,  # type: str
                'language': self._language,  # type str
                'country': self._country,  # type: str
                'cache_state': CacheIndex.UNINITIALIZED_STATE  # type: str
            })

            cache_changed: bool
            rebuild_cache: bool
            cache_changed, rebuild_cache = CacheParameters.load_cache(current_parameters)
            CacheIndex.load_cache(cache_changed)
            self._rebuild_cache = rebuild_cache

            if self._filter_genres:
                if self._selected_genres != '' or self._excluded_genres != '':
                    # If performing genre filter, then need separate query for genres
                    # and keywords and combine them. This way the results are the union.
                    # Otherwise they are  the intersection.

                    genre_movies = self.first_phase_discovery(tmdb_trailer_type,
                                                              tmdb_search_query="genre")
                    # None indicates already configured
                    if genre_movies is not None:
                        movies.extend(genre_movies)
                        del genre_movies
                if self._selected_keywords != '' or self._excluded_keywords != '':
                    keyword_movies = self.first_phase_discovery(tmdb_trailer_type,
                                                                tmdb_search_query="keyword")
                    # None indicates already configured
                    if keyword_movies is not None:
                        movies.extend(keyword_movies)
                        del keyword_movies
            else:
                # Need to determine if we will search by year or all years. The
                # total number of matching movies will govern this.
                generic_movies = self.first_phase_discovery(tmdb_trailer_type,
                                                            tmdb_search_query="generic")
                # None indicates already configured
                if generic_movies is not None:
                    movies.extend(generic_movies)
                    del generic_movies

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

        return movies

    def first_phase_discovery(self,
                              tmdb_trailer_type: str,
                              tmdb_search_query: str = "",
                              ) -> Optional[List[TMDbMoviePageData]]:
        """
        If a year range is NOT specified, then years are IGNORED. Only get
        search pages 1..n.

        If a year range is specified, then we want to get as close to an even
        sampling of movies across the years. What follows is how a range
        of years is processed:

        First, ignoring any specified years, find out how many total
        trailers will be found by the query. From this, decide if
        querying by year is needed.

        Get a page of data from TMDB. This page will give us the
        total number of pages, as well as the number of results.
        After that, get random pages worth of data.

        The first page does not have to be page #1, since metadata
        is returned by all pages.

        :param tmdb_trailer_type:
        :param tmdb_search_query:
        :return: movies
        """
        clz = type(self)

        # Is cache from previous run in a good state?
        cached_pages_data: CachedPagesData = CachedPagesData.pages_data[tmdb_search_query]
        if cached_pages_data.get_total_pages() != 0:
            return None

        page_to_get: int = 1
        if self._select_by_year_range:
            page_to_get = DiskUtils.RandomGenerator.randint(1, 50)

        url, data = self.create_request(
            tmdb_trailer_type, page=page_to_get, tmdb_search_query=tmdb_search_query)
        finished = False
        delay = 0.5
        page_data: MovieType = {}
        while not finished:
            try:
                result: Result = JsonUtilsBasic.get_json(
                    url, params=data)

                s_code = result.get_api_status_code()
                if s_code is not None:
                    clz.logger.debug(f'api status: {s_code}')

                status_code: JsonReturnCode = result.get_rc()
                if status_code == JsonReturnCode.OK:
                    finished = True

                    page_data = result.get_data()
                    if page_data is None:
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                            clz.logger.debug(f'page_data None status OK. Skipping page')

                if status_code in (JsonReturnCode.FAILURE_NO_RETRY,
                                   JsonReturnCode.UNKNOWN_ERROR):
                    clz.logger.debug_extra_verbose(f'TMDb call'
                                                   f' {status_code.name}')
                    finished = True

                if status_code == JsonReturnCode.RETRY:
                    clz.logger.debug_extra_verbose(f'TMDb call failed RETRY')
                    raise CommunicationException()

            except CommunicationException as e:
                self.throw_exception_on_forced_to_stop(timeout=delay)
                delay += delay

        total_results = page_data.get('total_results', 0)
        total_pages = page_data.get('total_pages', 0)

        # TMDb rejects requests requests for page #  > 1000

        if total_pages > 1000:
            total_pages = 1000

        query_by_year = False

        if self._select_by_year_range:
            years_in_range = self._maximum_year - self._minimum_year + 1
            if total_pages > (years_in_range * 1.5):
                query_by_year = True

        cached_pages_data.set_total_pages(total_pages)
        cached_pages_data.set_query_by_year(query_by_year)

        # Process this first page.
        #
        # In order to improve the randomness of the first
        # few trailers played, don't add movies to the list of
        # discovered movies until a second page is read.

        movies: List[TMDbMoviePageData]
        movies = self.process_page(page_data, url=url)

        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug('Search Query type:', tmdb_search_query,
                             'TMDB movies:', total_results,
                             'total_pages:', total_pages,
                             'query_by_year:', query_by_year)

        return movies

    def second_phase_discovery(self,
                               max_pages: int,
                               pages_in_chunk: int,
                               tmdb_trailer_type: str,
                               tmdb_search_query: str,
                               additional_movies: List[TMDbMoviePageData]
                               ) -> bool:
        """
        :param max_pages:
        :param pages_in_chunk: Limit pages read per call. Used when Genre and
                               Keyword queries exist. Allows alternating between
                               them to improve randomness.
        :param tmdb_trailer_type:
        :param tmdb_search_query:
        :param additional_movies:
        :return:
        """
        # Called after first_phase_discovery determines how many total movies
        # on TMDB match the search criteria. This drives the decision whether
        # to break the search down into multiple searches per-year, or
        # to search across all years within the specified range at once.
        # Performing searches on individual years ensures that the sampling
        # is more random.
        #
        # When complete:
        #  A plan for what years to search, and which "pages" to request from
        #  TMDb. (The results of a query are chunked into pages, a group
        #  of 20 movies from TMDb.)
        #
        #  If query_by_year, a chunk is read for each year in the query, in
        #  order to create a search plan, Each chunk contains the total number
        #  of movies for that year satisfy the query. From this a plan for
        #  how many pages to read for each year is created and persisted.
        #
        # If not query_by_year, the plan can be completed without reading
        # any more pages than the one read in first_phase_discovery.
        #
        # The plan is persisted as it is built.
        #
        # In case of interruption, this method will complete building the plan.
        #
        # As a side-effect, as each page is read, the movies for that page are
        # added to the discovered movies list for further processing by
        # AbstractTrailerFetcher thread.
        #
        clz = type(self)
        if additional_movies is None:
            additional_movies = []

        pages_read = 0
        cached_pages_data: CachedPagesData = CachedPagesData.pages_data[tmdb_search_query]
        query_by_year: bool = cached_pages_data.is_query_by_year()

        #  TODO: Verify this
        if cached_pages_data.is_search_pages_configured():
            return True  # Not known if finished reading pages

        if query_by_year:

            if cached_pages_data.get_years_to_query() is None:
                ###########################################################
                #
                #    SEARCH BY YEAR
                #
                # From the first phase, we know the total number of pages
                # in the database satisfy the query. We want to spread
                # the query out across the year range in proportion to
                # the the number of results for each year.
                #
                # Need to find out how many pages of movies are available
                # per year. Do this by querying a random page for each year.
                #

                clz.logger.debug('Query by year',
                                         trace=Trace.TRACE_CACHE_PAGE_DATA)

                page_to_get = 1  # Overwritten later
                url, data = self.create_request(
                    tmdb_trailer_type, page=page_to_get,
                    tmdb_search_query=tmdb_search_query)

                years_to_get = list(
                    range(self._minimum_year, self._maximum_year))
                DiskUtils.RandomGenerator.shuffle(years_to_get)
                cached_pages_data.set_years_to_query(years_to_get)
                cached_pages_data.save_search_pages(flush=True)
                clz.logger.debug('# years to get:',
                                         len(years_to_get),
                                         trace=Trace.TRACE_CACHE_PAGE_DATA)
            #
            # Cache now has years to query

            years_to_get = cached_pages_data.get_years_to_query()
            pages_in_year = {}
            total_pages_for_years = 0
            search_pages = []

            url, data = self.create_request(
                tmdb_trailer_type, page=1,  # dummy page #, updated in get_movies
                tmdb_search_query=tmdb_search_query)

            # Read one random page for each year to query. This gives us the number
            # of pages in the year. This will later guide us in what pages to read
            # for each year.

            for year in years_to_get:
                self.throw_exception_on_forced_to_stop()

                total_pages_in_year = cached_pages_data.get_total_pages_for_year(
                    year)

                # Check to see if there is already an entry for this year
                # in the cache (from an interrupted run). If there is
                # an entry, then all of the movies from that page were
                # read and put into the cache. In addition, the plan for
                # what pages to read was placed into the cache.

                if total_pages_in_year is not None:
                    first_page_to_get = 0  # Dummy
                    if str(year) not in pages_in_year:
                        # Ok, the plan for what pages to read for this year
                        # and the movies for at least the first page are in
                        # the cache. Add the total number of pages that TMDB
                        # returned for the year returned by the query.
                        #
                        aggregate_query_results = \
                            DiscoverTmdbMovies.AggregateQueryResults(
                                total_pages=total_pages_in_year)
                        pages_in_year[str(year)] = aggregate_query_results

                else:
                    # For a year not in the cache, query TMDB for any page from
                    # that year. The response will contain the total number of
                    # pages for that year.

                    movies_read: int = 0
                    first_page_to_get: int = 0
                    max_page_number = 50
                    while movies_read == 0:
                        first_page_to_get = DiskUtils.RandomGenerator.randint(
                            1, max_page_number)
                        # In case we overshoot the number of pages available.
                        max_page_number = int(max_page_number / 2)
                        if max_page_number == 0:
                            break

                        # get_movies processes any movies found. No additional
                        # work required here.

                        # A bit kludgey. Originally the page number was sent to
                        # get_movies, but it was highly desirable for the successfully
                        # discovered info to be recorded in the caches there rather than
                        # to pass back a complex structure indicating the successfully
                        # read pages and record into the caches here. Probably should
                        # come up with something cleaner.

                        dummy_page = CachedPage(year, first_page_to_get,
                                                processed=True,
                                                # movies sent to unprocessed
                                                total_pages_for_year=1)

                        movies_read = self.get_movies(url=url, data=data,
                                                      pages_to_get=[
                                                          dummy_page],
                                                      already_found_movies=
                                                      additional_movies,
                                                      year=year, year_map=pages_in_year,
                                                      tmdb_search_query=tmdb_search_query)
                    del additional_movies[:]

                    # Cache what page was read and total available in year

                    aggregate_query_results = pages_in_year[str(year)]
                    total_pages_in_year = aggregate_query_results.get_total_pages()
                    cached_page = CachedPage(year, first_page_to_get,
                                             processed=True,  # movies sent to unprocessed
                                             total_pages_for_year=total_pages_in_year)
                    search_pages.append(cached_page)
                    CacheIndex.add_search_pages(tmdb_search_query,
                                                search_pages)
                    cached_pages_data.save_search_pages(flush=True)

                    del search_pages[:]
                    pages_read += 1
                    if pages_read >= pages_in_chunk:
                        return False  # Not finished

                total_pages_for_years += int(total_pages_in_year)

            # Grand total of TMDB pages for all of the years read

            if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                clz.logger.debug('configuring search pages',
                                 'query_by_year: True',
                                 'total_pages_for_years:',
                                 total_pages_for_years,
                                 trace=Trace.TRACE_DISCOVERY)

            # Now that one page per year has been read and we also know
            # how many pages there are for each year. Create a plan for what
            # pages to read for each year based upon the proportion of pages
            # in each year. Consult the cache to determine if a plan for this
            # year already exists, and what pages have already been processed.
            #
            # We know the total number of pages that we want to read.
            # We know how many years that we want to read from.
            # We know how many pages are available for each year
            # We know how many pages that we have already processed for each
            # year.
            #
            # There are probably more movies matching the query than
            # we want to process (max_pages).

            page_scale_factor: float = 1.0
            if max_pages < total_pages_for_years:
                # Reduce the number of pages by each year proportionally.

                total_pages = cached_pages_data.get_total_pages()
                page_scale_factor = total_pages / max_pages

            pages_for_year = []
            for year in pages_in_year:
                aggregate_query_results = pages_in_year[year]
                total_pages_in_year = aggregate_query_results.get_total_pages()
                viewed_page = aggregate_query_results.get_viewed_page()
                scaled_pages = int(
                    (total_pages_in_year / page_scale_factor) + 0.5)
                try:
                    # Generate random list of pages to read for this year.
                    # But first, account for pages already read.

                    cached_pages_in_year = \
                        cached_pages_data.get_entries_for_year(int(year))
                    number_of_pages_in_plan = len(cached_pages_in_year)
                    if number_of_pages_in_plan > 1:
                        # Plan already set, no need to change. It IS possible
                        # that more movies for this year has been added to TMDB
                        # since the cache was created, but not likely, except
                        # for the most recent years. That could be handled, if
                        # it becomes a problem.
                        pass
                    else:
                        pages_for_year = DiskUtils.RandomGenerator.sample(
                            range(1, total_pages_in_year + 1), scaled_pages)
                        if viewed_page is not None and viewed_page in pages_for_year:
                            pages_for_year.remove(viewed_page)

                            # Generate year-page tuple pairs and add to list
                            # of all pages that are to be read for each year

                            for page in pages_for_year:
                                cached_page = CachedPage(int(year), page)
                                search_pages.append(cached_page)

                            CacheIndex.add_search_pages(tmdb_search_query,
                                                        search_pages, flush=False)

                    CacheIndex.save_cached_pages_data(
                        tmdb_search_query, flush=True)
                except KeyError:
                    pages_for_year = []
                except ValueError:
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug(f'ValueError: 1 {total_pages_in_year}  '
                                        f'scaled_pages: {scaled_pages}')

        if not query_by_year:
            # This is much easier. Just plan on what pages to read from TMDB.
            # Use the information returned from the initial query made in
            # first_phase_discovery to guide how many subsequent pages need to
            # be read.
            #
            # Do not read random pages to spread pages across years. We are bound
            # to the search order specified by the query.
            #

            search_pages = []
            total_pages = cached_pages_data.get_total_pages()
            for page in list(range(2, min(total_pages, max_pages) + 1)):
                cached_page = CachedPage(None, page)
                search_pages.append(cached_page)

            CacheIndex.add_search_pages(tmdb_search_query,
                                        search_pages, flush=True)

        cached_pages_data.set_search_pages_configured(flush=True)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug(f'SEARCH_PAGES_CONFIGURED: len(cached_pages_data): ',
                             f'{cached_pages_data.get_number_of_search_pages()} ',
                             trace=Trace.TRACE_DISCOVERY)
        return True  # finished

    def purge_cache_x(self, actually_delete: bool) -> None:
        """
        Settings have changed enough to warrant destroying all of the .json
        files in the TMDb cache.
        """
        clz = type(self)

        # TODO: How do we know when to do this? It is very expensive to traverse
        # files and load JSON. Perhaps track when it was last done?
        # It is effective only when settings change what movies are selected
        # so that there are some in the cache that were filtered out by last
        # settings. Just a waste of time if no settings change.
        #
        # If more trailers are needed, scan the cache for movies. This is
        # done because the cache is not purged when the search query is changed.

        '''
        All downloaded tmdb .json files are recorded in tmdb_json_cache.json.
        We can simply clear this cache without deleting the downloaded 
        tmdb json files. The metadata garbage collector will eventually
        blow away the downloaded tmdb json files, but it can be a while
        (the default is 180 days after file creation).
        
        TODO: We can create a setting to clear unreferenced downloaded 
        json files. If so, should probably also specify # days to wait
        before clearing them in case the new download filter will end
        up re-downloading the already cached files. 
        note: deletion of downloaded json files should ensure that they
        are not still referenced by the other xxx_json_cache files.
        '''

        clz.logger.debug_verbose(f'Purging Cache')

        json_cache = JsonCacheHelper.get_json_cache_for_source(MovieField.TMDB_SOURCE)
        json_cache.clear()

    def purge_cache(self, actually_delete: bool) -> None:
        """
        Settings have changed enough to warrant destroying all of the .json
        files in the TMDb cache.
        """
        clz = type(self)

        # TODO: How do we know when to do this? It is very expensive to traverse
        # files and load JSON. Perhaps track when it was last done?
        # It is effective only when settings change what movies are selected
        # so that there are some in the cache that were filtered out by last
        # settings. Just a waste of time if no settings change.
        #
        # If more trailers are needed, scan the cache for movies. This is
        # done because the cache is not purged when the search query is changed.

        clz.logger.debug_verbose(f'Purging Cache actually_delete: {actually_delete}')

        start_time: datetime.datetime = datetime.datetime.now()
        deleted_files: int = 0
        try:
            '''
            Walk the entire TMDb cache and delete all .json files
            '''
            cache_top: str = xbmcvfs.translatePath(
                Settings.get_remote_db_cache_path())

            path: Path
            file_iterable: FindFiles
            file_iterable = FindFiles(cache_top, Constants.TMDB_GLOB_JSON_PATTERN)
            for path in file_iterable:
                try:
                    self.throw_exception_on_forced_to_stop(0.0)
                    if path.parent.name == 'index':
                        continue

                    # clz.logger.debug(f'path: {path.absolute()} name: {path.name}')
                    match: Match = Constants.TMDB_ID_PATTERN.search(path.name)
                    if match is None:  # Just in case
                        continue

                    clz.logger.debug(f'Deleting TMDb JSON: {path}')
                    if actually_delete:
                        path.unlink(True)  # Missing is ok
                    deleted_files += 1

                except (AbortException, StopDiscoveryException):
                    reraise(*sys.exc_info())
                except Exception as e:
                    clz.logger.exception()

                # Get leftovers

            # In case loop is exited early, tell it to kill
            # file iteration thread.

            # file_iterable.kill()

            stop_time: datetime.datetime = datetime.datetime.now()
            delta_time_seconds: int = int((stop_time - start_time).total_seconds())

            clz.logger.debug_extra_verbose(
                f'Seconds to delete {deleted_files} json files: '
                f'{delta_time_seconds:,d} actually_delete: {actually_delete}')

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception()

    def send_cached_movies_to_discovery(self) -> None:
        """
            Before doing the expensive discovery of trailers from TMDb,
            enter previously discovered information into the discovery queue.

            First, load all TMDb ids which are known to have trailers. TMDb
            discovery will be required to determine if the trailer passes the
            current filter. Hopefully, the TMDb discovery data is already
            persisted so that the download from TMDb is not required.

            Next, get the persisted list of TMDb ids which passed the
            filter criteria from a previous run, but not yet fully discovered
            from TMDb. Add these to the discovery queue.

            Finally, get a list of every TMDb id from the
            local cache of TMDb information. This is done in an attempt to
            reuse information that is local.

        :return:
        """

        clz = type(self)
        additional_movies_to_get: int = 0

        try:

            #  Send any cached TMDb trailers to the discovered list first,
            #  since they require least processing AND known to have trailers.

            additional_movies_to_get = (Settings.get_max_tmdb_trailers()
                                        - self.get_number_of_known_trailers())
            '''
            TODO: Review if we can still use this, with modification.
            
            tmdb_movies: Set[TMDbMovieId] = \
                CacheIndex.get_tmdb_ids_with_trailers()
            

            # Only send movies which are also known to be in our cache of known
            # TMDb
            additional_movies_to_get -= len(tmdb_movies)
            
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose(
                    f"Sending {len(tmdb_movies)} TMDb movies with trailers to "
                    f"discovery. Additional to get: {additional_movies_to_get} "
                    f"# known trailers: {self.get_number_of_known_trailers()}")

            self.add_to_discovered_movies(tmdb_movies)
            '''
            pass
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

        if additional_movies_to_get > 0:
            try:
                unprocessed_movies: List[TMDbMovieId]

                # First, purge any unprocessed movies which are known to not
                # have a trailer

                unprocessed_movies = CacheIndex.get_unprocessed_movies()
                tmdb_movie_id: TMDbMovieId
                for tmdb_movie_id in unprocessed_movies:
                    tmdb_id_int: int = tmdb_movie_id.get_tmdb_id()
                    if TrailerUnavailableCache.is_tmdb_id_missing_trailer(tmdb_id_int):
                        CacheIndex.remove_unprocessed_movie(tmdb_id_int)

                # Next, add movies with known, local (cached) trailers to
                # first stage discovery. Also purge these from unprocessed
                # movies cache, since they were clearly processed once.

                unprocessed_movies = CacheIndex.get_unprocessed_movies()
                movies_with_trailers: List[TMDbMovieId]
                movies_with_trailers = TMDbTrailerIndex.get_all_with_local_trailers()

                self.add_to_discovered_movies(movies_with_trailers)
                for tmdb_movie_id in movies_with_trailers:
                    try:
                        unprocessed_movies.remove(tmdb_movie_id)
                    except ValueError:
                        pass

                additional_movies_to_get -= len(movies_with_trailers)

                # Same thing, but with movies that we know have a trailer, but not
                # yet downloaded

                unprocessed_movies = CacheIndex.get_unprocessed_movies()
                movies_with_trailers = TMDbTrailerIndex.get_all_with_non_local_trailers()

                self.add_to_discovered_movies(movies_with_trailers)
                for tmdb_movie_id in movies_with_trailers:
                    try:
                        unprocessed_movies.remove(tmdb_movie_id)
                    except ValueError:
                        pass

                additional_movies_to_get -= len(movies_with_trailers)

                if len(unprocessed_movies) > additional_movies_to_get:
                    del unprocessed_movies[additional_movies_to_get:]
                else:
                    unprocessed_movies.clear()

                clz.logger.debug_verbose(f'Sending {len(unprocessed_movies)} '
                                         f'unprocessed movies to discovery')
                self.add_to_discovered_movies(unprocessed_movies, shuffle=True)

            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                clz.logger.exception('')

        '''
            TODO: Review this
            
        # TODO: How do we know when to do this? It is very expensive to traverse
        # files and load JSON. Perhaps track when it was last done?
        # It is effective only when settings change what movies are selected
        # so that there are some in the cache that were filtered out by last
        # settings. Just a waste of time if no settings change.
        #
        # If more trailers are needed, scan the cache for movies. This is
        # done because the cache is not purged when the search query is changed.

        if additional_movies_to_get > 0:
            start_time: datetime.datetime = datetime.datetime.now()
            tmdb_ids_found: int = 0
            try:
                # The easiest way to do this is to walk the cache and collect
                # tmdb ids. Then treat the ids as get_tmdb_ids_with_trailers,
                # above. Later, movie fetcher will reject any that don't pass
                # the filter.

                # Add wait between each movie added = 0.1 + log(# trailers_added * 2)
                # seconds
                # For 1,000 trailers added, the delay is 0.1 + 3.3 = 3.4 seconds
                #
                # The delay does not occur until when they json files are read

                delay = Delay(bias=0.1, call_scale_factor=2.0, scale_factor=1.0)

                cache_top: str = xbmcvfs.translatePath(Settings.get_remote_db_cache_path())

                tmdb_movie_ids: List[TMDbMovieId] = []
                path: Path
                file_iterable: FindFiles
                file_iterable = FindFiles(cache_top, Constants.TMDB_GLOB_JSON_PATTERN)
                for path in file_iterable:
                    try:
                        self.throw_exception_on_forced_to_stop(0.0)
                        if path.parent.name == 'index':
                            continue

                        # clz.logger.debug(f'path: {path.absolute()} name: {path.name}')
                        match: Match = Constants.TMDB_ID_PATTERN.search(path.name)
                        if match is None:  # Just in case
                            continue

                        tmdb_id: str = match.group(1)

                        # Is Movie already discovered?

                        movie: BaseMovie = self.get_by_id(tmdb_id)
                        if movie is not None:
                            continue

                        try:
                            tmdb_movie_ids.append(TMDbMovieId(tmdb_id))
                            additional_movies_to_get -= 1
                        except ValueError:
                            clz.logger.debug(f'Could not convert tmdb_id to int: {tmdb_id}')

                        if len(tmdb_movie_ids) > 5:
                            additional_movies_to_get -= len(tmdb_movie_ids)
                            self.add_to_discovered_movies(tmdb_movie_ids)
                            tmdb_movie_ids.clear()

                        if additional_movies_to_get <= 0:
                            break

                    except (AbortException, StopDiscoveryException):
                        reraise(*sys.exc_info())
                    except Exception as e:
                        clz.logger.exception()

                    # Get leftovers

                # In case loop is exited early, tell it to kill
                # file iteration thread.

                # file_iterable.kill()

                tmdb_ids_found = len(tmdb_movie_ids)
                stop_time: datetime.datetime = datetime.datetime.now()
                delta_time_minutes: int = int((stop_time - start_time).total_seconds()
                                              / 60.0)

                clz.logger.debug_extra_verbose(f'Minutes to discover {tmdb_ids_found}'
                                               f' json files: '
                                               f'{delta_time_minutes:,d}')

                if tmdb_ids_found > 0:
                    additional_movies_to_get -= len(tmdb_movie_ids)
                    self.add_to_discovered_movies(tmdb_movie_ids)
                    tmdb_movie_ids.clear()

            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                clz.logger.exception()
            '''

    def discover_movies_using_search_pages(self,
                                           tmdb_trailer_type: str,
                                           tmdb_search_query: str = "",
                                           pages_in_chunk: int = 5) -> bool:
        """
        At this point the decision about what pages and years to search
        have been made and saved to the cache. Now, execute the plan!

        :param tmdb_trailer_type:
        :param tmdb_search_query:
        :param pages_in_chunk:
        :return: True when there are more movies to get
                 False when there are no more movies to get
        """
        clz = type(self)
        more_to_get: bool = True
        try:
            cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
            page_to_get = 1  # Will be overridden
            url, data = self.create_request(tmdb_trailer_type,
                                            page=page_to_get,
                                            tmdb_search_query=tmdb_search_query)
            query_by_year = cached_pages_data.is_query_by_year()
            additional_movies_to_get = (Settings.get_tmdb_max_download_movies()
                                        - self.get_number_of_movies())
            additional_pages_to_get = int(additional_movies_to_get / clz.MOVIES_PER_PAGE)

            if query_by_year:
                # Search delay is influenced by number of discovered pages

                number_of_discovered_pages = \
                    CacheIndex.get_number_of_discovered_search_pages()
                self._total_pages_read += number_of_discovered_pages
                # Generate year-page tuple pairs and add to giant list
                # of all pages that are to be read for each year

                search_pages = CacheIndex.get_search_pages(tmdb_search_query)

                # The reason to have a long list of every page to be read
                # by year is that it can be completely randomized to improve
                # randomness of trailers found. Further, it makes it
                # simpler to limit number of pages read without having
                # complex code to keep things fair.

                DiskUtils.RandomGenerator.shuffle(search_pages)
                pages_in_chunk = min(pages_in_chunk, len(search_pages))
                search_pages = search_pages[:pages_in_chunk]

                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug('length of year/page pairs:',
                                     len(search_pages),
                                     trace=Trace.TRACE_CACHE_PAGE_DATA)

                for cached_page in search_pages:
                    additional_pages_to_get -= 1
                    if additional_pages_to_get < 0:
                        more_to_get = False
                        break
                    if self.is_exceeded_limit_of_trailers():
                        more_to_get = False
                        break
                    if self.is_exceeded_limit_of_movies():
                        more_to_get = False
                        break
                    self.throw_exception_on_forced_to_stop()
                    year = cached_page.get_year()
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug(f'Getting trailers for year: {year} '
                                         f'page: {cached_page.get_page_number()}',
                                         trace=Trace.TRACE_CACHE_PAGE_DATA)

                    self.get_movies(url=url, data=data,
                                    pages_to_get=[cached_page],
                                    already_found_movies=[], year=year,
                                    tmdb_search_query=tmdb_search_query)

            if not query_by_year:
                # TODO: could be done much cleaner. Redundant
                # cached_pages_data, etc.

                search_pages = CacheIndex.get_search_pages(tmdb_search_query)
                processed_search_pages = []
                clz.logger.debug(f'# search_pages: {len(search_pages)} '
                                 f'additional_pages_to_get: {additional_pages_to_get} ')
                DiskUtils.RandomGenerator.shuffle(search_pages)
                for cached_page in search_pages:
                    additional_pages_to_get -= 1
                    if additional_pages_to_get < 0:
                        more_to_get = False
                        break
                    if self.is_exceeded_limit_of_trailers():
                        clz.logger.debug(f'Exceeded limit of trailers')
                        more_to_get = False
                        break
                    if self.is_exceeded_limit_of_movies():
                        clz.logger.debug(f'Exceeded limit of movies')
                        more_to_get = False
                        break
                    processed_search_pages.append(cached_page)

                self.get_movies(url=url, data=data,
                                pages_to_get=processed_search_pages,
                                tmdb_search_query=tmdb_search_query)

            # Make sure cache is flushed
            CacheIndex.save_unprocessed_movies_cache(flush=True)

            # Recalculate how many pages we still need to get, since there
            # may have been some failures in get_movies, or the remote
            # possibility that enough movies without trailers have ben
            # removed from the discovered trailer queue

            additional_movies_to_get = (Settings.get_tmdb_max_download_movies()
                                        - self.get_number_of_movies())
            additional_pages_to_get = int(additional_movies_to_get / clz.MOVIES_PER_PAGE)
            search_pages = CacheIndex.get_search_pages(tmdb_search_query)
            clz.logger.debug(f'Final # search_pages: {len(search_pages)} '
                             f'additional_pages_to_get: {additional_pages_to_get} ')

            more_to_get = True
            if len(search_pages) <= 0:
                more_to_get = False
            elif additional_pages_to_get <= 0:
                more_to_get = False
            elif self.is_exceeded_limit_of_trailers():
                clz.logger.debug(f'Exceeded limit of trailers')
                more_to_get = False
            elif self.is_exceeded_limit_of_movies():
                clz.logger.debug(f'Exceeded limit of movies')
                more_to_get = False

            #
            # API key used is marked inactive. Terms from Rotten Tomatoes appears to
            # require logo displayed and probably other disclosures. I have not
            # researched this much, but this seems to go against Kodi's open-source
            # goals, if not rules.
            #
            # ========================
            #
            #   DVDs
            #
            #  Info comes from Rotton Tomatoes and TMDB
            #  TODO: Need API key?
            #
            # ========================
            # elif tmdb_trailer_type == 'dvd':
            #    data = {}
            #    data['apikey'] = Settings.get_rotten_tomatoes_api_key()
            #    data['country'] = 'us'
            #    url = 'http://api.rottentomatoes.com/api/public/v1.0/lists/dvds
            #    /new_releases.json'
            #    statusCode, infostring = DiskUtils.get_json(url, params=data)
            #
            #    # TODO- Can you search for more than one move at a time?
            #
            #    for movie in infostring['movies']:
            #        data = {}
            #        data['api_key'] = Settings.get_tmdb_api_key()
            #        data['query'] = movie[MovieField.TITLE]
            #        data['year'] = movie['year']
            #        url = 'https://api.themoviedb.org/3/search/movie'
            #        statusCode, infostring = DiskUtils.get_json(url, params=data)
            #
            #        for m in infostring['results']:
            #            trailerId = m['id']
            #            trailerEntry = {MovieField.TRAILER: MovieField.TMDB_SOURCE,
            #                            MovieField.TMDB_ID: trailerId,
            #                            MovieField.SOURCE: MovieField.TMDB_SOURCE,
            #                            MovieField.TITLE: movie[MovieField.TITLE]}
            #            self.add_to_discovered_movies(trailerEntry)
            #
            #            clz.logger.debug(' DVD title: ' +
            #                              trailerEntry[MovieField.TITLE])
            #            break
            #
            # ========================
            #
            #   Everything else (popular, top_rated, upcoming, now playing)
            #
            # ========================

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception()
        return more_to_get

    def is_exceeded_limit_of_trailers(self) -> bool:
        """
            Checks to see if the maximum number of trailers has been
            discovered. Note that TMDb movie discovery occurs in two
            steps:
                1) general movie information matching a filter (from
                settings) is built. This is done over time.

                2) Other threads query TMDb for detail information for
                each movie discovered from step 1. Movies without trailers
                or not passing additional filtering will be eliminated.

            Therefore, this method returns the current count of known
            trailers. Another method, is_exceeded_limit_of_movies is
            used to limit how many movie entries are downloaded from
            step 1.

        :return:

        """
        clz = type(self)
        return self.get_number_of_known_trailers() > Settings.get_max_tmdb_trailers()

    def is_exceeded_limit_of_movies(self) -> bool:
        return self.get_number_of_movies() > Settings.get_tmdb_max_download_movies()

    def create_request(self,
                       tmdb_trailer_type: str,
                       page: int,
                       tmdb_search_query: str = ''
                       ) -> (str, Dict[str, Any]):
        """
            Create a URL and data required for a request to TMDB based
            upon the parameters specified here.

        :param tmdb_trailer_type:
        :param page:
        :param tmdb_search_query:
        :return:
        """
        """
            TMDB API

            Specify a ISO 3166-1 code to filter release dates. Must be uppercase.
            pattern: ^[A-Z]{2}$
            optional

            sort_by
            string
            Choose from one of the many available sort options.
                popularity.asc, popularity.desc,
                release_date.asc, release_date.desc,
                revenue.asc, revenue.desc,
                primary_release_date.asc, primary_release_date.desc,
                original_title.asc, original_title.desc,
                vote_average.asc, vote_average.desc,
                vote_count.asc, vote_count.desc
                default: popularity.desc
            optional

            certification_country
            string
            Used in conjunction with the certification filter, use this to specify
             a country with a valid certification.
            optional

            certification
            string
            Filter results with a valid certification from the 'certification_country'
            field.
            optional

            certification.lte
            string
            Filter and only include movies that have a certification that is
             less than or equal to the specified value.
            optional

            include_adult
            boolean
            A filter and include or exclude adult movies.
            optional

            include_video
            boolean
            A filter to include or exclude videos.
            default
            optional

            page
            integer
            Specify the page of results to query.
            minimum: 1
            maximum: 1000
            default: 1
            optional

            primary_release_year
            integer
            A filter to limit the results to a specific primary release year.
            optional

            primary_release_date.gte
            string
            Filter and only include movies that have a primary release date
            that is greater or equal to the specified value.
            format: date
            optional

            primary_release_date.lte
            string
            Filter and only include movies that have a primary release date
            that is less than or equal to the specified value.
            optional

            release_date.gte
            string
            Filter and only include movies that have a release date (looking at
             all release dates) that is greater or equal to the specified value.
            format: date
            optional

            release_date.lte
            string
            Filter and only include movies that have a release date (looking at
            all release dates) that is less than or equal to the specified value.
            format: date
            optional

            vote_count.gte
            integer
            Filter and only include movies that have a vote count that is
            greater or equal to the specified value.
            minimum: 0
            optional

            vote_count.lte
            integer
            Filter and only include movies that have a vote count that is l
            less than or equal to the specified value.
            minimum: 1
            optional

            vote_average.gte
            number
            Filter and only include movies that have a rating that is greater
             or equal to the specified value.
            minimum: 0
            optional

            vote_average.lte
            number
            Filter and only include movies that have a rating that is less
            than or equal to the specified value.
            minimum: 0
            optional

            with_cast
            string
            A comma or pipe separated list of person ID's. Only include movies that
             have one of the ID's added as an actor. (comma for AND, pipe (|) for OR)
            optional

            with_crew
            string
            A comma or pipe separated list of person ID's. Only include movies that
            have one of the ID's added as a crew member.(comma for AND, pipe (|) for OR)
            optional

            with_companies
            string
            A comma separated list of production company ID's. Only include
            movies that have one of the ID's added as a production company.
            optional

            with_genres
            string
            Comma or pipe separated value of genre ids that you want to include in
            the results. (comma for AND, pipe (|) for OR)
            optional

            with_keywords
            string
            A comma separated list of keyword ID's. Only include movies that
             have one of the ID's added as a keyword.
            optional

            with_people
            string
             Comma or pipe separated list of person ID's. Only include movies that
            have one of the ID's added as a either a actor or a crew member.
            (comma for AND, pipe (|) for OR)
            optional

            year
            integer
            A filter to limit the results to a specific year (looking at all
             release dates).
            optional

            without_genres
            string
            Comma or pipe separated value of genre ids that you want to exclude from
            the results. (comma for AND, pipe (|) for OR)
            optional

            with_runtime.gte
            integer
            Filter and only include movies that have a runtime that is greater
             or equal to a value.
            optional

            with_runtime.lte
            integer
            Filter and only include movies that have a runtime that is less
             than or equal to a value.
            optional

            with_release_type
            integer
            Specify a comma (AND) or pipe (OR) separated value to filter
             release types by. These release types map to the same values found on the
             movie release date method.
            minimum: 1
            maximum: 6
            optional

            with_original_language
            string
            Specify an ISO 639-1 string to filter results by their original
            language value.
            optional

            without_keywords
            string
            Exclude items with certain keywords. You can comma and pipe
            separate these values to create an 'AND' or 'OR' logic.
            optional

        """
        clz = type(self)
        data: Dict[str, Any] = {}
        url: str = ''

        try:
            data['page'] = page
            data['api_key'] = self._tmdb_api_key
            # We don't need a sort do we?
            # Since we are getting the first few
            # (hundred or so) flicks returned by this search,
            # sorting can heavily influence what we get.
            #
            # Options are:
            #
            # Note, you must add the suffix .asc or .desc to each
            # of the items below, according to your ascending/descending
            # preference.
            #
            # popularity release_date, revenue, primary_release_date,
            # original_title, vote_average, vote_count
            #
            # The default is popularity.desc

            data['sort_by'] = self._remote_trailer_preference
            data['include_video'] = 'false'
            data['include_adult'] = self._include_adult

            if self._vote_comparison == RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                data['vote_average.gte'] = '0'  # Try to force vote_average in result
            elif self._vote_comparison == RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                data['vote_average.gte'] = str(self._vote_value)
            else:
                data['vote_average.lte'] = str(self._vote_value)

            #
            # TMDB accepts iso-639-1 but adding an iso-3166- suffix
            # would be better (en_US)
            data['language'] = self._language

            # Country codes are: iso_3166_1. Kodi does not supply them
            # Further, learning and handling all of the world's rating
            # systems (including history of them for old movies) seems
            # a challenging task

            data['certification_country'] = Settings.get_country_iso_3166_1().lower()
            data['certification.lte'] = self._rating_limit_string

            # data['with_runtime.gte'] = '600'  # Ten minutes

            # TMDB API does not have a means to find different language
            # versions of movies (dubbed or subtitles). Can only use
            # original language version. Spoken Language is used to specify
            # different languages spoken in the original movie, not to indicate
            # translations.

            data['with_original_language'] = Settings.get_lang_iso_639_1()

            if tmdb_trailer_type == 'all':
                url = TMDbConstants.DISCOVER_ALL_URL
            else:
                url = f'{TMDbConstants.DISCOVER_TRAILER_URL}{tmdb_trailer_type}'

            if tmdb_search_query == "genre":
                data['with_genres'] = self._selected_genres
                data['without_genres'] = self._excluded_genres
                data['with_keywords'] = []
                data['without_keywords'] = []

            elif tmdb_search_query == "keyword":
                data['with_genres'] = []
                data['with_keywords'] = self._selected_keywords
                data['without_genres'] = []
                data['without_keywords'] = self._excluded_keywords

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

        finally:
            return url, data

    def get_movies(self,
                   url: str = None,
                   data: Dict[str, Any] = None,
                   pages_to_get: List[CachedPage] = None,
                   year: int = None,
                   already_found_movies: List[TMDbMoviePageData] = None,
                   year_map: Dict[str, ForwardRef('AggregateQueryResults')] = None,
                   tmdb_search_query: str = ""
                   ) -> int:
        """
            Discovers movies and adds them to the discovered movies pool
            via add_to_discovered_movies.

            Returns number of movies processed and added to discovered
            trailers pool.

        :param url:
        :param data:
        :param pages_to_get:
        :param year:
        :param already_found_movies:
        :param year_map:
        :param tmdb_search_query:
        :return:
        """
        clz = type(self)
        if already_found_movies is None:
            already_found_movies = []
        number_of_movies_processed: int = 0
        try:
            page: CachedPage
            for page in pages_to_get:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug(f'year: {year} page: {page.get_page_number()}')

                # Pages are read faster at the beginning, then progressively
                # slower.

                delay = self.get_delay()
                self.throw_exception_on_forced_to_stop(timeout=delay)

                data['page'] = page.get_page_number()
                if year is not None:
                    data['primary_release_year'] = year
                elif 'primary_release_year' in data:
                    del data['primary_release_year']  # Don't specify year

                if tmdb_search_query == "genre":
                    data['with_genres'] = self._selected_genres
                    data['with_keywords'] = []
                    data['without_genres'] = self._excluded_genres
                    data['without_keywords'] = []
                elif tmdb_search_query == "keyword":
                    data['with_genres'] = []
                    data['with_keywords'] = self._selected_keywords
                    data['without_genres'] = []
                    data['without_keywords'] = self._excluded_keywords

                finished = False
                delay: float = 0.5
                info_string: Dict[str, Any] = {}
                status_code: JsonReturnCode = JsonReturnCode.UNKNOWN_ERROR
                while not finished:
                    try:
                        result: Result = JsonUtilsBasic.get_json(
                            url, params=data)

                        s_code = result.get_api_status_code()
                        if s_code is not None:
                            clz.logger.debug(f'api status: {s_code}')

                        status_code = result.get_rc()
                        if status_code == JsonReturnCode.OK:
                            finished = True
                            info_string = result.get_data()
                            if info_string is None:
                                clz.logger.debug_extra_verbose(
                                    f'Status OK but data is None '
                                    f'Skipping page')
                                status_code = JsonReturnCode.UNKNOWN_ERROR
                        elif status_code in (JsonReturnCode.FAILURE_NO_RETRY,
                                             JsonReturnCode.UNKNOWN_ERROR):
                            clz.logger.debug_extra_verbose(f'TMDb call'
                                                           f' {status_code.name}')
                            finished = True
                        elif status_code == JsonReturnCode.RETRY:
                            clz.logger.debug_extra_verbose(
                                f'TMDb call failed RETRY')
                            raise CommunicationException()

                    except CommunicationException as e:
                        self.throw_exception_on_forced_to_stop(timeout=delay)
                        delay += delay

                # Optional, record the number of matching movies and pages
                # for this query. Can be used to decide which pages to
                # query later.

                if status_code != JsonReturnCode.OK:
                    # Skip processing this bad page
                    continue

                if year is not None and year_map is not None:
                    total_pages = info_string.get('total_pages')
                    if str(year) not in year_map:
                        aggregate_query_results = DiscoverTmdbMovies.AggregateQueryResults(
                            total_pages=total_pages,
                            viewed_page=page.get_page_number())

                        year_map[str(year)] = aggregate_query_results

                movies: List[TMDbMovieId]
                movies = self.process_page(info_string, url=url)
                #  TODO: Probably should have better error checking in process_page
                #        So that we can determine if a fatal error occurred that
                #        would cause us to re-do processing the page again later or not
                #        For now, assume that it worked.

                movies.extend(already_found_movies)
                number_of_movies_processed += len(movies)
                DiskUtils.RandomGenerator.shuffle(movies)
                clz.logger.debug(f'adding {len(movies)} movies to unprocessed and '
                                 f'discoverved_movies')
                CacheIndex.add_unprocessed_tmdb_movies(movies)
                self.add_to_discovered_movies(movies)
                cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                cached_pages_data.mark_page_as_discovered(page)

                # From now on, only add one page's worth of movies to discovered
                # trailers.

                already_found_movies = []
                if self.is_exceeded_limit_of_trailers():
                    break

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

        return number_of_movies_processed

    class AggregateQueryResults:
        """
            Contains movie information discovered through multiple TMDB API
            calls so that they can be conveniently processed in a different
            order than they are discovered.
        """

        def __init__(self,
                     total_pages: int = None,
                     viewed_page: int = None) -> None:
            """

            :param total_pages:
            :param viewed_page:
            """
            clz = type(self)
            clz.logger = module_logger.getChild(
                self.__class__.__name__)
            self._total_pages = total_pages
            self._viewed_page = viewed_page

        def get_total_pages(self) -> Union[int, None]:
            """

            :return:
            """
            clz = type(self)
            return self._total_pages

        def get_viewed_page(self) -> Union[int, None]:
            """

            :return:
            """
            clz = type(self)
            return self._viewed_page

    def process_page(self,
                     page_data: MovieType,
                     url: str = ''
                     ) -> List[TMDbMoviePageData]:
        """
            Parses a page's worth of movie results from TMDB into Kodi
            style MovieType dictionary entries.

        :param page_data:
        :param url:
        :return:
        """

        # The returned results have title, description, release date, rating.
        # Does not have actors, etc.
        '''
            {"total_results": 19844, "total_pages": 993, "page": 1,
                 "results": [{"poster_path": "/5Kg76ldv7VxeX9YlcQXiowHgdX6.jpg",
                              "title": "Aquaman",
                               "overview": "Once home to the most advanced civilization
                                  on Earth, the city of Atlantis is now an underwater
                                  ..,",
                               "release_date": "2018-12-07"
                               "popularity": 303.019, 
                               "original_title": "Aquaman",
                               "backdrop_path": "/5A2bMlLfJrAfX9bqAibOL2gCruF.jpg",
                               "vote_count": 3134,
                               "video": false,
                               "adult": false,
                               "vote_average": 6.9,
                               "genre_ids": [28, 14, 878, 12],
                               "id": 297802,
                               "original_language": "en"
                               },
        '''
        clz = type(self)
        movies: List[TMDbMoviePageData] = []
        try:
            page: int = page_data.get('page', 1)
            total_pages: int = page_data.get('total_pages', -1)
            movie_entries: Dict[str, MovieType] = page_data.get('results', None)
            if total_pages == -1:
                clz.logger.error('total_pages missing',
                                 json.dumps(page_data, indent=3, sort_keys=True))

            if movie_entries is None:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug('results not found. URL:',
                                     url, 'returned value:',
                                     json.dumps(page_data))
            else:
                # Shuffling is done later, but this helps keep the first few
                # (about 3) displayed being the same thing all of the time

                DiskUtils.RandomGenerator.shuffle(movie_entries)
                movie_entry: MovieType
                for movie_entry in movie_entries:
                    try:
                        if clz.logger.isEnabledFor(LazyLogger.DISABLED):
                            clz.logger.debug_extra_verbose('entry:',
                                                           json.dumps(movie_entry,
                                                                      indent=3,
                                                                      sort_keys=True))
                        self.throw_exception_on_forced_to_stop()

                        movie_summary_parser: ParseTMDbPageData = ParseTMDbPageData(movie_entry)
                        movie_id: int = movie_summary_parser.parse_tmdb_id()

                        movie_summary_parser.parse_total_number_of_pages()
                        movie_title: str = movie_summary_parser.parse_title()
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz.logger.debug_verbose(
                                'Processing:', movie_title)

                        year: int = movie_summary_parser.parse_year()
                        popularity: float = movie_summary_parser.parse_popularity()
                        original_title = movie_summary_parser.parse_original_title()
                        #  backdrop_path = movie_entry.get('backdrop_path', '')
                        votes: int = movie_summary_parser.parse_votes()
                        # is_video: bool = movie_summary_parser.parse_is_video()
                        # Certification not part of this type of discovery.
                        certification_id: str = \
                            movie_summary_parser.parse_certification()
                        vote_average = movie_summary_parser.parse_vote_average()
                        genre_ids: [int] = movie_summary_parser.parse_genre_ids()
                        original_language: str = \
                            movie_summary_parser.parse_original_language()

                        movie: TMDbMoviePageData = movie_summary_parser.get_movie()
                        movie.set_buffer_number(page)
                        movie.set_total_pages(total_pages)

                        if TMDbFilter.pre_filter_movie(movie):
                            movies.append(movie)
                    except AbortException:
                        reraise(*sys.exc_info())
                    except Exception as e:
                        clz.logger.exception()

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')
        finally:

            return movies

    def get_delay(self) -> float:
        """
        Gets the delay (in seconds) to wait before querying the TMDb for
        a page of movies matching a search criteria. A page contains basic
        information on 20 movies which most do not have trailers.

        These partially discovered trailers are first added (and persisted)
        to a map of unprocessed_trailers.

        These unprocessed movies are also added to the fetcher queue which
        will crawl through all of them to get more detailed info.

        Delay is based upon how many read and how many unprocessed.

        This is done to prevent overloading Kodi as well as TMDB.

        :return:
        """
        clz = type(self)

        # Pages (20 partially discovered movies) read this run of Kodi. They
        # are persisted so that over time the backlog will shrink

        self._total_pages_read += 1

        # If there is a backlog of movies discovered here, then slow down
        # discovering more. Note that depending upon the search, that most
        # TMDB movies are missing trailers.

        # number_of_unprocessed_movies:
        # These are the partially discovered trailers
        number_of_unprocessed_movies: int = \
            CacheIndex.get_number_of_unprocessed_movies()

        # number_of_movies_in_fetch_queue:
        # Number of movies in fetch queue. This includes partially discovered
        # and partially filtered movies, most without trailers as well as
        # fully discovered movies that have trailers and passed all search criteria.
        # As the trailer fetcher goes through this queue, it consults locally
        # cached TMDb movie information as well as querying TMDb. From the
        # TMDb info many of the entries in the queue are discarded.
        #
        # It is import to:
        #   1) Not overwhelm TMDb (and Kodi) with too many queries for more
        #   pages of partial movie info.
        #   2) Not starve the trailer fetcher queue (number_of_movies_in_fetch_queue)
        #
        #  There is little point in having too many movies in the fetcher queue,
        #  so we can slow things down a bit when it has a lot of entries,
        #  especially when there are a lot of partially discovered movies to
        #  be processed.

        # TODO: Needs more tweaking
        #
        number_of_movies_in_fetch_queue: int = self.get_number_of_movies()
        # number_of_fully_processed_movies: int = self.get_number_of_known_trailers()
        # number_of_partially_processed_movies: int = (number_of_movies_in_fetch_queue -
        #                                             number_of_fully_processed_movies)

        delay: float
        # If fetch queue is running a bit low on movies to discover details
        # for, then feed it more quickly

        if number_of_movies_in_fetch_queue < 100:
            delay = 1.0
        elif number_of_movies_in_fetch_queue < 200:
            delay = 60.0
        # If fetch queue is sufficiently full, then slow down adding more.
        # Instead, slow down even more based upon
        elif number_of_unprocessed_movies < 1000:
            delay = 120.0
        else:
            # Delay ten minutes per 1000 read
            delay = float(10 * 60 * number_of_unprocessed_movies / 1000)

        if self._calls_to_delay % 10 == 0 and clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug(
                f'Delay: {delay} unprocessed_movies: {number_of_unprocessed_movies} '
                f'pages: {self._total_pages_read} number_of_movies_in_fetch_queue: '
                f'{self.get_number_of_movies()}',
                trace=Trace.TRACE_DISCOVERY)

        self._calls_to_delay += 1
        return delay

    def cache_results(self, query_data: List, movies: List[MovieType]) -> None:
        """

        :param query_data:
        :param movies:
        :return:
        """
        pass

    def needs_restart(self) -> bool:
        """
            A restart is needed when settings that impact our results have
            changed.

        :returns: True if settings have changed requiring restart
                  False if relevant settings have changed or if it should
                  be allowed to die without restart
        """
        clz = type(self)

        clz.logger.enter()

        restart_needed: bool = False
        if Settings.is_include_tmdb_trailers():
            restart_needed = Settings.is_tmdb_loading_settings_changed()

        return restart_needed
