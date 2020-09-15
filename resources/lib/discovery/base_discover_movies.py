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

from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.abstract_movie_data import AbstractMovieData

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection Annotator,PyArgumentList
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
    logger = None

    def __init__(self,
                 group=None,  # type: None
                 # type: Callable[Union[None, Any], Union[Any, None]]
                 target=None,
                 thread_name=None,  # type: str
                 args=(),  # type: Optional[Any]
                 kwargs=None  # type: Optional[Any]
                 ):
        # type: (...) -> None
        """

        :param group:
        :param target:
        :param thread_name:
        :param args:
        :param kwargs:
        """
        if type(self).logger is None:
            type(self).logger = module_logger.getChild(type(self).__name__)
        type(self).logger.enter()
        movie_source = None
        if kwargs is not None:
            movie_source = kwargs.pop(Movie.SOURCE, None)

        assert movie_source is not None

        if thread_name is None or thread_name == '':
            thread_name = Constants.ADDON_PATH + '.BaseDiscoverMovies'
        super().__init__(group=group, target=target, name=thread_name,
                         args=args, kwargs=kwargs)
        if type(self).__name__ != 'BaseDiscoverMovies':
            Monitor.register_settings_changed_listener(
                self.on_settings_changed)

        self._trailers_discovered = threading.Event()
        self._removed_trailers = 0
        self._movie_data = None  # type: Optional[AbstractMovieData]
        self._discovery_complete = False
        self._stop_thread = False
        if movie_source is not None:
            BaseDiscoverMovies._instance_map['movie_source'] = movie_source

    def on_settings_changed(self):
        # type:() -> None
        """
            Static method to inform BaseTrailerManager of settings changed
            by front-end. If settings common to all trailer managers were
            changed, then all managers will re-discover, otherwise, each
            trailer manager will be informed that settings have changed
            via .settings_changed and then it will be up to them to decide
            what to do.
        """
        # TODO: Rework

        type(self).logger.enter()

    def restart_discovery(self, stop_thread):
        # type: (bool) -> None
        """

        :return:
        """

        type(self).logger.enter()

        # TODO: REWORK

        self._stop_thread = stop_thread
        self._movie_data.restart_discovery_event.set()

    def finished_discovery(self):
        # type: () -> None
        """

        :return:
        """
        # type(self).logger.debug('before self._movie_data.lock')

        with self._movie_data._discovered_trailers_lock:
            if type(self).logger.isEnabledFor(LazyLogger.DEBUG):
                # type(self).logger.debug('got self._movie_data.lock')
                type(self).logger.debug('Shuffling because finished_discovery',
                                   trace=Trace.TRACE_DISCOVERY)
            self._movie_data.shuffle_discovered_trailers(mark_unplayed=False)
            self._discovery_complete = True

    def add_to_discovered_trailers(self, movies):
        # type: (Union[Dict[str], List[Dict[str]]]) -> None
        """

        :param movies:
        :return:
        """
        type(self).logger.enter()
        self._movie_data.add_to_discovered_trailers(movies)

    def get_number_of_movies(self):
        # type: () -> int
        """

        :return:
        """
        return self.get_movie_data().get_number_of_movies()

    def get_movie_data(self):
        # type:() -> AbstractMovieData
        """

        :return:
        """
        return self._movie_data

    def wait_until_restart_or_shutdown(self):
        # type: () -> None
        """

        :return:
        """

        finished = False
        while not finished:
            Monitor.wait_for_abort(timeout=1.0)
            self.throw_exception_on_forced_to_stop()

    def throw_exception_on_forced_to_stop(self, delay=0):
        # type: (float) -> None
        """

        :param delay:
        :return:
        """
        try:
            Monitor.throw_exception_if_abort_requested(timeout=delay)
            if self._movie_data.restart_discovery_event.isSet():
                raise RestartDiscoveryException()
        except AbortException:
            self.get_movie_data().report_play_count_stats()
            reraise(*sys.exc_info())

    def prepare_for_restart_discovery(self):
        # type: () -> None
        """

        :return:
        """

        type(self).logger.enter()
        with self._movie_data._discovered_trailers_lock:
            self._movie_data.prepare_for_restart_discovery(self._stop_thread)
            self._trailers_discovered.clear()
            self._removed_trailers = 0
            self._discovery_complete = False
            self._movie_data.restart_discovery_event.clear()

    def remove_self(self):
        # type: () -> None
        """
            The Discoverxx thread is being shutdown, perhaps due to changed
            settings.
        """
        Monitor.unregister_settings_changed_listener(
            self.on_settings_changed)
        self._movie_data.remove()

    @staticmethod
    def get_instances():
        # type: () -> Dict[str, BaseDiscoverMovies]
        """

        :return:
        """

        return BaseDiscoverMovies._instance_map
