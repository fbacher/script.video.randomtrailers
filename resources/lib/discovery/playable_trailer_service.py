# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""


import sys
import datetime
import queue

from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException
from common.imports import *
from common.monitor import Monitor
from common.logger import *
from common.movie import AbstractMovie
from common.movie_constants import MovieField

from diagnostics.statistics import Statistics
from diagnostics.play_stats import PlayStatistics

from discovery.abstract_movie_data import AbstractMovieData
from discovery.restart_discovery_exception import StopDiscoveryException
from discovery.playable_trailers_container import PlayableTrailersContainer
from discovery.utils.recently_played_trailers import RecentlyPlayedTrailers

module_logger = BasicLogger.get_module_logger(module_path=__file__)


class PlayableTrailerService:
    """
        Abstract class with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """
    logger: BasicLogger = None

    def __init__(self) -> None:
        """

        :return:
        """
        clz = type(self)
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)
            clz.logger.debug(f'Initialized')

        self._next_total_duration: int = 0
        self._next_calls: int = 0
        self._next_attempts: int = 0
        self._load_fetch_total_duration: int = 0
        self._next_failures: int = 0
        self._next_total_first_method_attempts: int = 0
        self._next_second_attempts: int = 0
        self._next_second_total_Duration: int = 0
        self._played_movies_count: int = 0
        self._previous_title: str = ''

    def iter(self) -> Iterable:
        """

        :return:
        """
        return self.__iter__()

    def __iter__(self) -> Iterable:
        """

        :return:
        """
        return self

    def next(self) -> AbstractMovie:
        """

        :return:
        """
        return self.__next__()

    def __next__(self) -> AbstractMovie:
        """

        :return:
        """
        clz = type(self)
        movie: AbstractMovie = None
        try:
            finished: bool = False
            attempt: int = 0
            while not finished:
                try:
                    attempt += 1
                    movie = self._do_next()
                    finished = True
                except StopDiscoveryException:
                    Monitor.throw_exception_if_abort_requested(timeout=0.10)
                    if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                        clz.logger.debug_verbose(
                            f'Rediscovery in progress. attempt: {attempt}')
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')
            reraise(*sys.exc_info())

        return movie

    def _do_next(self) -> AbstractMovie:
        """
            Get the next trailer to play.

            Ideally, we get a random trailer that is playable.

            Since there are multiple sources of trailers (Library, TFH, TMDb, etc.)
            and that we are discovering the trailers as we go along, things are a bit
            messy. First, we estimate the number of trailers that will be found for
            each of the sources, then we pick a random movie from the aggregate of
            those sources. If the movie has a trailer, great, we are done. But if
            there is no trailer yet available, we have to try again, and again....
            This method attempts to give a distribution of played trailers
            from the sources in proportion the number of trailers from each source.
            But if we are early in discovery of trailers we can hit a lot of movies
            which we simply haven't had time to discover.

            Well, we can't stick with this method forever, so if after several tries
            we still don't have a trailer we switch to ignoring keeping the trailers in
            proportion to the number of movies in each source and simply find a source
            that has something playable. We randomize the source we pick from so we don't
            always pick from the same ones.

            If this still doesn't work, then the backup plan is to finding the first
            source which has a trailer which has already been played. We try to keep
            from playing the same ones over and over, but depending upon the situation
            this may not be completely avoidable. However, over time, as caches are
            built, this problem should go away.

        :return Movie containing trailer ready to play:
        """
        clz = type(self)
        try:
            while not PlayableTrailersContainer.is_any_trailers_available_to_play():
                self.throw_exception_on_forced_to_stop(
                    movie_data=None, delay=0.25)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

        """
        First, get the number of projected trailers for each movie source
        """
        start_time: datetime.datetime = datetime.datetime.now()
        playable_trailers_map: Dict[str, PlayableTrailersContainer]
        playable_trailers_map = PlayableTrailersContainer.get_instances()
        projected_sizes_map: Dict[str, int] = self.get_projected_sizes()
        total_number_of_trailers: int
        total_number_of_trailers = sum(projected_sizes_map.values())

        """ 
        Now, pick a virtual movie index based upon the total number of movies
        from all sources. Then, map the virtual index to a source and then see
        if we can play something from that source.
        
        """

        trailer: AbstractMovie = None
        attempts: int = 0
        while trailer is None and attempts < 3:
            attempts += 1
            if attempts > 1:
                Monitor.throw_exception_if_abort_requested(timeout=0.5)
            try:
                trailer_index_to_play = DiskUtils.RandomGenerator.randint(
                    0, total_number_of_trailers - 1)
                if clz.logger.isEnabledFor(DISABLED):
                    clz.logger.debug_extra_verbose(
                        f'PlayableTrailerService.next trailer_index_to_play: '
                        f'{trailer_index_to_play}')
            except ValueError as e:  # Empty range
                Monitor.throw_exception_if_abort_requested(timeout=0.01)
                continue

            # Translate virtual movie index into a specific movie from
            # a source.
            #
            # TODO: This could be simpler
            #
            total_number_of_trailers: int = 0
            found_playable_trailers: PlayableTrailersContainer = None
            source: str = ''
            for source in playable_trailers_map:
                playable_trailers: PlayableTrailersContainer
                playable_trailers = playable_trailers_map[source]
                if not playable_trailers.is_playable_trailers():
                    continue

                movie_data = playable_trailers.get_movie_data()
                self.throw_exception_on_forced_to_stop(movie_data=movie_data)
                try:
                    total_number_of_trailers += projected_sizes_map[source]
                    if trailer_index_to_play < total_number_of_trailers:
                        found_playable_trailers = playable_trailers
                        break
                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    clz.logger.exception(e)
            try:
                if attempts > 1 and clz.logger.isEnabledFor(DEBUG_VERBOSE):
                    clz.logger.debug_verbose(
                        f'PlayableTrailerService.next Attempt: {attempts} '
                        f'manager: {found_playable_trailers.__class__.__name__}')
                trailer = found_playable_trailers.get_next_movie()
            except queue.Empty:
                if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                    clz.logger.debug_verbose(f'source queue empty {source}')
                # found_playable_trailers.set_starving(True)
                trailer = None

        duration_of_first_attempt = datetime.datetime.now() - start_time
        Statistics.add_next_trailer_wait_time(duration_of_first_attempt.seconds,
                                              attempts)
        self._next_attempts += attempts
        self._next_total_first_method_attempts += attempts

        if trailer is None:
            """
            Well, that first method didn't work.

            Randomly go through each source, 
            ignoring number of movies in each source. Set starving on 
            second loop.

            """
            if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                clz.logger.debug_verbose('Trailer not found by preferred method',
                                         trace=Trace.TRACE)

            second_attempt_start_time = datetime.datetime.now()
            second_method_attempts = 0
            playable_trailers_list = [*playable_trailers_map.keys()]

            # Shuffle the list of keys (sources)

            DiskUtils.RandomGenerator.shuffle(playable_trailers_list)
            first_source: str = playable_trailers_list[0]
            source: str

            # First time through, don't set starving

            is_starving: bool = False
            for source in playable_trailers_list:
                second_method_attempts += 1
                if second_method_attempts > 1 and source == first_source:
                    # No more patience, get anything

                    is_starving = True
                playable_trailers = playable_trailers_map[source]
                if is_starving:
                    playable_trailers.set_starving(is_starving)
                if not playable_trailers.is_playable_trailers():
                    continue
                try:
                    if (second_method_attempts > 1
                            and clz.logger.isEnabledFor(DEBUG_VERBOSE)):
                        clz.logger.debug_verbose(
                            f'PlayableTrailerService.next Attempt: '
                            f'{second_method_attempts} '
                            f'manager: {playable_trailers.__class__.__name__}')
                    trailer = playable_trailers.get_next_movie()
                except queue.Empty:
                    if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                        clz.logger.debug_verbose(f'source queue empty {source}')
                    # playable_trailers.set_starving(True)
                    trailer = None

                if trailer is not None:
                    if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(f'movie: '
                                                       f'{trailer.get_title()} '
                                                       f'found in second method '
                                                       f'starving: {is_starving}')
                    break

            if second_method_attempts is not None:
                self._next_attempts += second_method_attempts
                self._next_second_attempts += second_method_attempts
                second_duration = datetime.datetime.now() - second_attempt_start_time
                self._next_second_total_Duration += second_duration.seconds
                Statistics.add_next_trailer_second_attempt_wait_time(
                    second_duration.seconds,
                    second_method_attempts)

        if trailer is None:
            """
            Well, that second method didn't work.
            
            This time, randomly pick a source and see if there is something playable from
            it. This ignores the number of movies in each source so we don't skip over
            some playable trailers from a source with few movies.
            
            TODO: Add middle loop, much like before, but looks at each source and
            sets starving on second traversal.
            
            """
            if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                clz.logger.debug_verbose('Trailer not found by preferred method',
                                         trace=Trace.TRACE)

            third_attempt_start_time = datetime.datetime.now()
            third_method_attempts: int = 0
            playable_trailers_list = [*playable_trailers_map.keys()]

            # Shuffle the list of keys (sources)

            DiskUtils.RandomGenerator.shuffle(playable_trailers_list)
            first_source: str = playable_trailers_list[0]
            source: str
            for source in playable_trailers_list:
                if third_method_attempts > 0 and source == first_source:

                    # No more patience, get anything
                    # Give some time to discover a movie
                    Monitor.throw_exception_if_abort_requested(timeout=5.0)

                if third_method_attempts == len(playable_trailers_list) - 1:
                    # After giving this second attempt a go through all
                    # of the trailer types, see if we can replay a trailer
                    # that we have on hand.
                    #
                    # Only need to try this once since none will be added
                    # until a trailer is found for playing

                    trailer = RecentlyPlayedTrailers.get_recently_played()
                    if trailer is not None:
                        if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                            clz.logger.debug_verbose(f'movie: {trailer.get_title()} '
                                                     f'found in third method')
                        break

                third_method_attempts += 1
                try:
                    playable_trailers = playable_trailers_map[source]
                    movie_data = playable_trailers.get_movie_data()
                    self.throw_exception_on_forced_to_stop(
                        movie_data=movie_data)

                    trailer = movie_data.get_playable_trailer_immediately()
                    if trailer is None:
                        if (not playable_trailers.is_shuffled()
                                and playable_trailers.get_number_of_playable_movies() == 0
                                and movie_data.get_number_of_movies() > 0
                                and playable_trailers.is_playable_trailers()):
                            if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                                clz.logger.debug_verbose(f'Shuffling because '
                                                         f'discoveredTrailerQueue empty '
                                                         f'source: {source}',
                                                         trace=Trace.TRACE_DISCOVERY)
                            #
                            # discovered movie queue empty because all have played.
                            # Reload.

                            movie_data.shuffle_discovered_movies(mark_unplayed=True)
                            playable_trailers.set_shuffled()

                        trailer = playable_trailers.get_next_movie()
                    if trailer is not None:

                        # If cached movie is invalid, then skip over this
                        # MovieField.

                        if (trailer.get_discovery_state() !=
                                MovieField.DISCOVERY_READY_TO_DISPLAY):
                            trailer = None

                    if trailer is not None:
                        break
                except queue.Empty:
                    pass  # try again
            if third_method_attempts is not None:
                self._next_attempts += third_method_attempts
                self._next_second_attempts += third_method_attempts
                third_duration = datetime.datetime.now() - third_attempt_start_time
                self._next_second_total_Duration += third_duration.seconds
                Statistics.add_next_trailer_second_attempt_wait_time(
                     third_duration.seconds,
                     third_method_attempts)

        if trailer is None:  # No movie found from all our sources (lib, tmdb, tfh, etc)
            self._next_failures += 1
        else:
            trailer.set_trailer_played(True)
            title = trailer.get_title() + ' : ' + trailer.get_trailer_path()
            if (self._previous_title == title and
                    RecentlyPlayedTrailers.get_number_of_trailers() > 1):
                if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                    clz.logger.debug_verbose(f'Skipping previously played: {title}')
                trailer = None
                self._previous_title = ''  # Don't do twice in a row

        duration = datetime.datetime.now() - start_time
        self._next_total_duration += duration.seconds
        self._next_calls += 1

        is_ok: bool = Debug.validate_detailed_movie_properties(trailer)
        if not is_ok:
            trailer.set_discovery_state(MovieField.NOT_FULLY_DISCOVERED)
            trailer.set_trailer_played(False)
            trailer = None

        if trailer is None:
            raise StopIteration()

        if clz.logger.isEnabledFor(DEBUG_VERBOSE):
            clz.logger.debug_verbose(f'Playing: {trailer.get_detail_title()} '
                                     f'type: {type(trailer)} '
                                     f'trailer: {trailer.get_optimal_trailer_path()}',
                                     trace=Trace.TRACE)

        # Periodically report on played movie statistics

        self._played_movies_count += 1
        if Trace.is_enabled(Trace.TRACE_PLAY_STATS):
            if (self._played_movies_count % 100) == 0:
                PlayStatistics.report_play_count_stats()

        return trailer

    def get_projected_sizes(self) -> Dict[str, int]:
        """
        The preferred way to get the next trailer is to try to get it evenly from the
        different sources based upon the number of trailers in each. So, if Library
        trailers make up 25% of the total, then 25% of time we get trailers from the
        Library. This doesn't always work out because we are discovering (downloading)
        the trailers and info as we go along, so sometimes we have to select from another
        source.

        Here we essentially pick a random number within the total number of movies
        likely to have trailers for all sources. Then figure out which source that
        number (index) belongs to.

        """
        clz = type(self)
        total_number_of_trailers: int = 0
        start_time: datetime.datetime = datetime.datetime.now()

        # Considered locking all TrailerManagers here to guarantee
        # that lengths don't change while finding the right movie
        # but that might block the readyToPlayQueue from getting
        # loaded. Besides, it doesn't matter too much if we play
        # the incorrect movie, as long as we get one. The
        # major fear is if we have no trailers at all, but that
        # will be handled elsewhere.

        # Get total number of trailers from all managers.

        # It is possible that all discovery is complete and there is nothing
        # to play.

        nothing_to_play: bool = True
        playable_trailers_map: Dict[str, PlayableTrailersContainer]
        playable_trailers_map = PlayableTrailersContainer.get_instances()

        # Need to use the same projected sizes throughout this method.

        projected_sizes_map: Dict[str, int] = {}

        for source in playable_trailers_map:
            playable_trailers: PlayableTrailersContainer
            playable_trailers = playable_trailers_map[source]
            playable_trailers.clear_shuffled()
            if not playable_trailers.is_playable_trailers():
                continue

            movie_data = playable_trailers.get_movie_data()
            self.throw_exception_on_forced_to_stop(movie_data=movie_data)
            number_of_trailers: int = movie_data.get_number_of_trailers()
            trailers_queue_size = movie_data.get_discovered_trailer_queue_size()
            if clz.logger.isEnabledFor(DEBUG):
                number_of_movies: int = movie_data.get_number_of_movies()
                ready_to_play_queue_size: int = \
                    playable_trailers.get_ready_to_play_queue().qsize()
                trailer_fetch_queue_size: int = \
                    movie_data.get_trailers_to_fetch_queue_size()
                if ready_to_play_queue_size < playable_trailers.READY_TO_PLAY_QUEUE_SIZE:
                    clz.logger.debug_extra_verbose(f'{source} trailers: '
                                                   f'{number_of_trailers} '
                                                   f'movies: {number_of_movies} '
                                                   f'discoveredTrailersQueue size:'
                                                   f'{trailers_queue_size} '
                                                   f'readyToPlayQueue size: '
                                                   f'{ready_to_play_queue_size} '
                                                   f'trailersToFetchQueue size: '
                                                   f'{trailer_fetch_queue_size}')

            projected_size = playable_trailers.get_projected_number_of_trailers()
            projected_sizes_map[source] = projected_size
            previous_projected_size: int = playable_trailers.previous_projected_size

            if (previous_projected_size != projected_size
                    and clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)
                    and Trace.is_enabled(Trace.TRACE_PLAY_STATS)):
                clz.logger.debug_extra_verbose(f'source: {source} ' 
                                               f'projected size: {projected_size}',
                                               trace=Trace.TRACE_PLAY_STATS)
            playable_trailers.previous_projected_size = previous_projected_size
            total_number_of_trailers += projected_size
            if not movie_data.is_discovery_complete() or number_of_trailers != 0:
                nothing_to_play = False

            # If we have played everything, then we start over.

            if (trailers_queue_size == 0
                    and playable_trailers.is_playable_trailers()):
                if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                    clz.logger.debug('Shuffling because discoveredTrailerQueue empty',
                                     trace=Trace.TRACE_DISCOVERY)
                movie_data.shuffle_discovered_movies(mark_unplayed=True)
                playable_trailers.set_shuffled()

        if (clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)
                and Trace.is_enabled(Trace.TRACE_PLAY_STATS)):
            clz.logger.debug_extra_verbose(f'total_number_of_trailers: '
                                           f'{total_number_of_trailers}',
                                           trace=Trace.TRACE_PLAY_STATS)
        if nothing_to_play:
            if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                clz.logger.debug_verbose(f'Nothing to Play! numTrailers: '
                                         f'{total_number_of_trailers}')
            raise StopIteration()

        return projected_sizes_map

    def throw_exception_on_forced_to_stop(self,
                                          movie_data: AbstractMovieData = None,
                                          delay: float = 0) -> None:
        """

        :param movie_data:
        :param delay:
        :return:
        """
        clz = type(self)
        Monitor.throw_exception_if_abort_requested(timeout=delay)
        if movie_data is not None and movie_data.stop_discovery_event.isSet():
            if clz.logger.isEnabledFor(DEBUG_VERBOSE):
                clz.logger.debug_verbose(f'StopDiscoveryException source: '
                                         f'{movie_data.get_movie_source()}')
            raise StopDiscoveryException()
