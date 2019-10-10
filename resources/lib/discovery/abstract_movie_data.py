# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import threading
import sys
import datetime
import six

from common.constants import Constants, Movie
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, ShutdownException
from common.kodi_queue import (KodiQueue)
from common.monitor import Monitor
from backend.movie_entry_utils import (MovieEntryUtils)
from common.logger import (Logger, Trace, LazyLogger)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.abstract_movie_data')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class MovieSourceData(object):
    """

    """

    def __init__(self, movie_source):
        # type: (TextType) -> None
        """

        :param movie_source:
        :return:
        """
        self.removed_trailers = 0
        self.number_of_added_movies = 0
        self.load_fetch_total_duration = 0
        self.discovery_complete = False
        self.movie_source = movie_source


class DuplicateException(Exception):
    """

    """
    pass


class UniqQueue(object):
    """

    """

    def __init__(self, maxsize=0, movie_source=''):
        # type: (int, TextType) -> None
        """
        :param maxsize:
        :param movie_source:
        :return:
        """
        self._logger = module_logger.getChild(self.__class__.__name__)

        self._queue = KodiQueue(maxsize)
        self._duplicate_check = set()
        self._lock = threading.RLock()
        self.movie_source = movie_source

    def clear(self):
        # type: () -> None
        """

        :return:
        """
        self._logger.enter()

        with self._lock:
            self._duplicate_check.clear()
            self._queue.clear()

            assert len(self._duplicate_check) == 0
            assert self._queue.empty()

    def put(self, movie, block=True, timeout=None):
        # type: (Any, bool, Optional[float]) -> None
        """

        :param movie:
        :param block:
        :param timeout:
        :return:
        """
        key = self.get_key(movie)

        # self._logger.debug('movie:', movie[Movie.TITLE], 'source:',
        #                    movie[Movie.SOURCE], 'key:', key)
        with self._lock:
            if key in self._duplicate_check:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Duplicate movie:', movie[Movie.TITLE],
                                       'source:', movie[Movie.SOURCE],
                                       'key:', key)
                raise DuplicateException()

            self._queue.put(movie, False)
            self._duplicate_check.add(key)
            # self._logger.debug('movie:', movie[Movie.TITLE], 'key:', key)

    def get(self, block=True, timeout=None):
        # type: (bool, Optional[float]) -> object
        """

        :param block:
        :param timeout:
        :return:
        """
        with self._lock:
            try:
                movie = None  # type: MovieType
                movie = self._queue.get(block=block, timeout=timeout)
                key = self.get_key(movie)
                self._duplicate_check.remove(key)
            except (KeyError) as e:
                self._logger.debug('movie:', movie[Movie.TITLE], 'key:', key)
                self._logger.dump_stack(movie[Movie.TITLE] +
                                        ' movie not found in duplicate_check for UniqueQueue')
        # if self._logger.isEnabledFor(Logger.DEBUG):
            # self._logger.debug('got movie:', item[Movie.TITLE], 'source:',
            #                    item[Movie.SOURCE], 'key:', key)
        return movie

    def qsize(self):
        # type: () -> int
        """

        :return:
        """
        with self._lock:
            size = int(self._queue.qsize())

        # self._logger.exit('size:', size)
        return size

    def get_key(self, movie):
        # type: (MovieType) -> TextType
        """

        :param movie:
        :return:
        """

        key = None
        movie_source = movie[Movie.SOURCE]
        if movie_source == Movie.TMDB_SOURCE:
            key = MovieEntryUtils.get_tmdb_id(movie)
        elif movie_source == Movie.ITUNES_SOURCE:
            key = movie[Movie.ITUNES_ID]
        elif movie_source == Movie.LIBRARY_SOURCE:
            key = movie_source + str(movie[Movie.MOVIEID])

        return key

    def empty(self):
        # type: () -> bool
        """

        :return:
        """
        # self._logger = self._logger.get_method_logger('empty')

        with self._lock:
            empty = self._queue.empty()

        # self._logger.exit('empty:', empty)
        return empty

    def full(self):
        # type () -> bool
        """

        :return:
        """
        # self._logger = self._logger.get_method_logger('full')

        with self._lock:
            full = self._queue.full()

        # self._logger.exit('full:', full)
        return full


