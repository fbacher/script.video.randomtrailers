# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
import sys
from collections import OrderedDict
import threading
import queue

from cache.library_trailer_index import LibraryTrailerIndex
from cache.tmdb_trailer_index import TMDbTrailerIndex
from cache.trailer_cache import TrailerCache
from common.constants import Constants
from common.exceptions import AbortException
from common.imports import *
from common.debug_utils import Debug
from common.monitor import Monitor
from common.logger import LazyLogger
from common.movie import AbstractMovie, TMDbMovieId, TMDbMovie, LibraryMovie, \
    LibraryMovieId
from common.movie_constants import MovieField

from diagnostics.play_stats import PlayStatistics
from discovery.abstract_movie_data import AbstractMovieData
from discovery.library_movie_data import LibraryMovieData
from discovery.playable_trailers_container_interface import \
    PlayableTrailersContainerInterface
from discovery.tmdb_movie_data import TMDbMovieData
from discovery.utils.recently_played_trailers import RecentlyPlayedTrailers

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class PlayableTrailersContainer(PlayableTrailersContainerInterface):
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    DUPLICATE_TRAILER_CHECK_LIMIT: Final[int] = 15

    _any_trailers_available_to_play:ClassVar[threading.Event] = threading.Event()
    _singleton_instance = None
    _instances = {}

    # Avoid playing duplicate trailers when we first start up.

    _aggregate_trailers_queued: int = 0

    def __init__(self,
                 source: str
                 ) -> None:
        """

        :return:
        """

        self.logger = module_logger.getChild(f'{type(self).__name__}:{source}')

        PlayableTrailersContainer._instances[source] = self
        self._source = source
        self._movie_data: AbstractMovieData = None
        self._ready_to_play_queue: queue.Queue = queue.Queue(maxsize=3)
        self._number_of_added_trailers: int = 0
        self._starving: bool = False
        self._starve_check_timer: threading.Timer = None
        self._starve_check_pending = False
        self._starve_check_lock: threading.RLock = threading.RLock()
        self._is_playable_trailers: threading.Event = threading.Event()
        self._stop_thread = False
        self._shuffled: bool = False

    def set_movie_data(self, movie_data: AbstractMovieData) -> None:
        """

        :return:
        """
        self._movie_data = movie_data

    def get_movie_data(self) -> AbstractMovieData:
        """

        :return:
        """

        return self._movie_data

    def stop_thread(self) -> None:
        """
        Stop using this instance

        :return:
        """
        self._stop_thread = True
        Monitor.throw_exception_if_abort_requested(timeout=0.5)
        type(self).remove_instance(self._source)

    def destroy(self) -> None:
        """

        Thread clean-up after it has stopped

        :return:
        """
        self._number_of_added_trailers = 0
        self._aggregate_trailers_queued = 0
        self.clear()

    def add_to_ready_to_play_queue(self, movie: AbstractMovie) -> None:
        """

        :param movie:
        :return:
        """
        clz = type(self)
        if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            Debug.validate_detailed_movie_properties(movie, stack_trace=False)

        if self.logger.isEnabledFor(LazyLogger.DEBUG):
            self.logger.debug_verbose('movie:', movie.get_title(), 'queue empty:',
                                      self._ready_to_play_queue.empty(), 'full:',
                                      self._ready_to_play_queue.full())

        finished: bool = False
        waited: int = 0
        while not finished:
            try:
                if self._stop_thread:
                    return

                self._ready_to_play_queue.put(movie, block=True, timeout=0.05)

                if Constants.SAVE_MEMORY:
                    # To keep data structures small, get rid of all
                    # easily rediscoverable data from movie_data structures. Just keep
                    # movie source & movieid.

                    if isinstance(movie, TMDbMovie):
                        tmdb_id_movie: TMDbMovieId
                        data: TMDbMovieData = self.get_movie_data()
                        tmdb_id_movie = data.purge_rediscoverable_data(movie)

                        self.logger.debug(f'tmdb_id_movie: {tmdb_id_movie}')
                        TMDbTrailerIndex.add(tmdb_id_movie)
                    elif isinstance(movie, LibraryMovie):
                        library_id_movie: LibraryMovieId
                        data: LibraryMovieData = self.get_movie_data()
                        # library_id_movie = data.purge_rediscoverable_data(movie)
                        LibraryTrailerIndex.add(movie)

                finished = True
                self._number_of_added_trailers += 1
            except queue.Full:
                waited += 1

            Monitor.throw_exception_if_abort_requested(timeout=0.5)

        if not clz._any_trailers_available_to_play.isSet():
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.debug_verbose(
                    'Setting _any_trailers_available_to_play')
            clz._any_trailers_available_to_play.set()

        self._is_playable_trailers.set()

        if self.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            self.logger.debug_extra_verbose('readyToPlayQueue size:',
                                            self._ready_to_play_queue.qsize(), 'waited:',
                                            waited)
        return

    def get_ready_to_play_queue(self) -> queue.Queue:
        """

        :return:
        """
        return self._ready_to_play_queue

    def get_number_of_playable_movies(self) -> int:
        """

        :return:
        """
        return self._ready_to_play_queue.qsize()

    def get_number_of_added_trailers(self) -> int:
        """

        :return:
        """
        return int(self._number_of_added_trailers)

    def get_next_movie(self) -> AbstractMovie:
        """

        :return:
        """
        clz = type(self)
        movie: AbstractMovie = None
        try:
            movie = self._ready_to_play_queue.get(block=False)
        except queue.Empty:
            movie = None

        if movie is not None:
            TrailerCache.is_more_discovery_needed(movie)

            # If cached movie is invalid, then skip over this MovieField.

            if (movie.get_discovery_state()
                    != MovieField.DISCOVERY_READY_TO_DISPLAY):
                movie = None
        if movie is not None:
            RecentlyPlayedTrailers.add_played_trailer(movie)
            self.logger.debug(f'Got movie: {movie.get_title()}')

            PlayStatistics.increase_play_count(movie)
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.exit('movie:', movie.get_title())
        elif self.is_starving():
            # self.set_starving(True)
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.exit('No movie in queue')
            movie = RecentlyPlayedTrailers.get_recently_played()
            movie.set_starving(True)
        else:
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.exit('No movie in queue. Starving not set')
        return movie

    @classmethod
    def is_any_trailers_available_to_play(cls) -> bool:
        """

        :return:
        """

        return cls._any_trailers_available_to_play.isSet()

    def is_playable_trailers(self) -> bool:
        """

        :return:
        """
        return self._is_playable_trailers.isSet()

    def get_projected_number_of_trailers(self) -> int:
        """

        :return:
        """
        return self._movie_data.get_projected_number_of_trailers()

    #
    #
    def set_starving(self, is_starving) -> None:
        """

        :return:
        """
        #
        # Inform the fetching code that at least one of the queues is out of
        # playable trailers.
        #
        # Since TrailerDialog pre-fetches the next movie to play and because
        # we don't want to force replaying the currently running movie when if
        # we just waited a few seconds we would have more options, we put a delay
        # before passing along the starving message.

        # self._starving = is_starving
        clz = type(self)
        self.logger.debug(f'starving: {is_starving} checking pending: '
                          f'{self._starve_check_pending}')

        with self._starve_check_lock:
            if self._starving and not self._starve_check_pending:
                if self._starve_check_timer is not None:
                    try:
                        self._starve_check_timer.join(timeout=0.05)
                    except AbortException:
                        reraise(*sys.exc_info())
                    except Exception:
                        pass

                    self._starve_check_timer = None

                # Wait two seconds before declaring starvation. This gives the
                # trailer_fetcher time to do something useful while movie is
                # playing.

                if not self._stop_thread:
                    self._starve_check_pending = True
                    self._starve_check_timer = threading.Timer(2.0, self.starving_check)
                    self._starve_check_timer.setName(f'Starve Check {self._source}')
                    self._starve_check_timer.start()

    def starving_check(self) -> None:
        clz = type(self)
        is_starving = self._ready_to_play_queue.empty()
        self.logger.debug(f'starving: {is_starving}')
        self._starving = is_starving
        self._starve_check_pending = False

    def is_starving(self) -> bool:
        """

        :return:
        """
        clz = type(self)
        starving = self._starving
        self.logger.debug(f'starving: {starving}')
        self._starving = False
        return starving

    def set_shuffled(self) -> None:
        self._shuffled = True

    def is_shuffled(self) -> bool:
        return self._shuffled

    def clear_shuffled(self) -> None:
        self._shuffled = False

    @staticmethod
    def get_instances() -> Dict[str, 'PlayableTrailersContainer']:
        """

        :return:
        """
        return PlayableTrailersContainer._instances

    @staticmethod
    def remove_instance(source: str) -> None:
        """

        :param source:
        :return:
        """
        if source in PlayableTrailersContainer._instances:
            del PlayableTrailersContainer._instances[source]

    def clear(self) -> None:
        self._movie_data = None
        while not self._ready_to_play_queue.empty():
            self._ready_to_play_queue.get_nowait()
