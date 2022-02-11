# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""


import datetime
import sys
import threading
from collections import OrderedDict

import xbmc

from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, DuplicateException
from common.imports import *
from common.kodi_queue import (KodiQueue)
from common.logger import *
from common.monitor import Monitor
from common.movie import BaseMovie, AbstractMovieId, AbstractMovie
from common.movie_constants import MovieField, MovieType
from diagnostics.play_stats import PlayStatistics
from discovery.trailer_fetcher_interface import TrailerFetcherInterface

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)

# The number of trailers to fully discover ahead of time. MUST be at least one
# but a bad idea to have < 3)

MOVIES_TO_PREFETCH: Final[int] = 3
LOCAL_TRAILERS_FOR_EACH_REMOTE: Final[int] = 2
INITIAL_LOCAL_TRAILERS_FOR_EACH_REMOTE: Final[int] = 4

local_trailers_for_each_remote: int = INITIAL_LOCAL_TRAILERS_FOR_EACH_REMOTE


class MovieSourceData:
    """

    """

    logger = None

    def __init__(self, movie_source: str) -> None:
        """

        :param movie_source:
        :return:
        """
        self.removed_trailers: int = 0
        self.number_of_added_movies: int = 0
        self.load_fetch_total_duration: int = 0
        self.discovery_complete: bool = False
        self.movie_source: str = movie_source


class UniqueQueue:
    """

    """
    logger: BasicLogger = None

    def __init__(self, maxsize: int = 0, movie_source: str = '') -> None:
        """
        :param maxsize:
        :param movie_source:
        :return:
        """
        clz = UniqueQueue
        if self.logger is None:
            self.logger = module_logger.getChild(clz.__name__)

        self._queue: Final[KodiQueue] = KodiQueue(maxsize)
        self.duplicate_check: Final[Set] = set()
        self._lock: Final[threading.RLock] = threading.RLock()
        self.movie_source: Final[str] = movie_source

    def __str__(self) -> str:
        return f'{self.movie_source} len: {self.qsize()}'
    
    def clear(self) -> None:
        """

        :return:
        """
        clz = UniqueQueue

        with self._lock:
            self.duplicate_check.clear()
            self._queue.clear()

            assert len(self.duplicate_check) == 0
            assert self._queue.empty()

    def put(self, movie: BaseMovie, block: bool = True,
            timeout: float = None) -> None:
        """

        :param movie:
        :param block:
        :param timeout:
        :return:
        """
        clz = UniqueQueue
        key = self.get_key(movie)

        # self.logger.debug(f'movie:{movie} source: {movie.get_source()} '
        #                   f'key: {key}')
        exception = None
        with self._lock:
            if key in self.duplicate_check:
                exception = DuplicateException()
            else:
                self._queue.put(movie, False)
                self.duplicate_check.add(key)

        if exception is not None:
            if self.logger.isEnabledFor(DEBUG_VERBOSE):
                self.logger.debug_verbose(f'Duplicate movie: {str(movie)} '
                                          f'source: {movie.get_source()} '
                                          f'key: {key}')
            raise exception

    def get(self, block: bool = True,
            timeout: float = None) -> BaseMovie:
        """

        :param block:
        :param timeout:
        :return:
        """
        clz = UniqueQueue
        with self._lock:
            try:
                movie: BaseMovie = None
                movie = self._queue.get(block=block, timeout=timeout)
                key = self.get_key(movie)
                self.duplicate_check.remove(key)
            except KeyError as e:
                if self.logger.isEnabledFor(DEBUG):
                    self.logger.debug(f'movie: {str(movie)} key: {key}')
                    self.logger.dump_stack(f'{str(movie)} '
                                           f'movie not found in duplicate_check for ',
                                           heading='')
        # if self.logger.isEnabledFor(DEBUG):
            # self.logger.debug('got movie:', item[Movie.TITLE], 'source:',
            #                    item[Movie.SOURCE], 'key:', key)
        return movie

    def qsize(self) -> int:
        """

        :return:
        """
        with self._lock:
            size: int = self._queue.qsize()

        # self.logger.debug('size:', size)
        return size

    def get_key(self, movie: BaseMovie) -> str:
        """

        :param movie:
        :return:
        """

        key: str = None
        movie_source = movie.get_source()
        key = movie_source + movie.get_id()

        return key

    def empty(self) -> bool:
        """

        :return:
        """
        # self.logger = self.logger.get_methodlogger('empty')

        with self._lock:
            empty = self._queue.empty()

        # self.logger.debug('empty:', empty)
        return empty

    def full(self) -> bool:
        """

        :return:
        """
        # self.logger = self.logger.get_methodlogger('full')

        with self._lock:
            full = self._queue.full()

        # self.logger.debug('full:', full)
        return full


