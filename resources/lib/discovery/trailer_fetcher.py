# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import six

from kodi_six import xbmc

from common.monitor import Monitor
from common.constants import Constants, Movie, RemoteTrailerPreference
from common.disk_utils import DiskUtils
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.watchdog import WatchDog
from common.settings import Settings
from common.logger import (Logger, Trace, LazyLogger)
from common.messages import Messages
from backend.tmdb_utils import (TMDBUtils)
from backend.movie_entry_utils import (MovieEntryUtils)

# from backend.base_movie_data import AbstractMovieData
from discovery.abstract_movie_data import AbstractMovieData
from backend.rating import Rating
from backend.json_utils import JsonUtils
from backend.json_utils_basic import (JsonUtilsBasic)
from cache.cache import (Cache)
from cache.cache_index import (CacheIndex)
from cache.trailer_unavailable_cache import (TrailerUnavailableCache)
from backend.genreutils import GenreUtils
from backend.backend_constants import YOUTUBE_URL_PREFIX
from backend.yd_stream_extractor_proxy import YDStreamExtractorProxy

from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from discovery.playable_trailers_container import PlayableTrailersContainer
from discovery.restart_discovery_exception import RestartDiscoveryException

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.trailer_fetcher')
else:
    module_logger = LazyLogger.get_addon_module_logger()


