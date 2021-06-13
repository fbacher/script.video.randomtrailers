# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import sys
import datetime
import threading

from common.constants import Constants
from common.disk_utils import DiskUtils
from common.debug_utils import Debug
from common.exceptions import AbortException, reraise
from common.garbage_collector import GarbageCollector
from common.imports import *
from common.monitor import Monitor
from common.movie import LibraryMovie, BaseMovie
from common.movie_constants import MovieField
from common.logger import Trace, LazyLogger
from common.settings import Settings
from discovery.utils.db_access import DBAccess
from discovery.utils.library_filter import LibraryFilter

from discovery.restart_discovery_exception import StopDiscoveryException
from backend.genreutils import GenreUtils
from backend.movie_utils import LibraryMovieStats
from backend.json_utils_basic import JsonUtilsBasic
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.library_movie_data import (LibraryMovieData, LibraryNoTrailerMovieData,
                                          LibraryURLMovieData)
from discovery.utils.parse_library import ParseLibrary

module_logger: Final[LazyLogger] = LazyLogger.get_addon_module_logger(file_path=__file__)


class DiscoverLibraryMovies(BaseDiscoverMovies):
    """
        Retrieve all movie entries from library. If specified, then limit to movies
        for the given genre. Note that entries include movies without trailers.
        Movies with local trailers or trailer URLs are immediately placed into
        BaseTrailerManager.readyToPlay. The others are placed into
        BaseTrailerManager.trailerFetchQue.
    """

    _singleton_instance = None
    logger: LazyLogger = None

    def __init__(self,
                 group: Any = None,  # Not used
                 target: Callable[[Union[None, Any]], Union[Any, None]] = None,
                 thread_name: str = None,
                 *args: Any,
                 **kwargs: Any
                 ) -> None:
        """

        :param group:
        :param target:
        :param thread_name:
        :param args:
        :param kwargs:
        """
        clz = type(self)
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)
        thread_name = 'Discv Lib'
        if kwargs is None:
            kwargs = {}
        kwargs[MovieField.SOURCE] = MovieField.LIBRARY_SOURCE
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = LibraryMovieData()

        self._selected_genres = []
        self._selected_keywords = []
        self._excluded_genres = []
        self._excluded_keywords = []
        self._libraryURLManager = None
        self._libraryNoTrailerInfoManager = None
        self._some_movies_discovered_event = threading.Event()
        self._include_library_trailers: bool = None
        self._include_library_no_trailers: bool = None
        self._include_library_remote_trailers: bool = None

    def discover_basic_information(self) -> None:
        """

        :return:
        """
        clz = DiscoverLibraryMovies
        self.start()
        #
        # In order to give good response during startup, block
        # other discovery (TMDB, iTunes) until a few local trailers have
        # been located (~50), or so many seconds have elapsed.

        countdown = Constants.EXCLUSIVE_LIBRARY_DISCOVERY_SECONDS * 5
        while not self._some_movies_discovered_event.wait(timeout=0.1):
            Monitor.throw_exception_if_abort_requested()
            if self._some_movies_discovered_event.is_set():
                break
            countdown -= 1
            if countdown <= 0:
                break

        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz.logger.debug_verbose(': started')

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return Settings.is_include_library_trailers()

    def run(self) -> None:
        """

        :return:
        """
        clz = DiscoverLibraryMovies
        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self._some_movies_discovered_event.clear()
                    self.run_worker()
                    self.finished_discovery()

                    # Unblock other discovery threads

                    self._some_movies_discovered_event.set()

                    duration = datetime.datetime.now() - start_time
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug('Time to discover:', duration.seconds, 'seconds',
                                         trace=Trace.STATS)
                    finished = True
                    # self.wait_until_restart_or_shutdown()
                except StopDiscoveryException:
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug('Stopping discovery')
                    self.destroy()
                    GarbageCollector.add_thread(self)
                    finished = True

        except AbortException:
            return  # Just exit thread
        except Exception as e:
            clz.logger.exception('')

    def run_worker(self) -> None:
        """
           Initial Discovery of all movies in Kodi.

        :return:
        """
        # Discovery is done in two parts:
        #
        # 1- query DB for every movie in library
        # 2- Get additional information
        #
        # There are three types of trailers for these movies:
        #
        #  a- Movies with local trailers
        #  b- Movies with movie URLS (typically youtube links from tmdb)
        #    TMdb will need to be queried for details
        #  c. Movies with no movie information, requiring a check with tmdb
        #     to see if one exists
        #
        # Because of the above, this manager will query the DB for every movie
        # and then only process the ones with local trailers. The others will
        # be handed off to their own managers. This is done because of
        # the way that this application works:
        #    Once enough information to identify a movie that matches
        #    what the user wants, it is added to the pool of movies that
        #    can be randomly selected for playing. Once a movie has been
        #    selected, it is placed into a TrailerFetcherQueue. A
        #    TrailerFetcher then gathers the remaining information so that
        #    it can be played.
        #
        #    If the lion's share of movies in the pool require significant
        #    extra processing because they don't have local trailers, then
        #    the fetcher can get overwhelmed.
        clz = DiscoverLibraryMovies
        self._selected_keywords = []
        self._excluded_keywords = []
        self._selected_genres = []
        self._excluded_genres = []
        if Settings.get_filter_genres():
            self._selected_genres = GenreUtils.get_internal_kodi_genre_ids(
                GenreUtils.LOCAL_DATABASE, exclude=False)
            self._excluded_genres = GenreUtils.get_internal_kodi_genre_ids(
                GenreUtils.LOCAL_DATABASE, exclude=True)
            self._selected_keywords = GenreUtils.get_internal_kodi_keyword_ids(
                GenreUtils.LOCAL_DATABASE, exclude=False)
            self._excluded_keywords = GenreUtils.get_internal_kodi_keyword_ids(
                GenreUtils.LOCAL_DATABASE, exclude=True)

        is_sparse = True
        query = DBAccess.create_query(is_sparse,
                                      self._selected_genres,
                                      self._excluded_genres,
                                      self._selected_keywords,
                                      self._excluded_keywords)

        if Monitor.is_abort_requested():
            return

        self._include_library_trailers = Settings.is_include_library_trailers()
        self._include_library_no_trailers = Settings.is_include_library_no_trailer_info()
        self._include_library_remote_trailers = \
            Settings.is_include_library_remote_trailers()
        collect_stats: bool = Settings.is_enable_movie_stats()
        start_time: datetime.datetime = datetime.datetime.now()
        Monitor.throw_exception_if_abort_requested()  # Expensive operation
        query_result: Dict[str, Any] = {}
        try:
            query_result: Dict[str, Any] =\
                JsonUtilsBasic.get_kodi_json(query, dump_results=False)
            if query_result.get('error') is not None:
                raise ValueError
                
            Monitor.throw_exception_if_abort_requested()
            elapsed_time = datetime.datetime.now() - start_time
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose('Library query seconds:',
                                         elapsed_time.total_seconds())

            self.throw_exception_on_forced_to_stop()
            result: Dict[str, Any] = query_result.get('result', {})
            movies: List[Dict[str, Any]] = result.get('movies', [])
        except Exception as e:
            message: str = ''
            if query_result is not None:
                error = query_result.get('error')
                if error is not None:
                    message: str = error.get('message')
            clz.logger.exception(message)
            try:
                import simplejson as json
                # json_encoded: Dict = json.loads(query)
                clz.logger.debug_extra_verbose('JASON DUMP:',
                                            json.dumps(
                                                    query, indent=3, sort_keys=True))
            except Exception:
                pass

            movies = []

        del query_result
        del result
        DiskUtils.RandomGenerator.shuffle(movies)
        if self._libraryURLManager is None:
            if self._include_library_remote_trailers:
                self._libraryURLManager = DiscoverLibraryURLTrailerMovies()
            if self._include_library_no_trailers:
                self._libraryNoTrailerInfoManager = DiscoverLibraryNoTrailerMovies()
        library_movies: List[LibraryMovie] = []
        library_url_movies: List[LibraryMovie] = []
        library_no_trailer_movies: List[LibraryMovie] = []
        batch_size = \
            Constants.NUMBER_OF_LIBRARY_MOVIES_TO_DISCOVER_DURING_EXCLUSIVE_DISCOVERY
        movie_data = None
        if Settings.is_enable_movie_stats():
            movie_data = LibraryMovieStats()

        movie: Dict[str, Any]

        movies_found: int = 0
        movies_with_trailer_urls: int = 0
        movies_with_local_trailers: int = 0
        movies_without_trailer_info: int = 0
        movies_skipped: int = 0

        movie_iterator: Iterator[Dict[str, Any]] = iter(movies)
        while True:
            self.throw_exception_on_forced_to_stop()
            try:
                raw_movie: Dict[str, Any] = next(movie_iterator)
                movies_found += 1

                movie: LibraryMovie = ParseLibrary.parse_movie(is_sparse=True,
                                                               raw_movie=raw_movie)

                rejection_reasons: List[int] = LibraryFilter.filter_movie(movie)
                if len(rejection_reasons) == 0:
                    if movie.is_trailer_url():
                        movies_with_trailer_urls += 1
                        if self._include_library_remote_trailers:
                            library_url_movies.append(movie)
                    else:
                        movies_with_local_trailers += 1
                        if self._include_library_trailers:
                            library_movies.append(movie)

                elif (MovieField.REJECTED_NO_TRAILER in rejection_reasons
                        and len(rejection_reasons) == 1):
                    rejection_reasons.clear()  # So we don't report as error
                    movies_without_trailer_info += 1
                    if self._include_library_no_trailers:
                        library_no_trailer_movies.append(movie)

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    if len(rejection_reasons) > 0: 
                        rejection_reasons_str: List[str] = \
                            BaseMovie.get_rejection_reasons_str(rejection_reasons)
                        clz.logger.debug_extra_verbose(
                            f'Filter failed for: '
                            f'{movie.get_title()} '
                            f'- {", ".join(rejection_reasons_str)}')

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    Debug.validate_basic_movie_properties(movie)

                if collect_stats:
                    movie_data.collect_data(movie)

                self.add_movies_to_discovery_queues(library_movies, library_url_movies,
                                                    library_no_trailer_movies,
                                                    batch_size)
            except AbortException:
                reraise(*sys.exc_info())
            except StopIteration:
                self.add_movies_to_discovery_queues(library_movies, library_url_movies,
                                                    library_no_trailer_movies,
                                                    batch_size)
                break
            except Exception:
                clz.logger.exception('')

        if (clz.logger.isEnabledFor(LazyLogger.DEBUG)
                and clz.logger.is_trace_enabled(Trace.STATS)):
            clz.logger.debug('Local movies found in library:',
                             movies_found, trace=Trace.STATS)
            clz.logger.debug('Local movies filtered out',
                             movies_skipped, trace=Trace.STATS)
            clz.logger.debug('Movies with local trailers:',
                             movies_with_local_trailers, trace=Trace.STATS)
            clz.logger.debug('Movies with trailer URLs:',
                             movies_with_trailer_urls, trace=Trace.STATS)
            clz.logger.debug('Movies with no trailer information:',
                             movies_without_trailer_info, trace=Trace.STATS)

        if Settings.is_enable_movie_stats():
            movie_data.report_data()
            del movie_data

    def add_movies_to_discovery_queues(self, library_movies: List[LibraryMovie],
                                       library_url_movies: List[LibraryMovie],
                                       library_no_trailer_movies: List[LibraryMovie],
                                       batch_size: int
                                       ) -> None:
        clz = type(self)
        try:
            # Basic discovery is complete at this point. Now send
            # all of the movies without any movie information to
            # DiscoverLibraryNoTrailerMovies while
            # those with movie URLs to DiscoverLibraryURLTrailerMovies

            if len(library_movies) >= batch_size:
                self.add_to_discovered_movies(library_movies)
                del library_movies[:]

                # Unblock other discovery now that a few movies have been
                # found.

                if not self._some_movies_discovered_event.isSet():
                    self._some_movies_discovered_event.set()

            if len(library_no_trailer_movies) >= batch_size:
                if self._include_library_no_trailers:
                    self._libraryNoTrailerInfoManager.add_to_discovered_movies(
                        library_no_trailer_movies)
                del library_no_trailer_movies[:]
            if len(library_url_movies) >= batch_size:
                if self._include_library_remote_trailers:
                    self._libraryURLManager.add_to_discovered_movies(
                        library_url_movies)
                del library_url_movies[:]

                # Unblock other discovery now that a few movies have been
                # found.

                self._some_movies_discovered_event.set()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            clz.logger.exception('')