class MovieList:
    """

    """
    logger: BasicLogger = None

    def __init__(self, movie_source: str) -> None:
        """
        :param movie_source:
        :return:
        """
        clz = MovieList

        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)

        self._movie_source: str = movie_source
        self._total_removed: int = 0
        self._play_count: Final[Dict[str, int]] = dict()
        self._lock: Final[threading.RLock] = threading.RLock()
        self._changed: bool = False
        self._number_of_added_movies: int = 0
        self._ordered_dict: OrderedDict = OrderedDict()

    def __str__(self):
        return f'{self._movie_source} len: {len(self._ordered_dict)}'

    def __sizeof__(self) -> int:
        approx_size: int = Debug.total_size(self._ordered_dict)
        return approx_size

    def clear(self) -> None:
        """

        :return:
        """
        clz = MovieList

        with self._lock:
            try:
                while self._ordered_dict.popitem() is not None:
                    pass
            except KeyError:
                pass
            if len(self._ordered_dict.items()) != 0:
                clz.logger.error('_ordered_dict not empty')
            self._number_of_added_movies = 0

        # clz.logger.debug()

    def add(self, movie: BaseMovie) -> None:
        """

        :param movie:
        :return:
        """
        clz = MovieList

        if self.logger.isEnabledFor(DISABLED):
            self.logger.debug_extra_verbose(f'movie: {movie.get_id()} '
                                            f'type: {type(movie)} '
                                            f'source: {movie.get_source()}')

        # Key is source + _ + id
        # Therefore if keys are identical, so are sources
        key = clz.get_key(movie)
        new_movie: bool = True
        dupe: bool = False
        with self._lock:
            if key in self._ordered_dict.keys():
                current_value = self._ordered_dict.get(key)
                dupe = True

                # If movies are from same source then complain about
                # duplicate, unless one is a movie id and the other
                # is a movie.

                if dupe:
                    if self.logger.isEnabledFor(DEBUG):
                        self.logger.debug(f'dupe: movie: {movie.get_id()} '
                                          f'type: {type(movie)} '
                                          f'from type: {type(current_value)} '
                                          f'source: {movie.get_source()}')
                    # self.logger.dump_stack(heading='', xbmc_level=xbmc.LOGDEBUG)

                        clz.logger.debug(f'Raising DuplicateException')
                        clz.logger.debug(f'isinstance current_value AbstractMovieId: '
                                         f'{isinstance(current_value, AbstractMovieId)}')
                        clz.logger.debug(f'isinstance current_value AbstractMovie: '
                                         f'{isinstance(current_value, AbstractMovie)}')
                        clz.logger.debug(f'isinstance movie AbstractMovieId: '
                                         f'{isinstance(movie, AbstractMovieId)}')
                        clz.logger.debug(f'isinstance movie AbstractMovie: '
                                         f'{isinstance(movie, AbstractMovie)}')
                    raise DuplicateException()

            # If we didn't raise Exception, then okay to add or replace
            self._ordered_dict[key] = movie
            self._number_of_added_movies += 1

            PlayStatistics.add(movie)

    def get_by_id(self, source: str, movie_id: str) -> BaseMovie:
        """

        :param source: Movie source- Movie.LIBRARY_SOURCE,
         Movie.TMDB_SOURCE, Movie.TFH_SOURCE, etc.

        :param movie_id: key appropriate for the movie source
               tmdb_id, tfh_id, itunes_id or library_id
        :return:
        """
        clz = type(self)
        key: str = source + str(movie_id)

        with self._lock:
            try:
                movie: BaseMovie = None
                movie = self._ordered_dict[key]

            except AbortException:
                reraise(*sys.exc_info())
            except KeyError:
                pass

            return movie

    def get_movies(self) -> List[BaseMovie]:
        with self._lock:
            movies: List[BaseMovie] = []
            movies.extend(self._ordered_dict.values())
            return movies

    def remove(self, movie: BaseMovie) -> None:
        """

        :param movie:
        :return:
        """
        clz = MovieList

        if movie is None:
            return

        if self.logger.isEnabledFor(DEBUG):
            self.logger.debug(f'movie: {movie.get_id()} type: {type(movie)} '
                              f'source: {movie.get_source()}')
            self.logger.dump_stack(heading='')
        with self._lock:
            try:
                del self._ordered_dict[clz.get_key(movie)]
                self._total_removed += 1

            except AbortException:
                reraise(*sys.exc_info())
            # except KeyError:  Let caller handle

    def len(self) -> int:
        """

        :return:
        """
        with self._lock:
            length = int(len(self._ordered_dict))

        return length

    def __len__(self) -> int:
        """

        :return:
        """
        return self.len()

    def shuffle(self) -> None:
        """

        :return:
        """
        clz = MovieList

        # self.logger.dump_stack(heading='', xbmc_level=xbmc.LOGDEBUG)

        with self._lock:
            items = list(self._ordered_dict.items())
            DiskUtils.RandomGenerator.shuffle(items)
            self._ordered_dict = OrderedDict(items)

    @staticmethod
    def get_key(movie: BaseMovie) -> str:
        """

        :param movie:
        :return:
        """

        key: str = movie.get_source() + '_' + str(movie.get_id())

        return key


