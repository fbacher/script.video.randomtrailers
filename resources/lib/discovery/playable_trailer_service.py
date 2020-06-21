# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import itertools
import sys
import datetime
import queue
import six

from common.development_tools import (Iterable, Union)
from common.constants import (Constants, Movie)
from common.disk_utils import DiskUtils
from common.monitor import Monitor
from common.logger import (Logger, Trace, LazyLogger)

from discovery.abstract_movie_data import AbstractMovieData
from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.playable_trailers_container import PlayableTrailersContainer
from cache.trailer_cache import (TrailerCache)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.playable_trailer_service')
else:
    module_logger = LazyLogger.get_addon_module_logger()


# noinspection Annotator,PyArgumentList
class PlayableTrailerService(object):
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """

    def __init__(self):
        # type: (...) -> None
        """

        :return:
        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._logger.enter()

        self._next_total_duration = 0
        self._next_calls = 0
        self._next_attempts = 0
        self._load_fetch_total_duration = 0
        self._next_failures = 0
        self._next_total_first_method_attempts = 0
        self._next_second_attempts = 0
        self._next_second_total_Duration = 0
        self._played_movies_count = 0

    def shutdown_thread(self):
        # type: () -> None
        # Force waits to end
        """
            Called by WatchDog during a plugin shutdown.

            Forces any waits to end

        :return:
        """
        pass

    def iter(self):
        # type: () -> Iterable
        """

        :return:
        """
        return self.__iter__()

    def __iter__(self):
        # type: () -> Iterable
        """

        :return:
        """
        return self

    def next(self):
        # type: () -> dict
        """

        :return:
        """
        return self.__next__()

    def __next__(self):
        # type: () -> Union[dict, None]
        """

        :return:
        """
        movie = None
        try:
            finished = False
            attempt = 0
            while not finished:
                try:
                    attempt += 1
                    movie = self._do_next()
                    finished = True
                except (RestartDiscoveryException):
                    Monitor.get_instance().throw_exception_if_shutdown_requested(0.10)
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'Rediscovery in progress. attempt:', attempt)
        except (Exception) as e:
            self._logger.exception('')
            six.reraise(*sys.exc_info())

        return movie

    def _do_next(self):
        # type: () -> Union[dict, None]
        """

        :return:
        """

        if self._logger.isEnabledFor(Logger.DEBUG):
            any_available = PlayableTrailersContainer.is_any_trailers_available_to_play()
            self._logger.debug(
                'trailersAvail:', any_available, trace=Trace.TRACE)

        try:
            while not PlayableTrailersContainer.is_any_trailers_available_to_play():
                self.throw_exception_on_forced_to_stop(
                    movie_data=None, delay=0.25)

        except (Exception) as e:
            self._logger.exception('')

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(
                'PlayableTrailerService.next after trailersAvail wait')
        total_number_of_trailers = 0
        start_time = datetime.datetime.now()

        # Considered locking all TrailerManagers here to guarantee
        # that lengths don't change while finding the right trailer
        # but that might block the readyToPlayQueue from getting
        # loaded. Besides, it doesn't matter too much if we play
        # the incorrect trailer, as long as we get one. The
        # major fear is if we have no trailers at all, but that
        # will be handled elsewhere.

        # Get total number of trailers from all managers.

        # It is possible that all discovery is complete and there is nothing
        # to play.

        nothing_to_play = True
        # playable_trailers_map = None  # type: Dict[TextType,
        # PlayableTrailersContainer]
        # type:
        playable_trailers_map = PlayableTrailersContainer.get_instances()
        # Dict[TextType, PlayableTrailersContainer]

        # Need to use the same projected sizes throughout this method.

        projected_sizes_map = {}
        for source in playable_trailers_map:
            playable_trailers = playable_trailers_map[source]
            if not playable_trailers.is_playable_trailers():
                continue

            movie_data = playable_trailers.get_movie_data()
            self.throw_exception_on_forced_to_stop(movie_data=movie_data)
            number_of_trailers = movie_data.get_number_of_movies()
            trailers_queue_size = movie_data.get_discovered_trailer_queue_size()
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(source, 'size:',
                                   number_of_trailers,
                                   'discoveredTrailersQueue size:',
                                   trailers_queue_size,
                                   'readyToPlayQueue size:',
                                   playable_trailers.get_ready_to_play_queue().qsize(),
                                   'trailersToFetchQueue size:',
                                   movie_data.get_trailers_to_fetch_queue_size())

            projected_size = movie_data.get_projected_number_of_trailers()
            projected_sizes_map[source] = projected_size
            total_number_of_trailers += projected_size
            if not movie_data.is_discovery_complete() or number_of_trailers != 0:
                nothing_to_play = False

            # If we have played everything, then we start over.

            if (trailers_queue_size == 0
                    and playable_trailers.is_playable_trailers()):
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Shuffling because discoveredTrailerQueue empty',
                                       trace=Trace.TRACE_DISCOVERY)
                movie_data.shuffle_discovered_trailers(mark_unplayed=True)

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('numTrailers:', total_number_of_trailers)
        if nothing_to_play:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Nothing to Play!')
            raise StopIteration
            # return None

        # Now, randomly pick playable_trailers to get a trailer from based upon
        # the number of trailers in each.
        #
        # We loop here because there may not be any trailers in the readyToPlayQueue
        # for a specific playable_trailers

        trailer = None
        attempts = 0
        while trailer is None and attempts < 10:
            try:
                trailer_index_to_play = DiskUtils.RandomGenerator.randint(
                    0, total_number_of_trailers - 1)
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('PlayableTrailerService.next trailer_index_to_play:',
                                       trailer_index_to_play)
            except (ValueError) as e:  # Empty range
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=0.10)
                continue

            total_number_of_trailers = 0
            found_playable_trailers = None
            for source in playable_trailers_map:
                playable_trailers = playable_trailers_map[source]
                if not playable_trailers.is_playable_trailers():
                    continue

                movie_data = playable_trailers.get_movie_data()
                self.throw_exception_on_forced_to_stop(movie_data=movie_data)

                projected_size = playable_trailers.get_projected_number_of_trailers()
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('source:', source, 'projected size:',
                                       projected_size)
                total_number_of_trailers += projected_sizes_map[source]

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('total_number_of_trailers:',
                                       total_number_of_trailers)
                if trailer_index_to_play < total_number_of_trailers:
                    found_playable_trailers = playable_trailers
                    break

            try:
                attempts += 1
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug(
                        'PlayableTrailerService.next Attempt:', attempts,
                        'manager:', found_playable_trailers.__class__.__name__)
                trailer = found_playable_trailers.get_next_movie()
                TrailerCache.validate_cached_files(trailer)

                # If cached trailer is invalid, then skip over this trailer.

                if trailer[Movie.DISCOVERY_STATE] != Movie.DISCOVERY_READY_TO_DISPLAY:
                    trailer = None
                else:
                    found_playable_trailers.set_starving(False)
                    title = trailer[Movie.TITLE] + \
                        ' : ' + trailer[Movie.TRAILER]
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'PlayableTrailerService.next found:', title)
            except (queue.Empty):
                found_playable_trailers.set_starving(True)
                trailer = None

        duration_of_first_attempt = datetime.datetime.now() - start_time
        second_attempt_start_time = None
        second_method_attempts = None

        if trailer is None:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(' trailer not found by preferred method',
                                   trace=Trace.TRACE)

            # Alternative method is to pick a random PlayableTrailersContainer to start
            # with and then find one that has a trailer. Otherwise, camp out.

            second_attempt_start_time = datetime.datetime.now()
            second_method_attempts = 0
            iteration = 0
            playable_trailers_list = [*playable_trailers_map.keys()]
            DiskUtils.RandomGenerator.shuffle(playable_trailers_list)
            for source in itertools.cycle(playable_trailers_list):
                try:
                    playable_trailers = playable_trailers_map[source]
                    movie_data = playable_trailers.get_movie_data()
                    self.throw_exception_on_forced_to_stop(
                        movie_data=movie_data)

                    if (playable_trailers.get_number_of_playable_movies() == 0
                            and playable_trailers.get_movie_data().get_number_of_movies() > 0
                            and playable_trailers.is_playable_trailers()):
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'Shuffling because',
                                'discoveredTrailerQueue empty',
                                'source:', source,
                                trace=Trace.TRACE_DISCOVERY)
                        playable_trailers.get_movie_data().\
                            shuffle_discovered_trailers(mark_unplayed=True)
                    trailer = playable_trailers.get_next_movie()

                    # If cached trailer is invalid, then skip over this
                    # trailer.

                    if trailer[Movie.DISCOVERY_STATE] != Movie.DISCOVERY_READY_TO_DISPLAY:
                        trailer = None

                    if trailer is not None:
                        break
                except (queue.Empty):
                    pass  # try again

                iteration += 1
                if iteration % len(playable_trailers_list) == 0:
                    second_method_attempts += 1
                    Monitor.get_instance().throw_exception_if_shutdown_requested(
                        delay=0.5)

        if trailer is None:
            self._next_failures += 1
        else:
            trailer[Movie.TRAILER_PLAYED] = True
            title = trailer[Movie.TITLE] + ' : ' + trailer[Movie.TRAILER]
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('PlayableTrailerService.next trailer:',
                                   title)

        duration = datetime.datetime.now() - start_time
        self._next_total_duration += duration.seconds
        self._next_calls += 1
        self._next_attempts += attempts
        self._next_total_first_method_attempts += attempts

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('elapsedTime:', duration.seconds, 'seconds',
                               'FirstMethod- elapsedTime:',
                               duration_of_first_attempt.seconds,
                               'attempts:', attempts, trace=Trace.STATS)
        if second_method_attempts is not None:
            self._next_attempts += second_method_attempts
            self._next_second_attempts += second_method_attempts
            second_duration = datetime.datetime.now() - second_attempt_start_time
            self._next_second_total_Duration += second_duration.seconds
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('SecondMethod- attempts:',
                                   second_method_attempts, 'elapsedTime:',
                                   second_duration.seconds, trace=Trace.STATS)

        if trailer is None:
            raise StopIteration

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Playing:', trailer[Movie.DETAIL_TITLE],
                               trace=Trace.TRACE)

        # Periodically report on played movie statistics

        self._played_movies_count += 1
        if (self._played_movies_count % 10) == 0:
            for source in playable_trailers_map:
                playable_trailers = playable_trailers_map[source]
                movie_data = playable_trailers.get_movie_data()
                movie_data.report_play_count_stats()

        return trailer

    def throw_exception_on_forced_to_stop(self, movie_data=None, delay=0):
        # type: (AbstractMovieData, float) -> None
        """

        :param movie_data:
        :param delay:
        :return:
        """
        Monitor.get_instance().throw_exception_if_shutdown_requested(delay=delay)
        if movie_data is not None and movie_data.restart_discovery_event.isSet():
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('RestartDiscoveryException source:',
                                   movie_data.get_movie_source())
            raise RestartDiscoveryException()