# noinspection Annotator
class TrailerFetcher(TrailerFetcherInterface):
    """

    """

    NUMBER_OF_FETCHERS = 1
    _trailer_fetchers = []

    def __init__(self, movie_data,
                 thread_name='No TrailerFetcher Thread Name'):
        # type: (AbstractMovieData, TextType, TextType)-> None
        """

                 :param movie_data
                 :param thread_name:
        """

        movie_source = movie_data.get_movie_source()
        self._logger = module_logger.getChild(
            self.__class__.__name__ + ':' + movie_source)
        self._logger.enter()
        thread_name = thread_name
        super().__init__(thread_name=thread_name)
        self._movie_data = movie_data  # type: AbstractMovieData
        self._playable_trailers = PlayableTrailersContainer(
            movie_data.get_movie_source())
        self._playable_trailers.set_movie_data(movie_data)
        self._missing_trailers_playlist = Playlist.get_playlist(
            Playlist.MISSING_TRAILERS_PLAYLIST, append=False, rotate=True)
        self._start_fetch_time = None
        self._stop_fetch_time = None
        self._stop_add_ready_to_play_time = None

    def start_fetchers(self):
        # type: () ->None
        """

        :return:
        """
        self._logger.enter()
        WatchDog.register_thread(self)
        i = 0
        while i < self.NUMBER_OF_FETCHERS:
            i += 1
            trailer_fetcher = TrailerFetcher(
                self._movie_data,
                thread_name='TrailerFetcher_' +
                self._movie_data.get_movie_source() + ':' + str(i))
            TrailerFetcher._trailer_fetchers.append(trailer_fetcher)
            WatchDog.register_thread(trailer_fetcher)
            trailer_fetcher.start()
            if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
                self._logger.debug_verbose('trailer fetcher started')

    def shutdown_thread(self):
        # type: () -> None
        """

        :return:
        """
        TrailerUnavailableCache.tmdb_cache_changed(flush=True)
        TrailerUnavailableCache.library_cache_changed(flush=True)
        self._movie_data = None
        self._playable_trailers = None

    def prepare_for_restart_discovery(self, stop_thread):
        # type: (bool) -> None
        """

        :param stop_thread
        :return:
        """
        self._logger.enter()
        self._playable_trailers.prepare_for_restart_discovery(stop_thread)

        if stop_thread:
            self._movie_data = None
            self._playable_trailers = None

    def run(self):
        # type: () -> None
        """

        :return:
        """
        try:
            self.run_worker()
        except (ShutdownException, AbortException):
            return  # Just exit thread
        except (Exception):
            self._logger.exception('')

    def run_worker(self):
        # type: () -> None
        """

        :param self:
        :return:
        """
        while not self._movie_data.have_trailers_been_discovered():
            Monitor.throw_exception_if_shutdown_requested(delay=0.5)

        # Wait one second after something has been discovered so that
        # there are more entries to process. This way the list is a bit more
        # randomized at the beginning.

        Monitor.throw_exception_if_shutdown_requested(delay=1.0)
        self._movie_data.shuffle_discovered_trailers(mark_unplayed=False)

        while True:
            try:
                Monitor.throw_exception_if_shutdown_requested()

                if (self._movie_data.is_discovery_complete() and
                        self._movie_data.get_number_of_movies() == 0):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Shutting down Trailer Fetcher',
                                           'due to no movies after discovery complete.')
                    break

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('waiting to fetch')
                player_starving = self._playable_trailers.is_starving()
                trailer = self._movie_data.get_from_fetch_queue(
                    player_starving)
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('got movie from fetch queue:',
                                       trailer[Movie.TITLE])
                self.fetch_trailer_to_play(trailer)
            except (AbortException, ShutdownException) as e:
                six.reraise(*sys.exc_info())
            except (Exception) as e:
                self._logger.exception('')

    def fetch_trailer_to_play(self,
                              trailer  # type: MovieType
                              ):
        # type: (...) -> None
        """

        :param trailer:
        :return:
        """
        finished = False
        while not finished:
            try:
                discovery_state = trailer[Movie.DISCOVERY_STATE]
                if discovery_state >= Movie.DISCOVERY_COMPLETE:
                    self.throw_exception_on_forced_to_stop()
                    if discovery_state < Movie.DISCOVERY_READY_TO_DISPLAY:
                        fully_populated_trailer = self.get_detail_info(trailer)
                        if fully_populated_trailer is None:
                            self._movie_data.remove_discovered_movie(trailer)
                            continue
                        self._playable_trailers.add_to_ready_to_play_queue(
                            fully_populated_trailer)
                    else:
                        self._playable_trailers.add_to_ready_to_play_queue(
                            trailer)
                else:
                    self._fetch_trailer_to_play_worker(trailer)
                finished = True
            except (RestartDiscoveryException):
                Monitor.throw_exception_if_shutdown_requested(0.10)

    def _fetch_trailer_to_play_worker(self,
                                      trailer  # type: MovieType
                                      ):
        # type: ( ...) -> None
        """

        :param trailer:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter('title:', trailer[Movie.TITLE],
                               'source:', trailer[Movie.SOURCE],
                               'discovery_state:', trailer[Movie.DISCOVERY_STATE],
                               'trailer:', trailer[Movie.TRAILER])
        self._start_fetch_time = datetime.datetime.now()
        keep_new_trailer = True

        self.throw_exception_on_forced_to_stop()
        if trailer[Movie.TRAILER] == Movie.TMDB_SOURCE:
            #
            # Entries with a'trailer' value of Movie.TMDB_SOURCE are trailers
            # which are not from any movie in Kodi but come from
            # TMDB, similar to iTunes or YouTube.
            #
            # Query TMDB for the details and replace the
            # temporary trailer entry with what is discovered.
            # Note that the Movie.SOURCE value will be
            # set to Movie.TMDB_SOURCE
            #
            # Debug.dump_json(text='Original trailer:', data=trailer)
            tmdb_id = MovieEntryUtils.get_tmdb_id(trailer)

            status, populated_trailer = self.get_tmdb_trailer(trailer[Movie.TITLE],
                                                              tmdb_id,
                                                              Movie.TMDB_SOURCE)
            self.throw_exception_on_forced_to_stop()

            if status == Constants.TOO_MANY_TMDB_REQUESTS:
                self._missing_trailers_playlist.record_played_trailer(
                    trailer, use_movie_path=True, msg='Too many TMDB requests')
                return
            elif status == Constants.REJECTED_STATUS:
                # Looks like there isn't an appropriate trailer for
                # this movie.
                self._missing_trailers_playlist.record_played_trailer(
                    trailer, use_movie_path=True, msg='No Trailer')
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('No valid trailer found for TMDB trailer:',
                                       trailer[Movie.TITLE],
                                       'removed:',
                                       self._movie_data.get_number_of_removed_trailers() + 1,
                                       'kept:',
                                       self._playable_trailers.get_number_of_added_trailers(),
                                       'movies:',
                                       self._movie_data.get_number_of_added_movies())
                keep_new_trailer = False
            elif populated_trailer is not None:
                trailer.update(populated_trailer)
            elif status == 0:
                # Not sure what happened. Reject movie anyway.
                self._missing_trailers_playlist.record_played_trailer(
                    trailer, use_movie_path=True, msg='No Trailer')
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('No trailer found for TMDB trailer:',
                                       trailer[Movie.TITLE],
                                       'removed:',
                                       self._movie_data.get_number_of_removed_trailers() + 1,
                                       'kept:',
                                       self._playable_trailers.get_number_of_added_trailers(),
                                       'movies:',
                                       self._movie_data.get_number_of_added_movies())
                keep_new_trailer = False

        else:
            source = trailer[Movie.SOURCE]
            if source == Movie.LIBRARY_SOURCE:

                if (trailer[Movie.TRAILER] == '' and
                        TrailerUnavailableCache.is_library_id_missing_trailer(trailer[Movie.MOVIEID])):
                    # Try to find trailer from TMDB
                    tmdb_id = MovieEntryUtils.get_tmdb_id(trailer)

                    # Ok, tmdb_id not in Kodi database, query TMDB

                    if (tmdb_id is None or tmdb_id == ''
                        ) and not trailer.get(Movie.TMDB_ID_NOT_FOUND, False):
                        tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                            trailer[Movie.TITLE], trailer['year'])
                        self.throw_exception_on_forced_to_stop()

                        if tmdb_id is None:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Can not get TMDB id for Library movie:',
                                                   trailer[Movie.TITLE], 'year:',
                                                   trailer[Movie.YEAR])
                            self._missing_trailers_playlist.record_played_trailer(
                                trailer, use_movie_path=True,
                                msg=' Movie not found at tmdb')
                            trailer[Movie.TMDB_ID_NOT_FOUND] = True
                        else:
                            MovieEntryUtils.set_tmdb_id(trailer, tmdb_id)

                            # We found an id from TMDB, update Kodi database
                            # so that we don't have to go through this again

                            if Settings.get_update_tmdb_id():
                                MovieEntryUtils.update_database_unique_id(
                                    trailer)

                    if tmdb_id is not None:

                        # We only want the trailer, ignore other fields.

                        status, new_trailer_data = self.get_tmdb_trailer(
                            trailer[Movie.TITLE], tmdb_id, source, ignore_failures=True,
                            library_id=trailer[Movie.MOVIEID])
                        self.throw_exception_on_forced_to_stop()

                        if status == Constants.TOO_MANY_TMDB_REQUESTS or status == -1:
                            keep_new_trailer = False
                            # Give up playing this trailer this time around. It will
                            # still be available for display later.
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(trailer[Movie.TITLE],
                                                   'could not get trailer due to status:',
                                                   status)
                            return

                        elif status == Constants.REJECTED_STATUS:
                            keep_new_trailer = False
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    'Unexpected REJECTED_STATUS. Ignoring')

                        elif (new_trailer_data is None
                              or new_trailer_data.get(Movie.TRAILER) is None
                              or new_trailer_data.get(Movie.TRAILER) == ''):
                            keep_new_trailer = False
                            TrailerUnavailableCache.add_missing_library_trailer(
                                tmdb_id=tmdb_id,
                                library_id=trailer[Movie.MOVIEID],
                                title=trailer[Movie.TITLE],
                                year=trailer[Movie.YEAR],
                                source=source)
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    'No valid trailer found for Library trailer:',
                                    trailer[Movie.TITLE],
                                    'removed:',
                                    self._movie_data.get_number_of_removed_trailers() + 1,
                                    'kept:',
                                    self._playable_trailers.get_number_of_added_trailers(),
                                    'movies:',
                                    self._movie_data.get_number_of_added_movies())
                        else:
                            # Keep trailer field,not entire new trailer
                            keep_new_trailer = False
                            trailer[Movie.TRAILER] = new_trailer_data[Movie.TRAILER]

            elif source == Movie.ITUNES_SOURCE:
                if not trailer.get(Movie.TMDB_ID_NOT_FOUND, False):
                    tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                        trailer[Movie.TITLE], trailer[Movie.YEAR])
                else:
                    tmdb_id = None

                self.throw_exception_on_forced_to_stop()
                if tmdb_id is None:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Can not get TMDB id for iTunes movie:',
                                           trailer[Movie.TITLE], 'year:',
                                           trailer[Movie.YEAR])
                    self._missing_trailers_playlist.record_played_trailer(
                        trailer, use_movie_path=True,
                        msg=' Movie not found at tmdb')
                    trailer[Movie.TMDB_ID_NOT_FOUND] = True
                else:
                    MovieEntryUtils.set_tmdb_id(trailer, tmdb_id)

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Finished second discovery level for movie:',
                               trailer.get(Movie.TITLE),
                               '(tentatively) keep:', keep_new_trailer)

        # If no trailer possible then remove it from further consideration

        if keep_new_trailer:
            if Movie.YEAR not in trailer:
                pass

            movie_id = trailer[Movie.TITLE] + '_' + str(trailer[Movie.YEAR])
            movie_id = movie_id.lower()

            self.throw_exception_on_forced_to_stop()
            with AbstractMovieData.get_aggregate_trailers_by_name_date_lock():
                if trailer[Movie.TRAILER] == '':
                    keep_new_trailer = False
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Not keeping:', trailer[Movie.TITLE],
                                           'because trailer is empty')
                elif movie_id in AbstractMovieData.get_aggregate_trailers_by_name_date():
                    keep_new_trailer = False

                    trailerInDictionary = (
                        AbstractMovieData.get_aggregate_trailers_by_name_date()[movie_id])
                    source_of_trailer_in_dictionary = trailerInDictionary[Movie.SOURCE]

                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Duplicate Movie id:', movie_id,
                                           'source:', source_of_trailer_in_dictionary)

                    # Always prefer the local trailer
                    source = trailer[Movie.SOURCE]
                    if source == Movie.LIBRARY_SOURCE:
                        if source_of_trailer_in_dictionary == Movie.LIBRARY_SOURCE:
                            #
                            # Joy, two copies, both with trailers. Toss the new one.
                            #

                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Not keeping:',
                                                   trailer[Movie.TITLE],
                                                   'because dupe and both in library')
                        else:
                            # Replace non-local version with this local one.
                            keep_new_trailer = True
                    elif source_of_trailer_in_dictionary == Movie.LIBRARY_SOURCE:
                        #

                        keep_new_trailer = False

                        # TODO: Verify

                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('Duplicate:', trailer[Movie.TITLE],
                                               'original source:',
                                               source_of_trailer_in_dictionary,
                                               'new source:', source)
                    elif source_of_trailer_in_dictionary == source:
                        keep_new_trailer = False
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('Not keeping:', trailer[Movie.TITLE],
                                               'because duplicate source')
                    elif source == Movie.FOLDER_SOURCE:
                        keep_new_trailer = True
                    elif source == Movie.ITUNES_SOURCE:
                        keep_new_trailer = True
                    elif source == Movie.TMDB_SOURCE:
                        keep_new_trailer = True

        if keep_new_trailer:
            if (Settings.is_use_trailer_cache() and
                    (DiskUtils.is_url(trailer[Movie.TRAILER]) or
                     trailer[Movie.SOURCE] != Movie.LIBRARY_SOURCE)):
                self.cache_remote_trailer(trailer)

                # If download for cache fails, then probably can't play from
                # URL either

                if trailer.get(Movie.CACHED_TRAILER) is None:
                    keep_new_trailer = False
            else:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Not caching:', trailer[Movie.TITLE],
                                       'trailer:', trailer[Movie.TRAILER],
                                       'source:', trailer[Movie.SOURCE],
                                       'state:', trailer[Movie.DISCOVERY_STATE])

        if keep_new_trailer:
            normalized = False
            if Settings.is_normalize_volume_of_downloaded_trailers():
                self.normalize_trailer_sound(trailer)
                normalized = True

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(trailer[Movie.TITLE], 'audio normalized:',
                                   normalized,
                                   'trailer:', trailer.get(
                                       Movie.NORMALIZED_TRAILER),
                                   'source:', trailer[Movie.SOURCE])

            trailer[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_COMPLETE
            AbstractMovieData.get_aggregate_trailers_by_name_date()[
                movie_id] = trailer
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(trailer[Movie.TITLE], 'added to AggregateTrailers',
                                   'trailer:', trailer[Movie.TRAILER],
                                   'source:', trailer[Movie.SOURCE])

        else:
            self._movie_data.remove_discovered_movie(trailer)

        if keep_new_trailer:
            fully_populated_trailer = self.get_detail_info(trailer)
            if fully_populated_trailer is None:
                self._movie_data.remove_discovered_movie(trailer)
            else:
                # TODO: DELETE ME
                assert trailer.get(Movie.DETAIL_TITLE) == \
                    fully_populated_trailer.get(Movie.DETAIL_TITLE), \
                    'LEAK: get_detail_info FAILED to copy fields to original trailer'

                self._playable_trailers.add_to_ready_to_play_queue(
                    fully_populated_trailer)

        self._stop_fetch_time = datetime.datetime.now()
        self._stop_add_ready_to_play_time = datetime.datetime.now()
        discovery_time = self._stop_fetch_time - self._start_fetch_time
        queue_time = self._stop_add_ready_to_play_time - self._stop_fetch_time
        trailer_type = trailer.get(Movie.TYPE, '')
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('took:', discovery_time.microseconds / 10000,
                               'ms',
                               'QueueTime:', queue_time.microseconds / 10000,
                               'ms',
                               'movie:', trailer.get(Movie.TITLE),
                               'type:', trailer_type,
                               'Kept:', keep_new_trailer, trace=Trace.STATS)

    def throw_exception_on_forced_to_stop(self, delay=0):
        # type: (float) -> None
        """

        :param delay:
        :return:
        """
        Monitor.throw_exception_if_shutdown_requested(delay=delay)
        if self._movie_data.restart_discovery_event.isSet():
            raise RestartDiscoveryException()

    # noinspection SyntaxError
    def get_tmdb_trailer(self,
                         movie_title,  # type: TextType
                         tmdb_id,  # type: Union[int, TextType]
                         source,  # type: TextType
                         ignore_failures=False,  # type: bool
                         library_id=None  # type: Union[None, TextType]
                         ):
        # type: (...) -> MovieType
        """
            Called in two situations:
                1) When a local movie does not have any trailer information
                2) When a TMDB search for multiple movies is used, which does NOT return
                    detail information, including trailer info.

            Given the movieId from TMDB, query TMDB for details and manufacture
            a trailer entry based on the results. The trailer itself will be a Youtube
            url.
        :param self:
        :param movie_title:
        :param tmdb_id:
        :param source:
        :param ignore_failures:
        :param library_id:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('title:', movie_title, 'tmdb_id:', tmdb_id,
                               'library_id:', library_id, 'ignore_failures:',
                               ignore_failures)

        if TrailerUnavailableCache.is_tmdb_id_missing_trailer(tmdb_id):
            CacheIndex.remove_unprocessed_movie(tmdb_id)
            if not ignore_failures:
                self._logger.exit(
                    'No trailer found for movie:', movie_title)
                return Constants.REJECTED_STATUS, None

        trailer_type = ''
        you_tube_base_url = YOUTUBE_URL_PREFIX
        image_base_url = 'http://image.tmdb.org/t/p/'
        include_adult = 'false'
        if Rating.check_rating(Rating.RATING_NC_17):
            include_adult = 'true'

        allowed_genres = []
        allowed_tags = []
        if Settings.get_filter_genres():
            allowed_genres = GenreUtils.get_instance().get_external_genre_ids(
                GenreUtils.TMDB_DATABASE, exclude=False)
            allowed_tags = GenreUtils.get_instance().get_external_keyword_ids(
                GenreUtils.TMDB_DATABASE, exclude=False)
        vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()

        # Since we may leave early, populate with dummy data
        messages = Messages.get_instance()
        missing_detail = messages.get_msg(Messages.MISSING_DETAIL)
        dict_info = {}
        dict_info[Movie.DISCOVERY_STATE] = Movie.NOT_FULLY_DISCOVERED
        dict_info[Movie.TITLE] = messages.get_msg(Messages.MISSING_TITLE)
        dict_info[Movie.ORIGINAL_TITLE] = ''
        dict_info[Movie.YEAR] = 0
        dict_info[Movie.STUDIO] = [missing_detail]
        dict_info[Movie.MPAA] = 'NR'
        dict_info[Movie.THUMBNAIL] = ''
        dict_info[Movie.TRAILER] = ''
        dict_info[Movie.FANART] = ''
        dict_info[Movie.FILE] = ''
        dict_info[Movie.DIRECTOR] = [missing_detail]
        dict_info[Movie.WRITER] = [missing_detail]
        dict_info[Movie.PLOT] = missing_detail
        dict_info[Movie.CAST] = [missing_detail]
        dict_info[Movie.RUNTIME] = 0
        dict_info[Movie.GENRE] = [missing_detail]
        dict_info[Movie.DETAIL_TAGS] = [missing_detail]
        dict_info[Movie.RATING] = 0
        dict_info[Movie.VOTES] = 0
        dict_info[Movie.ADULT] = False
        dict_info[Movie.SOURCE] = Movie.TMDB_SOURCE
        dict_info[Movie.TYPE] = 'Trailer'

        # Query The Movie DB for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        data = {}
        data['append_to_response'] = 'credits,releases,keywords,videos,alternative_titles'
        data['language'] = Settings.getLang_iso_639_1()
        data['api_key'] = Settings.get_tmdb_api_key()
        url = 'http://api.themoviedb.org/3/movie/' + str(tmdb_id)

        tmdb_result = None
        year = 0
        dump_msg = 'tmdb_id: ' + str(tmdb_id)
        try:
            if library_id is not None:
                cache_id = library_id
            else:
                cache_id = tmdb_id

            status_code, tmdb_result = JsonUtils.get_cached_json(
                url, movie_id=cache_id, error_msg=movie_title, source=source,
                params=data, dump_results=False, dump_msg=dump_msg)
            if status_code == 0:
                s_code = tmdb_result.get('status_code', None)
                if s_code is not None:
                    status_code = s_code
            if status_code != 0:
                if ignore_failures:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Ignore_failures getting TMDB data for:,'
                                           'movie_title')
                    return status_code, dict_info
                self._logger.debug(
                    'Error getting TMDB data for:', movie_title,
                    'status:', status_code)
                return Constants.REJECTED_STATUS, None
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception):
            self._logger.exception('')
            self._logger.exit('Error processing movie: ', movie_title)
            if ignore_failures:
                return -1, dict_info
            return -1, None

        add_movie = True
        # release_date TMDB key is different from Kodi's
        try:
            year = tmdb_result['release_date'][:-6]
            year = int(year)
        except (Exception):
            year = 0

        dict_info[Movie.YEAR] = year
        try:
            if tmdb_result.get(Movie.CACHED) is not None:
                dict_info[Movie.CACHED] = tmdb_result.get(Movie.CACHED)
            #
            # First, deal with the trailer. If there is no trailer, there
            # is no point continuing.
            #
            # Grab longest trailer that is in the appropriate language
            #
            best_size_map = {'Featurette': None, 'Clip': None, 'Trailer': None,
                             'Teaser': None}
            tmdb_trailer = None
            for tmdb_trailer in tmdb_result.get('videos', {'results': []}).get(
                    'results', []):
                if tmdb_trailer['site'] != 'YouTube':
                    continue

                # TODO: if Settings.is_allow_foreign_languages(), then get primary
                # lang
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('iso_639)1:', tmdb_trailer['iso_639_1'])
                if tmdb_trailer['iso_639_1'] != Settings.getLang_iso_639_1():
                    continue

                trailer_type = tmdb_trailer['type']
                size = tmdb_trailer['size']
                if trailer_type not in best_size_map:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Unrecognized trailer type:',
                                           trailer_type)

                if best_size_map.get(trailer_type, None) is None:
                    best_size_map[trailer_type] = tmdb_trailer

                if best_size_map[trailer_type]['size'] < size:
                    best_size_map[trailer_type] = tmdb_trailer

            # Prefer trailer over other types

            trailer_key = None
            if best_size_map['Trailer'] is not None:
                trailer_key = best_size_map['Trailer']['key']
                trailer_type = 'Trailer'
            elif Settings.get_include_featurettes() and best_size_map[
                    'Featurette'] is not None:
                trailer_key = best_size_map['Featurette']['key']
                trailer_type = 'Featurette'
            elif Settings.get_include_clips() and best_size_map['Clip'] is not None:
                trailer_key = best_size_map['Clip']['key']
                trailer_type = 'Clip'

            dict_info[Movie.TYPE] = trailer_type
            MovieEntryUtils.set_tmdb_id(dict_info, tmdb_id)

            # No point going on if we don't have a  trailer

            if trailer_key is None:
                TrailerUnavailableCache.add_missing_tmdb_trailer(tmdb_id=tmdb_id,
                                                                 library_id=library_id,
                                                                 title=movie_title,
                                                                 year=year,
                                                                 source=source)
                if source == Movie.LIBRARY_SOURCE:
                    TrailerUnavailableCache.add_missing_library_trailer(
                        tmdb_id=tmdb_id,
                        library_id=library_id,
                        title=movie_title,
                        year=year,
                        source=source)
                CacheIndex.remove_unprocessed_movie(tmdb_id)
                if not ignore_failures:
                    self._logger.exit(
                        'No trailer found for movie:', movie_title)
                    return Constants.REJECTED_STATUS, None
                else:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('No trailer found for movie:',
                                           movie_title,
                                           'Continuing to process other data')
            else:
                trailer_url = you_tube_base_url + tmdb_trailer['key']
                dict_info[Movie.TRAILER] = trailer_url
                CacheIndex.trailer_found(tmdb_id)

            tmdb_countries = tmdb_result.get('releases', None)
            if tmdb_countries is None:
                pass
            tmdb_countries = tmdb_result['releases']['countries']
            mpaa = ''
            for c in tmdb_countries:
                if c['iso_3166_1'] == Settings.getLang_iso_3166_1():
                    mpaa = c['certification']
            if mpaa == '':
                mpaa = Rating.RATING_NR
            dict_info[Movie.MPAA] = mpaa

            fanart = image_base_url + 'w380' + \
                str(tmdb_result['backdrop_path'])
            dict_info[Movie.FANART] = fanart

            thumbnail = image_base_url + 'w342' + \
                str(tmdb_result['poster_path'])
            dict_info[Movie.THUMBNAIL] = thumbnail

            title = tmdb_result[Movie.TITLE]
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Processing:', title, 'rating:',
                                   mpaa)

            if title is not None:
                dict_info[Movie.TITLE] = title

            plot = tmdb_result['overview']
            if plot is not None:
                dict_info[Movie.PLOT] = plot

            runtime = tmdb_result.get(Movie.RUNTIME, 0)
            if runtime is None:
                runtime = 0
            runtime = runtime * 60  # Kodi measures in seconds

            dict_info[Movie.RUNTIME] = runtime

            studios = tmdb_result['production_companies']
            studio = []
            for s in studios:
                studio.append(s['name'])

            if studio is not None:
                dict_info[Movie.STUDIO] = studio

            tmdb_cast_members = tmdb_result['credits']['cast']
            cast = []
            for cast_member in tmdb_cast_members:
                fake_cast_entry = {}
                fake_cast_entry['name'] = cast_member['name']
                fake_cast_entry['character'] = cast_member['character']
                cast.append(fake_cast_entry)

            dict_info[Movie.CAST] = cast

            tmdb_crew_members = tmdb_result['credits']['crew']
            director = []
            writer = []
            for crew_member in tmdb_crew_members:
                if crew_member['job'] == 'Director':
                    director.append(crew_member['name'])
                if crew_member['department'] == 'Writing':
                    writer.append(crew_member['name'])

            dict_info[Movie.DIRECTOR] = director
            dict_info[Movie.WRITER] = writer

            # Vote is float on a 0-10 scale

            vote_average = tmdb_result['vote_average']
            votes = tmdb_result['vote_count']

            if vote_average is not None:
                dict_info[Movie.RATING] = vote_average
            if votes is not None:
                dict_info[Movie.VOTES] = votes

            genre_found = False
            tag_found = False
            genres = tmdb_result['genres']
            genre = []
            for g in genres:
                genre.append(g['name'])
                if str(g['id']) in allowed_genres:
                    genre_found = True

            dict_info[Movie.GENRE] = genre

            keywords = tmdb_result.get('keywords', [])
            tmb_result_tags = keywords.get('keywords', [])
            tags = []
            for t in tmb_result_tags:
                tags.append(t['name'])
                if str(t['id']) in allowed_tags:
                    tag_found = True

            dict_info[Movie.DETAIL_TAGS] = tags

            language_information_found, original_language_found = is_language_present(
                tmdb_result, movie_title)

            dict_info[Movie.LANGUAGE_INFORMATION_FOUND] = language_information_found
            dict_info[Movie.LANGUAGE_MATCHES] = original_language_found

            if not ignore_failures and not (original_language_found
                                            or Settings.is_allow_foreign_languages()):
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Rejecting due to language')
                add_movie = False

            if Settings.get_filter_genres() and not tag_found and not genre_found:
                add_movie = False
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Rejected due to GenreUtils or Keyword')

            if vote_comparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                    if vote_average < vote_value:
                        add_movie = False
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'Rejected due to vote_average <')
                elif vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                    if vote_average > vote_value:
                        add_movie = False
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'Rejected due to vote_average >')

            original_title = tmdb_result['original_title']
            if original_title is not None:
                dict_info[Movie.ORIGINAL_TITLE] = original_title

            adult_movie = tmdb_result['adult'] == 'true'
            if adult_movie and not include_adult:
                add_movie = False
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Rejected due to adult')

            dict_info[Movie.ADULT] = adult_movie
            dict_info[Movie.SOURCE] = Movie.TMDB_SOURCE

            # Normalize rating

            mpaa = Rating.get_mpa_rating(mpaa_rating=mpaa, adult_rating=None)
            if not Rating.check_rating(mpaa):
                add_movie = False
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Rejected due to rating')
                    # Debug.dump_json(text='get_tmdb_trailer exit:', data=dict_info)

        except (AbortException, ShutdownException) as e:
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('%s %s'.format(
                'Error getting info for tmdb_id:', tmdb_id))
            try:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    json_text = json.dumps(
                        tmdb_result, indent=3, sort_keys=True)
                    self._logger.debug(json_text)
            except (Exception) as e:
                self._logger('failed to get Json data')

            if not ignore_failures:
                dict_info = None

        self._logger.exit('Finished processing movie: ', movie_title, 'year:',
                          year, 'add_movie:', add_movie)
        if add_movie:
            return 0, dict_info
        else:
            return Constants.REJECTED_STATUS, dict_info

    def get_detail_info(self,
                        trailer  # type: MovieType
                        ):
        # type: (...) -> MovieType
        """

        :param trailer:
        :return:
        """
        keep_trailer = True
        kodi_movie = None
        try:
            source = trailer[Movie.SOURCE]
            tmdb_id = MovieEntryUtils.get_tmdb_id(trailer)

            if source == Movie.ITUNES_SOURCE and tmdb_id is None:
                Monitor.throw_exception_if_shutdown_requested()
                if not trailer.get(Movie.TMDB_ID_NOT_FOUND, False):
                    tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                        trailer[Movie.TITLE], trailer[Movie.YEAR])
                    if tmdb_id is None:
                        trailer[Movie.TMDB_ID_NOT_FOUND] = True
                else:
                    tmdb_id = None

                MovieEntryUtils.set_tmdb_id(trailer, tmdb_id)

            trailer.setdefault(Movie.THUMBNAIL, '')
            tmdb_detail_movie_info = None
            if source == Movie.ITUNES_SOURCE:
                Monitor.throw_exception_if_shutdown_requested()
                status, tmdb_detail_movie_info = self.get_tmdb_trailer(
                    trailer[Movie.TITLE], tmdb_id, source, ignore_failures=True)

                # TODO: Verify that more fields should be cloned

                if status == Constants.REJECTED_STATUS:
                    # There is some data which is normally considered a deal-killer.
                    # Examine the fields that we are interested in to see if
                    # some of it is usable

                    # We don't care if TMDB does not have trailer, or if it does
                    # not have this trailer registered at all (it could be very
                    # new).

                    if not tmdb_detail_movie_info[Movie.LANGUAGE_MATCHES]:
                        keep_trailer = False

                if tmdb_detail_movie_info is None:  # An error occurred
                    tmdb_detail_movie_info = {}

                self.clone_fields(tmdb_detail_movie_info, trailer, Movie.PLOT)
            elif source == Movie.TMDB_SOURCE:
                # If a movie trailer was downloaded from TMDB, check to see if
                # the movie is in our library so that it can be included in the
                # UI.
                library_id = trailer.get(Movie.MOVIEID, None)
                if library_id is None:
                    tmdb_id = MovieEntryUtils.get_tmdb_id(trailer)
                    kodi_movie = TMDBUtils.get_movie_by_tmdb_id(tmdb_id)
                    if kodi_movie is not None:
                        trailer[Movie.MOVIEID] = kodi_movie.get_kodi_id()
                        trailer[Movie.FILE] = kodi_movie.get_kodi_file()

            movie_writers = self.get_writers(
                trailer, tmdb_detail_movie_info, source)
            trailer[Movie.DETAIL_WRITERS] = movie_writers

            trailer[Movie.DETAIL_DIRECTORS] = ', '.join(
                trailer.get(Movie.DIRECTOR, []))

            actors = self.get_actors(trailer, tmdb_detail_movie_info, source)
            trailer[Movie.DETAIL_ACTORS] = actors

            movie_studios = ', '.join(trailer.get(Movie.STUDIO, []))

            title_string = Messages.get_instance().get_formated_title(trailer)
            trailer[Movie.DETAIL_TITLE] = title_string

            trailer[Movie.DETAIL_STUDIOS] = movie_studios

            trailer[Movie.DETAIL_GENRES] = ' / '.join(
                trailer.get(Movie.GENRE, []))

            runTime = self.get_runtime(trailer, tmdb_detail_movie_info, source)
            trailer[Movie.DETAIL_RUNTIME] = runTime

            rating = Rating.get_mpa_rating(trailer.get(
                Movie.MPAA), trailer.get(Movie.ADULT))
            trailer[Movie.DETAIL_RATING] = rating

            img_rating = Rating.get_image_for_rating(rating)
            trailer[Movie.DETAIL_RATING_IMAGE] = img_rating

            trailer[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_READY_TO_DISPLAY

            if not keep_trailer:
                trailer = None

            return trailer
        except (Exception) as e:
            self._logger.exception('')
            return {}

    def clone_fields(self,
                     trailer,  # type: MovieType
                     detail_trailer,  # type: MovieType
                     *argv  # type: TextType
                     ):
        # type: (...) -> None
        """

        :param self:
        :param trailer:
        :param detail_trailer:
        :param argv:
        :return:
        """
        try:
            for arg in argv:
                detail_trailer[arg] = trailer.get(arg, None)
        except (Exception) as e:
            self._logger.exception('')

    def get_writers(self,
                    trailer,  # type: MovieType
                    tmdb_info,  # type: MovieType
                    source  # type: TextType
                    ):
        # type: (...) ->  TextType
        """

        :param self:
        :param trailer:
        :param tmdb_info:
        :param source:
        :return:
        """
        # Itunes does not supply writer info, get from TMDB query

        if source == Movie.ITUNES_SOURCE:
            writers = tmdb_info.get(Movie.WRITER, [])
        else:
            writers = trailer.get(Movie.WRITER, [])

        movie_writers = ', '.join(writers)

        return movie_writers

    def get_actors(self, trailer, info, source):
        # type: ( MovieType, MovieType, TextType) -> TextType
        """

        :param self:
        :param trailer:
        :param info:
        :param source:
        :return:
        """
        actors = trailer.get(Movie.CAST, [])
        if len(actors) > 6:
            actors = actors[:5]
        actors_list = []
        for actor in actors:
            actors_list.append(actor['name'])
        movie_actors = ', '.join(actors_list)

        return movie_actors

    def get_plot(self, trailer, info, source):
        # type: ( MovieType, MovieType, TextType) -> TextType
        """

        :param self:
        :param trailer:
        :param info:
        :param source:
        :return:
        """
        plot = ''
        if Movie.PLOT not in trailer or trailer[Movie.PLOT] == '':
            trailer[Movie.PLOT] = info.get(Movie.PLOT, '')

        if source == Movie.ITUNES_SOURCE:
            plot = info.get(Movie.PLOT, '')
        else:
            plot = trailer.get(Movie.PLOT, '')

        return plot

    def get_runtime(self, trailer, info, source):
        # type: ( MovieType, MovieType, TextType) -> TextType
        """

        :param self:
        :param trailer:
        :param info:
        :param source:
        :return:
        """
        runtime = ''
        if Movie.RUNTIME not in trailer or trailer[Movie.RUNTIME] == 0:
            if info is not None:
                trailer[Movie.RUNTIME] = info.get(Movie.RUNTIME, 0)

        if isinstance(trailer.get(Movie.RUNTIME), int):
            runtime = str(
                int(trailer[Movie.RUNTIME] / 60))
            runtime = Messages.get_instance().get_formatted_msg(
                Messages.MINUTES_DETAIL, runtime)

        return runtime

    def cache_remote_trailer(self, movie):
        # type: (MovieType) -> None
        """

        :param self:
        :param movie:
        :return:
        """
        # TODO: Verify Cached items cleared

        download_path = None
        movie_id = None

        try:
            start = datetime.datetime.now()
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(movie[Movie.TRAILER])

            movie_id = ''
            trailer_path = movie[Movie.TRAILER]

            # If cached files purged, then remove references

            if (movie.get(Movie.CACHED_TRAILER) is not None and
                    not os.path.exists(movie[Movie.CACHED_TRAILER])):
                movie[Movie.CACHED_TRAILER] = None
            if (movie.get(Movie.NORMALIZED_TRAILER) is not None and
                    not os.path.exists(movie[Movie.NORMALIZED_TRAILER])):
                movie[Movie.NORMALIZED_TRAILER] = None

            if not DiskUtils.is_url(trailer_path):
                return

            # No need for cached trailer if we have a cached normalized trailer
            if movie.get(Movie.NORMALIZED_TRAILER) is not None:
                return

            if trailer_path.startswith('plugin'):
                video_id = re.sub(r'^.*video_id=', '', trailer_path)
                # plugin://plugin.video.youtube/play/?video_id=
                new_path = 'https://youtu.be/' + video_id
                trailer_path = new_path

            valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                             Movie.ITUNES_SOURCE]
            if movie[Movie.SOURCE] not in valid_sources:
                return

            movie_id = Cache.get_video_id(movie)

            # Trailers for movies in the library are treated differently
            # from those that we don't have a local movie for:
            #  1- The library ID can be used for those from the library,
            #     otherwise an ID must be manufactured from the movie name/date
            #     or from the ID from the remote source, or some combination
            #
            #  2- Movies from the library have a known name and date. Those
            #    downloaded come with unreliable names.
            #

            # Create a uniqueId that can be used in a file name

            # Find out if this has already been cached
            # Get pattern for search
            if movie_id is not None and movie_id != '':
                cached_path = Cache.get_trailer_cache_file_path_for_movie_id(
                    movie, '*-movie.*', False)
                cached_trailers = glob.glob(cached_path)
                if len(cached_trailers) != 0:
                    if 'normalized' not in cached_trailers:
                        movie[Movie.CACHED_TRAILER] = cached_trailers[0]
                        stop = datetime.datetime.now()
                        locate_time = stop - start
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('time to locate movie:',
                                               locate_time.seconds, 'path:',
                                               movie[Movie.CACHED_TRAILER])
                else:
                    #
                    # Not in cache, download
                    #
                    download_info = None
                    youtube_data_stream_extractor_proxy = \
                        YDStreamExtractorProxy.get_instance()
                    trailer_folder = xbmc.translatePath(
                        'special://temp').encode("utf-8")
                    download_info = youtube_data_stream_extractor_proxy.get_video(
                        trailer_path, trailer_folder, movie_id)
                    if download_info is not None:
                        download_path = download_info.get('_filename', None)

                    """
                       To save json data from downloaded for debugging, uncomment
                       the following.

                    temp_file = os.path.join(trailer_folder, str(movie_id) + '.json')
                    import io
                    with io.open(temp_file, mode='wt', newline=None,
                                 encoding='utf-8', ) as cacheFile:
                        jsonText = utils.py2_decode(json.dumps(trailer_info,
                                                               encoding='utf-8',
                                                               ensure_ascii=False))
                        cacheFile.write(jsonText)

                    """

                    if download_path is None:
                        self._missing_trailers_playlist.record_played_trailer(
                            movie, use_movie_path=False, msg='Download FAILED')
                    else:
                        #
                        # Rename and cache
                        #
                        file_components = download_path.split('.')
                        trailer_file_type = file_components[len(
                            file_components) - 1]

                        # Create the final cached file name

                        trailer_file_name = (movie[Movie.TITLE]
                                             + ' (' + str(movie[Movie.YEAR])
                                             + ')-movie' + '.' + trailer_file_type)

                        cached_path = Cache.get_trailer_cache_file_path_for_movie_id(
                            movie, trailer_file_name, False)

                        try:
                            if not os.path.exists(cached_path):
                                DiskUtils.create_path_if_needed(
                                    os.path.dirname(cached_path))
                                shutil.move(download_path, cached_path)
                                movie[Movie.CACHED_TRAILER] = cached_path

                            stop = datetime.datetime.now()
                            locate_time = stop - start
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('movie download to cache time:',
                                                   locate_time.seconds)
                        except (Exception) as e:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Failed to move movie to cache.',
                                                   'movie:', trailer_path,
                                                   'cachePath:', download_path)
                            # self._logger.exception(
                            #                          'Failed to move movie to
                            #                          cache: ' +
                            #                        trailer_path)

        except (AbortException, ShutdownException) as e:
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Exception. Movie:', movie[Movie.TITLE],
                                   'ID:', movie_id, 'Path:', cached_path)
            self._logger.exception('')

    def normalize_trailer_sound(self, movie):
        # type: (TrailerFetcher, MovieType) -> None
        """
            Normalize the sound of the movie. The movie may be local
            and in the library, or may have been downloaded and placed
            in the cache.
        """
        normalized_path = None
        normalized_used = False
        start = datetime.datetime.now()
        try:
            # TODO: Add ability to normalize remote trailers
            # (occurs when caching is disabled).

            # FOLDER_SOURCE not supported at this time because a key
            # would have to be created.

            valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                             Movie.ITUNES_SOURCE]

            if movie[Movie.SOURCE] not in valid_sources:
                return

            # Can not normalize remote files. Downloaded and cached trailers
            # are in Movie.CACHED_TRAILER as local paths.

            # If cache purged, then delete cached trailer info

            if (movie.get(Movie.CACHED_TRAILER) is not None and
                    not os.path.exists(movie[Movie.CACHED_TRAILER])):
                movie[Movie.CACHED_TRAILER] = None
            if (movie.get(Movie.NORMALIZED_TRAILER) is not None and
                    not os.path.exists(movie.get(Movie.NORMALIZED_TRAILER))):
                movie[Movie.NORMALIZED_TRAILER] = None

            normalize = False

            # Prefer to use Cached Trailer, if available

            if (Settings.is_normalize_volume_of_downloaded_trailers() and
                    movie.get(Movie.CACHED_TRAILER) is not None):
                trailer_path = movie[Movie.CACHED_TRAILER]
                normalize = True
            else:
                trailer_path = movie[Movie.TRAILER]
                if (Settings.is_normalize_volume_of_local_trailers() and
                        os.path.exists(trailer_path)):
                    normalize = True

            if not normalize:
                return

            # Since the cached file name depends upon the movie's movie id,
            # then we can't cache a movie without one (like an iTunes movie
            # which is not yet registered with TMDB). There is a work-around
            # for this, but iTunes trailers probably don't need normalizing.

            if Cache.get_video_id(movie) is None:
                return

            cached_normalized_trailer = None
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('trailer', movie.get(Movie.TRAILER, ''),
                                   'cached trailer:', movie.get(Movie.CACHED_TRAILER, ''))

            # NORMALIZED_TRAILER is not automatically discovered from disk
            if movie.get(Movie.NORMALIZED_TRAILER, None) is None:
                # Discover from cache
                parent_dir, trailer_file_name = os.path.split(trailer_path)
                normalized_path = Cache.get_trailer_cache_file_path_for_movie_id(
                    movie, trailer_file_name, True)

                cached_normalized_trailers = glob.glob(normalized_path)
                if len(cached_normalized_trailers) > 0:
                    cached_normalized_trailer = cached_normalized_trailers[0]
                    movie[Movie.NORMALIZED_TRAILER] = cached_normalized_trailer

            normalized_trailer = movie.get(Movie.NORMALIZED_TRAILER, None)
            if normalized_trailer is not None:
                # If local movie is newer than normalized file, then
                # re-normalize it
                if os.path.exists(normalized_trailer):
                    if os.path.exists(trailer_path):
                        trailer_creation_time = os.path.getmtime(trailer_path)
                        normalized_trailer_creation_time = \
                            os.path.getmtime(normalized_trailer)
                        if trailer_creation_time <= normalized_trailer_creation_time:
                            return
                        else:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Trailer newer than normalized file',
                                                   'title:', movie[Movie.TITLE])

            # TODO: Handle the case where files are NOT cached
            # Delete temp file once falls off of TrailerDialog's movie
            # history.

            # A bit redundant, but perhaps clearer.

            if movie.get(Movie.CACHED_TRAILER) is not None:
                trailer_path = movie[Movie.CACHED_TRAILER]
            else:
                trailer_path = movie[Movie.TRAILER]

            normalized_used = False
            if cached_normalized_trailer is None:
                if not os.path.exists(normalized_path):
                    DiskUtils.create_path_if_needed(
                        os.path.dirname(normalized_path))
                    cmd_path = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                                            'resources', 'lib', 'shell',
                                            'ffmpeg_normalize.sh')
                    args = [cmd_path, trailer_path, normalized_path]
                    rc = subprocess.call(args, stdin=None, stdout=None,
                                         stderr=None, shell=False)

                    if rc == 0:
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'Normalized:', movie[Movie.TITLE])
                        cached_normalized_trailer = normalized_path
                        normalized_used = True
                    else:
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('Normalize failed:',
                                               movie[Movie.TITLE])

            if cached_normalized_trailer is not None:
                #
                # If source file was downloaded and cached, then just blow it away
                #
                if Cache.is_trailer_from_cache(trailer_path):
                    if os.path.exists(trailer_path):
                        os.remove(trailer_path)
                movie[Movie.NORMALIZED_TRAILER] = cached_normalized_trailer
                normalized_used = True
            if normalized_used and self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Used Normalized:', normalized_used)
        except (Exception) as e:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Exception. Movie:', movie[Movie.TITLE],
                                   'Path:', normalized_path)
            self._logger.exception('')
        finally:
            stop = datetime.datetime.now()
            elapsed_time = stop - start
            if normalized_used:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('time to normalize movie:',
                                       elapsed_time.seconds)
        return


