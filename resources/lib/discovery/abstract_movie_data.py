# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""


from collections import OrderedDict
import threading
import sys
import datetime

from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, DuplicateException, reraise
from common.imports import *
from common.kodi_queue import (KodiQueue)
from common.monitor import Monitor
from common.logger import (Trace, LazyLogger)
from common.movie import BaseMovie, AbstractMovieId, AbstractMovie, TFHMovie
from common.movie_constants import MovieField, MovieType
from diagnostics.play_stats import PlayStatistics

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


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
    logger: LazyLogger = None

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
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.debug_verbose(f'Duplicate movie: {str(movie)} '
                                          f'source: {movie.get_source()} ',
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
                if self.logger.isEnabledFor(LazyLogger.DEBUG):
                    self.logger.debug(f'movie: {str(movie)} key: {key}')
                    self.logger.dump_stack(f'{str(movie)} '
                                           f'movie not found in duplicate_check for '
                                           f'')
        # if self.logger.isEnabledFor(LazyLogger.DEBUG):
            # self.logger.debug('got movie:', item[Movie.TITLE], 'source:',
            #                    item[Movie.SOURCE], 'key:', key)
        return movie

    def qsize(self) -> int:
        """

        :return:
        """
        with self._lock:
            size: int = int(self._queue.qsize())

        # self.logger.exit('size:', size)
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

        # self.logger.exit('empty:', empty)
        return empty

    def full(self) -> bool:
        """

        :return:
        """
        # self.logger = self.logger.get_methodlogger('full')

        with self._lock:
            full = self._queue.full()

        # self.logger.exit('full:', full)
        return full


class MovieList:
    """

    """
    logger: ClassVar[LazyLogger] = None

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

    def __sizeof__(self) -> int:
        approx_size: int =  Debug.total_size(self._ordered_dict)
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

        # clz.logger.exit()

    def add(self, movie: BaseMovie) -> None:
        """

        :param movie:
        :return:
        """
        clz = MovieList

        if self.logger.isEnabledFor(LazyLogger.DISABLED):
            self.logger.debug(f'movie: {movie} source: {movie.get_source()}')

        # Key is source + _ + id
        # Therefore if keys are identical, so are sources
        key = clz.get_key(movie)
        new_movie: bool = True
        with self._lock:
            if key in self._ordered_dict.keys():
                current_value = self._ordered_dict.get(key)
                new_movie = False
                # Movies are from same source then complain about
                # duplicate, unless one is a movie id and the other
                # is a movie.

                if (not (isinstance(current_value, AbstractMovieId)
                         and isinstance(movie, AbstractMovie))
                        or not (isinstance(current_value, AbstractMovie)
                                and isinstance(movie, AbstractMovieId))):
                    raise DuplicateException()

            # If we didn't raise Exception, then okay to add or replace
            self._ordered_dict[key] = movie
            if new_movie:
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

    def get_movies(self) -> ValuesView[BaseMovie]:
        return self._ordered_dict.values()

    def remove(self, movie: BaseMovie) -> None:
        """

        :param movie:
        :return:
        """
        clz = MovieList

        if movie is None:
            return

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

        # clz.logger.enter()

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
    logger: LazyLogger = None
    _aggregate_trailers_by_name_date_lock: threading.RLock = threading.RLock()
    _aggregate_trailers_by_name_date: Dict[str, BaseMovie] = dict()
    _first_load: bool = True

    def __init__(self, movie_source: str = '') -> None:
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
        self._last_shuffled_index: int = -1
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
        self._movies_to_fetch_queue: KodiQueue = KodiQueue(maxsize=3)
        self._starvation_queue: KodiQueue = KodiQueue()
        self._movies_to_fetch_queueLock: threading.RLock = threading.RLock()
        self.stop_discovery_event: threading.Event = threading.Event()
        self._movie_source: str = movie_source

        from discovery.trailer_fetcher import TrailerFetcher
        fetcher_thread_name: Final[str] = f'{movie_source}_fetcher'
        self._parent_trailer_fetcher: TrailerFetcher = \
            TrailerFetcher(self, fetcher_thread_name)
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

        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz.logger.enter()

        with self._discovered_movies_lock:
            self.stop_discovery_event.set()
            self._parent_trailer_fetcher.destroy()
            self._movies_discovered_event.clear()
            self._removed_trailers = 0
            self._number_of_added_movies = 0
            self._load_fetch_total_duration = 0
            self._discovery_complete = False
            self._last_shuffle_time = datetime.datetime.fromordinal(1)
            self._last_shuffled_index = -1
            self._discovered_movies.clear()
            self._discovered_movies_queue.clear()
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
            #  if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            #     clz.logger.debug('Have discovered_trailers_lock')
            movie: BaseMovie
            for movie in movies:
                if clz.logger.isEnabledFor(LazyLogger.DISABLED):
                    clz.logger.debug_extra_verbose(f' {str(movie)} '
                                                   f'source: {movie.get_source()} '
                                                   f'discovery_state: '
                                                   f'{movie.get_discovery_state()} ')
                # Assume more discovery is required for movie details, etc.

                try:
                    self._discovered_movies.add(movie)
                except DuplicateException as e:
                    # if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
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

        last_shuffled_at_size = self._last_shuffled_index
        current_size = len(self._discovered_movies)
        if (movies_added
                and (current_size > 25
                     and current_size >= (last_shuffled_at_size * 2)
                     or (seconds_since_last_shuffle >
                         self.get_minimum_shuffle_seconds()))):
            reshuffle = True

        if reshuffle:
            if clz.logger.isEnabledFor(LazyLogger.DISABLED):
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
            self._discovered_movies.add(movie)

    def purge_rediscoverable_data(self, movie: AbstractMovie) -> None:
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
            # clz.logger.debug('Have discovered_trailers_lock')

            if self._discovered_movies.len() == 0:
                return

            self._discovered_movies.shuffle()
            if mark_unplayed:
                for movie in self._discovered_movies.get_movies():
                    movie.set_trailer_played(False)

            self._last_shuffled_index = self._discovered_movies.len() - 1
            self._last_shuffle_time = datetime.datetime.now()

            # Drain anything previously in queue

            self._discovered_movies_queue.clear()

            Monitor.throw_exception_if_abort_requested()
            # clz.logger.debug('reloading _discovered_movies_queue')
            for movie in self._discovered_movies.get_movies():
                if isinstance(movie, AbstractMovieId) or not movie.is_trailer_played():
                    # if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    #   clz.logger.debug('adding', movie[Movie.TITLE],
                    #                      'id:', hex(id(movie)),
                    #                      'to discovered_movies_queue',
                    #                      'state:', movie[Movie.DISCOVERY_STATE])
                    self._discovered_movies_queue.put(movie)

            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                seconds_since_last_shuffle: int = (
                        datetime.datetime.now() - self._last_shuffle_time).seconds
                last_shuffled_at_size = self._last_shuffled_index
                current_size = len(self._discovered_movies)
                clz.logger.debug_extra_verbose(
                    f'seconds_since_last_shuffle: {seconds_since_last_shuffle} '
                    f'current size: {current_size} '
                    f'previous size: {last_shuffled_at_size}'
                    f'_discoveredTrailerQueue length: '
                    f'{self._discovered_movies_queue.qsize()}',
                    trace=Trace.TRACE_DISCOVERY)

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
            for movie in self._discovered_movies.get_movies():
                if isinstance(movie, AbstractMovie):
                    trailer: str = movie.get_trailer_path()
                    if trailer is not None and trailer != '':
                        number_of_trailers += 1

        return number_of_trailers

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
            # if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            #     clz.logger.debug_verbose('movies discovered:',
            #                                self._number_of_added_movies,
            #                                'movies without trailers:',
            #                                self._removed_trailers)
        number_of_movies = self.get_number_of_movies()
        projected_number_of_trailers = success_ratio * number_of_movies
        if self._number_of_added_movies < self._removed_trailers:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
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
            # clz.logger.debug('Have discovered_trailers_lock')

            base_movie: BaseMovie = None
            try:
                source = movie.get_source()
                movie_id = movie.get_id()
                clz.logger.debug(f'Removing {source} {movie_id}')
                base_movie = self._discovered_movies.get_by_id(source, movie_id)
            except ValueError:  # Already deleted
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz.logger.debug_verbose(
                        f'Movie appears to already be removed: {movie}')

            if base_movie is not None:
                try:
                    self._discovered_movies.remove(base_movie)
                    self._removed_trailers += 1
                    if clz.logger.isEnabledFor(LazyLogger.DISABLED):
                        clz.logger.debug(f' : {movie} '
                                         f'removed: {self._removed_trailers} remaining: '
                                         f'{self.get_number_of_movies()}')
                except KeyError:
                    # Already deleted
                    pass

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
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
            Load the _movies_to_fetch_queue from._discovered_movies_queue.

            If _movies_to_fetch_queue is full, then return

            If discoveryComplete and _discovered_movies is empty,
            then return

            If discoveryComplete and._discovered_movies_queue is empty,
            then shuffle_discovered_movies and fill the _movies_to_fetch_queue
            from it. If there are not enough items to fill the fetch queue,
            then get as many as are available.

            Otherwise, discoveryComplete == False:

            If _discovered_movies_queue is empty and _movies_to_fetch_queue
            is not empty, then return without loading any.

            If _discovered_movies_queue is empty and _movies_to_fetch_queue is empty
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
                if attempts > 0:
                    if (attempts > 1
                            and clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                        clz.logger.debug_extra_verbose('Attempt:', attempts,
                                                       'elapsed:', elapsed.seconds)

                if self._movies_to_fetch_queue.full():
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose('_movies_to_fetch_queue full',
                                                       trace=Trace.TRACE)
                    finished = True
                    iteration_successful = True
                elif self._discovery_complete and len(self._discovered_movies) == 0:
                    if (not self._discovery_complete_reported and
                            clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                        self._discovery_complete_reported = True
                        clz.logger.debug_extra_verbose(
                            'Discovery Complete and nothing found.', trace=Trace.TRACE)
                    finished = True
                    iteration_successful = True
                elif self._discovery_complete and self._discovered_movies_queue.empty():
                    clz.logger.error(
                        'discoveryComplete,_discovered_movies_queue empty')
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'discoveryComplete,_discovered_movies_queue empty',
                            trace=Trace.TRACE)
                    shuffle = True
                    discovery_complete_queue_empty += 1
                    #
                    # In the following, Discovery is INCOMPLETE
                    #
                elif (self._discovered_movies_queue.empty()
                      and not self._movies_to_fetch_queue.empty):
                    discovered_and_fetch_queues_empty += 1
                    # Use what we have
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'Discovery incomplete._discovered_movies_queue '
                            'empty and _movies_to_fetch_queue not empty',
                            trace=Trace.TRACE)
                    finished = True
                elif not self._movies_to_fetch_queue.empty():
                    # Fetch queue is not empty, nor full. Discovery
                    # is not complete. Get something from _discoveredTrailerQueue
                    # if available

                    try:
                        discovery_incomplete_fetch_not_empty += 1
                        with self._discovered_movies_lock:
                            # clz.logger.debug_verbose('Have discovered_trailers_lock')

                            movie = self._discovered_movies_queue.get(timeout=0.25)

                        # if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        #     clz.logger.debug_extra_verbose(' Got', movie[Movie.TITLE],
                        #                        'from _discoveredTrailerQueue')
                    except KodiQueue.Empty:
                        pass

                    if movie is not None:
                        try:
                            self.put_in_fetch_queue(
                                movie, timeout=1)
                            # if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            #     clz.logger.debug_verbose('Put in _movies_to_fetch_queue qsize:',
                            #                        self._movies_to_fetch_queue.qsize(),
                            #                        movie.get(Movie.TITLE),
                            #                        trace=Trace.TRACE)
                            iteration_successful = True
                        except KodiQueue.Full:
                            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                clz.logger.debug_extra_verbose(
                                    '_movies_to_fetch_queue.put failed',
                                    trace=Trace.TRACE)
                        #
                        # It is not a crisis if the put fails. Since the
                        # fetch queue does have at least one entry, we are ok
                        # Even if the movie is lost from the FetchQueue,
                        # it will get reloaded once the queue is exhausted.
                        #
                        # But since iteration_successful is not true, we might
                        # still fix it at the end.
                        #
                else:
                    # Discovery incomplete, fetch queue is empty
                    # wait until we get an item, or discovery complete

                    discovery_incomplete_fetch_queue_empty += 1
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose('Discovery incomplete,',
                                                       '_movies_to_fetch_queue empty, '
                                                       'will wait',
                                                       trace=Trace.TRACE)

                if not iteration_successful:
                    if (self._discovered_movies_queue.empty()
                            and self._discovered_movies.len() > 0):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'Shuffling due to empty _discovered_movies_queue and',
                                '_discovered_movies not empty')
                        shuffle = True

                    if shuffle:  # Because we were empty
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'Shuffling due to empty _discovered_movies_queue')
                        Monitor.throw_exception_if_abort_requested()
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'load_fetch_queue Shuffling because',
                                'discoveredTrailerQueue empty',
                                trace=Trace.TRACE_DISCOVERY)
                        self.shuffle_discovered_movies(mark_unplayed=True)

                    if movie is None:
                        get_finished: bool = False
                        while not get_finished:
                            try:
                                get_attempts += 1
                                with self._discovered_movies_lock:
                                    # clz.logger.debug_verbose(
                                    # 'Have discovered_trailers_lock')

                                    movie = self._discovered_movies_queue.get(
                                        timeout=0.5)
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
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
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
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
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

        attempts = 0
        discovery_complete_queue_empty = 0
        discovered_and_fetch_queues_empty = 0
        discovery_incomplete_fetch_not_empty = 0
        discovery_incomplete_fetch_queue_empty = 0
        get_attempts = 0
        put_attempts = 0

        # if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
        #     clz.logger.debug_verbose('took', duration.seconds,
        #                              'seconds', trace=Trace.STATS)

    def get_from_fetch_queue(self, player_starving: bool = False) -> BaseMovie:
        """

        :return:
        """
        clz = type(self)
        # if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
        #     clz.logger.debug_extra_verbose('starving:', player_starving)
        self.load_fetch_queue()
        movie: BaseMovie = None
        if self._movies_to_fetch_queue.empty():
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose(': empty')
        while movie is None:
            try:
                if player_starving:
                    movie = self.get_from_starvation_queue()
                if movie is None:
                    movie = self._movies_to_fetch_queue.get(timeout=0.5)
            except KodiQueue.Empty:
                Monitor.throw_exception_if_abort_requested()

        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(
                f'Got: {movie} from fetch queue')

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
                    # clz.logger.debug('Have discovered_trailers_lock')

                    starvation_list: List[BaseMovie] = []
                    for movie in self._discovered_movies.get_movies():
                        if (movie.get_discovery_state() >=
                                MovieField.DISCOVERY_READY_TO_DISPLAY):
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
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz.logger.debug_verbose(f'movie: {title}')
        return movie

    def get_discovered_trailer_queue_size(self) -> int:
        """

            :return: int
        """

        return self._discovered_movies_queue.qsize()

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
        # self._last_shuffled_index: int = -1
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
        # from discovery.trailer_fetcher import TrailerFetcher
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
