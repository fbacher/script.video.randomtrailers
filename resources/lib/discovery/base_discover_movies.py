# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import threading

from common.development_tools import (Any, Callable, Optional, Dict, Union,
                                      TextType)
from common.constants import Constants, Movie
from common.exceptions import (ShutdownException, AbortException)
from common.monitor import Monitor
from common.watchdog import WatchDog
from common.logger import (Logger, Trace, LazyLogger)

from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.abstract_movie_data import AbstractMovieData

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.base_discover_movies')
else:
    module_logger = LazyLogger.get_addon_module_logger()


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

    def __init__(self,
                 group=None,  # type: None
                 # type: Callable[Union[None, Any], Union[Any, None]]
                 target=None,
                 thread_name=None,  # type: TextType
                 args=(),  # type: Optional[Any]
                 kwargs=None,  # type: Optional[Any]
                 verbose=None  # type: Optional[bool]
                 ):
        # type: (...) -> None
        """

        :param group:
        :param target:
        :param thread_name:
        :param args:
        :param kwargs:
        :param verbose:
        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._logger.enter()
        movie_source = None
        if kwargs is not None:
            movie_source = kwargs.pop(Movie.SOURCE, None)

        assert movie_source is not None

        if thread_name is None or thread_name == '':
            thread_name = Constants.ADDON_PATH + '.BaseDiscoverMovies'
        super().__init__(group=group, target=target, name=thread_name,
                         args=args, kwargs=kwargs, verbose=verbose)
        if self.__class__.__name__ != 'BaseDiscoverMovies':
            Monitor.get_instance().register_settings_changed_listener(
                self.on_settings_changed)

        WatchDog.register_thread(self)
        self._trailers_discovered = threading.Event()
        self._removed_trailers = 0
        self._movie_data = None  # type: Optional[AbstractMovieData]
        self._discovery_complete = False
        self._stop_thread = False
        if movie_source is not None:
            BaseDiscoverMovies._instance_map['movie_source'] = movie_source

    def shutdown_thread(self):
        # type: () -> None
        # Force waits to end
        """
            Called by WatchDog during a plugin shutdown.

            Forces any waits to end

        :return:
        """
        pass

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

        self._logger.enter()

    def restart_discovery(self, stop_thread):
        # type: (bool) -> None
        """

        :return:
        """

        self._logger.enter()

        # TODO: REWORK

        self._stop_thread = stop_thread
        self._movie_data.restart_discovery_event.set()

    def finished_discovery(self):
        # type: () -> None
        """

        :return:
        """
        # self._logger.debug('before self._movie_data.lock')

        with self._movie_data._discovered_trailers_lock:
            if self._logger.isEnabledFor(Logger.DEBUG):
                # self._logger.debug('got self._movie_data.lock')
                self._logger.debug('Shuffling because finished_discovery',
                                   trace=Trace.TRACE_DISCOVERY)
            self._movie_data.shuffle_discovered_trailers(mark_unplayed=False)
            self._discovery_complete = True

    def add_to_discovered_trailers(self, movies):
        # type: (Union[Dict[TextType], List[Dict[TextType]]]) -> None
        """

        :param movies:
        :return:
        """
        self._logger.enter()
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
            Monitor.get_instance().wait_for_shutdown(timeout=1.0)
            self.throw_exception_on_forced_to_stop()

    def throw_exception_on_forced_to_stop(self, delay=0):
        # type: (float) -> None
        """

        :param delay:
        :return:
        """
        try:
            Monitor.get_instance().throw_exception_if_shutdown_requested(delay=delay)
            if self._movie_data.restart_discovery_event.isSet():
                raise RestartDiscoveryException()
        except (ShutdownException, AbortException) as e:
            self.get_movie_data().report_play_count_stats()

    def prepare_for_restart_discovery(self):
        # type: () -> None
        """

        :return:
        """

        self._logger.enter()
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
        Monitor.get_instance().unregister_settings_changed_listener(
            self.on_settings_changed)
        self._movie_data.remove()

    @staticmethod
    def get_instances():
        # type: () -> Dict[TextType, BaseDiscoverMovies]
        """

        :return:
        """

        return BaseDiscoverMovies._instance_map