class MovieList(object):
    """

    """

    def __init__(self, movie_source):
        # type: (TextType) -> None
        """
        :param movie_source:
        :return:
        """

        self._logger = module_logger.getChild(self.__class__.__name__)

        self._movie_source = movie_source
        self._list = list()
        self._duplicate_check = set()
        self._total_removed = 0
        self._play_count = dict()
        self._lock = threading.RLock()
        self._iter = None
        self._cursor = None
        self._changed = False
        self._iterating = False
        self._saved_stack_trace = None
        self._saved_thread_name = None
        self._number_of_added_movies = 0

    def clear(self):
        # type: () -> None
        """

        :return:
        """
        self._logger.enter()

        with self._lock:
            if self._iterating:
                self._changed = True
                self._saved_stack_trace, self._saved_thread_name = LazyLogger.capture_stack()

            self._duplicate_check.clear()
            del self._list[:]
            self._number_of_added_movies = 0

        # self._logger.exit()

    def add(self, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        # if self._logger.isEnabledFor(Logger.DEBUG):
        # self._logger.debug('movie:', movie[Movie.TITLE], 'source:',
        #                   movie[Movie.SOURCE])
        key = self.get_key(movie)
        with self._lock:
            if self._iterating:
                self._changed = True
                self._saved_stack_trace, self._saved_thread_name = LazyLogger.capture_stack()

            if key in self._duplicate_check:
                raise DuplicateException()

            self._list.append(movie)
            self._duplicate_check.add(key)
            self._play_count.setdefault(key, 0)
            self._number_of_added_movies += 1

        # self._logger.exit()

    def __iter__(self):
        # type: () -> MovieList
        """

        :return:
        """
        self._cursor = -1
        self._changed = False
        self._iterating = True
        self._saved_stack_trace = None
        return self

    def __next__(self):
        # type: () -> MovieType
        """

        :return:
        """
        # self._logger.enter()
        next_item = None
        with self._lock:
            if self._changed:
                LazyLogger.log_stack('List changed while iterating',
                                     self._saved_track_trace,
                                     thread_name=self._saved_thread_name)
                self._saved_stack_trace = None

            self._cursor += 1
            if self._cursor >= len(self._list):
                self._iterating = False
                self._saved_stack_trace = None
                raise StopIteration

            next_item = self._list[self._cursor]

        return next_item

    def __getitem__(self, y):
        # type: (Any) -> MovieType
        # self._logger.enter()
        item = None
        with self._lock:
            item = self._list.__getitem__(y)

        # self._logger.exit()
        return item

    def remove(self, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        # self._logger.enter()
        with self._lock:
            try:
                if self._iterating:
                    self._changed = True
                    self._saved_stack_trace, self._saved_thread_name = \
                        LazyLogger.capture_stack()

                self._duplicate_check.remove(self.get_key(movie))
                self._total_removed += 1
            except (KeyError):
                pass
            try:
                self._list.remove(movie)
            except (ValueError):
                pass

    def len(self):
        # type: () -> int
        """

        :return:
        """
        with self._lock:
            length = int(len(self._list))

        return length

    def __len__(self):
        # type: () -> int
        """

        :return:
        """
        return self.len()

    def shuffle(self):
        # type: () -> None
        """

        :return:
        """
        # self._logger.enter()

        with self._lock:
            if self._iterating:
                self._changed = True
                del self._saved_stack_trace
                self._saved_stack_trace, self._saved_thread_name = \
                    LazyLogger.capture_stack()

            DiskUtils.RandomGenerator.shuffle(self._list)

    def get_play_count(self, movie):
        # type: (MovieType) -> int
        """

        :param movie:
        :return:
        """
        count = None
        try:
            with self._lock:
                count = self._play_count.get(self.get_key(movie), 0)
        except (KeyError) as e:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(
                    'Could not find entry for:', movie[Movie.TITLE])

        return count

    def increase_play_count(self, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        try:
            key = self.get_key(movie)
            with self._lock:
                count = self._play_count.get(key, 0) + 1
                self._play_count[key] = count

        except (KeyError) as e:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Could not find entry for:',
                                   movie[Movie.TITLE])

        # self.report_play_count_stats()
        return

    def report_play_count_stats(self):
        # type: () -> None
        """

        :return:
        """

        try:
            with self._lock:
                Monitor.throw_exception_if_shutdown_requested()
                movie_keys = sorted(self._play_count, key=lambda key:
                                    self._play_count[key], reverse=False)
                # Number of times this set of movies were played
                previous_play_count = -1
                # Running count of number of discovered movies
                movie_count = 0
                movie_count_in_group = 0
                # Total number of movies that were played
                total_play_count = 0
                # play_count is number of times a movie was played
                movies_with_same_count = []
                for movie_key in movie_keys:
                    Monitor.throw_exception_if_shutdown_requested()
                    play_count = self._play_count[movie_key]
                    if play_count == previous_play_count:
                        movie_count_in_group += 1
                        movies_with_same_count.append(movie_key)
                    else:
                        if previous_play_count != -1:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    '{} movies played {} times'.format(movie_count_in_group,
                                                                       previous_play_count))
                            if previous_play_count != 0:
                                self.wrap_text(
                                    self._logger.debug, movies_with_same_count)
                            del movies_with_same_count[:]
                            movie_count += movie_count_in_group
                            total_play_count += previous_play_count * movie_count_in_group

                        movie_count_in_group = 1
                        movies_with_same_count.append(movie_key)
                        previous_play_count = play_count

            # movie_count_in_group += 1
            if movie_count_in_group > 0:
                movie_count += movie_count_in_group
                total_play_count += previous_play_count * movie_count_in_group
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('{} movies played {} times'.format(movie_count_in_group,
                                                                          previous_play_count))
                if previous_play_count > 0:
                    self.wrap_text(self._logger.debug, movies_with_same_count)

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(
                    'Total movies played: {} Total Movies: {} Total Removed: {} Total Added: {}'.format(
                        total_play_count,
                        movie_count,
                        self._total_removed,
                        self._number_of_added_movies))
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())

        except (Exception) as e:
            self._logger.exception('')

    MAX_LINE_LENGTH = 80

    def wrap_text(self, logger, movies_with_same_count):
        # type: (Callable, List[TextType]) -> None
        """

        :param logger:
        :param movies_with_same_count:
        :return:
        """
        movies_in_line = []
        line_length = 0
        for movie in movies_with_same_count:
            Monitor.throw_exception_if_shutdown_requested()
            try:
                if line_length + len(movie) + 2 > MovieList.MAX_LINE_LENGTH:
                    logger('   {}'.format(', '.join(movies_in_line)))
                    del movies_in_line[:]
                    line_length = 0
            except (AbortException, ShutdownException):
                six.reraise(*sys.exc_info())

            except (Exception) as e:
                logger('blew up joining')

            movies_in_line.append(movie)
            line_length += len(movies_in_line) + 2  # Slightly inaccurate

        if len(movies_in_line) > 0:
            try:
                logger('   {}'.format(', '.join(movies_in_line)))
            except (Exception) as e:
                logger('blew up joining')

    def get_key(self, movie):
        # type: (MovieType) -> TextType
        """

        :param movie:
        :return:
        """

        key = None
        movie_source = movie[Movie.SOURCE]
        if movie_source == Movie.TMDB_SOURCE:
            key = str(MovieEntryUtils.get_tmdb_id(movie))
        elif movie_source == Movie.ITUNES_SOURCE:
            key = movie[Movie.ITUNES_ID]
        elif movie_source == Movie.LIBRARY_SOURCE:
            key = movie_source + str(movie[Movie.MOVIEID])

        return key

