# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import datetime
import json
import six

from cache.cache import (Cache)
from cache.cache_index import (CachedPage, CacheIndex, CacheParameters,
                               CachedPagesData)
from common.constants import Constants, Movie, RemoteTrailerPreference
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, ShutdownException
from common.monitor import Monitor
from backend.movie_entry_utils import MovieEntryUtils
from common.logger import (Logger, LazyLogger, Trace)
from common.settings import Settings
from common.tmdb_settings import TmdbSettings

from discovery.restart_discovery_exception import RestartDiscoveryException
from backend.genreutils import GenreUtils
from backend.json_utils_basic import JsonUtilsBasic
from backend.rating import Rating
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.tmdb_movie_data import TMDBMovieData

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.discover_tmdb_movies')
else:
    module_logger = LazyLogger.get_addon_module_logger()


# noinspection Annotator
class DiscoverTFHMovies(BaseDiscoverMovies):
    """
        TMDB, like iTunes, provides trailers. Query TMDB for trailers
        and manufacture trailer entries for them.
    """

    _singleton_instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        thread_name = type(self).__name__
        kwargs = {}
        kwargs[Movie.SOURCE] = Movie.TMDB_SOURCE

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None, verbose=None)
        self._movie_data = TMDBMovieData()
        self._select_by_year_range = None
        self._language = None
        self._country = None
        self._tmdb_api_key = None
        self._include_adult = None
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
        # type: () -> DiscoverTFHMovies
        """

        :return:
        """
        return super(DiscoverTFHMovies, cls).get_instance()

    def discover_basic_information(self):
        # type: () -> None
        """
            Starts the discovery thread

        :return: # type: None
        """
        self.start()
        # self._trailer_fetcher.start_fetchers(self)

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(': started')

    def on_settings_changed(self):
        # type: () -> None
        """
            Rediscover trailers if the changed settings impacts this manager.

            By being here, TMDB discover is currently running. Only restart
            if there is a change.
        """
        self._logger.enter()

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
        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    self.wait_until_restart_or_shutdown()
                except (RestartDiscoveryException):
                    # Restart discovery
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.get_include_tmdb_trailers():
                        finished = True
                        self.remove_self()

            self.finished_discovery()
            duration = datetime.datetime.now() - start_time
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Time to discover:', duration.seconds, ' seconds',
                                   trace=Trace.STATS)

        except (AbortException, ShutdownException):
            return
        except (Exception) as e:
            self._logger.exception('')

    def run_worker(self):
        # type: () -> None
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return: #type: None
        """
        try:
            Monitor.get_instance().throw_exception_if_shutdown_requested()
            tmdb_trailer_type = TmdbSettings.get_instance().get_trailer_type()

            #
            # TMDB accepts iso-639-1 but adding an iso-3166- suffix
            # would be better (en_US)
            #
            self._language = Settings.getLang_iso_639_1()
            self._country = Settings.getLang_iso_3166_1()
            self._tmdb_api_key = Settings.get_tmdb_api_key()
            self._include_adult = Rating.check_rating(Rating.RATING_NC_17)

            self._selected_keywords = ''
            self._selected_genres = ''
            self._excluded_genres = ''
            self._excluded_keywords = ''
            if Settings.get_filter_genres():
                self._selected_genres = GenreUtils.get_instance(
                ).get_external_genre_ids_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=False, or_operator=True)
                self._selected_keywords = GenreUtils.get_instance(
                ).get_external_keywords_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=False, or_operator=True)
                self._excluded_genres = GenreUtils.get_instance(
                ).get_external_genre_ids_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=True, or_operator=True)
                self._excluded_keywords = GenreUtils.get_instance(
                ).get_external_keywords_as_query(
                    GenreUtils.TMDB_DATABASE, exclude=True, or_operator=True)
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
        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    def discover_movies(self, max_pages, tmdb_trailer_type=''):
        # type: (int, TextType) -> None
        """
            Calls configure_search_parameters as many times as appropriate to
            discover movies based on the filters specified by the settings.

        :param max_pages: # type int
                The TMDB API returns movies in pages which contains info for
                about 20 movies. The caller specifies which page to get.
        :param tmdb_trailer_type: # type: TextType
                Specifies the type of movies to get (popular, recent, etc.)
        :return: # type: None (Lower code uses add_to_discovered_trailers).
        """

        """
        youtube-dl --ignore-errors --skip-download --get-id https://www.youtube.com/user/trailersfromhell/videos 
        gives ids. Extract movies via id by:
        
        time youtube-dl --ignore-errors --skip-download https://www.youtube.com/watch?v=YbqC0b_jfxQ

        or-
        Get JSON for TFH entire trailers in playlist:
        youtube-dl --ignore-errors --skip-download --playlist-random  
            --print-json https://www.youtube.com/user/trailersfromhell/videos >>downloads2
        Each line is a separate JSON "file" for a single trailer.
        
        From JSON youtube download for a single trailer:
          "license": null,
  "title": "Allan Arkush on SMALL CHANGE",
  "thumbnail": "https://i.ytimg.com/vi/YbqC0b_jfxQ/maxresdefault.jpg",
  "description": "François Truffaut followed up the tragic The Story of Adele H 
  with this sunny comedy about childhood innocence and resiliency (to show just 
  how resilient, one baby falls out a window and merely bounces harmlessly off
   the bushes below). Truffaut worked with a stripped down script to allow for 
   more improvisation from his young cast. The rosy cinematography was by 
   Pierre-William Glenn (Day for Night).\n\nAs always, you can find more
    commentary, more reviews, more podcasts, and more deep-dives into the films
     you don't know you love yet over on the Trailers From Hell 
     mothership:\n\nhttp://www.trailersfromhell.com\n\n
     What's that podcast, you ask? Why, it's THE MOVIES THAT MADE ME, where 
     you can join Oscar-nominated screenwriter Josh Olson and TFH Fearless 
     Leader Joe Dante in conversation with filmmakers, comedians, and 
     all-around interesting people about the movies that made them who they are. 
     Check it out now, and please subscribe wherever podcasts can be found.
     \n\nApple Podcasts:
      https://podcasts.apple.com/us/podcast/the-movies-that-made-me/id1412094313\n
      Spotify: http://spotify.trailersfromhell.com\n
      Libsyn: http://podcast.trailersfromhell.com\n
      Google Play: http://googleplay.trailersfromhell.com\nRSS: http://goo.gl/3faeG7",
  """

        try:
            self._rejected_due_to_year = 0
            movies = self.configure_search_parameters(
                tmdb_trailer_type=tmdb_trailer_type
            )
            self.send_cached_movies_to_discovery()

            if Settings.get_filter_genres():
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
                        genre_finished = self.create_search_pages(
                            max_pages,
                            pages_in_chunk,
                            tmdb_trailer_type,  # type: TextType
                            "genre", additional_movies=movies)
                        del movies[:]
                        if genre_finished:
                            process_genres = False
                    if process_keywords:
                        keyword_finished = self.create_search_pages(
                            max_pages,
                            pages_in_chunk,
                            tmdb_trailer_type,  # type: TextType
                            "keyword", additional_movies=movies)
                        if keyword_finished:
                            process_keywords = False

            else:
                self.create_search_pages(
                    max_pages,
                    max_pages,
                    tmdb_trailer_type,  # type: TextType
                    "generic",
                    additional_movies=movies)

            finished = False
            while not finished:
                finished = True
                if Settings.get_filter_genres():
                    if self._selected_genres != '' or self._excluded_genres != '':
                        tmdb_search_query = "genre"
                        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                        number_of_pages = cached_pages_data.get_number_of_undiscovered_search_pages()
                        if number_of_pages > 0:
                            genre_finished = False
                        self.discover_movies_using_search_pages(
                            tmdb_trailer_type,  # type: TextType
                            tmdb_search_query=tmdb_search_query  # type: TextType
                        )
                    if self._selected_keywords != '' or self._excluded_keywords != '':
                        tmdb_search_query = "keyword"
                        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                        number_of_pages = \
                            cached_pages_data.get_number_of_undiscovered_search_pages()
                        if number_of_pages > 0:
                            finished = False
                        self.discover_movies_using_search_pages(
                            tmdb_trailer_type,  # type: TextType
                            tmdb_search_query=tmdb_search_query  # type: TextType
                        )
                else:
                    tmdb_search_query = "generic"
                    cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
                    number_of_pages = \
                        cached_pages_data.get_number_of_undiscovered_search_pages()
                    if number_of_pages > 0:
                        finished = False
                    self.discover_movies_using_search_pages(
                        tmdb_trailer_type,  # type: TextType
                        tmdb_search_query=tmdb_search_query  # type: TextType
                    )

        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    def configure_search_parameters(self,
                                    tmdb_trailer_type=''  # type: TextType
                                    ):
        # type: (...) -> List[MovieType]
        """
            Performs the critical task of translating complex
            search parameters into multiple groups of API calls
            to carry out the search.

            The most complex queries specify a range of years as well
            as other search criteria.

        :param tmdb_trailer_type: # type: TextType
                Specifies a trailer-type search parameter
        :return: # type: List[MovieType]
        """

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
                # type: List[TextType]
                'included_genres': self._selected_genres,
                # type: List[TextType]
                'excluded_genres': self._excluded_genres,
                # type: List[TextType]
                'included_tags': self._selected_keywords,
                # type: List[TextType]
                'excluded_tags': self._excluded_keywords,
                'minimum_year': self._minimum_year,  # type: int
                'maximum_year': self._maximum_year,  # type: int
                'remote_trailer_preference': self._remote_trailer_preference,
                'vote_comparison': self._vote_comparison,  # type: int
                'vote_value': self._vote_value,  # type: int
                'rating_limit_string': self._rating_limit_string,  # type: TextType
                'language': self._language,  # type TextType
                'country': self._country,  # type: TextType
                'cache_state': CacheIndex.UNINITIALIZED_STATE  # type: TextType
            })

            cache_changed = CacheParameters.load_cache(current_parameters)
            CacheIndex.load_cache(cache_changed)

            if Settings.get_filter_genres():
                if self._selected_genres != '' or self._excluded_genres != '':
                    # If performing genre filter, then need separate query for genres
                    # and keywords and combine them. This way the results are the union.
                    # Otherwise they are  the intersection.

                    genre_movies = self.configure_year_query(tmdb_trailer_type,
                                                             tmdb_search_query="genre")
                    movies.extend(genre_movies)
                    del genre_movies
                if self._selected_keywords != '' or self._excluded_keywords != '':
                    keyword_movies = self.configure_year_query(tmdb_trailer_type,
                                                               tmdb_search_query="keyword")
                    movies.extend(keyword_movies)
                    del keyword_movies
            else:
                # Need to determine if we will search by year or all years. The
                # total number of matching movies will govern this.
                generic_movies = self.configure_year_query(tmdb_trailer_type,
                                                           tmdb_search_query="generic")
                movies.extend(generic_movies)
                del generic_movies

        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

        return movies

    def configure_year_query(self,
                             tmdb_trailer_type,  # type: TextType
                             tmdb_search_query="",  # type: TextType
                             ):

        # type: (...) -> List[MovieType]
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

        # Is cache from previous run in a good state?

        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
        if cached_pages_data.get_total_pages() != 0:
            return None

        page_to_get = DiskUtils.RandomGenerator.randint(1, 50)
        url, data = self.create_request(
            tmdb_trailer_type, page=page_to_get, tmdb_search_query=tmdb_search_query)
        movies = []
        status_code, info_string = JsonUtilsBasic.get_json(
            url, params=data)
        if info_string is None:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(
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

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Search Query type:', tmdb_search_query,
                               'TMDB movies:', total_results,
                               'total_pages:', total_pages,
                               'query_by_year:', query_by_year)

        return movies

    def create_search_pages(self,
                            max_pages,  # type: int
                            pages_in_chunk,  # type: int
                            tmdb_trailer_type,  # type: TextType
                            tmdb_search_query,  # type: TextType
                            additional_movies=[]  # List[MovieType]
                            ):
        # type: (...) -> bool
        """
        :param max_pages:
        :param pages_in_chunk:
        :param tmdb_trailer_type:
        :param tmdb_search_query:
        :param additional_movies:
        :return:
        """
        pages_read = 0
        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
        if not cached_pages_data.is_search_pages_configured():
            query_by_year = cached_pages_data.is_query_by_year()
            if query_by_year:

                ###########################################################
                #
                #   Determine whether to query by years
                #
                # Based on the info returned from first page, determine what
                # other pages to read and if a year range is specified, then
                # whether to read by year or not.
                #
                # The issue is that the TMDB API will only accept one date. Therefore, if
                # 10 years must be searched, then a minimum of 10 queries must be made
                # even if most of those years have hardly any results. Use the heuristic
                # that if the generic query that does not specify the year returns a
                # total number of result pages that is less than 1.5 times the number of
                # years in the range, then use the generic, non-year specific query.
                # Otherwise, specify the year.

                page_to_get = 1  # Overridden
                url, data = self.create_request(
                    tmdb_trailer_type, page=page_to_get,
                    tmdb_search_query=tmdb_search_query)

                ###########################################################
                #
                #    SEARCH BY YEAR
                #
                # Need to find out how many pages of movies are available
                # per year. Do this by querying a random page for each year.
                #

                years_to_get = cached_pages_data.get_years_to_get()
                if years_to_get is None:
                    years_to_get = list(
                        range(self._minimum_year, self._maximum_year))
                    DiskUtils.RandomGenerator.shuffle(years_to_get)
                    cached_pages_data.set_years_to_get(years_to_get)

                # No matter what page you request for, TMDB will give how many
                # pages are available, so even if you overshoot all is not lost.
                # For the first request for a year, pick a random page from a
                # relatively small range, say, 50 pages.
                #
                # After this point, get a random page from a random year
                # at a time until max_pages read.

                year_map = {}
                total_pages_for_years = 0
                search_pages = []

                for year in years_to_get:
                    self.throw_exception_on_forced_to_stop()

                    total_pages_in_year = cached_pages_data.get_total_pages_for_year(
                        year)

                    # Skip over previously discovered pages. Movie info is
                    # cached and already bulk added.

                    if total_pages_in_year is not None:
                        first_page_to_get = 0  # Dummy
                        if str(year) not in year_map:
                            aggregate_query_results = \
                                DiscoverTFHMovies.AggregateQueryResults(
                                    total_pages=total_pages_in_year)

                            year_map[str(year)] = aggregate_query_results
                    else:
                        first_page_to_get = DiskUtils.RandomGenerator.randint(
                            1, 50)

                        # get_trailers processes any movies found. No additional
                        # work required here.

                        self.get_trailers(url=url, data=data,
                                          tmdb_trailer_type=tmdb_trailer_type,
                                          pages_to_get=[first_page_to_get],
                                          already_found_movies=additional_movies,
                                          year=year, year_map=year_map,
                                          tmdb_search_query=tmdb_search_query)
                        del additional_movies[:]

                        aggregate_query_results = year_map[str(year)]
                        total_pages_in_year = aggregate_query_results.get_total_pages()
                        cached_page = CachedPage(year, first_page_to_get,
                                                 total_pages_for_year=total_pages_in_year)
                        cached_page.processed = True
                        search_pages.append(cached_page)
                        CacheIndex.add_search_pages(tmdb_search_query,
                                                    search_pages)
                        del search_pages[:]
                        pages_read += 1
                        if pages_read >= pages_in_chunk:
                            cached_pages_data.save_search_pages(flush=True)
                            return False  # Not finished

                    total_pages_for_years += int(total_pages_in_year)

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('configuring search pages',
                                       'query_by_year: True',
                                       'total_pages_for_years:',
                                       total_pages_for_years)

                # Second pass is to build lists of unique, random page
                # numbers to drive queries.
                #
                # There are probably more movies matching the query than
                # we want to process (max_pages).

                page_scale_factor = 1
                if max_pages < total_pages_for_years:
                    total_pages = cached_pages_data.get_total_pages()
                    page_scale_factor = total_pages / max_pages

                pages_for_year = []
                for year in year_map:
                    aggregate_query_results = year_map[year]
                    total_pages_in_year = aggregate_query_results.get_total_pages()
                    viewed_page = aggregate_query_results.get_viewed_page()
                    scaled_pages = int(
                        (total_pages_in_year / page_scale_factor) + 0.5)
                    try:
                        pages_for_year = DiskUtils.RandomGenerator.sample(
                            xrange(1, total_pages_in_year + 1), scaled_pages)
                        if viewed_page is not None and viewed_page in pages_for_year:
                            pages_for_year.remove(viewed_page)
                    except (KeyError):
                        pages_for_year = []
                    except (ValueError):
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('ValueError: 1,',
                                               total_pages_in_year,
                                               'scaled_pages:',
                                               scaled_pages)

                    # Generate year-page tuple pairs and add to giant list
                    # of all pages that are to be read for each year

                    for page in pages_for_year:
                        cached_page = CachedPage(year, page)
                        search_pages.append(cached_page)

                    CacheIndex.add_search_pages(tmdb_search_query,
                                                search_pages, flush=True)

            if not query_by_year:
                search_pages = []
                total_pages = cached_pages_data.get_total_pages()
                for page in list(range(1, min(total_pages, max_pages) + 1)):
                    cached_page = CachedPage(None, page)
                    search_pages.append(cached_page)

                CacheIndex.add_search_pages(tmdb_search_query,
                                            search_pages, flush=True)

            cached_pages_data.set_search_pages_configured(flush=True)
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('SEARCH_PAGES_CONFIGURED',
                                   'len(cached_pages_data):',
                                   cached_pages_data.get_number_of_search_pages())
            return True  # finished

    def send_cached_movies_to_discovery(self):
        # type: () -> None
        """

        :return:
        """

        try:
            # Send any unprocessed TMDB trailers to the discovered list

            unprocessed_movies = CacheIndex.get_unprocessed_movies()
            for movie in unprocessed_movies.values():
                self.add_to_discovered_trailers(movie)
        except (Exception) as e:
            self._logger.exception('')

        try:
            # Send any cached TMDB trailers to the discovered list
            tmdb_trailer_ids = CacheIndex.get_found_tmdb_trailer_ids()
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
                    movies.append(movie_entry)
            CacheIndex.add_unprocessed_movies(movies)
            self.add_to_discovered_trailers(movies)
        except (Exception) as e:
            self._logger.exception('')

    def discover_movies_using_search_pages(self,
                                           tmdb_trailer_type,  # type: TextType
                                           tmdb_search_query="",  # type: TextType
                                           pages_in_chunk=5  # type: int
                                           ):
        # type: (...) -> None
        """
        At this point the decision about what pages and years to search
        have been made and saved to the cache. Now, execute the plan!

        :param tmdb_trailer_type:
        :param tmdb_trailer_type:
        :param tmdb_search_query:
        :param pages_in_chunk:
        :return:
        """

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

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('length of year/page pairs:',
                                       len(search_pages))

                for cached_page in search_pages:
                    self.throw_exception_on_forced_to_stop()
                    year = cached_page.get_year()
                    page = cached_page.get_page_number()
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Getting trailers for year:',
                                           year, 'page:', page
                                           )
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
            #            self._logger.debug(' DVD title: ' +
            #                              trailerEntry[Movie.TITLE])
            #            break
            #
            # ========================
            #
            #   Everything else (popular, top_rated, upcoming, now playing)
            #
            # ========================

        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())

        except (Exception) as e:
            self._logger.exception('')
        return

    def is_exceeded_limit_of_trailers(self):
        # type: () -> bool
        """
            Checks to see if the maximum number of trailers has been
            discovered.

        :return: # type: bool

        """
        # TODO: trailers vs movies

        if self.get_number_of_movies() > Settings.get_max_tmdb_trailers():
            return True
        return False

    def create_request(self,
                       tmdb_trailer_type,  # type: TextType
                       page,  # type: int
                       tmdb_search_query=''  # type: TextType
                       ):
        # type: (...) -> (TextType, Dict[TextType, Any])
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

            # Country codes are: iso_3166_1
            #
            # TODO: Limitation
            #
            # Not sure what to do here. Kodi does not supply country codes
            # To implement, would also need to know certification rules for
            # different countries, codes, history of codes... groan
            #
            data['certification_country'] = 'us'
            data['certification.lte'] = self._rating_limit_string

            # TMDB API does not have a means to find different language
            # versions of movies (dubbed or subtitles). Can only use
            # original language version. Spoken Language is used to specify
            # different languages spoken in the original movie, not to indicate
            # translations.

            data['with_original_language'] = Settings.getLang_iso_639_1()

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

        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

        finally:
            return url, data

    def get_trailers(self,
                     url=None,  # type: Optional[TextType]
                     data=None,  # type: Optional[Dict[TextType, Any]]
                     tmdb_trailer_type=None,  # type: Optional[TextType]
                     pages_to_get=None,  # type: List[int]
                     year=None,  # type: Optional[int]
                     # type: Optional[List[MovieType]]
                     already_found_movies=None,
                     # type: Optional[Dict[TextType, MovieType]]
                     year_map=None,
                     tmdb_search_query=""
                     ):
        # type: (...) ->None
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
        if already_found_movies is None:
            already_found_movies = []
        try:
            for page in pages_to_get:
                # After first 100 movies read we have enough to keep
                # trailer fetcher busy and random enough hunting for
                # trailers. Keep reading a page (20 movies) every
                # minute.

                if self.get_number_of_movies() > 100:
                    self.throw_exception_on_forced_to_stop(delay=60)

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('year:', year, 'page:', page)
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

                # Optional, record the number of matching movies and pages
                # for this query. Can be used to decide which pages to
                # query later.

                if year is not None and year_map is not None:
                    total_results = info_string['total_results']
                    total_pages = info_string['total_pages']
                    if str(year) not in year_map:
                        aggregate_query_results = DiscoverTFHMovies.AggregateQueryResults(
                            total_pages=total_pages,
                            viewed_page=page)

                        year_map[str(year)] = aggregate_query_results

                movies = self.process_page(
                    info_string, data, tmdb_trailer_type, url=url)
                movies.extend(already_found_movies)
                DiskUtils.RandomGenerator.shuffle(movies)
                CacheIndex.add_unprocessed_movies(movies)
                self.add_to_discovered_trailers(movies)

                # From now on, only add one page's worth of movies to discovered
                # trailers.

                already_found_movies = []
                if self.is_exceeded_limit_of_trailers():
                    break

        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    class AggregateQueryResults(object):
        """
            Contains movie information discovered through multiple TMDB API
            calls so that they can be conveniently processed in a different
            order than they are discovered.
        """

        def __init__(self,
                     total_pages=None,  # type: Union[int, None]
                     viewed_page=None   # type: Union[int, None]
                     ):
            # type: (...) -> None
            """

            :param total_pages:
            :param viewed_page:
            """
            self._logger = module_logger.getChild(self.__class__.__name__)
            self._total_pages = total_pages
            self._viewed_page = viewed_page

        def get_total_pages(self):
            # type: () -> Union[int, None]
            """

            :return:
            """
            return self._total_pages

        def get_viewed_page(self):
            # type: () -> Union[int, None]
            """

            :return:
            """
            return self._viewed_page

    def process_page(self,
                     info_string,  # type: MovieType
                     query_data,  # type: List
                     tmdb_trailer_type,  # type: TextType
                     url=''  # type: TextType
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
        movies = []
        try:
            page = info_string.get('page', 1)
            total_pages = info_string.get('total_pages', -1)
            movie_entries = info_string.get('results', None)
            if total_pages == -1:
                self._logger.error('total_pages missing',
                                   json.dumps(info_string, indent=3, sort_keys=True))

            if movie_entries is None:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('results not found. URL:',
                                       url, 'returned value:',
                                       json.dumps(info_string))
            else:
                # Shuffling is done later, but this helps keep the first few
                # (about 3) displayed being the same thing all of the time

                DiskUtils.RandomGenerator.shuffle(movie_entries)
                for movie_entry in movie_entries:
                    self.throw_exception_on_forced_to_stop()

                    trailer_id = movie_entry['id']
                    if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                        tmp_title = movie_entry[Movie.TITLE]
                        self._logger.debug_verbose('Processing:', tmp_title)
                    try:
                        year = movie_entry['release_date'][:-6]
                        year = int(year)
                    except (Exception):
                        year = datetime.datetime.now().year

                    if year != 0 and self._select_by_year_range:
                        if self._minimum_year is not None and year < self._minimum_year:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    'Omitting movie_entry older than minimum Year:',
                                    self._minimum_year, 'movie_entry:',
                                    movie_entry[Movie.TITLE],
                                    'release:', year)
                            self._rejected_due_to_year += 1
                            continue
                        if self._maximum_year is not None and year > self._maximum_year:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
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

        except (AbortException, ShutdownException, RestartDiscoveryException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')
        finally:

            return movies

    def get_delay(self):
        # type: () -> int
        """

        :return:
        """

        self._total_pages_read += 1
        # If there is a backlog of movies discovered here, then slow down
        # discovering more. Note that depending upon the search, that most
        # TMDB movies are missing trailers.

        if len(CacheIndex.get_unprocessed_movies()) > 1000:
            delay = 10 * 60  # ten minutes
        elif self._total_pages_read > 20 and self.get_number_of_movies() > 200:
            delay = 120
        else:
            delay = 5

        return int(delay)

    def cache_results(self, query_data, movies):
        # type: (List, List[MovieType]) -> None
        """

        :param query_data:
        :param movies:
        :return:
        """
        pass
