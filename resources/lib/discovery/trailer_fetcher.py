# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""


import sys
import datetime
import glob
import json
import os
import re
import shutil

import xbmcvfs

from common.monitor import Monitor
from common.constants import Constants, Movie, RemoteTrailerPreference
from cache.tfh_cache import TFHCache
from common.disk_utils import DiskUtils
from common.playlist import Playlist
from common.exceptions import AbortException
from common.imports import *
from common.rating import WorldCertifications
from common.settings import Settings
from common.logger import (Trace, LazyLogger)
from common.messages import Messages
from backend.ffmpeg_normalize import RunCommand
from backend import ffmpeg_normalize
from backend.tmdb_utils import (TMDBUtils)
from backend.movie_entry_utils import (MovieEntryUtils)

from discovery.abstract_movie_data import AbstractMovieData
from backend.json_utils import JsonUtils
from backend.json_utils_basic import (JsonUtilsBasic)
from cache.cache import (Cache)
from cache.tmdb_cache_index import (CacheIndex)
from cache.trailer_cache import (TrailerCache)
from cache.trailer_unavailable_cache import (TrailerUnavailableCache)
from backend.genreutils import GenreUtils
from backend.backend_constants import YOUTUBE_URL_PREFIX
from backend.video_downloader import VideoDownloader