# noinspection Annotator,PyArgumentList


class AbstractMovieData(object):
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    _aggregate_trailers_by_name_date_lock = threading.RLock()
    _aggregate_trailers_by_name_date = dict()
    _discovered_trailers = None
    _discovered_trailers_queue = None
    _trailers_to_fetch_queue = None
    _iterator = None

    def __init__(self,
                 movie_source=''  # type: TextType
                 ):
        # type: (...) -> None
        """

        :param name:
        :param args:
        :param kwargs:
        :param verbose:
        """

        self._logger = module_logger.getChild(self.__class__.__name__ +
                                              ':' + movie_source)

        self._trailers_discovered_event = threading.Event()
        self._movie_source_data = {}  # type: Dict[TextType, MovieSourceData]
        self._removed_trailers = 0
        self._number_of_added_movies = 0
        self._load_fetch_total_duration = 0
        self._discovery_complete = False
        self._last_shuffle_time = datetime.datetime.fromordinal(1)
        self._last_shuffled_index = -1
        self._discovered_trailers_lock = threading.RLock()
        self._discovered_trailers = MovieList(
            movie_source)  # Access via self.lock
        self._discovered_trailers_queue = UniqQueue(
            maxsize=0, movie_source=movie_source)
        self._trailers_to_fetch_queue = KodiQueue(maxsize=3)
        self._starvation_queue = KodiQueue()
        self._trailers_to_fetch_queueLock = threading.RLock()
        self.restart_discovery_event = threading.Event()
        self._movie_source = movie_source

        from discovery.trailer_fetcher import TrailerFetcher
        self._trailer_fetcher = TrailerFetcher(self)

    def start_trailer_fetchers(self):
        # type: () -> None
        """

        :return:
        """
        self._trailer_fetcher.start_fetchers()

    def get_movie_source(self):
        # type: () -> TextType
        """

        :return:
        """
        return self._movie_source

    def prepare_for_restart_discovery(self, stop_thread):
        # type: (bool) -> None
        """
        :param stop_thread
        :return:
        """

        self._logger.enter()

        with self._discovered_trailers_lock:
            # self._logger.debug('Have Lock')
            self._trailer_fetcher.prepare_for_restart_discovery(stop_thread)
            self._trailers_discovered_event.clear()
            self._removed_trailers = 0
            self._number_of_added_movies = 0
            self._load_fetch_total_duration = 0
            self._discovery_complete = False
            self._last_shuffle_time = datetime.datetime.fromordinal(1)
            self._last_shuffled_index = -1
            self._discovered_trailers.clear()
            self._discovered_trailers_queue.clear()

            if stop_thread:
                # Forget what was in queue

                self._starvation_queue = KodiQueue()
                self._discovery_complete = True
                del self._trailer_fetcher
                self._trailer_fetcher = None

    def finished_discovery(self):
        # type: () -> None
        """

        :return:
        """
        with self._discovered_trailers_lock:
            if self._logger.isEnabledFor(Logger.DEBUG):
                # self._logger.debug('Have discovered_trailers_lock')
                self._logger.debug('Shuffling because finished_discovery',
                                   trace=Trace.TRACE_DISCOVERY)
            self.shuffle_discovered_trailers(mark_unplayed=False)
            self._discovery_complete = True

    def is_discovery_complete(self):
        # type: () -> bool
        """

        :return:
        """
        return self._discovery_complete

    @classmethod
    def get_aggregate_trailers_by_name_date_lock(cls):
        # type: () -> threading.RLock
        """

        :return:
        """
        return cls._aggregate_trailers_by_name_date_lock

    @classmethod
    def get_aggregate_trailers_by_name_date(cls):
        # type: () -> dict
        """

        :return:
        """
        return cls._aggregate_trailers_by_name_date

    def add_to_discovered_trailers(self, movies):
        # type: (Union[Dict[TextType], List[Dict[TextType]]]) -> None
        """

        :param movies:
        :return:
        """
        if not isinstance(movies, list):
            temp = movies
            movies = list()
            movies.append(temp)

        movies_added = False
        with self._discovered_trailers_lock:
            #  if self._logger.isEnabledFor(Logger.DEBUG):
                # self._logger.debug('Have discovered_trailers_lock')
            for movie in movies:
                if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                    self._logger.debug_verbose(movie.get(Movie.TITLE),
                                               'source:', movie.get(
                                                   Movie.SOURCE),
                                               'discovery_state:',
                                               movie.get(
                                                   Movie.DISCOVERY_STATE),
                                               'length:',
                                               len(self._discovered_trailers))
                # Assume more discovery is required for movie details, etc.

                try:
                    self._discovered_trailers.add(movie)
                except (DuplicateException) as e:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Ignoring duplicate movie:',
                                           movie[Movie.TITLE])
                    continue

                movies_added = True
                self._number_of_added_movies += 1
                movie[Movie.TRAILER_PLAYED] = False
                if movie.get(Movie.DISCOVERY_STATE, None) is None:
                    movie[Movie.DISCOVERY_STATE] = Movie.NOT_FULLY_DISCOVERED

            if self._discovered_trailers.len() > 0:
                self._trailers_discovered_event.set()

            seconds_since_last_shuffle = (
                datetime.datetime.now() - self._last_shuffle_time).seconds

        reshuffle = False
        # Reshuffle every minute or when there is a 20% change

        last_shuffled_at_size = self._last_shuffled_index
        current_size = len(self._discovered_trailers)
        if (movies_added and current_size >= (last_shuffled_at_size * 1.20)
                or seconds_since_last_shuffle > Constants.SECONDS_BEFORE_RESHUFFLE):
            reshuffle = True

        if reshuffle:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(
                    'Shuffling seconds_since_last_shuffle:',
                    seconds_since_last_shuffle,
                    'current size:', current_size,
                    '   previous size:', last_shuffled_at_size,
                    trace=Trace.TRACE_DISCOVERY)

            self.shuffle_discovered_trailers(mark_unplayed=False)

    def have_trailers_been_discovered(self):
        # type: () -> bool
        """

        :return:
        """
        return self._trailers_discovered_event.isSet()

    def shuffle_discovered_trailers(self, mark_unplayed=False):
        # type: (bool) -> None
        """

        :param mark_unplayed:
        :return:
        """
        Monitor.get_instance().throw_exception_if_shutdown_requested()
        # self._logger.debug('before self.lock')

        with self._discovered_trailers_lock:
            # self._logger.debug('Have discovered_trailers_lock')

            if self._discovered_trailers.len() == 0:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('nothing to shuffle')
                return

            self._discovered_trailers.shuffle()
            if mark_unplayed:
                for trailer in self._discovered_trailers:
                    trailer[Movie.TRAILER_PLAYED] = False

            self._last_shuffled_index = self._discovered_trailers.len() - 1
            self._last_shuffle_time = datetime.datetime.now()
            # if self._logger.isEnabledFor(Logger.DEBUG):
            # self._logger.debug('lastShuffledIndex:', self._last_shuffled_index)

            # Drain anything previously in queue

            self._discovered_trailers_queue.clear()

            Monitor.get_instance().throw_exception_if_shutdown_requested()
            # self._logger.debug('reloading _discovered_trailers_queue')
            for trailer in self._discovered_trailers:
                if not trailer[Movie.TRAILER_PLAYED]:
                    # if self._logger.isEnabledFor(Logger.DEBUG):
                    #   self._logger.debug('adding', trailer[Movie.TITLE],
                    #                      'id:', hex(id(trailer)),
                    #                      'to discovered_trailers_queue',
                    #                      'state:', trailer[Movie.DISCOVERY_STATE])
                    self._discovered_trailers_queue.put(trailer)

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('_discoveredTrailerQueue length:',
                                   self._discovered_trailers_queue.qsize(),
                                   '_discovered_trailers length:',
                                   len(self._discovered_trailers))

    def get_number_of_movies(self):
        # type: () -> int
        """

        :return:
        """
        return self._discovered_trailers.len()

    def get_number_of_added_movies(self):
        # type: () -> int
        """

        :return:
        """
        return int(self._number_of_added_movies)

    def get_projected_number_of_trailers(self):
        # type: () -> int
        """

        :return:
        """

        success_ratio = 1.0
        if self._removed_trailers > 100:
            success_ratio = (self._number_of_added_movies - self._removed_trailers) /\
                self._number_of_added_movies
            if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                self._logger.debug_verbose('movies discovered:',
                                           self._number_of_added_movies,
                                           'movies without trailers:',
                                           self._removed_trailers)
        number_of_trailers = self.get_number_of_movies()
        projected_number_of_trailers = success_ratio * number_of_trailers
        if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
            self._logger.debug_extra_verbose('removed:', self._removed_trailers,
                                             'projected_number_of_trailers:',
                                             projected_number_of_trailers)
        return int(projected_number_of_trailers)

    def get_trailers_to_fetch_queue_size(self):
        # type: () -> int
        """

        :return:
        """
        return self._trailers_to_fetch_queue.qsize()

    def get_number_of_removed_trailers(self):
        # type: () -> int
        """

        :return:
        """

        return int(self._removed_trailers)

    def remove_discovered_movie(self, movie):
        # type: (MovieType) -> None
        """
            When a trailer can not be found for a movie, then we need to remove it
            so that we don't keep looking for it.

        :param movie:
        :return:
        """
        with self._discovered_trailers_lock:
            # self._logger.debug('Have discovered_trailers_lock')

            try:
                self._discovered_trailers.remove(movie)
            except (ValueError):  # Already deleted
                if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                    self._logger.debug_verbose('Movie appears to already be removed:',
                                               movie.get(Movie.TITLE))

            if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
                try:
                    key = self._discovered_trailers_queue.get_key(movie)
                    if key in self._discovered_trailers_queue._duplicate_check:
                        self._logger.debug_extra_verbose('Deleted movie still in',
                                                         'fetch queue. Movie:', movie.get(Movie.TITLE))
                except (ValueError):  # Already deleted
                    pass

        self._removed_trailers += 1
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(' : ',
                               movie.get(Movie.TITLE), 'removed:',
                               self._removed_trailers, 'remaining:',
                               self.get_number_of_movies() - 1)

    _first_load = True

    def load_fetch_queue(self):
        # type: () -> None
        """
            Load the _trailers_to_fetch_queue from._discovered_trailers_queue.

            If _trailers_to_fetch_queue is full, then return

            If discoveryComplete and _discovered_trailers is empty,
            then return

            If discoveryComplete and._discovered_trailers_queue is empty,
            then shuffle_discovered_trailers and fill the _trailers_to_fetch_queue
            from it. If there are not enough items to fill the fetch queue,
            then get as many as are available.

            Otherwise, discoveryComplete == False:

            If._discovered_trailers_queue is empty and _trailers_to_fetch_queue
            is not empty, then return without loading any.

            If._discovered_trailers_queue is empty and _trailers_to_fetch_queue is empty
            then block until an item becomes available or discoveryComplete == True.

            Finally, _trailers_to_fetch_queue is not full, fill it from any available
            items from._discovered_trailers_queue.
        :return:
        """
        start_time = datetime.datetime.now()
        if AbstractMovieData._first_load:
            Monitor.get_instance().wait_for_shutdown(timeout=2.0)
            AbstractMovieData._first_load = False

        Monitor.get_instance().throw_exception_if_shutdown_requested()
        finished = False
        attempts = 0
        discovery_complete_queue_empty = 0
        discovered_and_fetch_queues_empty = 0
        discovery_incomplete_fetch_not_empty = 0
        discovery_incomplete_fetch_queue_empty = 0
        get_attempts = 0
        put_attempts = 0
        while not finished:
            trailer = None  # type: MovieType
            Monitor.get_instance().throw_exception_if_shutdown_requested()
            attempts += 1
            shuffle = False
            iteration_successful = False
            try:
                elapsed = datetime.datetime.now() - start_time
                if attempts > 0:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Attempt:',
                                           attempts, 'elapsed:', elapsed.seconds)

                if self._trailers_to_fetch_queue.full():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('_trailers_to_fetch_queue full',
                                           trace=Trace.TRACE)
                    finished = True
                    iteration_successful = True
                elif self._discovery_complete and len(self._discovered_trailers) == 0:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Discovery Complete and nothing found.',
                                           trace=Trace.TRACE)
                    finished = True
                    iteration_successful = True
                elif self._discovery_complete and self._discovered_trailers_queue.empty():
                    self._logger.error(
                        'discoveryComplete,_discovered_trailers_queue empty')
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'discoveryComplete,_discovered_trailers_queue empty',
                            trace=Trace.TRACE)
                    shuffle = True
                    discovery_complete_queue_empty += 1
                    #
                    # In the following, Discovery is INCOMPLETE
                    #
                elif (self._discovered_trailers_queue.empty()
                      and not self._trailers_to_fetch_queue.empty):
                    discovered_and_fetch_queues_empty += 1
                    # Use what we have
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Discovery incomplete._discovered_trailers_queue',
                                           'empty and _trailers_to_fetch_queue not empty',
                                           trace=Trace.TRACE)
                    finished = True
                elif not self._trailers_to_fetch_queue.empty():
                    # Fetch queue is not empty, nor full. Discovery
                    # is not complete. Get something from _discoveredTrailerQueue
                    # if available

                    try:
                        discovery_incomplete_fetch_not_empty += 1
                        with self._discovered_trailers_lock:
                            # self._logger.debug('Have discovered_trailers_lock')

                            trailer = self._discovered_trailers_queue.get(
                                timeout=0.25)

                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(' Got', trailer[Movie.TITLE],
                                               'from _discoveredTrailerQueue')
                    except (KodiQueue.Empty):
                        pass

                    if trailer is not None:
                        try:
                            self.put_in_fetch_queue(
                                trailer, timeout=1)
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Put in _trailers_to_fetch_queue qsize:',
                                                   self._trailers_to_fetch_queue.qsize(),
                                                   trailer.get(Movie.TITLE),
                                                   trace=Trace.TRACE)
                            iteration_successful = True
                        except (KodiQueue.Full):
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('_trailers_to_fetch_queue.put failed',
                                                   trace=Trace.TRACE)
                        #
                        # It is not a crisis if the put fails. Since the
                        # fetch queue does have at least one entry, we are ok
                        # Even if the trailer is lost from the FetchQueue,
                        # it will get reloaded once the queue is exhausted.
                        #
                        # But since iteration_successful is not true, we might
                        # still fix it at the end.
                        #
                else:
                    # Discovery incomplete, fetch queue is empty
                    # wait until we get an item, or discovery complete

                    discovery_incomplete_fetch_queue_empty += 1
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Discovery incomplete,',
                                           '_trailers_to_fetch_queue empty, will wait',
                                           trace=Trace.TRACE)

                if not iteration_successful:
                    if (self._discovered_trailers_queue.empty()
                            and self._discovered_trailers.len() > 0):
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'Shuffling due to empty _discovered_trailers_queue and',
                                '_discovered_trailers not empty')
                        shuffle = True

                    if shuffle:  # Because we were empty
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'Shuffling due to empty _discovered_trailers_queue')
                        Monitor.get_instance().throw_exception_if_shutdown_requested()
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('load_fetch_queue Shuffling because',
                                               'discoveredTrailerQueue empty',
                                               trace=Trace.TRACE_DISCOVERY)
                        self.shuffle_discovered_trailers(mark_unplayed=True)

                    if trailer is None:
                        get_finished = False
                        while not get_finished:
                            try:
                                get_attempts += 1
                                with self._discovered_trailers_lock:
                                    # self._logger.debug('Have discovered_trailers_lock')

                                    trailer = self._discovered_trailers_queue.get(
                                        timeout=0.5)
                                get_finished = True
                            except (KodiQueue.Empty):
                                Monitor.get_instance().throw_exception_if_shutdown_requested()

                    put_finished = False
                    while not put_finished:
                        try:
                            put_attempts += 1
                            self.put_in_fetch_queue(trailer, timeout=0.25)
                            put_finished = True
                        except (KodiQueue.Full):
                            Monitor.get_instance().throw_exception_if_shutdown_requested()
                        iteration_successful = True

                if trailer is not None:
                    movie_title = trailer.get(Movie.TITLE)
                else:
                    movie_title = 'no movie'

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Queue has:',
                                       self._trailers_to_fetch_queue.qsize(),
                                       'Put in _trailers_to_fetch_queue:', movie_title)
            except (AbortException, ShutdownException):
                six.reraise(*sys.exc_info())
            except (Exception) as e:
                self._logger.exception('')
                # TODO Continue?

            if self._trailers_to_fetch_queue.full():
                finished = True

            if not self._trailers_to_fetch_queue.empty() and not iteration_successful:
                finished = True

            if not finished:
                if attempts % 10 == 0:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'hung reloading from._discovered_trailers_queue.',
                            'length of _discovered_trailers:',
                            len(self._discovered_trailers),
                            'length of._discovered_trailers_queue:',
                            self._discovered_trailers_queue.qsize(),
                            trace=Trace.TRACE)
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=0.5)

        stop_time = datetime.datetime.now()
        duration = stop_time - start_time
        self._load_fetch_total_duration += duration.seconds

        attempts = 0
        discovery_complete_queue_empty = 0
        discovered_and_fetch_queues_empty = 0
        discovery_incomplete_fetch_not_empty = 0
        discovery_incomplete_fetch_queue_empty = 0
        get_attempts = 0
        put_attempts = 0

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('took',
                               duration.seconds, 'seconds', trace=Trace.STATS)

    def get_from_fetch_queue(self, player_starving=False):
        # type: (bool) -> MovieType
        """

        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('starving:', player_starving)
        self.load_fetch_queue()
        trailer = None
        if self._trailers_to_fetch_queue.empty():
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(': empty')
        while trailer is None:
            try:
                if player_starving:
                    trailer = self.get_from_starvation_queue()
                if trailer is None:
                    trailer = self._trailers_to_fetch_queue.get(timeout=0.5)
            except (KodiQueue.Empty):
                Monitor.get_instance().throw_exception_if_shutdown_requested()

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(
                'Got:', trailer[Movie.TITLE], 'from fetch queue')

        return trailer

    def put_in_fetch_queue(self, trailer, timeout=None):
        # type: (MovieType, float) -> None
        """
            Simple wrapper around queue.put so that a debug message can
            be consistently issued on success. All exceptions to be handled
            by caller.

        :param trailer:
        :param timeout:
        :return:
        """
        self._trailers_to_fetch_queue.put(trailer, timeout=timeout)

    def get_from_starvation_queue(self):
        # type: () -> MovieType
        """

        :return:
        """
        movie = None
        try:
            if self._starvation_queue.empty():
                with self._discovered_trailers_lock:
                    # self._logger.debug('Have discovered_trailers_lock')

                    starvation_list = []
                    for movie in self._discovered_trailers:
                        if (movie[Movie.DISCOVERY_STATE] >=
                                Movie.DISCOVERY_READY_TO_DISPLAY):
                            starvation_list.append(movie)
                    DiskUtils.RandomGenerator.shuffle(starvation_list)
                    for movie in starvation_list:
                        # Should not block, but if it does, KodiQueue.Full exception
                        # will be thrown so we will know about it and not
                        # hang.
                        self._starvation_queue.put(movie, timeout=0.25)

            movie = None
            if not self._starvation_queue.empty():
                movie = self._starvation_queue.get()

        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())

        except (Exception) as e:
            self._logger.exception('')

        title = None
        if movie is not None:
            title = movie[Movie.TITLE]
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('movie:', title)
        return movie

    def get_discovered_trailer_queue_size(self):
        # type: () -> int
        """

            :return: int
        """

        return self._discovered_trailers_queue.qsize()

    def remove(self):
        # type: () -> None
        """
            The Discoverxx thread is being shutdown, perhaps due to changed
            settings.

        :return:
        """
        pass

    def increase_play_count(self, movie):
        # type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        self._discovered_trailers.increase_play_count(movie)

    def report_play_count_stats(self):
        # type: () -> None
        """

        :return:
        """
        self._discovered_trailers.report_play_count_stats()
