# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import sys
import datetime
import json

from cache.cache import (Cache)
from cache.tmdb_cache_index import (CachedPage, CacheIndex, CacheParameters,
                                    CachedPagesData)
from common.constants import Constants, Movie, RemoteTrailerPreference
from common.disk_utils import DiskUtils
from common.exceptions import AbortException
from common.imports import *
from common.monitor import Monitor
from backend.movie_entry_utils import MovieEntryUtils
from common.logger import (LazyLogger, Trace)
from common.settings import Settings
from common.tmdb_settings import TmdbSettings

from discovery.restart_discovery_exception import RestartDiscoveryException
from backend.genreutils import GenreUtils
from backend.json_utils_basic import JsonUtilsBasic
from common.rating import WorldCertifications
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.tmdb_movie_data import TMDBMovieData

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection Annotator
class DiscoverTmdbMovies(BaseDiscoverMovies):
    """
        TMDB, like iTunes, provides trailers. Query TMDB for trailers
        and manufacture trailer entries for them.
    """

    _singleton_instance = None
    logger: LazyLogger = None

    def __init__(self):
        # type: () -> None
        """

        """
        local_class = DiscoverTmdbMovies
        local_class.logger = module_logger.getChild(local_class.__name__)
        thread_name = 'Disc TMDB'
        kwargs = {}
        kwargs[Movie.SOURCE] = Movie.TMDB_SOURCE

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = TMDBMovieData()
        self._select_by_year_range = None
        self._language = None
        self._country = None
        self._tmdb_api_key = None
        self._include_adult = None
        self._filter_genres = None
        self._selected_keywords = None
        self._selected_genres = None
        self._excluded_genres = None
        self._excluded_keywords = None
        self._remote_trailer_preference = None
        self._vote_comparison = None
        self._vote_value = None
        self._rating_limit_string = None
        self._minimum_year = None
        self._maximum_year = None
        self._rejected_due_to_year = None
        self._total_pages_read = 0

    @classmethod
    def get_instance(cls):
        # type: () -> DiscoverTmdbMovies
        """

        :return:
        """
        local_class = DiscoverTmdbMovies

        return super(DiscoverTmdbMovies, cls).get_instance()

    def discover_basic_information(self):
        # type: () -> None
        """
            Starts the discovery thread

        :return: # type: None
        """
        local_class = DiscoverTmdbMovies

        self.start()
        # self._trailer_fetcher.start_fetchers(self)

        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug(': started')

    def on_settings_changed(self):
        # type: () -> None
        """
            Rediscover trailers if the changed settings impacts this manager.

            By being here, TMDB discover is currently running. Only restart
            if there is a change.
        """
        local_class = DiscoverTmdbMovies

        local_class.logger.enter()

        if Settings.is_tmdb_loading_settings_changed():
            stop_thread = not Settings.get_include_tmdb_trailers()
            self.restart_discovery(stop_thread)

    def run(self):
        # type: () -> None
        """
            Thread run method that is started as a result of running
            discover_basic_information

            This method acts as a wrapper around run_worker. This
            wrapper is able to restart discovery and to handle a few
            details after discovery is complete.

        :return: # type: None
        """
        local_class = DiscoverTmdbMovies
        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    self.wait_until_restart_or_shutdown()
                except RestartDiscoveryException:
                    # Restart discovery
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        local_class.logger.debug_verbose(
                            'Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.get_include_tmdb_trailers():
                        finished = True
                        self.remove_self()

            self.finished_discovery()
            duration = datetime.datetime.now() - start_time
            if local_class.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                local_class.logger.debug_verbose('Time to discover:',
                                                 duration.seconds,
                                                 'seconds',
                                                 trace=Trace.STATS)

        except AbortException:
            return
        except Exception as e:
            local_class.logger.exception('')

    def run_worker(self):
        # type: () -> None
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return: #type: None
        """
        local_class = DiscoverTmdbMovies

        try:
            Monitor.throw_exception_if_abort_requested()
            tmdb_trailer_type = TmdbSettings.get_instance().get_trailer_type()

            #
            # TMDB accepts iso-639-1 but adding an iso-3166- suffix
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
            self._vote_comparison, self._vote_value = Settings.get_tmdb_avg_vote_preference()
            self._rating_limit_string = TmdbSettings.get_instance(
            ).get_rating_limit_string_from_setting()

            # Trailers may be sparse for old movies. Could implement a max# of trailers,
            # but that is done much later in the pipeline

            if Settings.get_tmdb_include_old_movie_trailers():
                max_pages = Settings.get_tmdb_max_download_movies() / 20
            else:
                max_pages = int(110)

            self.discover_movies(
                max_pages, tmdb_trailer_type=tmdb_trailer_type)
        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')

    def discover_movies(self, max_pages, tmdb_trailer_type=''):
        # type: (int, str) -> None
        """
            Calls configure_search_parameters as many times as appropriate to
            discover movies based on the filters specified by the settings.

        :param max_pages: # type int
                The TMDB API returns movies in pages which contains info for
                about 20 movies. The caller specifies which page to get.
        :param tmdb_trailer_type: # type: str
                Specifies the type of movies to get (popular, recent, etc.)
        :return: # type: None (Lower code uses add_to_discovered_trailers).
        """
        local_class = DiscoverTmdbMovies

        try:
            self._rejected_due_to_year = 0
            movies = self.configure_search_parameters(
                tmdb_trailer_type=tmdb_trailer_type
            )
            self.send_cached_movies_to_discovery()

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
                            tmdb_trailer_type,  # type: str
                            "genre", additional_movies=movies)
                        del movies[:]
                        if genre_finished:
                            process_genres = False
                    if process_keywords:
                        keyword_finished = self.second_phase_discovery(
                            max_pages,
                            pages_in_chunk,
                            tmdb_trailer_type,  # type: str
                            "keyword", additional_movies=movies)
                        if keyword_finished:
                            process_keywords = False

            else:
                self.second_phase_discovery(
                    max_pages,
                    max_pages,
                    tmdb_trailer_type,  # type: str
                    "generic",
                    additional_movies=movies)

            finished = False
            while not finished:
                finished = True
                if self._filter_genres:
                    if self._selected_genres != '' or self._excluded_genres != '':
                        tmdb_search_query = "genre"
                        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                        number_of_pages = cached_pages_data.get_number_of_undiscovered_search_pages()
                        if number_of_pages > 0:
                            genre_finished = False
                        self.discover_movies_using_search_pages(
                            tmdb_trailer_type,  # type: str
                            tmdb_search_query=tmdb_search_query  # type: str
                        )
                    if self._selected_keywords != '' or self._excluded_keywords != '':
                        tmdb_search_query = "keyword"
                        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                        number_of_pages = \
                            cached_pages_data.get_number_of_undiscovered_search_pages()
                        if number_of_pages > 0:
                            finished = False
                        self.discover_movies_using_search_pages(
                            tmdb_trailer_type,  # type: str
                            tmdb_search_query=tmdb_search_query  # type: str
                        )
                else:
                    tmdb_search_query = "generic"
                    cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                    number_of_pages = \
                        cached_pages_data.get_number_of_undiscovered_search_pages()
                    if number_of_pages > 0:
                        finished = False
                    self.discover_movies_using_search_pages(
                        tmdb_trailer_type,  # type: str
                        tmdb_search_query=tmdb_search_query  # type: str
                    )

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception:
            local_class.logger.exception('')

    def configure_search_parameters(self,
                                    tmdb_trailer_type=''  # type: str
                                    ):
        # type: (...) -> List[MovieType]
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
        local_class = DiscoverTmdbMovies
        self.throw_exception_on_forced_to_stop()
        movies = []  # type: List[MovieType]
        try:
            self._minimum_year = None
            self._maximum_year = None
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

            cache_changed = CacheParameters.load_cache(current_parameters)
            CacheIndex.load_cache(cache_changed)

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

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')

        return movies

    def filter_movie(self,
                     movie  # type: MovieType
                     ):
        # type: (...) -> bool
        """

        :param movie: # type: MovieType
                Movie to filter
        :return: # type: bool
        """
        local_class = DiscoverTmdbMovies
        result = True
        try:
            if self._minimum_year is not None \
                    and movie[Movie.YEAR] < self._minimum_year:
                result = False
            elif self._maximum_year is not None \
                    and movie[Movie.YEAR] > self._maximum_year:
                result = False
            movie_type = movie.get(Movie.TYPE, '')
            if (movie_type == Constants.VIDEO_TYPE_FEATURETTE
                    and not Settings.get_include_featurettes()):
                result = False
            elif (movie_type == Constants.VIDEO_TYPE_CLIP
                    and not Settings.get_include_clips()):
                result = False
            elif (movie_type == Constants.VIDEO_TYPE_TRAILER
                  and not Settings.get_include_tmdb_trailers()):
                result = False
            # if Settings.get_country_iso_3166_1() != movie[Movie.COUNTRY]:
            #     break
            elif movie.get(Movie.MPAA) is not None:
                country_id = Settings.get_country_iso_3166_1().lower()
                certifications = WorldCertifications.get_certifications(
                    country_id)
                certification = certifications.get_certification(
                    movie.get(Movie.MPAA), movie.get(Movie.ADULT))

                if not certifications.filter(certification):
                    result = False
            # if self._vote_value

            elif not Settings.is_allow_foreign_languages() \
                    and movie[Movie.ORIGINAL_LANGUAGE] != Settings.get_lang_iso_639_1():
                result = False
            """
            if self._filter_genres and not tag_found and not genre_found:
                add_movie = False
                if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                    local_class.logger.debug('Rejected due to GenreUtils or Keyword')

            if vote_comparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                    if vote_average < vote_value:
                        add_movie = False
                        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                            local_class.logger.debug(
                                'Rejected due to vote_average <')
                elif vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                    if vote_average > vote_value:
                        add_movie = False
                        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                            local_class.logger.debug(
                                'Rejected due to vote_average >')

            original_title = tmdb_result['original_title']
            if original_title is not None:
                dict_info[Movie.ORIGINAL_TITLE] = original_title

            adult_movie = tmdb_result['adult'] == 'true'
            if adult_movie and not include_adult:
                add_movie = False
                if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                    local_class.logger.debug('Rejected due to adult')

            dict_info[Movie.ADULT] = adult_movie
            dict_info[Movie.SOURCE] = Movie.TMDB_SOURCE

            # Normalize rating

            mpaa = Rating.get_certification(mpaa_rating=mpaa, adult_rating=None)
            if not Rating.filter(mpaa):
                add_movie = False
                if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                    local_class.logger.debug('Rejected due to rating')
                    # Debug.dump_json(text='get_tmdb_trailer exit:', data=dict_info)

            current_parameters = CacheParameters({
                'excluded_tags': self._excluded_keywords,
                'remote_trailer_preference': self._remote_trailer_preference,
                'vote_comparison': self._vote_comparison,  # type: int
                'vote_value': self._vote_value,  # type: int
                'rating_limit_string': self._rating_limit_string,  # type: str
                'language': self._language,  # type str
                'country': self._country,  # type: str
            })
            """

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')

        return result

    def first_phase_discovery(self,
                              tmdb_trailer_type,  # type: str
                              tmdb_search_query="",  # type: str
                              ) -> Optional[List[MovieType]]:
        """
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
        local_class = DiscoverTmdbMovies

        # Is cache from previous run in a good state?
        cached_pages_data: CachedPagesData = CachedPagesData.pages_data[tmdb_search_query]
        if cached_pages_data.get_total_pages() != 0:
            return None

        page_to_get = DiskUtils.RandomGenerator.randint(1, 50)
        url, data = self.create_request(
            tmdb_trailer_type, page=page_to_get, tmdb_search_query=tmdb_search_query)
        movies = []
        status_code, info_string = JsonUtilsBasic.get_json(
            url, params=data)
        if info_string is None:
            if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                local_class.logger.debug(
                    'Problem communicating with TMDB')
            # TODO: Wait for communication to resume
            # TODO: Notification to user
            return None

        total_results = info_string.get('total_results', 0)
        total_pages = info_string.get('total_pages', 0)

        # TMDB rejects requests requests for page #  > 1000

        if total_pages > 1000:
            total_pages = 1000

        query_by_year = False

        if self._select_by_year_range:
            minimum_year = 1928  # Start of talkies
            if self._minimum_year is not None:
                minimum_year = self._minimum_year
            maximum_year = datetime.datetime.now().year
            if self._maximum_year is not None:
                maximum_year = self._maximum_year
            years_in_range = maximum_year - minimum_year + 1
            if total_pages > (years_in_range * 1.5):
                query_by_year = True

        cached_pages_data.set_total_pages(total_pages)
        cached_pages_data.set_query_by_year(query_by_year)

        # Process this first page.
        #
        # In order to improve the randomness of the first
        # few trailers played, don't add movies to the list of
        # discovered movies until a second page is read.

        movies = self.process_page(info_string, data, tmdb_trailer_type,
                                   url=url)

        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug('Search Query type:', tmdb_search_query,
                                     'TMDB movies:', total_results,
                                     'total_pages:', total_pages,
                                     'query_by_year:', query_by_year)

        return movies

    def second_phase_discovery(self,
                               max_pages: int,
                               pages_in_chunk: int,
                               tmdb_trailer_type: str,
                               tmdb_search_query: str,
                               additional_movies: List[MovieType]
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
        #  TMDB. (The results of a query are chunked into pages, a group
        #  of 20 movies from TMDB.)
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
        # TrailerFetcher thread.
        #
        local_class = DiscoverTmdbMovies
        if additional_movies is None:
            additional_movies = []

        pages_read = 0
        cached_pages_data: CachedPagesData = CachedPagesData.pages_data[tmdb_search_query]
        query_by_year = cached_pages_data.is_query_by_year()

        #  TODO: Verify this
        if cached_pages_data.is_search_pages_configured():
            return False  # Not known if finished reading pages

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

                local_class.logger.debug('Query by year',
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
                local_class.logger.debug('# years to get:',
                                         len(years_to_get),
                                         trace=Trace.TRACE_CACHE_PAGE_DATA)
            #
            # Cache now has years to query

            years_to_get = cached_pages_data.get_years_to_query()
            pages_in_year = {}
            total_pages_for_years = 0
            search_pages = []

            url, data = self.create_request(
                tmdb_trailer_type, page=1,  # dummy page #, updated in get_trailers
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

                        # get_trailers processes any movies found. No additional
                        # work required here.

                        movies_read = self.get_trailers(url=url, data=data,
                                                        tmdb_trailer_type=tmdb_trailer_type,
                                                        pages_to_get=[
                                                            first_page_to_get],
                                                        already_found_movies=additional_movies,
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

            if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                local_class.logger.debug('configuring search pages',
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
                        #
                        #  TODO: could randomize the pages read in a year
                        #
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
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                        local_class.logger.debug('ValueError: 1,',
                                                 total_pages_in_year,
                                                 'scaled_pages:',
                                                 scaled_pages)

        if not query_by_year:
            # This is much easier. Just plan on what pages to read from TMDB.
            # (The pages TMDB returns is based upon the query results. The
            # year only impacts if it is part of the query).
            # Use the information returned from the initial query made in
            # first_phase_discovery to guide how many subsequent pages need to
            # be read.
            #

            search_pages = []
            total_pages = cached_pages_data.get_total_pages()
            for page in list(range(1, min(total_pages, max_pages) + 1)):
                cached_page = CachedPage(None, page)
                search_pages.append(cached_page)

            CacheIndex.add_search_pages(tmdb_search_query,
                                        search_pages, flush=True)

        cached_pages_data.set_search_pages_configured(flush=True)
        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug('SEARCH_PAGES_CONFIGURED',
                                     'len(cached_pages_data):',
                                     cached_pages_data.get_number_of_search_pages(),
                                     trace=Trace.TRACE_DISCOVERY)
        return True  # finished

    def send_cached_movies_to_discovery(self) -> None:
        """

        :return:
        """
        local_class = DiscoverTmdbMovies
        try:
            # Send any cached TMDB trailers to the discovered list first,
            # since they require least processing.

            if local_class.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                local_class.logger.debug_verbose(
                    "Sending cached TMDB trailers to discovered list")

            tmdb_trailer_ids: Set[int] = \
                CacheIndex.get_found_tmdb_ids_with_trailer()
            movies = []
            for tmdb_id in tmdb_trailer_ids:
                cached_movie = Cache.read_tmdb_cache_json(tmdb_id, Movie.TMDB_SOURCE,
                                                          error_msg='TMDB trailer '
                                                                    'not found')
                if cached_movie is not None:
                    year = cached_movie['release_date'][:-6]
                    year = int(year)
                    movie_entry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                   Movie.SOURCE: Movie.TMDB_SOURCE,
                                   Movie.TITLE: cached_movie[Movie.TITLE],
                                   Movie.YEAR: year,
                                   Movie.ORIGINAL_LANGUAGE:
                                       cached_movie[Movie.ORIGINAL_LANGUAGE]}
                    MovieEntryUtils.set_tmdb_id(movie_entry, tmdb_id)
                    if self.filter_movie(movie_entry):
                        movies.append(movie_entry)

            # Don't add found trailers to unprocessed_movies

            self.add_to_discovered_trailers(movies)
            #
            # Give fetcher time to load ready_to_play list. The next add
            # will likely shuffle and mix these up with some that will take
            # longer to process.
            #
            if len(movies) > 0:
                Monitor.throw_exception_if_abort_requested(timeout=5.0)
        except Exception as e:
            local_class.logger.exception('')

        try:
            # Send any unprocessed TMDB trailers to the discovered list
            if local_class.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                local_class.logger.debug_verbose(
                    "Sending unprocessed movies to discovered list")

            discovery_complete_movies: List[MovieType] = []
            discovery_needed_movies: List[MovieType] = []
            unprocessed_movies = CacheIndex.get_unprocessed_movies()
            for movie in unprocessed_movies.values():
                if local_class.logger.isEnabledFor(LazyLogger.DISABLED):
                    if Movie.MPAA not in movie or movie[Movie.MPAA] == '':
                        cert = movie.get(Movie.MPAA, 'none')
                        local_class.logger.debug_extra_verbose('No certification. Title:',
                                                               movie[Movie.TITLE],
                                                               'year:',
                                                               movie.get(
                                                                   Movie.YEAR),
                                                               'certification:', cert,
                                                               'trailer:',
                                                               movie.get(
                                                                   Movie.TRAILER),
                                                               trace=Trace.TRACE_DISCOVERY)
                        movie[Movie.MPAA] = ''

                discovery_state = movie.get(Movie.DISCOVERY_STATE,
                                            Movie.NOT_FULLY_DISCOVERED)
                if (discovery_state < Movie.DISCOVERY_COMPLETE
                        and self.filter_movie(movie)):
                    discovery_needed_movies.append(movie)
                if (discovery_state >= Movie.DISCOVERY_COMPLETE
                        and self.filter_movie(movie)):
                    discovery_complete_movies.append(movie)
                    tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
                    CacheIndex.remove_unprocessed_movies(tmdb_id)

            # Add the fully discovered movies first, this should be rare,
            # but might feed a few that can be displayed soon first.
            # There will likely be a shuffle on each call, so they will be
            # blended together anyway.

            self.add_to_discovered_trailers(discovery_complete_movies)
            if len(discovery_complete_movies) > 0:
                Monitor.throw_exception_if_abort_requested(timeout=5.0)
            self.add_to_discovered_trailers(discovery_needed_movies)

        except Exception as e:
            local_class.logger.exception('')

    def discover_movies_using_search_pages(self,
                                           tmdb_trailer_type: str,
                                           tmdb_search_query: str = "",
                                           pages_in_chunk: int = 5) -> None:
        """
        At this point the decision about what pages and years to search
        have been made and saved to the cache. Now, execute the plan!

        :param tmdb_trailer_type:
        :param tmdb_trailer_type:
        :param tmdb_search_query:
        :param pages_in_chunk:
        :return:
        """
        local_class = DiscoverTmdbMovies
        try:
            cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
            page_to_get = 1  # Will be overridden
            url, data = self.create_request(
                tmdb_trailer_type, page=page_to_get, tmdb_search_query=tmdb_search_query)
            query_by_year = cached_pages_data.is_query_by_year()

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

                if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                    local_class.logger.debug('length of year/page pairs:',
                                             len(search_pages),
                                             trace=Trace.TRACE_CACHE_PAGE_DATA)

                for cached_page in search_pages:
                    self.throw_exception_on_forced_to_stop()
                    year = cached_page.get_year()
                    page = cached_page.get_page_number()
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                        local_class.logger.debug('Getting trailers for year:',
                                                 year, 'page:', page,
                                                 trace=Trace.TRACE_CACHE_PAGE_DATA)

                    self.get_trailers(url=url, data=data,
                                      tmdb_trailer_type=tmdb_trailer_type,
                                      pages_to_get=[page],
                                      already_found_movies=[], year=year,
                                      tmdb_search_query=tmdb_search_query)

                    cached_pages_data.mark_page_as_discovered(cached_page)
                    if self.is_exceeded_limit_of_trailers():
                        break

            if not query_by_year:
                # TODO: could be done much cleaner. Redundant
                # cached_pages_data, etc.

                search_pages = CacheIndex.get_search_pages(tmdb_search_query)
                pages_to_get = []
                for cached_page in search_pages:
                    pages_to_get.append(cached_page.get_page_number())

                DiskUtils.RandomGenerator.shuffle(pages_to_get)
                self.get_trailers(url=url, data=data,
                                  tmdb_trailer_type=tmdb_trailer_type,
                                  pages_to_get=pages_to_get,
                                  tmdb_search_query=tmdb_search_query)

                for cached_page in search_pages:
                    cached_pages_data.mark_page_as_discovered(cached_page)
                    if self.is_exceeded_limit_of_trailers():
                        break

            # Make sure cache is flushed
            CacheIndex.save_unprocessed_movie_cache(flush=True)

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
            #        data['query'] = movie[Movie.TITLE]
            #        data['year'] = movie['year']
            #        url = 'https://api.themoviedb.org/3/search/movie'
            #        statusCode, infostring = DiskUtils.get_json(url, params=data)
            #
            #        for m in infostring['results']:
            #            trailerId = m['id']
            #            trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
            #                            Movie.TMDB_ID: trailerId,
            #                            Movie.SOURCE: Movie.TMDB_SOURCE,
            #                            Movie.TITLE: movie[Movie.TITLE]}
            #            self.add_to_discovered_trailers(trailerEntry)
            #
            #            local_class.logger.debug(' DVD title: ' +
            #                              trailerEntry[Movie.TITLE])
            #            break
            #
            # ========================
            #
            #   Everything else (popular, top_rated, upcoming, now playing)
            #
            # ========================

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())

        except Exception as e:
            local_class.logger.exception('')
        return

    def is_exceeded_limit_of_trailers(self):
        # type: () -> bool
        """
            Checks to see if the maximum number of trailers has been
            discovered.

        :return: # type: bool

        """
        # TODO: trailers vs movies
        local_class = DiscoverTmdbMovies
        if self.get_number_of_movies() > Settings.get_max_tmdb_trailers():
            return True
        return False

    def create_request(self,
                       tmdb_trailer_type,  # type: str
                       page,  # type: int
                       tmdb_search_query=''  # type: str
                       ):
        # type: (...) -> (str, Dict[str, Any])
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
        local_class = DiscoverTmdbMovies
        data = {}
        url = ''

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

            if self._vote_comparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if self._vote_comparison != \
                        RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
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

            # TMDB API does not have a means to find different language
            # versions of movies (dubbed or subtitles). Can only use
            # original language version. Spoken Language is used to specify
            # different languages spoken in the original movie, not to indicate
            # translations.

            data['with_original_language'] = Settings.get_lang_iso_639_1()

            if tmdb_trailer_type == 'all':
                url = 'http://api.themoviedb.org/3/discover/movie'
            else:
                url = 'https://api.themoviedb.org/3/movie/' + tmdb_trailer_type

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

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')

        finally:
            return url, data

    def get_trailers(self,
                     url: Optional[str] = None,
                     data: Optional[Dict[str, Any]] = None,
                     tmdb_trailer_type: Optional[str] = None,
                     pages_to_get: List[int] = None,
                     year: Optional[int] = None,
                     already_found_movies: Optional[List[MovieType]] = None,
                     year_map=None,
                     # type:  Dict[str, DiscoverTmdbMovies.AggregateQueryResults]
                     tmdb_search_query: str = ""
                     ) -> int:
        """
            Discovers movies and adds them to the discovered trailers pool
            via add_to_discovered_trailers.

        :param url:
        :param data:
        :param tmdb_trailer_type:
        :param pages_to_get:get_trailers
        :param year:
        :param already_found_movies:
        :param year_map:
        :param tmdb_search_query:
        :return:
        """
        local_class = DiscoverTmdbMovies
        if already_found_movies is None:
            already_found_movies = []
        number_of_movies_processed = 0
        try:
            for page in pages_to_get:
                if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                    local_class.logger.debug('year:', year, 'page:', page)

                # Pages are read faster at the beginning, then progressively
                # slower.

                delay = self.get_delay()
                self.throw_exception_on_forced_to_stop(delay=delay)

                data['page'] = page
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

                status_code, info_string = JsonUtilsBasic.get_json(
                    url, params=data)

                if info_string is None:
                    continue

                # Optional, record the number of matching movies and pages
                # for this query. Can be used to decide which pages to
                # query later.

                if year is not None and year_map is not None:
                    total_results = info_string['total_results']
                    total_pages = info_string['total_pages']
                    if str(year) not in year_map:
                        aggregate_query_results = DiscoverTmdbMovies.AggregateQueryResults(
                            total_pages=total_pages,
                            viewed_page=page)

                        year_map[str(year)] = aggregate_query_results

                movies = self.process_page(
                    info_string, data, tmdb_trailer_type, url=url)
                movies.extend(already_found_movies)
                number_of_movies_processed += len(movies)
                DiskUtils.RandomGenerator.shuffle(movies)
                CacheIndex.add_unprocessed_movies(movies)
                self.add_to_discovered_trailers(movies)

                # From now on, only add one page's worth of movies to discovered
                # trailers.

                already_found_movies = []
                if self.is_exceeded_limit_of_trailers():
                    break

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')

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
            local_class = DiscoverTmdbMovies
            local_class.logger = module_logger.getChild(
                self.__class__.__name__)
            self._total_pages = total_pages
            self._viewed_page = viewed_page

        def get_total_pages(self):
            # type: () -> Union[int, None]
            """

            :return:
            """
            local_class = DiscoverTmdbMovies
            return self._total_pages

        def get_viewed_page(self):
            # type: () -> Union[int, None]
            """

            :return:
            """
            local_class = DiscoverTmdbMovies
            return self._viewed_page

    def process_page(self,
                     info_string,  # type: MovieType
                     query_data,  # type: List
                     tmdb_trailer_type,  # type: str
                     url=''  # type: str
                     ):
        # type: (...) -> List[MovieType]
        """
            Parses a page's worth of movie results from TMDB into Kodi
            style MovieType dictionary entries.

        :param info_string:
        :param query_data
        :param tmdb_trailer_type:
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
                               "popularity": 303.019, "
                               "original_title": "Aquaman",
                               "backdrop_path": "/5A2bMlLfJrAfX9bqAibOL2gCruF.jpg",
                               "vote_count": 3134,
                               "video": false,
                               "adult": false,
                               "vote_average": 6.9,
                               "genre_ids": [28, 14, 878, 12],
                               "id": 297802,
                                "original_language": "en"},
        '''
        local_class = DiscoverTmdbMovies
        movies = []
        try:
            page = info_string.get('page', 1)
            total_pages = info_string.get('total_pages', -1)
            movie_entries = info_string.get('results', None)
            if total_pages == -1:
                local_class.logger.error('total_pages missing',
                                         json.dumps(info_string, indent=3, sort_keys=True))

            if movie_entries is None:
                if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                    local_class.logger.debug('results not found. URL:',
                                             url, 'returned value:',
                                             json.dumps(info_string))
            else:
                # Shuffling is done later, but this helps keep the first few
                # (about 3) displayed being the same thing all of the time

                DiskUtils.RandomGenerator.shuffle(movie_entries)
                for movie_entry in movie_entries:
                    self.throw_exception_on_forced_to_stop()

                    trailer_id = movie_entry['id']
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        tmp_title = movie_entry[Movie.TITLE]
                        local_class.logger.debug_verbose(
                            'Processing:', tmp_title)
                    try:
                        year = movie_entry['release_date'][:-6]
                        year = int(year)
                    except Exception:
                        year = datetime.datetime.now().year

                    if year != 0 and self._select_by_year_range:
                        if self._minimum_year is not None and year < self._minimum_year:
                            if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                                local_class.logger.debug(
                                    'Omitting movie_entry older than minimum Year:',
                                    self._minimum_year, 'movie_entry:',
                                    movie_entry[Movie.TITLE],
                                    'release:', year)
                            self._rejected_due_to_year += 1
                            continue
                        if self._maximum_year is not None and year > self._maximum_year:
                            if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                                local_class.logger.debug(
                                    'Omitting movie_entry newer than maximum Year: ',
                                    self._maximum_year, 'movie_entry:',
                                    movie_entry[Movie.TITLE],
                                    'release:', year)
                            self._rejected_due_to_year += 1
                            continue

                    original_language = movie_entry[Movie.ORIGINAL_LANGUAGE]
                    trailer_entry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                     Movie.SOURCE: Movie.TMDB_SOURCE,
                                     Movie.TITLE: movie_entry[Movie.TITLE],
                                     Movie.YEAR: year,
                                     Movie.ORIGINAL_LANGUAGE: original_language,
                                     Movie.TMDB_PAGE: page,
                                     Movie.TMDB_TOTAL_PAGES: total_pages}
                    MovieEntryUtils.set_tmdb_id(trailer_entry, trailer_id)
                    movies.append(trailer_entry)

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')
        finally:

            return movies

    def get_delay(self):
        # type: () -> int
        """
        Gets the delay (in seconds) to wait before querying the database.
        Delay is based upon how many read and how many unprocessed.

        This is done to prevent overloading Kodi as well as TMDB.

        :return:
        """
        local_class = DiscoverTmdbMovies
        self._total_pages_read += 1
        # If there is a backlog of movies discovered here, then slow down
        # discovering more. Note that depending upon the search, that most
        # TMDB movies are missing trailers.

        # No delay for first 100 movies
        number_of_unprocessed_movies = len(CacheIndex.get_unprocessed_movies())
        if self.get_number_of_movies() < 100:
            delay = 0
        elif self.get_number_of_movies() < 200:
            delay = 60
        elif number_of_unprocessed_movies < 1000:
            delay = 120
        elif number_of_unprocessed_movies > 1000:
            # Delay ten minutes per /100 read
            delay = 10 * 60 * number_of_unprocessed_movies / 1000
        else:
            delay = 5

        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug(
                f'Delay: {delay} unprocessed_movies: {number_of_unprocessed_movies} '
                f'pages: {self._total_pages_read} number_of_movies: {self.get_number_of_movies()}',
                trace=Trace.TRACE_DISCOVERY)
        return int(delay)

    def cache_results(self, query_data, movies):
        # type: (List, List[MovieType]) -> None
        """

        :param query_data:
        :param movies:
        :return:
        """
        pass
