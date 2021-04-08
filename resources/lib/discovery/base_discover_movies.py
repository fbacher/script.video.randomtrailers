# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import sys
import threading

from common.imports import *
from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import (Trace, LazyLogger)

from diagnostics.play_stats import PlayStatistics
from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.abstract_movie_data import AbstractMovieData

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class BaseDiscoverMovies(threading.Thread):
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    _instance_map = {}
    logger: ClassVar[LazyLogger] = None

    def __init__(self,
                 group=None,
                 target: Callable[[Union[Any, None]], Union[None, Any]] = None,
                 thread_name: str = None,
                 args: Tuple[Any] = (),
                 kwargs: Dict[str, Any] = {}
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

        movie_source: str = None
        if kwargs is not None:
            movie_source = kwargs.pop(Movie.SOURCE, None)

        assert movie_source is not None

        if thread_name is None or thread_name == '':
            thread_name = Constants.ADDON_PATH + '.BaseDiscoverMovies'
        super().__init__(group=group, target=target, name=thread_name,
                         args=args, kwargs=kwargs)
        if clz.__name__ != 'BaseDiscoverMovies':
            Monitor.register_settings_changed_listener(
                self.on_settings_changed)

        self._trailers_discovered: threading.Event = threading.Event()
        self._removed_trailers: int = 0
        self._movie_data: AbstractMovieData = None
        self._discovery_complete: bool = False
        self._stop_thread: bool = False
        if movie_source is not None:
            BaseDiscoverMovies._instance_map['movie_source'] = movie_source

    def on_settings_changed(self) -> None:
        """
            Static method to inform BaseTrailerManager of settings changed
            by front-end. If settings common to all trailer managers were
            changed, then all managers will re-discover, otherwise, each
            trailer manager will be informed that settings have changed
            via .settings_changed and then it will be up to them to decide
            what to do.
        """
        # TODO: Rework
        clz = type(self)

    def restart_discovery(self, stop_thread: bool) -> None:
        """

        :return:
        """
        clz = type(self)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.enter()

        # TODO: REWORK

        self._stop_thread: bool = stop_thread
        self._movie_data.restart_discovery_event.set()

    def finished_discovery(self) -> None:
        """

        :return:
        """
        clz = type(self)

        # clz.logger.debug('before self._movie_data.lock')

        with self._movie_data._discovered_trailers_lock:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                # clz.logger.debug('got self._movie_data.lock')
                clz.logger.debug_verbose('Shuffling because finished_discovery',
                                   trace=Trace.TRACE_DISCOVERY)
            self._movie_data.shuffle_discovered_trailers(mark_unplayed=False)
            self._discovery_complete = True

    def add_to_discovered_trailers(self,
                                   movies: Union[MovieType,
                                                 List[MovieType]]) -> None:
        """

        :param movies:
        :return:
        """
        clz = type(self)

        # clz.logger.enter()
        self._movie_data.add_to_discovered_trailers(movies)

    def get_number_of_movies(self) -> int:
        """
        Gets the number of movie entries in the discovery queue for the the
        current movie type (from self: library, library_url_trailers, tmdb, tfh,
        etc.). Note that not every movie entry will have a trailer. In
        particular, TMDb trailer discovery happens in two steps: First, a general
        query for movies matching a filter is made. Next, TMDb is queried for
        each movie found in first step to get detail information, including
        trailer information.

        :return:
        """
        clz = type(self)

        return self.get_movie_data().get_number_of_movies()

    def get_number_of_known_trailers(self) -> int:
        """
        Gets the number of movie entries in the discovery queue for the the
        current movie type (from self: library, library_url_trailers, tmdb, tfh,
        etc.). Note that not every movie entry will have a trailer. In
        particular, TMDb trailer discovery happens in two steps: First, a general
        query for movies matching a filter is made. Next, TMDb is queried for
        each movie found in first step to get detail information, including
        trailer information.

        :return:
        """
        clz = type(self)

        return self.get_movie_data().get_number_of_trailers()

    def get_movie_data(self) -> AbstractMovieData:
        """

        :return:
        """
        clz = type(self)

        return self._movie_data

    def wait_until_restart_or_shutdown(self) -> None:
        """

        :return:
        """
        clz = type(self)
        finished: bool = False
        while not finished:
            Monitor.wait_for_abort(timeout=1.0)
            self.throw_exception_on_forced_to_stop()

    def throw_exception_on_forced_to_stop(self, delay: float = 0.0) -> None:
        """

        :param delay:
        :return:
        """
        clz = type(self)

        try:
            Monitor.throw_exception_if_abort_requested(timeout=delay)
            if self._movie_data.restart_discovery_event.isSet():
                raise RestartDiscoveryException()
        except AbortException:
            if clz.logger.is_trace_enabled(Trace.TRACE_PLAY_STATS):
                PlayStatistics.report_play_count_stats()
            reraise(*sys.exc_info())

    def prepare_for_restart_discovery(self) -> None:
        """

        :return:
        """
        clz = type(self)

        clz.logger.enter()
        with self._movie_data._discovered_trailers_lock:
            self._movie_data.prepare_for_restart_discovery(self._stop_thread)
            self._trailers_discovered.clear()
            self._removed_trailers = 0
            self._discovery_complete = False
            self._movie_data.restart_discovery_event.clear()

    def remove_self(self) -> None:
        """
            The Discoverxx thread is being shutdown, perhaps due to changed
            settings.
        """
        clz = type(self)

        Monitor.unregister_settings_changed_listener(
            self.on_settings_changed)
        self._movie_data.remove()