class AbstractMovieData:
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/movie information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    logger: BasicLogger = None
    _aggregate_trailers_by_name_date_lock: threading.RLock = threading.RLock()
    _aggregate_trailers_by_name_date: Dict[str, BaseMovie] = dict()
    _first_load: bool = True

    def __init__(self, trailer_fetcher_class: Type[TrailerFetcherInterface],
                 movie_source: str = '') -> None:
        """
        """
        clz = type(self)
        clz.logger = module_logger.getChild(f'{clz.__name__}:{movie_source}')
        self._movies_discovered_event: threading.Event = threading.Event()
        self._movie_source_data: Dict[str, MovieSourceData] = {}
        self._removed_trailers: int = 0
        self._number_of_added_movies: int = 0
        self._load_fetch_total_duration: int = 0
        self._discovery_complete: bool = False
        self._discovery_complete_reported: bool = False
        self._last_shuffle_time: datetime.datetime = datetime.datetime.fromordinal(1)
        self._last_shuffled_size: int = 0
        self._discovered_movies_lock: threading.RLock = threading.RLock()

        #  Access via self._discovered_movies_lock

        # _discovered_movies is the primary source of all trailers,
        # (well, they do come from the library database or TMDb or from
        # the local cache, but as far as this application, the primary data
        # structure is _discovered_movies).
        self._discovered_movies: MovieList = MovieList(movie_source)

        # _discovered_movies_queue is filled up with movies (not copies of the
        # movies) from _discovered_movies. Any change should be reflected in
        # both places. When empty, or under other conditions,
        # _discovered_movies_queue is emptied and then filled with all of the
        # movies from _discovered_movies, after shuffling. Then, movies to
        # display trailers for are drawn from _discovered_movies_queue until
        # empty, or some other condition causes it to be refilled.

        self._discovered_movies_queue: UniqueQueue = UniqueQueue(
            maxsize=0, movie_source=movie_source)

        # _previously_discovered_movies_queue contains movies which appear to
        # have been previously discovered. The assumption is that if they were
        # discovered once, they are probably easier to discover again (in particular,
        # if the trailers and json data is cached). The purpose is to reduce the
        # chance that we have nothing to play because downloads are or discovery
        # is slow.
        #
        # We can have the policy that we fetch two trailers from the previously
        # discovered queue for every one (new) one from the _discovered_movies_queue.
        # This fits well since the capacity of the output queue is 3.

        self._previously_discovered_movies_queue: UniqueQueue = UniqueQueue(
            maxsize=0, movie_source=movie_source)
        self._fetch_count: int = 0

        # _movies_to_fetch_queue is a small queue that has movies that
        # trailers are actively being searched for. The small size limits
        # how many trailers are discovered ahead of time, but is large
        # enough to have a decent buffer from starving.

        self._movies_to_fetch_queue: KodiQueue = KodiQueue(maxsize=MOVIES_TO_PREFETCH)
        self._starvation_queue: KodiQueue = KodiQueue()
        self._movies_to_fetch_queueLock: threading.RLock = threading.RLock()
        self.stop_discovery_event: threading.Event = threading.Event()
        self._movie_source: str = movie_source

        if clz.logger.isEnabledFor(DEBUG):
            clz.logger.debug(f'movie_data: {self} instantiating trailer_fetcher: '
                             f'{trailer_fetcher_class}')
        self._parent_trailer_fetcher: TrailerFetcherInterface = \
            trailer_fetcher_class(movie_data=self)
        self._minimum_shuffle_seconds: int = 10

    def get_size_of(self) -> int:
        size_of_discovered_movies: int = Debug.total_size(self._discovered_movies,
                                                          verbose=True)
        return size_of_discovered_movies

    def start_trailer_fetchers(self) -> None:
        """

        :return:
        """
        self._parent_trailer_fetcher.start_fetchers()

    def stop_discovery(self):
        self.stop_discovery_event.set()
        self.stop_trailer_fetchers()

    def stop_trailer_fetchers(self) -> None:
        #  Removes and joins trailer fetcher threads
        if self._parent_trailer_fetcher is not None:
            self._parent_trailer_fetcher.stop_fetchers()

    def get_movie_source(self) -> str:
        """

        :return:
        """
        return self._movie_source

    def destroy(self) -> None:
        """
        :return:
        """
        clz = type(self)

        if clz.logger.isEnabledFor(DEBUG_VERBOSE):
            clz.logger.debug_verbose('Entered')

        with self._discovered_movies_lock:
            self.stop_discovery_event.set()
            self._parent_trailer_fetcher.destroy()
            self._movies_discovered_event.clear()
            self._removed_trailers = 0
            self._number_of_added_movies = 0
            self._load_fetch_total_duration = 0
            self._discovery_complete = False
            self._last_shuffle_time = datetime.datetime.fromordinal(1)
            self._last_shuffled_size = 0
            self._discovered_movies.clear()
            self._discovered_movies_queue.clear()
            self._previously_discovered_movies_queue.clear()
            self._discovery_complete = True

            self._movie_source_data = {}
            self._movies_to_fetch_queue.clear()
            self._starvation_queue.clear()

    def finished_discovery(self) -> None:
        """

        :return:
        """
        clz = type(self)

        with self._discovered_movies_lock:
            clz = type(self)
            clz.logger.debug('Finished discovery')
            self.shuffle_discovered_movies(mark_unplayed=False)
            self._discovery_complete = True

    def is_discovery_complete(self) -> bool:
        """

        :return:
        """
        return self._discovery_complete

    @classmethod
    def get_aggregate_trailers_by_name_date_lock(cls) -> threading.RLock:
        """

        :return:
        """
        return cls._aggregate_trailers_by_name_date_lock

    @classmethod
    def get_aggregate_trailers_by_name_date(cls) -> Dict[str, BaseMovie]:
        """

        :return:
        """
        return cls._aggregate_trailers_by_name_date

    def get_by_id(self, movie_id: str) -> BaseMovie:
        movie: BaseMovie = None
        with self._discovered_movies_lock:
            movie = self._discovered_movies.get_by_id(self._movie_source, movie_id)
        return movie

    def add_to_discovered_movies(self,
                                 movies: Union[BaseMovie, MovieType,
                                               Iterable[BaseMovie]]) -> None:
        """

        :param movies:
        :return:
        """
        clz = type(self)
        movies: List[BaseMovie] = BaseMovie.convert_to_movie(movies)

        movies_added: bool = False
        with self._discovered_movies_lock:
            #  if clz.logger.isEnabledFor(DEBUG):
            #     clz.logger.debug('Have discovered_movies_lock')
            movie: BaseMovie
            for movie in movies:
                if clz.logger.isEnabledFor(DISABLED):
                    clz.logger.debug_extra_verbose(f' {str(movie)} '
                                                   f'source: {movie.get_source()} '
                                                   f'discovery_state: '
                                                   f'{movie.get_discovery_state()} ')
                # Assume more discovery is required for movie details, etc.

                try:
                    self._discovered_movies.add(movie)
                except DuplicateException as e:
                    # if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                    #     clz.logger.debug_extra_verbose(
                    #                        'Ignoring duplicate movie:',
                    #                        movie[Movie.TITLE])
                    continue

                movies_added = True
                self._number_of_added_movies += 1
                movie.set_trailer_played(False)

            if self._discovered_movies.len() > 0:
                self._movies_discovered_event.set()

            seconds_since_last_shuffle: int = (
                datetime.datetime.now() - self._last_shuffle_time).seconds

        reshuffle: bool = False
        # Reshuffle every minute or when there is a 20% change

        last_shuffled_at_size = self._last_shuffled_size
        current_size = len(self._discovered_movies)
        if (movies_added
                and (current_size > 25
                     and current_size >= (last_shuffled_at_size * 2)
                     or (seconds_since_last_shuffle >
                         self.get_minimum_shuffle_seconds()))):
            reshuffle = True

        if reshuffle:
            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(
                    f'seconds_since_last_shuffle: {seconds_since_last_shuffle} '
                    f'current size: {current_size} '
                    f'previous size: {last_shuffled_at_size}',
                    trace=Trace.TRACE_DISCOVERY)

            self.shuffle_discovered_movies(mark_unplayed=False)

    def replace(self, movie: Union[BaseMovie, MovieType]) -> None:
        """
            Replace a MovieId with a MovieType or visa versa. Done
            to save space, or to add newly discovered information.

        :param movie:
        :return:
        """
        clz = type(self)
        with self._discovered_movies_lock:
            try:
                self._discovered_movies.add(movie)
            except DuplicateException:
                pass  # Expected

    def purge_rediscoverable_data(self, movie: AbstractMovie) -> AbstractMovieId:
        #
        # Used to clear out fully populated movie data and just keep movieid.
        # This keeps tables from continually growing. When caching is enabled
        # the data is locally available and not too expensive to rediscover.

        pass

    def have_trailers_been_discovered(self) -> bool:
        """

        :return:
        """
        clz = type(self)
        # clz.logger.debug(f'{self._movies_discovered_event.is_set()}')
        return self._movies_discovered_event.isSet()

    def shuffle_discovered_movies(self, mark_unplayed: bool = False) -> None:
        """

        :param mark_unplayed:
        :return:
        """
        clz = type(self)

        Monitor.throw_exception_if_abort_requested()
        # clz.logger.debug('before self.lock')

        with self._discovered_movies_lock:
            # clz.logger.debug('Have discovered_movies_lock')

            if self._discovered_movies.len() == 0:
                return

            self._discovered_movies.shuffle()
            if mark_unplayed:
                # Force starvation queue to be rebuilt

                self._starvation_queue.clear()
                for movie in self._discovered_movies.get_movies():
                    movie.set_trailer_played(False)

            # Drain anything previously in queue

            self._discovered_movies_queue.clear()
            self._previously_discovered_movies_queue.clear()

            Monitor.throw_exception_if_abort_requested()
            # clz.logger.debug('reloading _discovered_movies_queue')
            movies_with_local_trailers: List[BaseMovie] = []
            movies_with_remote_trailers: List[BaseMovie] = []
            for movie in self._discovered_movies.get_movies():
                if isinstance(movie, AbstractMovieId) or not movie.is_trailer_played():
                    # if clz.logger.isEnabledFor(DEBUG):
                    #   clz.logger.debug('adding', movie[Movie.TITLE],
                    #                      'id:', hex(id(movie)),
                    #                      'to discovered_movies_queue',
                    #                      'state:', movie[Movie.DISCOVERY_STATE])

                    # When a movie has been previously played, then it is likely
                    # much easier/quicker to prepare it for viewing. By segregating
                    # movies according to whether they are likely to be quick to
                    # ready them for playing a trailer for or not means that we may
                    # be able to avoid long periods of not playing trailers while
                    # we are finding a movie with a playable trailer.

                    if movie.has_local_trailer():
                        movies_with_local_trailers.append(movie)
                    elif movie.get_has_trailer():
                        movies_with_remote_trailers.append(movie)
                    else:
                        self._discovered_movies_queue.put(movie)

            # To help out with startup, make sure a few local trailers
            # are at the beginning of the queue

            try:
                for i in range(1, 10):
                    movie: BaseMovie = movies_with_local_trailers.pop(0)
                    self._previously_discovered_movies_queue.put(movie)
                    movie: BaseMovie = movies_with_local_trailers.pop(0)
                    self._previously_discovered_movies_queue.put(movie)
                    movie: BaseMovie = movies_with_remote_trailers.pop(0)
                    self._previously_discovered_movies_queue.put(movie)
            except IndexError:
                pass

            # Just mix up the rest

            biggest_list: List[BaseMovie]
            smallest_list: List[BaseMovie]
            if len(movies_with_local_trailers) > len(movies_with_remote_trailers):
                biggest_list = movies_with_local_trailers
                smallest_list = movies_with_remote_trailers
            else:
                biggest_list = movies_with_remote_trailers
                smallest_list = movies_with_local_trailers

            # Joy, another shuffle. I'm sure this could be made more
            # efficient.

            biggest_list.extend(smallest_list)
            DiskUtils.RandomGenerator.shuffle(biggest_list)
            del smallest_list

            for movie in biggest_list:
                self._previously_discovered_movies_queue.put(movie)

            # See comment in get_candidate_movie
            self._fetch_count = 0

            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                seconds_since_last_shuffle: int = (
                        datetime.datetime.now() - self._last_shuffle_time).seconds
                last_shuffled_at_size = self._last_shuffled_size
                current_size = len(self._discovered_movies)
                clz.logger.debug_extra_verbose(
                    f'seconds_since_last_shuffle: {seconds_since_last_shuffle} '
                    f'current size: {current_size} '
                    f'previous size: {last_shuffled_at_size}'
                    f'_discovered_movies_queue length: '
                    f'{self._discovered_movies_queue.qsize()} '
                    f'_previously_discovered_movies_queue length: '
                    f'{self._previously_discovered_movies_queue.qsize()}',
                    trace=Trace.TRACE_DISCOVERY)

            self._last_shuffled_size = self._discovered_movies.len()
            self._last_shuffle_time = datetime.datetime.now()

    def get_number_of_movies(self) -> int:
        """

        :return:
        """
        return self._discovered_movies.len()

    def get_number_of_added_movies(self) -> int:
        """

        :return:
        """
        return int(self._number_of_added_movies)

    def get_number_of_trailers(self) -> int:
        """
        Gets the number of known trailers so far. Note that this value can
        change up or down depending upon further discovery.

        :return:
        """
        number_of_trailers: int = 0
        with self._discovered_movies_lock:
            movie: BaseMovie
            for movie in self._discovered_movies.get_movies():
                if movie.get_has_trailer():
                    number_of_trailers += 1

        return number_of_trailers

    def get_playable_trailer_immediately(self) -> AbstractMovie:
        """
        Called when the player is desperate to find something to play.
        Not very likely to succeed when Constants.SAVE_MEMORY is True
        (the default) since very few AbstractMovie instances will be present.

        It would not be very expensive to use AbstractMovieId instances
        that has_local_trailer, but would require a bit more care to
        handle the edge cases within playable_trailers_container thread.
        You probably would want to have separate trailer_fetcher threads
        just to handle this (separate threads would not disturb other
        fetching activity).

        """
        clz = type(self)
        with self._discovered_movies_lock:
            movie: BaseMovie
            for movie in self._discovered_movies.get_movies():
                if isinstance(movie, AbstractMovieId):
                    movie_id: AbstractMovieId
                    movie_id = movie
                    if movie_id.has_local_trailer():
                        pass  # Perhaps send to separate TrailerFetcher thread
                if isinstance(movie, AbstractMovie):
                    the_movie: AbstractMovie = movie
                    if (the_movie.get_discovery_state() ==
                            MovieField.DISCOVERY_READY_TO_DISPLAY):
                        clz.logger.debug(f'Found trailer: {the_movie}')
                        return the_movie

        return None

    def is_any_likely_playable(self) -> bool:
        """
        Scans the (partially) discovered movies to see if there are any
        that appear to have a trailer that we can play.
        """
        clz = type(self)

        with self._discovered_movies_lock:
            movie: BaseMovie
            for movie in self._discovered_movies.get_movies():
                if movie.has_local_trailer():
                    return True
        return False

    def get_projected_number_of_trailers(self) -> int:
        """
        Project the number of trailers that will be discovered based upon
        what has been discovered so far.

        :return:
        """
        clz = type(self)
        success_ratio = 1.0
        if self._removed_trailers > 100:
            success_ratio = (self._number_of_added_movies - self._removed_trailers) /\
                self._number_of_added_movies
            # if clz.logger.isEnabledFor(DEBUG_VERBOSE):
            #     clz.logger.debug_verbose('movies discovered:',
            #                                self._number_of_added_movies,
            #                                'movies without trailers:',
            #                                self._removed_trailers)
        number_of_movies = self.get_number_of_movies()
        projected_number_of_trailers = success_ratio * number_of_movies
        if self._number_of_added_movies < self._removed_trailers:
            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(f'added: {self._number_of_added_movies} '
                                               f'removed: {self._removed_trailers} '
                                               f'projected_number_of_trailers: '
                                               f'{projected_number_of_trailers}')
        return int(projected_number_of_trailers)

    def get_trailers_to_fetch_queue_size(self) -> int:
        """

        :return:
        """
        return self._movies_to_fetch_queue.qsize()

    def get_number_of_removed_trailers(self) -> int:
        """

        :return:
        """

        return int(self._removed_trailers)

    def remove_discovered_movie(self, movie: BaseMovie) -> None:
        """
            When a trailer can not be found for a movie, then we need to remove it
            so that we don't keep looking for it.

        :param movie: Can be an AbstractMovie or an AbstractMovieId
        :return:
        """
        clz = type(self)
        Monitor.throw_exception_if_abort_requested()
        with self._discovered_movies_lock:
            # clz.logger.debug('Have discovered_movies_lock')

            base_movie: BaseMovie = None
            try:
                source = movie.get_source()
                movie_id = movie.get_id()
                if clz.logger.isEnabledFor(DEBUG):
                    clz.logger.debug(f'Removing {source} {movie_id}')
                base_movie = self._discovered_movies.get_by_id(source, movie_id)
            except ValueError:  # Already deleted
                if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                    clz.logger.debug_verbose(
                        f'Movie appears to already be removed: {movie}')

            if base_movie is not None:
                try:
                    self._discovered_movies.remove(base_movie)
                    self._removed_trailers += 1
                    if clz.logger.isEnabledFor(DISABLED):
                        clz.logger.debug(f' : {movie} '
                                         f'removed: {self._removed_trailers} remaining: '
                                         f'{self.get_number_of_movies()}')
                except KeyError:
                    # Already deleted
                    pass

                if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                    try:
                        key = self._discovered_movies_queue.get_key(base_movie)
                        if key in self._discovered_movies_queue.duplicate_check:
                            clz.logger.debug_extra_verbose(
                                f'Deleted movie still in fetch queue. Movie: '
                                f'{base_movie}')
                    except ValueError:  # Already deleted
                        pass

    def load_fetch_queue(self) -> None:
        """
            Load the _movies_to_fetch_queue from either _discovered_movies_queue
            or _previously_discovered_movies_queue

            If _movies_to_fetch_queue is full, then return

            If discoveryComplete and _discovered_movies is empty,
            then return

            If discoveryComplete and both _discovered_movies_queue and
            _previously_discovered_movies_queue are empty,
            then shuffle _discovered_movies and fill the _movies_to_fetch_queue
            from it. If there are not enough items to fill the fetch queue,
            then get as many as are available.

            Otherwise, discoveryComplete == False:

            If both _discovered_movies_queue and _previously_discovered_movies_queue
            are empty and _movies_to_fetch_queue
            is not empty, then return without loading any.

            If both _discovered_movies_queue and _previously_discovered_movies_queue
            are empty and _movies_to_fetch_queue is empty
            then block until an item becomes available or discoveryComplete == True.

            Finally, if _movies_to_fetch_queue is not full, fill it from any available
            items from _discovered_movies_queue.
        :return:
        """
        clz = type(self)
        start_time: datetime.datetime.time = datetime.datetime.now()
        if AbstractMovieData._first_load:
            Monitor.wait_for_abort(timeout=2.0)
            AbstractMovieData._first_load = False

        Monitor.throw_exception_if_abort_requested()
        finished: bool = False
        attempts: int = 0
        discovery_complete_queue_empty: int = 0
        discovered_and_fetch_queues_empty: int = 0
        discovery_incomplete_fetch_not_empty: int = 0
        discovery_incomplete_fetch_queue_empty: int = 0
        get_attempts: int = 0
        put_attempts: int = 0
        while not finished:
            movie: BaseMovie = None
            Monitor.throw_exception_if_abort_requested()
            attempts += 1
            shuffle: bool = False
            iteration_successful = False
            try:
                elapsed: datetime.timedelta = datetime.datetime.now() - start_time
                discovered_movies_queues_empty: bool = False
                #
                # No point doing anything if no movies have passed the initial
                # discovery phase. (discovered_movies_queue)
                #
                if (self._discovered_movies_queue.empty() and
                        self._previously_discovered_movies_queue.empty()):
                    discovered_movies_queues_empty = True

                if attempts > 0:
                    if (attempts > 1
                            and clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
                        clz.logger.debug_extra_verbose(f'Attempt: {attempts} '
                                                       f'elapsed: {elapsed.seconds}')

                if self._movies_to_fetch_queue.full():

                    # If the output queue to the fetch stage is full, then leave

                    if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose('_movies_to_fetch_queue full',
                                                       trace=Trace.TRACE)
                    finished = True
                    iteration_successful = True
                    continue

                if self._discovery_complete:
                    # First phase discovery complete. Simply play trailers from what
                    # we already have info on, if any.
                    #
                    if len(self._discovered_movies) == 0:
                        #
                        # No movies will ever be discovered, give up
                        #
                        if (not self._discovery_complete_reported and
                                clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
                            self._discovery_complete_reported = True
                            clz.logger.debug_extra_verbose(
                                    'Discovery Complete and nothing found.',
                                    trace=Trace.TRACE)
                        finished = True
                        iteration_successful = True
                        continue

                    if discovered_movies_queues_empty:
                        #
                        # Reload our discovery queues from the master
                        # list of discovered movies, after reshuffling

                        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                f'discoveryComplete and discovered_movies_queues empty',
                                trace=Trace.TRACE)
                        shuffle = True
                        discovery_complete_queue_empty += 1
                    else:
                        # The discovered_movies_queues are not empty, meaning that
                        # We can load the fetch queue from them.
                        #
                        # Drop through to the point where you see:
                        #       if not iteration_successful:
                        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                f'discoveryComplete and discovered_movies_queues NOT '
                                f'empty',
                                trace=Trace.TRACE)
                        pass

                else:
                    #
                    # In the following, Discovery is INCOMPLETE
                    #
                    if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'Discovery incomplete',
                            trace=Trace.TRACE)
                    if discovered_movies_queues_empty:
                        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'discovered_movies_queues empty',
                                trace=Trace.TRACE)
                        if not self._movies_to_fetch_queue.empty():

                            # Nothing available to add to fetch queue, but fetch queue
                            # is not starving yet. Skip this round.

                            discovered_and_fetch_queues_empty += 1
                            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                                clz.logger.debug_extra_verbose(
                                    '_movies_to_fetch_queue not empty',
                                    trace=Trace.TRACE)
                            finished = True
                            continue
                        else:
                            # Discovery incomplete, discovery and fetch queue are empty.
                            # Don't mark as finished, which will trigger a
                            # reshuffle and reloading of the discovery queues from
                            # the master list of trailers found in first-phase of
                            # discovery. Once the queues are reloaded, this loop will
                            # try again.

                            discovery_incomplete_fetch_queue_empty += 1
                            shuffle = True
                            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                                clz.logger.debug_extra_verbose('_movies_to_fetch_queue'
                                                               ' empty, '
                                                               'reshuffle should occur',
                                                               trace=Trace.TRACE)
                    else:  # discovered_queues Not empty
                        starving: bool = self._movies_to_fetch_queue.empty()
                        if starving:
                            discovery_incomplete_fetch_queue_empty += 1
                            if clz.logger.isEnabledFor(DEBUG):
                                clz.logger.debug(f'discovered_queues not empty '
                                                 f'starving: {starving}')
                        else:
                            discovery_incomplete_fetch_not_empty += 1

                        movie = self.get_candidate_movie(starving=starving)

                        if movie is not None:
                            try:
                                self.put_in_fetch_queue(
                                    movie, timeout=1)
                                if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                                    clz.logger.debug_verbose(f'Put in '
                                                       f'_movies_to_fetch_queue qsize: '
                                                       f'{self._movies_to_fetch_queue.qsize()} '
                                                       f'{movie.get_title()} '
                                                       f'{movie.get_id}',
                                                       trace=Trace.TRACE)
                                iteration_successful = True
                            except KodiQueue.Full:
                                #
                                # It is not a crisis if the put fails. Since the
                                # fetch queue does have at least one entry, we are ok
                                # Even if the movie is lost from the FetchQueue,
                                # it will get reloaded once the queue is exhausted.
                                #
                                # But since iteration_successful is not true, we might
                                # still fix it at the end.
                                #
                                if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                                    clz.logger.debug_extra_verbose(
                                        '_movies_to_fetch_queue.put failed',
                                        trace=Trace.TRACE)

                if not iteration_successful:
                    # Failed to get a candidate movie to do further discovery
                    # Is a queue empty, needing re-filling?

                    # No point shuffling if nothing discoverd
                    clz.logger.debug(f'iteration NOT successful')

                    #  TODO: need complete decision tree

                    if len(self._discovered_movies) > 0:
                        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug(f'discovered_movies '
                                             f'{self._discovered_movies}')

                        # No point shuffling due to empty discovered_movies_queue
                        # When there will be none added to that queue
                        if (self._previously_discovered_movies_queue.empty()
                                and self.is_any_likely_playable()):
                            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                                self.logger.debug(f'previously_discovered_movies_queue '
                                                  f'empty and '
                                                  f'is_any_likely_playable')
                            shuffle = True
                        elif self._discovered_movies_queue.empty():
                            # Since there are discovered trailers AND none
                            # of them are likely playable then the rest
                            # must require further discovery. Shuffle if
                            # that queue empty
                            if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                                self.logger.debug(f'discovered_movies_queue_empty')
                            shuffle = True
                        else:
                            clz.logger.warning(f'LOGIC error: discovered movies '
                                               f'but none picked for further '
                                               f'discovery: '
                                               f'previously_discovered empty: '
                                               f'{self._previously_discovered_movies_queue.empty()} '
                                               f'likely_playable: '
                                               f'{self.is_any_likely_playable()} '
                                               f'discovered_movies empty: '
                                               f'{self._discovered_movies_queue.empty()}')

                    if shuffle:  # Because we were empty
                        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'Shuffling due to empty _discovered_movies_queue')
                        Monitor.throw_exception_if_abort_requested()
                        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'load_fetch_queue Shuffling because '
                                'discovered_movies_queue empty',
                                trace=Trace.TRACE_DISCOVERY)
                        self.shuffle_discovered_movies(mark_unplayed=True)

                    if movie is None:
                        get_finished: bool = False
                        while not get_finished:
                            try:
                                get_attempts += 1
                                with self._discovered_movies_lock:
                                    # clz.logger.debug_verbose(
                                    # 'Have discovered_movies_lock')

                                    movie = self.get_candidate_movie()
                                get_finished = True
                            except KodiQueue.Empty:
                                Monitor.throw_exception_if_abort_requested()

                    put_finished: bool = False
                    while not put_finished:
                        try:
                            put_attempts += 1
                            self.put_in_fetch_queue(movie, timeout=0.25)
                            put_finished = True
                        except KodiQueue.Full:
                            Monitor.throw_exception_if_abort_requested()
                        iteration_successful: bool = True

                '''
                if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                    if movie is not None:
                        movie_title = movie.get(Movie.TITLE)
                    else:
                        movie_title = 'no movie'
                        
                    clz.logger.debug_verbose('Queue has:',
                                        self._movies_to_fetch_queue.qsize(),
                                        'Put in _movies_to_fetch_queue:', movie_title)
                '''
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                clz.logger.exception('')
                # TODO Continue?

            if self._movies_to_fetch_queue.full():
                finished = True

            if not self._movies_to_fetch_queue.empty() and not iteration_successful:
                finished = True

            if not finished:
                if attempts % 10 == 0:
                    if clz.logger.isEnabledFor(DEBUG):
                        clz.logger.debug(
                            f'hung reloading from _discovered_movies_queue. '
                            f'length of _discovered_movies: '
                            f'{len(self._discovered_movies)} '
                            f'length of._discovered_movies_queue: '
                            f'{self._discovered_movies_queue.qsize()}',
                            trace=Trace.TRACE)
                Monitor.throw_exception_if_abort_requested(timeout=0.5)

        stop_time: datetime.datetime.time = datetime.datetime.now()
        duration: datetime.timedelta = stop_time - start_time
        self._load_fetch_total_duration += duration.seconds

        # if clz.logger.isEnabledFor(DEBUG_VERBOSE):
        #     clz.logger.debug_verbose('took', duration.seconds,
        #                              'seconds', trace=Trace.STATS)

    def get_candidate_movie(self, starving: bool = False) -> BaseMovie:
        # Fetch queue is not empty, nor full. Discovery
        # is not complete. Get something from either
        # discovered_movies_queue or previously_discovered_movies_queue,
        # if available

        movie: BaseMovie = None
        clz = type(self)
        try:
            with self._discovered_movies_lock:
                # clz.logger.debug_verbose('Have discovered_movies_lock')

                # When we start out and may not have a large number of
                # trailers downloaded and ready to go. For this reason,
                # try to prepare a few easy to prepare
                # trailers for viewing (to keep from black screens). Over
                # time, the % of these will grow, so we can back off
                # how many we intentionally add.
                #
                # TThe Trailer fetcher queue holds 3, meaning that the trailer
                # fetcher can get three trailers ahead of what is playing.
                #
                # The PlayableTrailerService & PlayableTrailerContainer have
                # a queue, which gives more buffer room. The Front-End
                # service always fetches one ahead. Further, the front-end
                # has a history queue that can bue used if the back-end is not
                # forthcoming with trailers fast enough. Also, PlayableTrailersService
                # and PlayableTrailersContainer keeps a history of recently
                # processed Trailers that can be used if the back-end is too
                # slow.
                #
                # All this means is that there is some wiggle room for trailer
                # trailer to play.
                #
                # So, we start off playing four trailers that we know ahead of
                # time are local. Then we discover a trailer which has no
                # known local trailer.
                #
                # There is a problem with the approach, which was seen with 1,400
                # trailers (all but about 10 non-local, or unknown if they were
                # local). A bug in the front-end caused it to discard trailers
                # which it had played too recently. In this scenario, the
                # front-end was starving (blak screen) waiting to get a
                # new trailer. The Back-End noticed that starvation was
                # occurring (it could not prepare trailers fast enough for
                # the front-end). Because of the starvation, the backend
                # (the TrailerFetcher would force a reshuffle of all of the
                # movies/trailers and, once again, give priority to playing
                # the known trailers which were local. This resulted in
                # new trailers either never being discovered, or very slowly.
                #
                # After playing 20 trailers this way, the mix is changed to
                # Three trailers that are known to be local for every one that
                # is not.
                #
                # By adding one to count, which is 0 based, we make sure that
                # first two trailers are biased to be from movies that are
                # most likely to be inexpensive to prepare for playing.

                if self._fetch_count < 200:
                    local_trailers_for_each_remote = INITIAL_LOCAL_TRAILERS_FOR_EACH_REMOTE
                elif self._fetch_count < 300:
                    local_trailers_for_each_remote = LOCAL_TRAILERS_FOR_EACH_REMOTE
                else:
                    local_trailers_for_each_remote = 1

                prefer_undiscovered: bool = ((self._fetch_count + 1) %
                                             local_trailers_for_each_remote) == 0
                prefer_previously_discovered: bool
                prefer_previously_discovered = (starving
                                                or not prefer_undiscovered)

                if (prefer_previously_discovered
                        and not
                        self._previously_discovered_movies_queue.empty()):
                    movie = self._previously_discovered_movies_queue.get(
                        timeout=0.25)
                    if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug(f'fetch_count: {self._fetch_count} '
                                         f'prev_discovered movie: {movie} '
                                         f'{movie.get_id()}')
                    self._fetch_count += 1
                else:
                    movie = self._discovered_movies_queue.get(timeout=0.25)
                    if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug(f'fetch_count: {self._fetch_count} '
                                         f'discovered movie: {movie}')
                    self._fetch_count += 1

            # if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            #     clz.logger.debug_extra_verbose(f'Got {movieget_title()} '
            #                         f'from _discovered_movies_queue')
        except KodiQueue.Empty:
            pass

        return movie

    def get_from_fetch_queue(self, player_starving: bool = False) -> BaseMovie:
        """

        :return:
        """
        clz = type(self)
        # if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
        #     clz.logger.debug_extra_verbose('starving:', player_starving)
        self.load_fetch_queue()
        movie: BaseMovie = None
        if self._movies_to_fetch_queue.empty():
            if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                clz.logger.debug_verbose(': empty')
        while movie is None:
            try:
                if player_starving:
                    movie = self.get_from_starvation_queue()
                if movie is None:
                    movie = self._movies_to_fetch_queue.get(timeout=0.5)
            except KodiQueue.Empty:
                Monitor.throw_exception_if_abort_requested()

        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(
                f'Got: {movie}')

        return movie

    def put_in_fetch_queue(self, movie: BaseMovie,
                           timeout: float = None) -> None:
        """
            Simple wrapper around queue.put so that a debug message can
            be consistently issued on success. All exceptions to be handled
            by caller.

        :param movie:
        :param timeout:
        :return:
        """
        clz = type(self)
        self._movies_to_fetch_queue.put(movie, timeout=timeout)

    def get_from_starvation_queue(self) -> BaseMovie:
        """

        :return:
        """
        clz = type(self)
        movie: BaseMovie = None
        try:
            if self._starvation_queue.empty():
                with self._discovered_movies_lock:
                    # clz.logger.debug('Have discovered_movies_lock')

                    starvation_list: List[BaseMovie] = []
                    for movie in self._discovered_movies.get_movies():
                        if ((movie.get_discovery_state() >=
                             MovieField.DISCOVERY_READY_TO_DISPLAY)
                                or movie.is_been_fully_discovered()
                                or movie.has_local_trailer()):
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

        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            clz.logger.exception('')

        title = None
        if movie is not None:
            title = movie.get_title()
        if clz.logger.isEnabledFor(DEBUG_VERBOSE):
            clz.logger.debug_verbose(f'movie: {title}')
        return movie

    def get_discovered_trailer_queue_size(self) -> int:
        """

            :return: int
        """

        return (self._discovered_movies_queue.qsize() +
                self._previously_discovered_movies_queue.qsize())

    def remove(self) -> None:
        """
            The Discoverxx thread is being shutdown, perhaps due to changed
            settings.

        :return:
        """
        pass
        clz = type(self)
        # self._movies_discovered_event: threading.Event = threading.Event()
        self._movie_source_data = {}
        # self._removed_trailers: int = 0
        # self._number_of_added_movies: int = 0
        # self._load_fetch_total_duration: int = 0
        # self._discovery_complete: bool = False
        # self._discovery_complete_reported: bool = False
        # self._last_shuffle_time: datetime.datetime = datetime.datetime.fromordinal(1)
        # self._last_shuffled_size: int = -1
        # self._discovered_movies_lock: threading.RLock = threading.RLock()

        #  Access via self._discovered_movies_lock

        # _discovered_movies is the primary source of all trailers,
        # (well, they do come from the library database or TMDb or from
        # the local cache, but as far as this application, the primary data
        # structure is _discovered_movies).
        self._discovered_movies = MovieList(self._movie_source)

        # _discovered_movies_queue is filled up with movies (not copies of the
        # movies) from _discovered_movies. Any change should be reflected in
        # both places. When empty, or under other conditions,
        # _discovered_movies_queue is emptied and then filled with all of the
        # movies from _discovered_movies, after shuffling. Then, movies to
        # display trailers for are drawn from _discovered_movies_queue until
        # empty, or some other condition causes it to be refilled.

        self._discovered_movies_queue.clear()
        self._movies_to_fetch_queue.clear()
        self._starvation_queue.clear()
        # self._movies_to_fetch_queueLock
        # self.stop_discovery_event: threading.Event = threading.Event()
        # self._movie_source: str = movie_source

        # fetcher_thread_name: Final[str] = 'Fetcher_' + movie_source
        # from discovery.trailer_fetcher import AbstractTrailerFetcher
        # self._minimum_shuffle_seconds: int = 10

    def increase_play_count(self, movie: BaseMovie) -> None:
        """

        :param movie:
        :return:
        """
        PlayStatistics.increase_play_count(movie)

    def get_minimum_shuffle_seconds(self) -> int:
        seconds: int = self._minimum_shuffle_seconds
        if self._minimum_shuffle_seconds < 60:
            self._minimum_shuffle_seconds += self._minimum_shuffle_seconds

        return seconds