def get_tmdb_id_from_title_year(title, year):
    # type: (TextType, int) -> int
    """

    :param title:
    :param year:
    :return:
    """
    trailer_id = None
    try:
        year = int(year)
        trailer_id = _get_tmdb_id_from_title_year(title, year)
        if trailer_id is None:
            trailer_id = _get_tmdb_id_from_title_year(title, year + 1)
        if trailer_id is None:
            trailer_id = _get_tmdb_id_from_title_year(title, year - 1)

    except (Exception):
        module_logger.exception('Error finding tmdbid for movie:', title,
                                'year:', year)

    return trailer_id


def _get_tmdb_id_from_title_year(title, year):
    # type: (TextType, int) -> int
    """
        When we don't have a trailer for a movie, we can
        see if TMDB has one.
    :param title:
    :param year:
    :return:
    """
    year_str = str(year)
    logger = module_logger
    if logger.isEnabledFor(Logger.DEBUG):
        logger.debug('title:', title, 'year:', year)

    found_movie = None
    trailer_id = None
    data = {}
    data['api_key'] = Settings.get_tmdb_api_key()
    data['page'] = '1'
    data['query'] = title
    data['language'] = Settings.getLang_iso_639_1()
    data['primary_release_year'] = year

    try:
        include_adult = 'false'
        if Rating.check_rating(Rating.RATING_NC_17):
            include_adult = 'true'
        data['include_adult'] = include_adult

        url = 'https://api.themoviedb.org/3/search/movie'
        status_code, _info_string = JsonUtilsBasic.get_json(url, params=data,
                                                            dump_msg='get_tmdb_id_from_title_year',
                                                            dump_results=True,
                                                            error_msg=title +
                                                            ' (' + year_str + ')')
        logger.debug('status:', status_code)
        if _info_string is not None:
            results = _info_string.get('results', [])
            if len(results) > 1:
                if logger.isEnabledFor(Logger.DEBUG):
                    logger.debug('Got multiple matching movies:', title,
                                 'year:', year)

            # TODO: Improve. Create best trailer function from get_tmdb_trailer
            # TODO: find best trailer_id

            matches = []
            current_language = Settings.getLang_iso_639_1()
            movie = None
            for movie in results:
                release_date = movie.get('release_date', '')  # 1932-04-22
                found_year = release_date[:-6]
                found_title = movie.get('title', '')

                if (found_title.lower() == title.lower()
                        and found_year == year_str
                        and movie.get('original_language') == current_language):
                    matches.append(movie)

            # TODO: Consider close match heuristics.

            if len(matches) == 1:
                found_movie = matches[0]
            elif len(matches) > 1:
                if logger.isEnabledFor(Logger.DEBUG):
                    logger.debug('More than one matching movie in same year',
                                 'choosing first one matching current language.',
                                 'Num choices:', len(matches))
                found_movie = matches[0]

            if movie is None:
                if logger.isEnabledFor(Logger.DEBUG):
                    logger.debug('Could not find movie:', title, 'year:', year,
                                 'at TMDB. found', len(results), 'candidates')
                for a_movie in results:
                    release_date = a_movie.get(
                        'release_date', '')  # 1932-04-22
                    found_year = release_date[:-6]
                    found_title = a_movie.get('title', '')
                    tmdb_id = a_movie.get('id', None)
                    if logger.isEnabledFor(Logger.DEBUG):
                        logger.debug('found:', found_title, '(', found_year, ')',
                                     'tmdb id:', tmdb_id)
                    tmdb_data = MovieEntryUtils.get_alternate_titles(
                        title, tmdb_id)
                    for alt_title, country in tmdb_data['alt_titles']:
                        if alt_title.lower() == title.lower():
                            found_movie = tmdb_data  # Not actually in "movie" format
                            break

                    '''
                             parsed_data[Movie.YEAR] = year

                    title = tmdb_result[Movie.TITLE]
                    if cls._logger.isEnabledFor(Logger.DEBUG):
                        cls._logger.debug('Processing:', title, 'type:',
                                           type(title).__name__)
                    parsed_data[Movie.TITLE] = title

                    studios = tmdb_result['production_companies']
                    studio = []
                    for s in studios:
                        studio.append(s['name'])

                    parsed_data[Movie.STUDIO] = studio

                    tmdb_cast_members = tmdb_result['credits']['cast']
                    cast = []
                    for cast_member in tmdb_cast_members:
                        fake_cast_entry = {}
                        fake_cast_entry['name'] = cast_member['name']
                        fake_cast_entry['character'] = cast_member['character']
                        cast.append(fake_cast_entry)

                    parsed_data[Movie.CAST] = cast

                    tmdb_crew_members = tmdb_result['credits']['crew']
                    director = []
                    writer = []
                    for crew_member in tmdb_crew_members:
                        if crew_member['job'] == 'Director':
                            director.append(crew_member['name'])
                        if crew_member['department'] == 'Writing':
                            writer.append(crew_member['name'])

                    parsed_data[Movie.DIRECTOR] = director
                    parsed_data[Movie.WRITER] = writer

                    titles = tmdb_result.get('alternative_titles', {'titles': []})
                    alt_titles = []
                    for title in titles['titles']:
                        alt_title = (title['title'], title['iso_3166_1'])
                        alt_titles.append(alt_title)

                    parsed_data['alt_titles'] = alt_titles
                    original_title = tmdb_result['original_title']
                    if original_title is not None:
                        parsed_data[Movie.ORIGINAL_TITLE] = original_title

                        '''
        else:
            if logger.isEnabledFor(Logger.DEBUG):
                logger.debug('Could not find movie:', title, 'year:', year,
                             'at TMDB. found no candidates')
    except (Exception):
        logger.exception('')

    tmdb_id = None
    if found_movie is not None:
        tmdb_id = found_movie.get('id', None)
    if logger.isEnabledFor(Logger.DEBUG):
        logger.exit('title:', title, 'tmdb_id:', tmdb_id)
    return tmdb_id


