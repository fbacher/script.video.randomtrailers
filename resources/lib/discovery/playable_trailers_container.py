# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from collections import OrderedDict
import threading
import queue

from common.imports import *
from common.debug_utils import Debug
from common.constants import Movie
from common.monitor import Monitor
from common.logger import LazyLogger

from diagnostics.play_stats import PlayStatistics
from discovery.abstract_movie_data import AbstractMovieData

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class PlayableTrailersContainer:
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
    logger: ClassVar[LazyLogger] = None
    _recently_played_trailers: ClassVar[OrderedDict] = OrderedDict()

    # Avoid playing duplicate trailers when we first start up.

    _aggregate_trailers_queued: int = 0

    def __init__(self,
                 source: str
                 ) -> None:
        """

        :return:
        """
        self.logger = module_logger.getChild(type(self).__name__
                                                + ':' + source)

        PlayableTrailersContainer._instances[source] = self
        self._movie_data: AbstractMovieData = None
        self._ready_to_play_queue: queue.Queue = queue.Queue(maxsize=3)
        self._number_of_added_trailers: int = 0
        self._starving: bool = False
        self._starve_check_timer: threading.Timer = None
        self._is_playable_trailers: threading.Event = threading.Event()

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

    def prepare_for_restart_discovery(self, stop_thread: bool) -> None:
        """

        :param stop_thread
        :return:
        """
        self._number_of_added_trailers = 0

        if stop_thread:
            instances = PlayableTrailersContainer.get_instances()
            for movie_source in instances:
                playable_trailer_container = instances[movie_source]
                if playable_trailer_container == self:
                    del PlayableTrailersContainer._instances[movie_source]
                    break

            self._movie_data = None
            self._aggregate_trailers_queued = 0

    def settings_changed(self) -> None:
        """
            Instance method
        """
        pass

    def add_to_ready_to_play_queue(self, movie: MovieType) -> None:
        """

        :param movie:
        :return:
        """
        clz = type(self)
        if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            if Movie.TITLE not in movie:
                self.logger.warning('Invalid movie entry. Missing title: ',
                                   str(movie))
            Debug.validate_detailed_movie_properties(movie, stack_trace=False)
        """
        try:
            title = movie[Movie.TITLE]
            
            self._aggregate_trailers_queued += 1

            if self._aggregate_trailers_queued <= clz.DUPLICATE_TRAILER_CHECK_LIMIT:
                if title in clz._recently_played_trailers:
                    if self._ready_to_play_queue.empty():
                        if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            self.logger.debug_verbose(
                                f'Movie: {title} played recently, but starving')
                    elif self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        self.logger.debug_verbose(
                            f'Movie: {title} played recently, skipping')
                        return

                # Adding to queue, below, will block if it is full, preventing this
                # from running away

                clz._recently_played_trailers[title] = movie
        except Exception as e:
            self.logger.exception(e)
        """

        if self.logger.isEnabledFor(LazyLogger.DEBUG):
            self.logger.debug_verbose('movie:', movie[Movie.TITLE], 'queue empty:',
                                     self._ready_to_play_queue.empty(), 'full:',
                                     self._ready_to_play_queue.full())

        finished: bool = False
        waited: int = 0
        while not finished:
            try:
                self._ready_to_play_queue.put(movie, block=True, timeout=0.05)
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

    @classmethod
    def get_recently_played_trailers(cls) -> Dict[str, MovieType]:
        return cls._recently_played_trailers

    def get_number_of_added_trailers(self) -> int:
        """

        :return:
        """
        return int(self._number_of_added_trailers)

    def get_next_movie(self) -> MovieType:
        """

        :return:
        """
        clz = type(self)
        movie = self._ready_to_play_queue.get(block=False)
        if movie is not None:
            title = movie[Movie.TITLE]
            clz._recently_played_trailers[title] = movie

            PlayStatistics.increase_play_count(movie)
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.exit('movie:', movie[Movie.TITLE])
        else:
            if self.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                self.logger.exit('No movie in queue')
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
        # Since TrailerDialog pre-fetches the next trailer to play and because
        # we don't want to force replaying the currently running trailer when if
        # we just waited a few seconds we would have more options, we put a delay
        # before passing along the starving message.

        self._starving = False

        if is_starving:
            if self._starve_check_timer is not None:
                try:
                    self._starve_check_timer.join(timeout=0.05)
                except Exception:
                    pass

                self._starve_check_timer = None

            # Wait ten seconds before declaring starvation. This gives the
            # trailer_fetcher time to do something useful while trailer is
            # playing.

            self._starve_check_timer = threading.Timer(10.0, self.starving_check)
            self._starve_check_timer.setName('Starve Check')
            self._starve_check_timer.start()

    def starving_check(self) -> None:
        is_starving = self._ready_to_play_queue.empty()
        self._starving = is_starving

    def is_starving(self) -> bool:
        """

        :return:
        """
        starving = self._starving
        self._starving = False
        return starving

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
        del PlayableTrailersContainer._instances[source]

    def clear(self) -> None:
        self._movie_data = None
        while not self._ready_to_play_queue.empty():
            self._ready_to_play_queue.get_nowait()
