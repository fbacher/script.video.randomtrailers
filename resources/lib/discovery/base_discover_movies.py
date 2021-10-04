# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import sys
import threading

from common.critical_settings import CriticalSettings
from common.imports import *
from common.constants import Constants
from common.exceptions import AbortException, reraise
from common.monitor import Monitor
from common.movie_constants import MovieField
from common.logger import Trace, LazyLogger
from common.movie import BaseMovie

from diagnostics.play_stats import PlayStatistics
from discovery.restart_discovery_exception import StopDiscoveryException
from discovery.abstract_movie_data import AbstractMovieData

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class BaseDiscoverMovies(threading.Thread):
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/movie information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    logger: ClassVar[LazyLogger] = None

    def __init__(self,
                 group=None,
                 target: Callable[[Union[Any, None]], Union[None, Any]] = None,
                 thread_name: str = None,
                 args: Tuple = (),
                 kwargs: Dict[str, Any] = None
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
            movie_source = kwargs.pop(MovieField.SOURCE, None)

        assert movie_source is not None

        if thread_name is None or thread_name == '':
            thread_name = Constants.ADDON_PATH + '.BaseDiscoverMovies'
        super().__init__(group=group, target=target, name=thread_name,
                         args=args, kwargs=kwargs)

        self._trailers_discovered: threading.Event = threading.Event()
        self._removed_trailers: int = 0
        self._movie_data: AbstractMovieData = None
        self._discovery_complete: bool = False
        self._stop_thread: bool = False

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return False

    def finished_discovery(self) -> None:
        """

        :return:
        """
        clz = type(self)

        with self._movie_data._discovered_movies_lock:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                # clz.logger.debug('got self._movie_data.lock')
                clz.logger.debug_verbose('Shuffling because finished_discovery',
                                   trace=Trace.TRACE_DISCOVERY)
            self._movie_data.shuffle_discovered_movies(mark_unplayed=False)
            self._discovery_complete = True

    def discover_basic_information(self):
        raise NotImplemented()

    def get_by_id(self, movie_id: str) -> BaseMovie:
        return self._movie_data.get_by_id(movie_id)

    def add_to_discovered_movies(self,
                                 movies: Union[BaseMovie,
                                               Iterable[BaseMovie]]) -> None:
        """

        :param movies:
        :return:
        """
        clz = type(self)

        # clz.logger.enter()
        self._movie_data.add_to_discovered_movies(movies)

    def get_number_of_movies(self) -> int:
        """
        Gets the number of movie entries in the discovery queue for the the
        current movie type (from self: library, library_url_trailers, tmdb, tfh,
        etc.). Note that not every movie entry will have a movie. In
        particular, TMDb movie discovery happens in two steps: First, a general
        query for movies matching a filter is made. Next, TMDb is queried for
        each movie found in first step to get detail information, including
        movie information.

        :return:
        """
        clz = type(self)

        return self.get_movie_data().get_number_of_movies()

    def get_number_of_known_trailers(self) -> int:
        """
        Gets the number of movie entries in the discovery queue for the the
        current movie type (from self: library, library_url_trailers, tmdb, tfh,
        etc.). Note that not every movie entry will have a movie. In
        particular, TMDb movie discovery happens in two steps: First, a general
        query for movies matching a filter is made. Next, TMDb is queried for
        each movie found in first step to get detail information, including
        movie information.

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

    def wait_until_restart_or_shutdown(self, timeout: float = -1.0) -> None:
        """

        :return:
        :exception: AbortException, StopDiscoveryException
        """
        clz = type(self)
        finished: bool = False
        if timeout < 0.0:
            forever = True
        else:
            forever = False
        while not finished:
            self.throw_exception_on_forced_to_stop(CriticalSettings.SHORT_POLL_DELAY)
            if not forever:
                timeout -= 0.2  # Accuracy not needed
                if timeout < 0:
                    finished = True

    def throw_exception_on_forced_to_stop(self, timeout: float = 0.0) -> None:
        """

        :param timeout:
        :return:

        :exception: AbortException, StopDiscoveryException
        """
        clz = type(self)

        try:
            Monitor.throw_exception_if_abort_requested(timeout=timeout)
            if self._movie_data.stop_discovery_event.isSet():
                raise StopDiscoveryException()
        except AbortException:
            if clz.logger.is_trace_enabled(Trace.TRACE_PLAY_STATS):
                PlayStatistics.report_play_count_stats()
            reraise(*sys.exc_info())

    def stop_thread(self) -> None:
        """

        :return:
        """
        clz = type(self)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.enter()

        self._stop_thread = True
        self._movie_data.stop_discovery()

    def destroy(self) -> None:
        """

        :return:
        """
        clz = type(self)

        clz.logger.enter()
        count: int = 0
        while  not Monitor.wait_for_abort(timeout=0.2):
            if not self.is_alive():
                break
            elif (count % 10) == 0:
                clz.logger.debug_extra_verbose(f'Waiting to die: {self.name} '
                                               f'{self.ident}')

        with self._movie_data._discovered_movies_lock:
            self._movie_data.destroy()
            self._trailers_discovered.clear()
            self._removed_trailers = 0
            self._discovery_complete = False
            self._movie_data.remove()

    def needs_restart(self) -> bool:
        # return False
        raise NotImplementedError()