class DiscoverLibraryURLTrailerMovies(BaseDiscoverMovies):
    """
        This manager does not do any discovery, it receives local movies
        with trailer URLs from LibraryManager. This manager primarily
        acts as a container to hold the list of movies while the
        TrailerFetcher and BaseTrailerManager does the work
    """

    def __init__(self) -> None:
        """

        """
        clz = DiscoverLibraryURLTrailerMovies
        clz.logger = module_logger.getChild(clz.__class__.__name__)
        thread_name = clz.__name__
        kwargs = {}
        kwargs[MovieField.SOURCE] = MovieField.LIBRARY_URL_TRAILER
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = LibraryURLMovieData()

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return (Settings.is_include_library_remote_trailers()
                and Settings.is_include_library_trailers())

    def discover_basic_information(self) -> None:
        """

        :return:
        """
        clz = DiscoverLibraryURLTrailerMovies
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.warning('dummy method')

    def run(self) -> None:
        """

        :return:
        """
        clz = DiscoverLibraryURLTrailerMovies
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.warning('dummy thread, Join Me!')
        finished = False
        while not finished:
            try:
                self.finished_discovery()
                self.wait_until_restart_or_shutdown()
            except StopDiscoveryException:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz.logger.debug_verbose('Stopping discovery')
                self.destroy()
                finished = True
            except AbortException:
                return  # Just exit thread
            except Exception as e:
                clz.logger.exception('')