from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from discovery.playable_trailers_container import PlayableTrailersContainer
from discovery.restart_discovery_exception import RestartDiscoveryException

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection Annotator
class TrailerFetcher(TrailerFetcherInterface):
    """
    The Discover* classes do the initial discovery to get the basic information
    about movies to have their trailers played. This class is responsible for
    discovering everything else needed to actually play the trailer (i.e. the
    trailer might needed downloading, Extra metadata may be needed from TMDB,
    etc.).

    Originally designed to have multiple fetchers per trailer type. As
    such, an instance was initially created to "manage" the other
    instances. This manager is not needed when a single fetcher is used,
    someday someone should get rid of the extra 'manager'.
    """

    NUMBER_OF_FETCHERS = 1
    _trailer_fetchers = []
    _logger: LazyLogger = None

    def __init__(self, movie_data: AbstractMovieData,
                 thread_name: str = 'No TrailerFetcher Thread Name') -> None:
        """

                 :param movie_data
                 :param thread_name:
        """
        clz = TrailerFetcher
        clz._logger = module_logger.getChild(clz.__name__)
        clz._logger.enter()
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

    def start_fetchers(self) -> None:
        """
        Originally designed to have multiple fetchers per trailer type. As
        such, an instance was initially created to "manage" the other
        instances. This manager is not needed when a single fetcher is used,
        someday someone should get rid of the extra 'manager'.

        :return:
        """
        clz = TrailerFetcher
        Monitor.register_abort_listener(self.shutdown_thread)
        i = 0
        while i < self.NUMBER_OF_FETCHERS:
            i += 1
            trailer_fetcher = TrailerFetcher(
                self._movie_data,
                thread_name='Fetcher_' +
                self._movie_data.get_movie_source() + ':' + str(i))
            Monitor.register_abort_listener(trailer_fetcher.shutdown_thread)
            TrailerFetcher._trailer_fetchers.append(trailer_fetcher)
            trailer_fetcher.start()
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                clz._logger.debug_verbose('trailer fetcher started')

    def shutdown_thread(self) -> None:
        """

        :return:
        """
        try:
            TrailerUnavailableCache.save_cache(ignore_shutdown=True)
            self._playable_trailers.clear()
        except Exception as e:
            pass  # plugin shutting down, who cares.

    def prepare_for_restart_discovery(self, stop_thread: bool) -> None:
        """

        :param stop_thread
        :return:
        """
        clz = TrailerFetcher
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.enter()
        self._playable_trailers.prepare_for_restart_discovery(stop_thread)

        if stop_thread:
            self._movie_data = None
            self._playable_trailers = None

    def run(self) -> None:
        """

        :return:
        """
        clz = TrailerFetcher

        try:
            self.run_worker()
        except AbortException:
            return  # Just exit thread
        except Exception:
            clz._logger.exception('')

    def run_worker(self) -> None:
        """

        :param self:
        :return:
        """
        clz = TrailerFetcher

        while not self._movie_data.have_trailers_been_discovered():
            Monitor.throw_exception_if_abort_requested(timeout=0.5)

        # Wait one second after something has been discovered so that
        # there are more entries to process. This way the list is a bit more
        # randomized at the beginning.

        Monitor.throw_exception_if_abort_requested(timeout=1.0)
        self._movie_data.shuffle_discovered_trailers(mark_unplayed=False)

        while True:
            try:
                Monitor.throw_exception_if_abort_requested()

                if (self._movie_data.is_discovery_complete() and
                        self._movie_data.get_number_of_movies() == 0):
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug('Shutting down Trailer Fetcher',
                                          'due to no movies after discovery complete.')
                    break

                player_starving = self._playable_trailers.is_starving()
                trailer = self._movie_data.get_from_fetch_queue(
                    player_starving)
                self.fetch_trailer_to_play(trailer)
            except AbortException as e:
                reraise(*sys.exc_info())
            except Exception as e:
                clz._logger.exception('')

    def fetch_trailer_to_play(self,
                              trailer: MovieType
                              ) -> None:
        """

        :param trailer:
        :return:
        """
        clz = TrailerFetcher
        finished = False
        while not finished:
            try:
                discovery_state = trailer[Movie.DISCOVERY_STATE]
                if discovery_state >= Movie.DISCOVERY_COMPLETE:
                    self.throw_exception_on_forced_to_stop()

                    # if cached files purged, then reload them

                    if discovery_state == Movie.DISCOVERY_READY_TO_DISPLAY:
                        TrailerCache.is_more_discovery_needed(trailer)
                        discovery_state = trailer[Movie.DISCOVERY_STATE]
                        if discovery_state < Movie.DISCOVERY_READY_TO_DISPLAY:
                            self.cache_and_normalize_trailer(trailer)

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

                    trailer_path = trailer[Movie.TRAILER]
                    if DiskUtils.is_url(trailer_path) \
                            and trailer[Movie.SOURCE] == Movie.TMDB_SOURCE:
                        tmdb_id = MovieEntryUtils.get_tmdb_id(trailer)
                        if tmdb_id is not None:
                            tmdb_id = int(tmdb_id)

                        CacheIndex.remove_unprocessed_movies(tmdb_id)
                else:
                    self._fetch_trailer_to_play_worker(trailer)
                finished = True
            except RestartDiscoveryException:
                Monitor.throw_exception_if_abort_requested(timeout=0.10)

    def _fetch_trailer_to_play_worker(self,
                                      trailer: MovieType
                                      ) -> None:
        """

        :param trailer:
        :return:
        """
        clz = TrailerFetcher
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.enter('title:', trailer[Movie.TITLE],
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
            tmdb_id: Union[int, None] = MovieEntryUtils.get_tmdb_id(trailer)
            if tmdb_id is not None:
                tmdb_id = int(tmdb_id)

            rejection_reasons, populated_trailer = self.get_tmdb_trailer(trailer[Movie.TITLE],
                                                              tmdb_id,
                                                              Movie.TMDB_SOURCE)
            self.throw_exception_on_forced_to_stop()

            if Movie.REJECTED_TOO_MANY_TMDB_REQUESTS in rejection_reasons:
                self._missing_trailers_playlist.record_played_trailer(
                    trailer, use_movie_path=True, msg='Too many TMDB requests')
                return
            elif len(rejection_reasons) > 0:
                # Looks like there isn't an appropriate trailer for
                # this movie. A Large % of TMDB movies do not have a trailer (at
                # least for old movies). Don't log, unless required.
                self._missing_trailers_playlist.record_played_trailer(
                    trailer, use_movie_path=True, msg='No Trailer')
                if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                    clz._logger.debug_extra_verbose('No valid trailer found for TMDB movie:',
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
            else:  # No trailer returned but not rejected
                # Not sure what happened. Reject movie anyway.
                self._missing_trailers_playlist.record_played_trailer(
                    trailer, use_movie_path=True, msg='No Trailer')
                if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                    clz._logger.debug_extra_verbose('No trailer found for TMDB trailer:',
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
                    tmdb_id: Optional[int] = MovieEntryUtils.get_tmdb_id(
                        trailer)
                    if tmdb_id is not None:
                        tmdb_id = int(tmdb_id)

                    # Ok, tmdb_id not in Kodi database, query TMDB

                    if ((tmdb_id is None or tmdb_id == '')
                            and not trailer.get(Movie.TMDB_ID_NOT_FOUND, False)):
                        tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                            trailer[Movie.TITLE], trailer['year'],
                            runtime_seconds=trailer[Movie.RUNTIME])
                        self.throw_exception_on_forced_to_stop()

                        if tmdb_id is None:
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
                                    'Can not get TMDB id for Library movie:',
                                    trailer[Movie.TITLE], 'year:',
                                    trailer[Movie.YEAR])
                            self._missing_trailers_playlist.record_played_trailer(
                                trailer, use_movie_path=True,
                                msg=' Movie not found at tmdb')
                            trailer[Movie.TMDB_ID_NOT_FOUND] = True
                        else:
                            changed = MovieEntryUtils.set_tmdb_id(trailer, tmdb_id)

                            # We found an id from TMDB, update Kodi database
                            # so that we don't have to go through this again

                            if changed:
                                if Settings.get_update_tmdb_id():
                                    MovieEntryUtils.update_database_unique_id(
                                        trailer)

                                if trailer[Movie.SOURCE] == Movie.TFH_SOURCE:
                                    TFHCache.update_trailer(trailer)

                    if tmdb_id is not None:

                        # We only want the trailer, ignore other fields.

                        rejection_reasons, new_trailer_data = self.get_tmdb_trailer(
                            trailer[Movie.TITLE], tmdb_id, source, ignore_failures=True,
                            library_id=trailer[Movie.MOVIEID])
                        self.throw_exception_on_forced_to_stop()

                        if Constants.TOO_MANY_TMDB_REQUESTS in rejection_reasons:
                            keep_new_trailer = False
                            # Give up playing this trailer this time around. It will
                            # still be available for display later.
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(trailer[Movie.TITLE],
                                                          'could not get trailer due to '
                                                          'TOO MANY REQUESTS')
                            return

                        elif len(rejection_reasons) > 0:
                            keep_new_trailer = False
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
                                    'Unexpected REJECTED_STATUS. Ignoring')

                        elif (new_trailer_data is None
                              or new_trailer_data.get(Movie.TRAILER, '') == ''):
                            keep_new_trailer = False
                            TrailerUnavailableCache.add_missing_library_trailer(
                                tmdb_id=tmdb_id,
                                library_id=trailer[Movie.MOVIEID],
                                title=trailer[Movie.TITLE],
                                year=trailer[Movie.YEAR],
                                source=source)
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
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

            elif source in (Movie.ITUNES_SOURCE, Movie.TFH_SOURCE):
                if not trailer.get(Movie.TMDB_ID_NOT_FOUND, False):
                    if source == Movie.TFH_SOURCE:
                        year = None
                    else:
                        year = trailer[Movie.YEAR]
                    tmdb_id: Optional[int] = TMDBUtils.get_tmdb_id_from_title_year(
                        trailer[Movie.TITLE], year,
                        runtime_seconds=trailer.get(Movie.RUNTIME, 0))
                else:
                    tmdb_id = None

                self.throw_exception_on_forced_to_stop()
                if tmdb_id is None:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.debug_verbose(f'Can not get TMDB id for {source} movie: '
                                                  f'{trailer[Movie.TITLE]} year: '
                                                  f'[{trailer[Movie.YEAR]}')
                    self._missing_trailers_playlist.record_played_trailer(
                        trailer, use_movie_path=True,
                        msg=' Movie not found at TMDB')
                    trailer[Movie.TMDB_ID_NOT_FOUND] = True
                else:
                    changed = MovieEntryUtils.set_tmdb_id(trailer, tmdb_id)
                    if changed and source == Movie.TFH_SOURCE:
                        TFHCache.update_trailer(trailer)

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Finished second discovery level for movie:',
                                            trailer.get(Movie.TITLE),
                                            '(tentatively) keep:', keep_new_trailer)

        # If no trailer possible then remove it from further consideration

        movie_id = None
        if keep_new_trailer:
            if Movie.YEAR not in trailer:
                pass

            movie_id = trailer[Movie.TITLE] + '_' + str(trailer[Movie.YEAR])
            movie_id = movie_id.lower()

            self.throw_exception_on_forced_to_stop()
            with AbstractMovieData.get_aggregate_trailers_by_name_date_lock():
                if trailer[Movie.TRAILER] == '':
                    keep_new_trailer = False
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose('Not keeping:', trailer[Movie.TITLE],
                                                        'because trailer is empty')
                elif movie_id in AbstractMovieData.get_aggregate_trailers_by_name_date():
                    keep_new_trailer = False

                    trailerInDictionary = (
                        AbstractMovieData.get_aggregate_trailers_by_name_date()[movie_id])
                    source_of_trailer_in_dictionary = trailerInDictionary[Movie.SOURCE]

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose('Duplicate Movie id:', movie_id,
                                                        'source:', source_of_trailer_in_dictionary)

                    # Always prefer the local trailer
                    source = trailer[Movie.SOURCE]
                    if source == Movie.LIBRARY_SOURCE:
                        if source_of_trailer_in_dictionary == Movie.LIBRARY_SOURCE:
                            #
                            # Joy, two copies, both with trailers. Toss the new one.
                            #

                            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                                clz._logger.debug_extra_verbose('Not keeping:',
                                                                trailer[Movie.TITLE],
                                                                'because dupe and both in library')
                        else:
                            # Replace non-local version with this local one.
                            keep_new_trailer = True
                    elif source_of_trailer_in_dictionary == Movie.LIBRARY_SOURCE:
                        keep_new_trailer = False

                        # TODO: Verify

                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz._logger.debug_verbose('Duplicate:', trailer[Movie.TITLE],
                                                      'original source:',
                                                      source_of_trailer_in_dictionary,
                                                      'new source:', source)
                    elif source_of_trailer_in_dictionary == source:
                        keep_new_trailer = False
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz._logger.debug_verbose('Not keeping:', trailer[Movie.TITLE],
                                                      'because duplicate source')
                    elif source == Movie.FOLDER_SOURCE:
                        keep_new_trailer = True
                    elif source == Movie.ITUNES_SOURCE:
                        keep_new_trailer = True
                    elif source == Movie.TMDB_SOURCE:
                        keep_new_trailer = True

        if keep_new_trailer:
            keep_new_trailer = self.cache_and_normalize_trailer(trailer)

        if keep_new_trailer:
            trailer[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_COMPLETE
            AbstractMovieData.get_aggregate_trailers_by_name_date()[
                movie_id] = trailer
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(trailer[Movie.TITLE],
                                                'added to AggregateTrailers',
                                                'trailer:', trailer[Movie.TRAILER],
                                                'source:', trailer[Movie.SOURCE])

        else:
            self._movie_data.remove_discovered_movie(trailer)

        if keep_new_trailer:
            fully_populated_trailer = self.get_detail_info(trailer)
            if fully_populated_trailer is None:
                self._movie_data.remove_discovered_movie(trailer)
            else:
                self._playable_trailers.add_to_ready_to_play_queue(
                    fully_populated_trailer)

        self._stop_fetch_time = datetime.datetime.now()
        self._stop_add_ready_to_play_time = datetime.datetime.now()
        discovery_time = self._stop_fetch_time - self._start_fetch_time
        queue_time = self._stop_add_ready_to_play_time - self._stop_fetch_time
        trailer_type = trailer.get(Movie.TRAILER_TYPE, '')
        if (clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                and clz._logger.is_trace_enabled(Trace.STATS)):
            clz._logger.debug('took:', discovery_time.microseconds / 10000,
                              'ms',
                              'QueueTime:', queue_time.microseconds / 10000,
                              'ms',
                              'movie:', trailer.get(Movie.TITLE),
                              'type:', trailer_type,
                              'Kept:', keep_new_trailer, trace=Trace.STATS)

    def throw_exception_on_forced_to_stop(self, delay: float = 0) -> None:
        """

        :param delay:
        :return:
        """
        Monitor.throw_exception_if_abort_requested(timeout=delay)
        if self._movie_data.restart_discovery_event.isSet():
            raise RestartDiscoveryException()

    def cache_and_normalize_trailer(self, movie: MovieType) -> bool:
        clz = TrailerFetcher
        rc = 0
        trailer_ok = True

        if (Settings.is_use_trailer_cache() and
                (DiskUtils.is_url(movie[Movie.TRAILER]) or
                 movie[Movie.SOURCE] != Movie.LIBRARY_SOURCE)):

            if VideoDownloader().check_too_many_requests(movie[Movie.TITLE],
                                                         movie[Movie.SOURCE]) == 429:
                return trailer_ok

            rc = self.cache_remote_trailer(movie)
            if rc != 0 and rc != 429:
                trailer_ok = False

        elif not Settings.is_use_trailer_cache():
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                clz._logger.debug_verbose('Not caching:', movie[Movie.TITLE],
                                          'trailer:', movie[Movie.TRAILER],
                                          'source:', movie[Movie.SOURCE],
                                          'state:', movie[Movie.DISCOVERY_STATE])

        if rc == 0:
            normalized = False
            if (Settings.is_normalize_volume_of_downloaded_trailers() or
                    Settings.is_normalize_volume_of_local_trailers()):
                normalized = self.normalize_trailer_sound(movie)

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz._logger.debug_verbose(movie[Movie.TITLE], 'audio normalized:',
                                          normalized,
                                          'trailer:',
                                          movie.get(Movie.NORMALIZED_TRAILER),
                                          'source:', movie[Movie.SOURCE])
        return trailer_ok

    # noinspection SyntaxError
    def get_tmdb_trailer(self,
                         movie_title: str,
                         tmdb_id: Union[int, str],
                         source: str,
                         ignore_failures: bool = False,
                         library_id: Union[None, str] = None
                         ) -> (List[int], MovieType):
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
        clz = TrailerFetcher
        rejection_reasons = []
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.debug_verbose('title:', movie_title, 'tmdb_id:', tmdb_id,
                                      'library_id:', library_id, 'ignore_failures:',
                                      ignore_failures)

        if TrailerUnavailableCache.is_tmdb_id_missing_trailer(tmdb_id):
            CacheIndex.remove_unprocessed_movies(tmdb_id)
            rejection_reasons.append(Movie.REJECTED_NO_TRAILER)
            if not ignore_failures:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.exit(
                        'No trailer found for movie:', movie_title)
                return rejection_reasons, None

        trailer_type = ''
        you_tube_base_url = YOUTUBE_URL_PREFIX
        image_base_url = 'http://image.tmdb.org/t/p/'
        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        adult_certification = certifications.get_adult_certification()
        include_adult = certifications.filter(adult_certification)
        vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()

        # Since we may leave early, populate with dummy data

        unrated_id = certifications.get_unrated_certification().get_preferred_id()

        messages = Messages
        missing_detail = messages.get_msg(Messages.MISSING_DETAIL)
        dict_info = {}
        dict_info[Movie.DISCOVERY_STATE] = Movie.NOT_FULLY_DISCOVERED
        dict_info[Movie.TITLE] = messages.get_msg(Messages.MISSING_TITLE)
        dict_info[Movie.ORIGINAL_TITLE] = ''
        dict_info[Movie.YEAR] = 0
        dict_info[Movie.STUDIO] = [missing_detail]
        dict_info[Movie.MPAA] = unrated_id
        dict_info[Movie.THUMBNAIL] = ''
        dict_info[Movie.TRAILER] = ''
        dict_info[Movie.FANART] = ''
        dict_info[Movie.FILE] = ''
        dict_info[Movie.DIRECTOR] = [missing_detail]
        dict_info[Movie.WRITER] = [missing_detail]
        dict_info[Movie.PLOT] = missing_detail
        dict_info[Movie.CAST] = []
        dict_info[Movie.RUNTIME] = 0
        dict_info[Movie.GENRE] = [missing_detail]
        dict_info[Movie.TMDB_TAGS] = [missing_detail]
        dict_info[Movie.RATING] = 0.0
        dict_info[Movie.VOTES] = 0
        dict_info[Movie.ADULT] = False
        dict_info[Movie.SOURCE] = Movie.TMDB_SOURCE
        dict_info[Movie.TRAILER_TYPE] = Movie.VIDEO_TYPE_TRAILER

        # Query The Movie DB for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        data = {
            'append_to_response': 'credits,releases,keywords,videos,alternative_titles',
            'language': Settings.get_lang_iso_639_1(),
            'api_key': Settings.get_tmdb_api_key()
        }
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
                rejection_reasons.append(Movie.REJECTED_FAIL)
                if ignore_failures:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            f'Ignore_failures getting TMDB data for: {movie_title}')
                    return rejection_reasons, None
                clz._logger.debug_verbose('Error getting TMDB data for:', movie_title,
                                          'status:', status_code)
                return rejection_reasons, None
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            clz._logger.exception('Error processing movie: ', movie_title)
            rejection_reasons.append(Movie.REJECTED_FAIL)
            if ignore_failures:
                return rejection_reasons, None
            return rejection_reasons, None

        add_movie = True
        # release_date TMDB key is different from Kodi's

        # TFH titles are all caps, or otherwise wonky: use TMDb's title

        if source == Movie.TFH_SOURCE:
            movie_title = tmdb_result[Movie.TITLE]
            dict_info[Movie.TITLE] = movie_title

        try:
            year = tmdb_result['release_date'][:-6]
            year = int(year)
        except Exception:
            year = 0

        dict_info[Movie.YEAR] = year

        # Leave it to initial discovery date filter, except for TFH
        # Currently, even TFH YEAR filtering ignored.

        if source == Movie.TFH_SOURCE:
            if year not in range(Settings.get_tmdb_minimum_year(),
                                 Settings.get_tmdb_maximum_year()):
                rejection_reasons.append(Movie.REJECTED_FILTER_DATE)

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
                             'Teaser': None, 'Behind the Scenes': None}
            tmdb_trailer = None
            for tmdb_trailer in tmdb_result.get('videos', {'results': []}).get(
                    'results', []):
                if tmdb_trailer['site'] != 'YouTube':
                    continue

                if tmdb_trailer['iso_639_1'] != Settings.get_lang_iso_639_1():
                    continue

                trailer_type = tmdb_trailer['type']
                size = tmdb_trailer['size']
                if trailer_type not in best_size_map:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug('Unrecognized trailer type:',
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

            dict_info[Movie.TRAILER_TYPE] = trailer_type
            changed = MovieEntryUtils.set_tmdb_id(dict_info, tmdb_id)

            # Do NOT update TFH_cache or local DB since this is dict_info is
            # NOT in the DB or TFH cache. External user will decide.

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                tmdb_countries = tmdb_result['releases']['countries']
                mpaa = ''
                for c in tmdb_countries:
                    if c['iso_3166_1'] == Settings.get_country_iso_3166_1():
                        mpaa = c['certification']
                if mpaa == '':
                    clz._logger.debug_extra_verbose('No certification. Title:',
                                                    tmdb_result[Movie.TITLE],
                                                    'year:', year, 'trailer:',
                                                    trailer_key)

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
                CacheIndex.remove_unprocessed_movies(tmdb_id)
                rejection_reasons.append(Movie.REJECTED_NO_TRAILER)
                if not ignore_failures:
                    rejection_reasons.append(Movie.REJECTED_FAIL)
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.exit('No trailer found for movie:',
                                         movie_title)
                    return rejection_reasons, None
                else:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.debug_verbose('No trailer found for movie:',
                                                  movie_title,
                                                  'Continuing to process other data')
            else:
                trailer_url = you_tube_base_url + tmdb_trailer['key']
                dict_info[Movie.TRAILER] = trailer_url
                CacheIndex.add_cached_tmdb_trailer(tmdb_id)

            tmdb_countries = tmdb_result.get('releases', None)
            if tmdb_countries is None:
                pass
            tmdb_countries = tmdb_result['releases']['countries']
            mpaa = ''
            for c in tmdb_countries:
                if c['iso_3166_1'] == Settings.get_country_iso_3166_1():
                    mpaa = c['certification']
            if mpaa == '' or mpaa is None:
                mpaa = unrated_id
            dict_info[Movie.MPAA] = mpaa

            # fanart = image_base_url + 'w380' + \
            #     str(tmdb_result['backdrop_path'])
            fanart = image_base_url + 'original' + \
                     str(tmdb_result['backdrop_path'])
            dict_info[Movie.FANART] = fanart

            # thumbnail = image_base_url + 'w342' + \
            #     str(tmdb_result['poster_path'])
            thumbnail = image_base_url + 'original' + \
                        str(tmdb_result['poster_path'])
            dict_info[Movie.THUMBNAIL] = thumbnail

            title = tmdb_result[Movie.TITLE]
            if title is not None:
                dict_info[Movie.TITLE] = title

            plot = tmdb_result.get('overview', None)
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

            tmdb_genres = tmdb_result['genres']
            kodi_movie_genres = []
            tmdb_genre_ids: List[str] = []
            for tmdb_genre in tmdb_genres:
                kodi_movie_genres.append(tmdb_genre['name'])
                tmdb_genre_ids.append(str(tmdb_genre['id']))

            dict_info[Movie.GENRE] = kodi_movie_genres

            keywords = tmdb_result.get('keywords', [])
            tmdb_keywords = keywords.get('keywords', [])
            tmdb_keyword_ids = []
            kodi_movie_tags = []
            for tmdb_keyword in tmdb_keywords:
                kodi_movie_tags.append(tmdb_keyword['name'])
                tmdb_keyword_ids.append(str(tmdb_keyword['id']))

            dict_info[Movie.TMDB_TAGS] = kodi_movie_tags

            include_movie = GenreUtils.include_movie(genres=tmdb_genre_ids,
                                                     tags=tmdb_keyword_ids)
            if not include_movie:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        f'Rejected due to GenreUtils or Keyword: {movie_title}')
                add_movie = False
                rejection_reasons.append(Movie.REJECTED_FILTER_GENRE)

            language_information_found, original_language_found = is_language_present(
                tmdb_result, movie_title)

            dict_info[Movie.LANGUAGE_INFORMATION_FOUND] = language_information_found
            dict_info[Movie.LANGUAGE_MATCHES] = original_language_found

            if not ignore_failures and not (original_language_found
                                            or Settings.is_allow_foreign_languages()):
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        f'Rejected due to foreign language: {movie_title}')
                add_movie = False
                rejection_reasons.append(Movie.REJECTED_LANGUAGE)

            if vote_comparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                    if vote_average < vote_value:
                        add_movie = False
                        rejection_reasons.append(Movie.REJECTED_VOTE)
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(
                                f'Rejected due to vote_average < {movie_title}')
                elif vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                    if vote_average > vote_value:
                        add_movie = False
                        rejection_reasons.append(Movie.REJECTED_VOTE)
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(
                                f'Rejected due to vote_average > {movie_title}')

            original_title = tmdb_result['original_title']
            if original_title is not None:
                dict_info[Movie.ORIGINAL_TITLE] = original_title

            adult_movie = tmdb_result['adult'] == 'true'
            if adult_movie and not include_adult:
                add_movie = False
                rejection_reasons.append(Movie.REJECTED_ADULT)
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        f'Rejected due to adult, {movie_title}')

            dict_info[Movie.ADULT] = adult_movie
            dict_info[Movie.SOURCE] = Movie.TMDB_SOURCE

            # Normalize certification

            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            certification = certifications.get_certification(
                dict_info.get(Movie.MPAA), dict_info.get(Movie.ADULT))

            if not certifications.filter(certification):
                add_movie = False
                rejection_reasons.append(Movie.REJECTED_CERTIFICATION)
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        f'Rejected due to rating: {movie_title}')
                    # Debug.dump_json(text='get_tmdb_trailer exit:', data=dict_info)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception(
                f'Error getting info for tmdb_id: {str(tmdb_id)}')
            try:
                if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                    json_text = json.dumps(
                        tmdb_result, indent=3, sort_keys=True)
                    clz._logger.debug_extra_verbose(json_text)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                clz._logger.error('failed to get Json data')

            if not ignore_failures:
                dict_info = None

        clz._logger.exit('Finished processing movie: ', movie_title, 'year:',
                         year, 'add_movie:', add_movie)
        if add_movie:
            return rejection_reasons, dict_info
        else:
            return rejection_reasons, dict_info

    def get_detail_info(self, movie: MovieType) -> Union[MovieType, None]:
        """

        :param movie:
        :return:
        """
        clz = TrailerFetcher
        keep_trailer = True
        try:
            source = movie[Movie.SOURCE]
            tmdb_id: Optional[int] = MovieEntryUtils.get_tmdb_id(movie)
            if tmdb_id is not None:
                tmdb_id = int(tmdb_id)

            if (clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)
                    and clz._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                clz._logger.debug_verbose(f'title: {movie[Movie.TITLE]}'
                                          f' source: {source}'
                                          f' tmdb_id: {tmdb_id}'
                                          f' {movie.get(Movie.TMDB_ID_NOT_FOUND, "")}')

            if ((source in (Movie.ITUNES_SOURCE, Movie.TFH_SOURCE))
                    and tmdb_id is None):
                Monitor.throw_exception_if_abort_requested()
                if not movie.get(Movie.TMDB_ID_NOT_FOUND, False):
                    if source == Movie.TFH_SOURCE:
                        year = None
                    else:
                        year = movie[Movie.YEAR]
                    tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                        movie[Movie.TITLE], year,
                        runtime_seconds=movie.get(Movie.RUNTIME, 0))
                    if tmdb_id is None:
                        movie[Movie.TMDB_ID_NOT_FOUND] = True
                else:
                    tmdb_id = None

                changed = MovieEntryUtils.set_tmdb_id(movie, tmdb_id)
                if changed and source == Movie.TFH_SOURCE:
                    TFHCache.update_trailer(movie)

            movie.setdefault(Movie.THUMBNAIL, '')
            tmdb_detail_info = None
            if source == Movie.ITUNES_SOURCE:
                Monitor.throw_exception_if_abort_requested()
                rejection_reasons, tmdb_detail_info = self.get_tmdb_trailer(
                    movie[Movie.TITLE], tmdb_id, source, ignore_failures=True)

                if len(rejection_reasons) > 0:
                    # There is some data which is normally considered a deal-killer.
                    # Examine the fields that we are interested in to see if
                    # some of it is usable

                    # We don't care if TMDB does not have trailer, or if it does
                    # not have this movie registered at all (it could be very
                    # new).

                    if (tmdb_detail_info is not None
                            and not tmdb_detail_info.get(Movie.LANGUAGE_MATCHES)):
                        keep_trailer = False

                else:
                    tmdb_detail_info[Movie.PLOT] = tmdb_detail_info.get(Movie.PLOT, '')
                    self.clone_fields(tmdb_detail_info, movie, Movie.PLOT)

            if source == Movie.TFH_SOURCE:
                Monitor.throw_exception_if_abort_requested()
                rejection_reasons, tmdb_detail_info = self.get_tmdb_trailer(
                    movie[Movie.TITLE], tmdb_id, source, ignore_failures=True)

                if len(rejection_reasons) > 0:
                    keep_trailer = False
                    tmdb_detail_info = None
                    if (Movie.REJECTED_ADULT, Movie.REJECTED_CERTIFICATION,
                            Movie.REJECTED_FAIL) in rejection_reasons:
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(f'Rejecting TFH movie'
                                                            f' {movie[Movie.TITLE]} '
                                                            f'due to Certification')

                if tmdb_detail_info is not None:
                    if (clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                            and clz._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                        from common.debug_utils import Debug
                        Debug.dump_dictionary(movie, heading='Dumping TFH movie_info',
                                              log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)

                    self.clone_fields(tmdb_detail_info, movie,  # Movie.PLOT,
                                      Movie.TITLE, Movie.YEAR, Movie.CAST,
                                      Movie.DIRECTOR, Movie.WRITER, Movie.GENRE,
                                      Movie.STUDIO, Movie.MPAA, Movie.ADULT,
                                      Movie.FANART, Movie.TRAILER_TYPE,
                                      Movie.RUNTIME, set_default=True)
                    tmdb_id = MovieEntryUtils.get_tmdb_id(movie)

                    if (movie.get(Movie.THUMBNAIL, '') == ''
                            and tmdb_detail_info[Movie.THUMBNAIL].startswith('http')):
                        movie[Movie.THUMBNAIL] = tmdb_detail_info[Movie.THUMBNAIL]

                    if movie[Movie.PLOT] == '':
                        movie[Movie.PLOT] = tmdb_detail_info[Movie.PLOT]

                    if (clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                            and clz._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                        from common.debug_utils import Debug
                        Debug.dump_dictionary(movie,
                                              heading='Dumping Modified movie info',
                                              log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)

            if source in (Movie.TMDB_SOURCE, Movie.TFH_SOURCE):
                # If a movie was downloaded from TMDB or TFH, check to see if
                # the movie is in our library so that it can be included in the
                # UI.
                library_id = movie.get(Movie.MOVIEID, None)
                if library_id is None:
                    tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
                    if tmdb_id is not None:
                        tmdb_id = int(tmdb_id)

                    kodi_movie = TMDBUtils.get_movie_by_tmdb_id(tmdb_id)

                    if kodi_movie is not None:
                        movie[Movie.MOVIEID] = kodi_movie.get_kodi_id()
                        movie[Movie.FILE] = kodi_movie.get_kodi_file()

                    if (clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                            and clz._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                        clz._logger.debug_extra_verbose(
                            f'{movie[Movie.TITLE]}: '
                            f' source: {source}'
                            f' tmdbId: {str(tmdb_id)}'
                            f' MovieId: {movie.get(Movie.MOVIEID, "")}')

            (movie_writers, voiced_writers) = self.get_writers(movie,
                                                               tmdb_detail_info,
                                                               source)
            movie[Movie.DETAIL_WRITERS] = movie_writers
            movie[Movie.VOICED_DETAIL_WRITERS] = voiced_writers

            movie[Movie.DETAIL_DIRECTORS] = ', '.join(
                movie.get(Movie.DIRECTOR, []))

            movie[Movie.VOICED_DETAIL_DIRECTORS] = movie.get(Movie.DIRECTOR, [])
            if len(movie[Movie.VOICED_DETAIL_DIRECTORS]) > Movie.MAX_VOICED_DIRECTORS:
                movie[Movie.VOICED_DETAIL_DIRECTORS] = \
                    movie[Movie.VOICED_DETAIL_DIRECTORS][:Movie.MAX_VOICED_DIRECTORS - 1]

            actors, voiced_actors_list = self.get_actors(movie, tmdb_detail_info,
                                                         source)
            movie[Movie.DETAIL_ACTORS] = actors
            movie[Movie.VOICED_DETAIL_ACTORS] = voiced_actors_list

            title_string = Messages.get_formated_title(movie)
            movie[Movie.DETAIL_TITLE] = title_string

            movie_studios = ', '.join(movie.get(Movie.STUDIO, []))
            movie[Movie.DETAIL_STUDIOS] = movie_studios
            voiced_studios = movie.get(Movie.STUDIO, [])
            if len(voiced_studios) > Movie.MAX_VOICED_STUDIOS:
                voiced_studios = voiced_studios[:Movie.MAX_VOICED_STUDIOS - 1]
            movie[Movie.VOICED_DETAIL_STUDIOS] = voiced_studios

            movie[Movie.DETAIL_GENRES] = ' / '.join(
                movie.get(Movie.GENRE, []))

            run_time = self.get_runtime(movie, tmdb_detail_info, source)
            movie[Movie.DETAIL_RUNTIME] = run_time

            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            certification = certifications.get_certification(
                movie.get(Movie.MPAA), movie.get(Movie.ADULT))
            movie[Movie.DETAIL_CERTIFICATION] = certification.get_label()

            img_rating = certifications.get_image_for_rating(certification)
            movie[Movie.DETAIL_CERTIFICATION_IMAGE] = img_rating

            movie[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_READY_TO_DISPLAY
            if tmdb_id is not None:
                CacheIndex.remove_unprocessed_movies(tmdb_id)

            if not keep_trailer:
                movie = None
                if tmdb_id is not None:
                    CacheIndex.remove_cached_tmdb_trailer_id(tmdb_id)
            else:
                if (clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)
                        and clz._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                    clz._logger.debug_verbose('Fully discovered and ready to play:',
                                              movie[Movie.TITLE],
                                              movie[Movie.DETAIL_TITLE],
                                              trace=Trace.TRACE_DISCOVERY)

            return movie
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')
            return None

    def clone_fields(self,
                     trailer: MovieType,
                     detail_trailer: MovieType,
                     *argv: str,
                     set_default: bool = False
                     ) -> None:
        """

        :param self:
        :param trailer:
        :param detail_trailer:
        :param argv:
        :param set_default:
        :return:
        """
        clz = TrailerFetcher
        try:
            for arg in argv:
                value = trailer.get(arg, None)
                if value is None and set_default:
                    value = ''
                detail_trailer[arg] = value
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')

    def get_writers(self,
                    trailer: MovieType,
                    tmdb_info: MovieType,
                    source: str
                    ) -> (str, List[str]):
        """

        :param self:
        :param trailer:
        :param tmdb_info:
        :param source:
        :param max_writers:
        :return:
        """
        # Itunes does not supply writer info, get from TMDB query
        clz = TrailerFetcher

        if source == Movie.ITUNES_SOURCE:
            writers_temp = tmdb_info.get(Movie.WRITER, [])
        else:
            writers_temp = trailer.get(Movie.WRITER, [])

        # The same person can be the book author, the script writer,
        # etc.

        unique_writers = dict()
        writers = []
        for writer in writers_temp:
            if unique_writers.get(writer, None) is None:
                unique_writers[writer] = writer
                writers.append(writer)

        movie_writers = ', '.join(writers)
        if len(writers) > Movie.MAX_VOICED_WRITERS:
            writers = writers[:(Movie.MAX_VOICED_WRITERS - 1)]
        return movie_writers, writers

    def get_actors(self, movie: MovieType, info: MovieType, source: str
                   ) -> (str, List[str]):
        """
        :param self:
        :param movie:
        :param info:
        :param source:
        :return:
        """
        clz = TrailerFetcher
        movie_actors = ''
        actors = movie.get(Movie.CAST, [])
        if len(actors) > Movie.MAX_DISPLAYED_ACTORS:
            actors = actors[:Movie.MAX_DISPLAYED_ACTORS - 1]
        actors_list = []
        try:
            for actor in actors:
                if actor.get('name') is not None:
                    actors_list.append(actor['name'])
            movie_actors = ', '.join(actors_list)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            movie_actors = ''
            clz._logger.error('Movie:', movie[Movie.TITLE],
                              'cast:', movie[Movie.CAST])

        if len(actors) > Movie.MAX_VOICED_ACTORS:
            actors_list = actors_list[:Movie.MAX_VOICED_ACTORS - 1]
        return movie_actors, actors_list

    def get_plot(self, trailer: MovieType, info: MovieType, source: str) -> str:
        """

        :param self:
        :param trailer:
        :param info:
        :param source:
        :return:
        """
        clz = TrailerFetcher
        plot = ''
        if Movie.PLOT not in trailer or trailer[Movie.PLOT] == '':
            trailer[Movie.PLOT] = info.get(Movie.PLOT, '')

        if source == Movie.ITUNES_SOURCE:
            plot = info.get(Movie.PLOT, '')
        else:
            plot = trailer.get(Movie.PLOT, '')

        return plot

    def get_runtime(self,
                    trailer: MovieType,
                    info: MovieType,
                    source: str) -> str:
        """

        :param self:
        :param trailer:
        :param info:
        :param source:
        :return:
        """
        clz = TrailerFetcher
        runtime = ''
        if Movie.RUNTIME not in trailer or trailer[Movie.RUNTIME] == 0:
            if info is not None:
                trailer[Movie.RUNTIME] = info.get(Movie.RUNTIME, 0)

        if isinstance(trailer.get(Movie.RUNTIME), int):
            runtime = str(
                int(trailer[Movie.RUNTIME] / 60))
            runtime = Messages.get_formatted_msg(
                Messages.MINUTES_DETAIL, runtime)

        return runtime

    def cache_remote_trailer(self, movie: MovieType) -> int:
        """

        :param self:
        :param movie:
        :return:
        """
        clz = TrailerFetcher

        # TODO: Verify Cached items cleared

        download_path = None
        movie_id = None
        cached_path = None
        rc = 0

        try:
            start = datetime.datetime.now()
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz._logger.debug_verbose(
                    movie[Movie.TITLE], movie[Movie.TRAILER])

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
                return rc

            # No need for cached trailer if we have a cached normalized trailer

            if (movie.get(Movie.NORMALIZED_TRAILER) is not None
                    and os.path.exists(movie[Movie.NORMALIZED_TRAILER])):
                return rc

            if trailer_path.startswith('plugin'):
                video_id = re.sub(r'^.*video_?id=', '', trailer_path)
                # plugin://plugin.video.youtube/play/?video_id=
                new_path = 'https://youtu.be/' + video_id
                trailer_path = new_path

            valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                             Movie.ITUNES_SOURCE, Movie.TFH_SOURCE]
            if movie[Movie.SOURCE] not in valid_sources:
                return 0

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
                    already_normalized = False
                    for cached_trailer in cached_trailers:
                        if 'normalized' in cached_trailer:
                            already_normalized = True
                            if movie.get(Movie.NORMALIZED_TRAILER) is None:
                                movie[Movie.NORMALIZED_TRAILER] = cached_trailer

                    if not already_normalized:
                        movie[Movie.CACHED_TRAILER] = cached_trailers[0]
                        stop = datetime.datetime.now()
                        locate_time = stop - start
                        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                            clz._logger.debug_extra_verbose('time to locate movie:',
                                                            locate_time.seconds, 'path:',
                                                            movie[Movie.CACHED_TRAILER])
                else:
                    #
                    # Not in cache, download
                    #
                    downloaded_movie = None
                    error_code = 0
                    trailer_folder = xbmcvfs.translatePath('special://temp')
                    video_downloader = VideoDownloader()
                    error_code, downloaded_movie = \
                        video_downloader.get_video(
                            trailer_path, trailer_folder, movie_id,
                            movie[Movie.TITLE], movie[Movie.SOURCE], block=False)
                    if error_code == 429:
                        rc = 429
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                            clz._logger.debug_extra_verbose(
                                'Too Many Requests')
                            clz._logger.debug(
                                'Can not download trailer for cache at this time')
                        return rc

                    if downloaded_movie is not None:
                        download_path = downloaded_movie[Movie.TRAILER]

                    """
                       To save json data from downloaded for debugging, uncomment
                       the following.

                    temp_file = os.path.join(trailer_folder, str(movie_id) + '.json')
                    import io
                    with io.open(temp_file, mode='wt', newline=None,
                                 encoding='utf-8', ) as cacheFile:
                        jsonText = utils.py2_decode(json.dumps(downloaded_movie,
                                                               encoding='utf-8',
                                                               ensure_ascii=False))
                        cacheFile.write(jsonText)

                    """

                    if download_path is None:
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                            clz._logger.debug('Video Download failed',
                                              f'{movie[Movie.TITLE]}')
                        self._missing_trailers_playlist.record_played_trailer(
                            movie, use_movie_path=False, msg='Download FAILED')
                        if rc == 0:
                            rc = 1
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
                            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                                clz._logger.debug_extra_verbose(
                                    'movie download to cache time:',
                                    locate_time.seconds)
                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                clz._logger.debug_extra_verbose(
                                    'Failed to move movie to cache.',
                                    'movie:', trailer_path,
                                    'cachePath:', download_path)
                            # clz._logger.exception(
                            #                          'Failed to move movie to
                            #                          cache: ' +
                            #                        trailer_path)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception(f'Exception. Movie: {movie[Movie.TITLE]}',
                                  'ID:', movie_id, 'Path:', cached_path)

        return rc

    def normalize_trailer_sound(self, movie: MovieType) -> bool:
        """
            Normalize the sound of the movie. The movie may be local
            and in the library, or may have been downloaded and placed
            in the cache.

            :param movie: Movie trailer to consider normalizing
            :return: True if trailer was normalized by this call
        """
        clz = TrailerFetcher
        normalized_path = None
        normalized_used = False
        start = datetime.datetime.now()
        try:
            # TODO: Add ability to normalize remote trailers
            # (occurs when caching is disabled).

            # FOLDER_SOURCE not supported at this time because a key
            # would have to be created.

            # iTunes and TFH trailers probably don't require normalization, at
            # least not due to low-quality recordings by amateurs. However,
            # maybe you want to smooth them out a bit.

            valid_sources = [Movie.LIBRARY_SOURCE, Movie.TMDB_SOURCE,
                             Movie.ITUNES_SOURCE, Movie.TFH_SOURCE]

            if movie[Movie.SOURCE] not in valid_sources:
                return False

            # We have to have a uniqueid for caching to work. If we don't
            # have one, give up. iTunes trailers have no id, so we get the
            # id from tmdb, but if the movie is unknown to TMDb, then we
            # give up.
            #
            # We could come up with another key (perhaps a hash of name & date)
            # but iTunes trailers probably don't need normalizing. Besides,
            # using tmdbIds allows us to share trailers across TFH, TMDb and
            # iTunes, if we choose.
            #

            if Cache.get_video_id(movie) is None:
                return False

            # Can not normalize remote files. Movie.CACHED_TRAILER contains
            # the path to any downloaded trailers (by cache_remote_trailer)

            # Verify cache was not purged

            if (movie.get(Movie.CACHED_TRAILER) is not None and
                    not os.path.exists(movie[Movie.CACHED_TRAILER])):
                movie[Movie.CACHED_TRAILER] = None
            if (movie.get(Movie.NORMALIZED_TRAILER) is not None and
                    not os.path.exists(movie.get(Movie.NORMALIZED_TRAILER))):
                movie[Movie.NORMALIZED_TRAILER] = None

            normalize = False

            # Assume trailer is local
            trailer_path = movie[Movie.TRAILER]  # Might be a URL

            # Presence of cached trailer means there is no Movie.TRAILER, or
            # that it is a url and already downloaded. So use it if present.

            if Settings.is_normalize_volume_of_downloaded_trailers():
                if movie.get(Movie.CACHED_TRAILER) is not None:
                    #
                    # If remote trailer was downloaded by cache_remote_trailer,
                    # then use it.
                    #
                    trailer_path = movie[Movie.CACHED_TRAILER]
                    normalize = True
                elif movie.get(Movie.NORMALIZED_TRAILER) is not None:
                    normalize = True  # Verify that we don't have to re-normalize
            else:
                if (Settings.is_normalize_volume_of_local_trailers() and
                        os.path.exists(trailer_path)):
                    normalize = True

            if not normalize:
                return False

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('trailer',
                                                movie.get(Movie.TRAILER, ''),
                                                'cached trailer:',
                                                movie.get(Movie.CACHED_TRAILER, ''))

            # Populate NORMALIZED_TRAILER path, if needed.

            normalized_trailer_path = movie.get(Movie.NORMALIZED_TRAILER, None)
            if normalized_trailer_path is None:
                # trailer_path is either a cached_path or a library path.

                # Discover from cache
                parent_dir, trailer_file_name = os.path.split(trailer_path)
                normalized_trailer_path = Cache.get_trailer_cache_file_path_for_movie_id(
                    movie, trailer_file_name, True)

                cached_normalized_trailers = glob.glob(normalized_trailer_path)
                if len(cached_normalized_trailers) > 0:
                    normalized_trailer_path = cached_normalized_trailers[0]

                movie[Movie.NORMALIZED_TRAILER] = normalized_trailer_path

            if normalized_trailer_path is not None:
                if os.path.exists(normalized_trailer_path):
                    # If local movie is newer than normalized file, then
                    # re-normalize it
                    if (not DiskUtils.is_url(trailer_path)
                            and os.path.exists(trailer_path)):
                        trailer_creation_time = os.path.getmtime(trailer_path)
                        normalized_trailer_creation_time = \
                            os.path.getmtime(normalized_trailer_path)
                        if trailer_creation_time <= normalized_trailer_creation_time:
                            return False  # Already Normalized
                        else:
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
                                    'Trailer newer than normalized file',
                                    'title:', movie[Movie.TITLE])

            # TODO: Handle the case where files are NOT cached

            # A bit redundant, but perhaps clearer.

            if movie.get(Movie.CACHED_TRAILER) is not None:
                trailer_path = movie[Movie.CACHED_TRAILER]
            else:
                trailer_path = movie[Movie.TRAILER]

            normalized_used = False
            if not os.path.exists(normalized_trailer_path):
                DiskUtils.create_path_if_needed(
                    os.path.dirname(normalized_trailer_path))

                rc = ffmpeg_normalize.normalize(
                    trailer_path, normalized_trailer_path)

                if rc == 0:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.debug_verbose(
                            f'Normalized: {movie[Movie.TITLE]}',
                            f'path: {normalized_trailer_path}')
                    normalized_used = True
                else:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug('Normalize failed:',
                                          movie[Movie.TITLE],
                                          f'path: {normalized_trailer_path}')

                #
                # If source file was downloaded and cached, then just blow it away
                #
                if Cache.is_trailer_from_cache(trailer_path):
                    if os.path.exists(trailer_path):
                        os.remove(trailer_path)
                movie[Movie.NORMALIZED_TRAILER] = normalized_trailer_path

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('Exception. Movie:', movie[Movie.TITLE],
                                  'Path:', normalized_path)
        finally:
            stop = datetime.datetime.now()
            elapsed_time = stop - start
            if normalized_used:
                #  TODO: Log in statistics module
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('time to normalize movie:',
                                                    elapsed_time.seconds)
        return normalized_used


def get_tmdb_id_from_title_year(title: str, year: Union[int, str]) -> int:
    """

    :param title:
    :param year:
    :return:
    """
    tmdb_id = None
    try:
        year = int(year)
        tmdb_id: Optional[int] = _get_tmdb_id_from_title_year(title, year)
        if tmdb_id is None:
            tmdb_id = _get_tmdb_id_from_title_year(title, year + 1)
        if tmdb_id is None:
            tmdb_id = _get_tmdb_id_from_title_year(title, year - 1)

    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        module_logger.exception('Error finding tmdbid for movie:', title,
                                'year:', year)

    if tmdb_id is not None:
        tmdb_id = int(str(tmdb_id))

    return tmdb_id


def _get_tmdb_id_from_title_year(title: str, year: Union[int, str]) -> int:
    """
    TODO: This is nearly a duplicate in another class!!!

        When we don't have a trailer for a movie, we can
        see if TMDB has one.
    :param title:
    :param year:
    :return:
    """
    year_str = str(year)
    logger = module_logger
    if logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
        logger.debug_extra_verbose('title:', title, 'year:', year)

    found_movie = None
    trailer_id = None
    data = {}
    data['api_key'] = Settings.get_tmdb_api_key()
    data['page'] = '1'
    data['query'] = title
    data['language'] = Settings.get_lang_iso_639_1()
    data['primary_release_year'] = year

    try:
        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        adult_certification = certifications.get_adult_certification()

        include_adult = 'false'
        if certifications.filter(adult_certification):
            include_adult = 'true'
        data['include_adult'] = include_adult

        url = 'https://api.themoviedb.org/3/search/movie'
        status_code, _info_string = JsonUtilsBasic.get_json(url, params=data,
                                                            dump_msg='get_tmdb_id_from_title_year',
                                                            dump_results=True,
                                                            error_msg=title +
                                                            ' (' + year_str + ')')
        if logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            logger.debug_extra_verbose('status:', status_code)
        if _info_string is not None:
            results = _info_string.get('results', [])
            if len(results) > 1:
                if logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    logger.debug_verbose('Got multiple matching movies:', title,
                                         'year:', year)

            # TODO: Improve. Create best trailer function from get_tmdb_trailer
            # TODO: find best trailer_id

            matches = []
            current_language = Settings.get_lang_iso_639_1()
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
                if logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    logger.debug_verbose('More than one matching movie in same year',
                                         'choosing first one matching current language.',
                                         'Num choices:', len(matches))
                found_movie = matches[0]

            if movie is None:
                if logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    logger.debug_verbose('Could not find movie:', title, 'year:', year,
                                         'at TMDB. found', len(results), 'candidates')
                for a_movie in results:
                    release_date = a_movie.get(
                        'release_date', '')  # 1932-04-22
                    found_year = release_date[:-6]
                    found_title = a_movie.get('title', '')
                    tmdb_id = a_movie.get('id', None)
                    if logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        logger.debug_extra_verbose(f'found: {found_title}',
                                                   f'({found_year})',
                                                   'tmdb id:', tmdb_id)
                    tmdb_data = MovieEntryUtils.get_alternate_titles(
                        title, tmdb_id)
                    for alt_title, country in tmdb_data['alt_titles']:
                        if alt_title.lower() == title.lower():
                            found_movie = tmdb_data  # Not actually in "movie" format
                            break
        else:
            if logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                logger.debug_verbose('Could not find movie:', title, 'year:', year,
                                     'at TMDB. found no candidates')
    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        logger.exception('')

    tmdb_id = None
    if found_movie is not None:
        tmdb_id = found_movie.get('id', None)
    if logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
        logger.exit('title:', title, 'tmdb_id:', tmdb_id)

    if tmdb_id is not None:
        tmdb_id = int(tmdb_id)
    return tmdb_id


def is_language_present(tmdb_json: MovieType, title: str) -> (bool, bool, bool):
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
    #     if language_entry['iso_639_1'] == Settings.get_lang_iso_639_1():
    #         # current_language_found = True
    #         spoken_language_matches = True
    #         break
    #     else:
    #         if config_logger.isEnabledFor(LazyLogger.DEBUG):
    #             found_langs.append(language_entry['iso_639_1'])

    original_language = tmdb_json.get('original_language', '')
    if len(original_language) > 0:
        language_information_found = True

    if original_language == Settings.get_lang_iso_639_1():
        original_language_matches = True

    if logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE) and not original_language_matches:
        logger.exit('Language not found for movie: ', title,
                    'lang:', original_language)

    return language_information_found, original_language_matches
