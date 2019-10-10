# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import threading
import queue

from common.debug_utils import Debug
from common.development_tools import (Dict, TextType, MovieType)
from common.constants import (Constants, Movie)
from common.monitor import Monitor
from common.logger import (Logger, LazyLogger, Trace)

from discovery.abstract_movie_data import AbstractMovieData

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.playable_trailers_container')
else:
    module_logger = LazyLogger.get_addon_module_logger()


# noinspection Annotator,PyArgumentList
class PlayableTrailersContainer(object):
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    _any_trailers_available_to_play = threading.Event()
    _singleton_instance = None
    _instances = {}

    def __init__(self,
                 source  # type: TextType
                 ):
        # type: (...) -> None
        """

        :return:
        """
        self._logger = module_logger.getChild(
            self.__class__.__name__ + ':' + source)
        self._logger.enter()

        PlayableTrailersContainer._instances[source] = self
        self._movie_data = None
        self._ready_to_play_queue = queue.Queue(maxsize=3)
        self._number_of_added_trailers = 0
        self._starving = False
        self._is_playable_trailers = threading.Event()

    def set_movie_data(self, movie_data):
        # type: (AbstractMovieData) -> None
        """

        :return:
        """
        self._movie_data = movie_data

    def get_movie_data(self):
        # type: () -> AbstractMovieData
        """

        :return:
        """

        return self._movie_data

    def shutdown_thread(self):
        # type: () -> None
        # Force waits to end
        """
            Called by WatchDog during a plugin shutdown.

            Forces any waits to end

        :return:
        """
        pass

    def prepare_for_restart_discovery(self, stop_thread):
        # type: (bool) -> None
        """

        :param stop_thread
        :return:
        """
        self._logger.enter()
        self._number_of_added_trailers = 0

        if stop_thread:
            instances = PlayableTrailersContainer.get_instances()
            for movie_source in instances:
                playable_trailer_container = instances[movie_source]
                if playable_trailer_container == self:
                    del PlayableTrailersContainer._instances[movie_source]
                    break

            self._movie_data = None

    def settings_changed(self):
        # type: () -> None
        """
            Instance method
        """
        pass

    def add_to_ready_to_play_queue(self, movie):
        # type: (MovieType]) -> None
        """

        :param movie:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('movie:', movie[Movie.TITLE], 'queue empty:',
                               self._ready_to_play_queue.empty(), 'full:',
                               self._ready_to_play_queue.full())
            Debug.validate_detailed_movie_properties(movie, stack_trace=False)

        finished = False
        waited = 0
        while not finished:
            try:
                self._ready_to_play_queue.put(movie, block=True, timeout=0.25)
                finished = True
                self._number_of_added_trailers += 1
            except (queue.Full):
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=0.75)
                waited += 1

        if not PlayableTrailersContainer._any_trailers_available_to_play.isSet():
            PlayableTrailersContainer._any_trailers_available_to_play.set()

        self._is_playable_trailers.set()

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('readyToPlayQueue size:',
                               self._ready_to_play_queue.qsize(), 'waited:',
                               waited)
        return

    def get_ready_to_play_queue(self):
        # type: () -> queue.Queue
        """

        :return:
        """
        return self._ready_to_play_queue

    def get_number_of_playable_movies(self):
        # type: () -> int
        """

        :return:
        """
        return self._ready_to_play_queue.qsize()

    def get_number_of_added_trailers(self):
        # type: () -> int
        """

        :return:
        """
        return int(self._number_of_added_trailers)

    def get_next_movie(self):
        # type: () -> MovieType
        """

        :return:
        """
        movie = self._ready_to_play_queue.get(block=False)
        if movie is not None:
            self._movie_data.increase_play_count(movie)

        self._logger.exit('movie:', movie[Movie.TITLE])
        return movie

    @staticmethod
    def is_any_trailers_available_to_play():
        # type: () -> bool
        """

        :return:
        """
        return PlayableTrailersContainer._any_trailers_available_to_play.isSet()

    def is_playable_trailers(self):
        # type: () -> bool
        """

        :return:
        """
        return self._is_playable_trailers.isSet()

    def get_projected_number_of_trailers(self):
        # type: () -> int
        """

        :return:
        """
        return self._movie_data.get_projected_number_of_trailers()

    def set_starving(self, is_starving):
        # type: (bool) -> None
        """

        :param is_starving:
        :return:
        """
        self._starving = is_starving

    def is_starving(self):
        # type: () -> bool
        """

        :return:
        """
        return self._starving

    @staticmethod
    def get_instances():
        # type: () -> Dict[TextType, PlayableTrailersContainer]
        """

        :return:
        """
        return PlayableTrailersContainer._instances

    @staticmethod
    def remove_instance(source):
        # type: (TextType) -> None
        """

        :param source:
        :return:
        """
        del PlayableTrailersContainer._instances[source]