class DiscoverLibraryNoTrailerMovies(BaseDiscoverMovies):
    """
        This manager does not do any discovery, it receives local movies
        without any trailer information from LibraryManager. This manager
        primarily acts as a container to hold the list of movies while the
        TrailerFetcher and BaseTrailerManager does the work
    """

    def __init__(self) -> None:
        """

        """
        clz = DiscoverLibraryNoTrailerMovies
        clz.logger = module_logger.getChild(clz.__name__)
        thread_name = clz.__name__
        self._validate_number_of_trailers = 0
        self._reported_trailers = 0
        kwargs = {}
        kwargs[MovieField.SOURCE] = MovieField.LIBRARY_NO_TRAILER
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = LibraryNoTrailerMovieData()

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return (Settings.is_include_library_no_trailer_info()
                and Settings.is_include_library_trailers())

    def discover_basic_information(self) -> None:
        """

        :return:
        """
        clz = DiscoverLibraryNoTrailerMovies
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.warning('dummy method')

    def run(self) -> None:
        """

        :return:
        """
        clz = DiscoverLibraryNoTrailerMovies
        if clz.logger.isEnabledFor(LazyLogger.WARNING):
            clz.logger.warning('dummy thread, Join Me!')
        finished = False
        while not finished:
            try:
                self.finished_discovery()
                self.wait_until_restart_or_shutdown()
            except StopDiscoveryException:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug('Stopping discovery')
                self.destroy()
                finished = True
            except AbortException:
                return  # Just exit thread
            except Exception as e:
                clz.logger.exception('')