def is_language_present(tmdb_json, title):
    # type: (MovieType, TextType) -> (bool, bool, bool)
    """

    :param tmdb_json:
    :param title
    :return:
    """
    # Original Language appears to be the only reliable value. Spoken languages
    # does not appear to be for dubbed versions.

    logger = module_logger

    language_information_found = False
    current_language_found = False
    languages_found = False
    spoken_language_matches = False
    original_language_matches = False

    # "spoken_languages": [{"iso_639_1": "es", "name": "Español"},
    # {"iso_639_1": "fr", "name": "Français"}],
    #  found_langs = []
    #  for language_entry in tmdb_json.get('spoken_languages', {}):
    #     languages_found = True
    #     language_information_found = True
    #     if language_entry['iso_639_1'] == Settings.getLang_iso_639_1():
    #         # current_language_found = True
    #         spoken_language_matches = True
    #         break
    #     else:
    #         if config_logger.isEnabledFor(Logger.DEBUG):
    #             found_langs.append(language_entry['iso_639_1'])

    original_language = tmdb_json.get('original_language', '')
    if len(original_language) > 0:
        language_information_found = True

    if original_language == Settings.getLang_iso_639_1():
        original_language_matches = True

    if logger.isEnabledFor(Logger.DEBUG) and not original_language_matches:
        logger.exit('Language not found for movie: ', title,
                    'lang:', original_language)

    return language_information_found, original_language_matches
