# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import datetime
import glob
import os
import sys

from backend import ffmpeg_normalize
from backend.movie_entry_utils import MovieEntryUtils
from backend.tmdb_utils import TMDBUtils
from backend.video_downloader import VideoDownloader
from cache.cache import Cache
from cache.library_trailer_index import LibraryTrailerIndex
from cache.tfh_cache import TFHCache
from cache.tmdb_cache_index import CacheIndex
from cache.tmdb_trailer_index import TMDbTrailerIndex
from cache.trailer_cache import TrailerCache
from cache.trailer_unavailable_cache import (TrailerUnavailableCache)
from common.constants import Constants
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, CommunicationException
from common.garbage_collector import GarbageCollector
from common.imports import *
from common.logger import Trace, LazyLogger
from common.monitor import Monitor
from common.movie import (BaseMovie, AbstractMovieId, AbstractMovie, FolderMovie,
                          ITunesMovie, LibraryMovie, TFHMovie, TMDbMovie, TMDbMovieId)
from common.movie_constants import MovieField
from common.playlist import Playlist
from common.settings import Settings
from discovery.abstract_movie_data import AbstractMovieData
from discovery.movie_detail import MovieDetail
from discovery.playable_trailers_container_interface import \
    PlayableTrailersContainerInterface
from discovery.restart_discovery_exception import StopDiscoveryException
from discovery.tmdb_movie_downloader import TMDbMovieDownloader
from discovery.trailer_fetcher_interface import TrailerFetcherInterface
from discovery.utils.tmdb_filter import TMDbFilter

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class AbstractTrailerFetcher(TrailerFetcherInterface):
    """
    The Discover* classes do the initial discovery to get the basic information
    about movies to have their trailers played. This class is responsible for
    discovering everything else needed to actually play the trailer (i.e. the
    trailer might needed downloading, Extra metadata may be needed from TMDB,
    etc.).

    TODO: Originally designed to have multiple fetchers per movie type. As
          such, an instance was initially created to "manage" the other
          instances. This manager is not needed when a single fetcher is used,
          someday someone should get rid of the extra 'manager'.
    """

    NUMBER_OF_FETCHERS: Final[int] = 1
    _logger: LazyLogger = None

    def __init__(self, *args: Any, movie_data: AbstractMovieData = None,
                 **kwargs: Any) -> None:
        """

                 :param movie_data
        """
        kwargs.setdefault('name', 'No AbstractTrailerFetcher Thread Name')
        clz = type(self)
        clz._logger = module_logger.getChild(clz.__name__)
        #  movie_datax: AbstractMovieData = kwargs['movie_data']
        clz._logger.debug(f'movie_data: {movie_data} '
                          f'kwargs movie_data: {kwargs.get("movie_data")} '
                          f'kwargs name: {kwargs["name"]} ')
        super().__init__(*args, **kwargs)
        clz._logger.debug(f'post super movie_data: {movie_data} '
                          f'kwargs movie_data: {kwargs.get("movie_data")} '
                          f'kwargs name: {kwargs["name"]} ')
        self._movie_data: AbstractMovieData = movie_data
        self._playable_trailers: PlayableTrailersContainerInterface = \
            PlayableTrailersContainerInterface.get_container(
                movie_data.get_movie_source())
        self._playable_trailers.set_movie_data(movie_data)
        self._missing_trailers_playlist: Playlist = Playlist.get_playlist(
            Playlist.MISSING_TRAILERS_PLAYLIST, append=False, rotate=True)
        self._start_fetch_time: datetime.datetime = None
        self._stop_fetch_time: datetime.datetime = None
        self._stop_add_ready_to_play_time: datetime.datetime = None
        self._stop_thread: bool = False
        self._child_trailer_fetchers: List['AbstractTrailerFetcher'] = []

    def start_fetchers(self) -> None:
        """
        Originally designed to have multiple fetchers per movie type. As
        such, an instance was initially created to "manage" the other
        instances. This manager is not needed when a single fetcher is used,
        someday someone should get rid of the extra 'manager'.

        :return:
        """
        clz = type(self)
        Monitor.register_abort_listener(self.shutdown_thread)
        i: int = 0
        while i < self.NUMBER_OF_FETCHERS:
            i += 1
            thread_name = f'Fetcher_{self._movie_data.get_movie_source()}: {str(i)}'
            trailer_fetcher: AbstractTrailerFetcher = AbstractTrailerFetcher(
                movie_data=self._movie_data,
                name=thread_name,
                daemon=False)
            trailer_fetcher.setName(thread_name)

            Monitor.register_abort_listener(trailer_fetcher.shutdown_thread)
            self._child_trailer_fetchers.append(trailer_fetcher)
            trailer_fetcher.start()
            trailer_fetcher.setName(thread_name)

            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                clz._logger.debug_verbose(f'trailer fetcher started thread name: '
                                          f'{trailer_fetcher.name} '
                                          f'daemon: {trailer_fetcher.isDaemon()} '
                                          f'parent daemon: {self.isDaemon()} '
                                          f'id: {trailer_fetcher.ident}')

    def stop_fetchers(self) -> None:
        #
        # Only call from primary (parent) AbstractTrailerFetcher for this type of Movie Discovery.
        #
        clz = type(self)
        trailer_fetcher: AbstractTrailerFetcher
        for trailer_fetcher in self._child_trailer_fetchers:
            # Will cause thread to stop

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_verbose(f'Stopping: '
                                          f'{trailer_fetcher.name} '
                                          f'daemon: {trailer_fetcher.isDaemon()} '
                                          f'parent daemon: {self.isDaemon()} '
                                          f'id: {trailer_fetcher.ident}')
            trailer_fetcher._stop_thread = True

        self._playable_trailers.stop_thread()

    def destroy(self) -> None:
        """

        Clean up after thread(s) have stopped
        :return:
        """
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.enter()
        self._playable_trailers.destroy()

        for trailer_fetcher in self._child_trailer_fetchers:
            # GarbageCollector.add_thread(trailer_fetcher)
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_verbose(f'Destroying: '
                                          f'{trailer_fetcher.name} '
                                          f'daemon: {trailer_fetcher.isDaemon()} '
                                          f'parent daemon: {self.isDaemon()} '
                                          f'id: {trailer_fetcher.ident}')

        TrailerUnavailableCache.save_cache(ignore_shutdown=True)
        del self._child_trailer_fetchers[:]
        self._movie_data = None

    def shutdown_thread(self) -> None:
        """
        Quickly stop thread because whole application is stopping
        :return:
        """
        try:
            TrailerUnavailableCache.save_cache(ignore_shutdown=True)
            self._playable_trailers.clear()
        except Exception as e:
            pass  # plugin shutting down, who cares.

    def run(self) -> None:
        """
            Thread which processes movies from the discovery queue and puts
            successfully processed movies into the playable_trailers_queue.
            Activity is blocked when the playable_trailers_queue is full
            (holds 3 movies).
        :return:
        """
        clz = type(self)

        try:
            clz._logger.debug_verbose(f'run: '
                                      f'{self.name} '
                                      f'daemon: {self.isDaemon()} '
                                      f'id: {self.ident}')
            self.run_worker()
        except AbortException:
            pass
        except StopDiscoveryException:
            clz._logger.debug_extra_verbose(f'Exiting {self.getName()} '
                                            f'ident: {self.ident}')
        except Exception:
            clz._logger.exception()

        finally:
            GarbageCollector.add_thread(self)

    def run_worker(self) -> None:
        """
        Wrapper around actual worker, fetch_trailer_to_play.

        :param self:
        :return:
        """
        clz = type(self)

        while not self._movie_data.have_trailers_been_discovered():
            self.throw_exception_on_forced_to_stop(timeout=0.5)

        # Wait one second after something has been discovered so that
        # there are more entries to process. This way the list is a bit more
        # randomized at the beginning.

        self.throw_exception_on_forced_to_stop(timeout=1.0)
        self._movie_data.shuffle_discovered_movies(mark_unplayed=False)

        while True:
            try:
                self.throw_exception_on_forced_to_stop()

                if (self._movie_data.is_discovery_complete() and
                        self._movie_data.get_number_of_movies() == 0):
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug('Shutting down Trailer Fetcher',
                                          'due to no movies after discovery complete.')
                    break

                player_starving = self._playable_trailers.is_starving()
                movie: BaseMovie = self._movie_data.get_from_fetch_queue(
                    player_starving)
                self.fetch_trailer_to_play(movie)
            except (AbortException, StopDiscoveryException) as e:
                reraise(*sys.exc_info())
            except Exception as e:
                clz._logger.exception('')
        return

    def fetch_trailer_to_play(self,
                              base_movie: BaseMovie
                              ) -> None:
        """
        Processes the given movie, gathering any missing information and placing
        movies with trailers suitable for playing into the playable_trailers queue.
        Movies which are not suitable include:
            * Movies without trailers
            * Movies which don't pass the various user configured filters
              (Certification, year range, genre, etc.)

        When a movie is missing information, we generally try to get it from TMDb.
        More specifically:
            If a movie is from the Library, we only get missing trailers from TMDb
            when the user settings request it (is_include_library_no_trailer_info
            and is_include_library_remote_trailers).

            If a movie is from TFH or itunes, then the trailer is already known,
            but we need metadata from TMDb because info from TFH and iTunes is a
            bit sparse. If there is no TMDb movie found, then we play the trailer
            anyway, but with missing info.

            And, of course, if a movie is from TMDb, then we get all of the info
            from TMDb.

        Note that there is other code which has the job of finding the TMDb id
        for a given movie, particularly library movie. That code does not get
        the full data discovered here.

        :param base_movie:
        :return:
        """
        clz = type(self)
        movie: TMDbMovie = None
        rejection_reasons: List[int] = []

        # The base_movie can either be an AbstractMovieId or an AbstractMovie
        #

        if isinstance(base_movie, AbstractMovieId):
            tmdb_id: int = None
            try:
                tmdb_id: int = base_movie.get_tmdb_id()

                rejection_reasons, movie = TMDbMovieDownloader.get_tmdb_movie(base_movie)
            except CommunicationException as e:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug(f'Can not communicate with TMDb, skipping: '
                                      f'{tmdb_id}', Trace=Trace.TRACE_DISCOVERY)
                    return

            if MovieField.REJECTED_TOO_MANY_TMDB_REQUESTS in rejection_reasons:
                self._missing_trailers_playlist.record_played_trailer(
                    movie, use_movie_path=True, msg='Too many TMDB requests')
                clz._logger.debug(f'Too many TMDb requests tmdb_id: {tmdb_id}',
                                  Trace=Trace.TRACE_DISCOVERY)
                return
            if movie is None:

                # Redundant check. It can only be a TMDbMovie.

                if isinstance(movie, TMDbMovie):
                    # May as well purge it
                    self._movie_data.remove_discovered_movie(base_movie)
                    #  TODO: should be done elsewhere in consistent manner
                    CacheIndex.remove_tmdb_id_with_trailer(tmdb_id)
                return

            self.throw_exception_on_forced_to_stop(timeout=0.01)
            rejection_reasons = TMDbFilter.filter_movie(movie)
            if len(rejection_reasons) > 0:
                # Rejected due to no trailer, or certification, genre, etc.
                #
                # Remove from discovered movie queue so that we don't keep
                # revisiting this. Also, removes from caches

                clz._logger.debug(f'Removing rejected movie from discovered_movies '
                                  f'and caches: {movie.get_title()}',
                                  Trace=Trace.TRACE_DISCOVERY)
                self._movie_data.remove_discovered_movie(movie)
                return

            # This will replace inferior AbstractMovieId version

            clz._logger.debug(f'replacing {movie.get_id()} type: {type(base_movie)} with '
                              f'{type(movie)}')
            self._movie_data.add_to_discovered_movies(movie)

        else:  # if base_movie is not AbstractMovieId, then must be AbstractMovie
            movie: AbstractMovie = base_movie

        # At this point on use 'movie' the AbstractMovie representation of movie

        finished: bool = False

        while not finished:
            if self._stop_thread:
                raise StopDiscoveryException()

            discovery_state: str = movie.get_discovery_state()
            if discovery_state >= MovieField.DISCOVERY_NEARLY_COMPLETE:
                self.throw_exception_on_forced_to_stop()

                # if cached files purged, then reload them

                if discovery_state == MovieField.DISCOVERY_READY_TO_DISPLAY:
                    TrailerCache.is_more_discovery_needed(movie)
                    discovery_state = movie.get_discovery_state()
                    if discovery_state < MovieField.DISCOVERY_READY_TO_DISPLAY:
                        self.cache_and_normalize_trailer(movie)
                        movie.validate_local_trailer()

                        if isinstance(movie, TMDbMovie):
                            TMDbTrailerIndex.add(movie)
                        elif isinstance(movie, LibraryMovie):
                            LibraryTrailerIndex.add(movie)
                if discovery_state < MovieField.DISCOVERY_READY_TO_DISPLAY:
                    fully_populated_movie: AbstractMovie = \
                        MovieDetail.get_detail_info(movie)
                    if (fully_populated_movie is None
                            and not isinstance(movie, TFHMovie)):
                        self._movie_data.remove_discovered_movie(movie)
                        continue
                    self._playable_trailers.add_to_ready_to_play_queue(
                        fully_populated_movie)
                else:
                    self._playable_trailers.add_to_ready_to_play_queue(movie)

                trailer_path: str = movie.get_trailer_path()
                if DiskUtils.is_url(trailer_path) and movie.is_tmdb_movie():
                    tmdb_id = movie.get_tmdb_id()

                    if tmdb_id is not None:
                        CacheIndex.remove_unprocessed_movie(tmdb_id)
            else:
                self._fetch_trailer_to_play_worker(movie)
            finished = True

    def _fetch_trailer_to_play_worker(self,
                                      movie: AbstractMovie
                                      ) -> None:
        """

        :param movie:
        :return:
        """
        clz = type(self)
        rejection_reasons: List[int] = []

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.enter(f'title: {movie.get_title()} '
                              f'source: {movie.get_source()} ' 
                              f'discovery_state: {movie.get_discovery_state()} '
                              f'trailer: {movie.get_trailer_path()} '
                              f'has_trailer: {movie.get_has_trailer()}')
        self._start_fetch_time = datetime.datetime.now()
        keep_new_trailer: bool = True
        source: str = movie.get_source()

        # The TMDb id for a movie can be very useful, and frequently required.

        if not self.find_and_update_tmdb_id(movie):
            '''
            If a TFH or iTunes movie, then we use information from TMDb to supply
            missing details from TFH and iTunes. It is not absolutely required to
            have TMDb info, but there will be missing data displayed
            
            In the case of TFH, the title is unreliable and there is no date, so
            1) we expect some errors
            2) when we get TMDb info, we update the TFH movie entry with this
               found title and date. This must be done carefully since the title
               and date are used as unique ids for movies in some circumstances.
            
               Normally, a movie's unique id is whatever the source database uses,
               but, when we want to check to see if the movie exists from other
               databases, we use the title + date as the unique id. This is
               used for Aggregate Trailer tables. For this reason, it is highly
               desirable to get the TMDb id before searching for the movie
               in the Aggregate Trailer tables. 
            
            For iTunes movies, we have reliable-enough date and title. Just use 
            them, even if we don't have TMDb info. Note that iTunes movies are
            mostly for unreleased, or recently released movies so even if title or 
            date are changed, it is not such a big deal since collisions with 
            other databases are not frequent and the damage of having duplicate
            movies is not such crisis.
            
            For movies from TFH, we can't rely on date or title. So when we can't
            determine TMDb id, just use the bogus TFH title and a date of zero 
            for the Aggregate Trailer tables. We must, however, determine that we
            can't find TMDb id now, prior to searching Aggregate Trailer tables, 
            otherwise we will have a job correcting it when we do find TMDb id.
            
            For TMDb movies, we have no issue. If we can't find the id, then we 
            can't find the movie either.
            
            For Library movies, finding the TMDb id is useful for 1) updating db with
            the TMDb id (if setting is enabled) and 2) find any missing trailer on 
            TMDb.
            
            '''

            if movie.is_tmdb_movie():
                keep_new_trailer = False
                rejection_reasons.append(MovieField.REJECTED_NO_TMDB_ID)
                return

        self.throw_exception_on_forced_to_stop()
        clz._logger.debug(f'is library_movie: {movie.is_library_movie()} '
                          f'has_trailer_path: {movie.has_trailer_path()} '
                          f'include lib no info: '
                          f'{Settings.is_include_library_no_trailer_info()}')
        if (movie.is_library_movie() and not movie.has_trailer_path()
                and Settings.is_include_library_no_trailer_info()):

            downloaded_movie: TMDbMovie
            rejection_reasons, downloaded_movie =\
                TMDbMovieDownloader.get_tmdb_movie(movie)
            self.throw_exception_on_forced_to_stop()

            if MovieField.REJECTED_TOO_MANY_TMDB_REQUESTS in rejection_reasons:
                self._missing_trailers_playlist.record_played_trailer(
                    movie, use_movie_path=True, msg='Too many TMDB requests')
                return

            keep_new_trailer = self.handle_rejection(rejection_reasons, movie)
            if keep_new_trailer:
                rejection_reasons = TMDbFilter.filter_movie(downloaded_movie)
                keep_new_trailer = self.handle_rejection(rejection_reasons, movie)

            if keep_new_trailer :
                clz._logger.debug(f'merging path: {downloaded_movie.get_trailer_path()}')
                movie.set_trailer_path(downloaded_movie.get_trailer_path())

                if isinstance(movie, (TMDbMovie, TMDbMovieId)):
                    TMDbTrailerIndex.add(movie)

                    #     Cache.write_tmdb_cache_json(movie, library_id=library_id)

                    # Merge information from discovery with original data
                    movie.update(downloaded_movie)
                    del downloaded_movie
        else:
            if isinstance(movie, LibraryMovie):
                self.throw_exception_on_forced_to_stop()

                '''
                For movies in the Library, we sometimes need to look up TMDb information:
                    * Just to know it's tmdb ID 
                    * Or when there is no local trailer info and the user wants us to
                      search TMDb for a trailer.
                '''
                if ((movie.get_tmdb_id() is None)
                        and (movie.has_trailer_path() or Settings.is_include_library_no_trailer_info())
                        and
                        TrailerUnavailableCache.is_library_id_missing_trailer(
                            movie.get_library_id())):
                    # Try to find movie from TMDb
                    tmdb_id: Union[int, None] = MovieEntryUtils.get_tmdb_id(movie)

                    # Ok, tmdb_id not in Kodi database, query TMDb

                    if (tmdb_id is None
                            and movie.is_tmdb_id_findable()):
                        try:
                            tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                                movie.get_title(), movie.get_year(),
                                runtime_seconds=movie.get_runtime())

                            if tmdb_id is None:
                                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                    clz._logger.debug_verbose(
                                        f'Can not get TMDB id for Library movie: '
                                        f'{movie.get_title()} year: {movie.get_year()}')
                                self._missing_trailers_playlist.record_played_trailer(
                                    movie, use_movie_path=True,
                                    msg=' Movie not found at tmdb')
                                movie.set_tmdb_id_findable(False)
                                LibraryTrailerIndex.remove(movie)
                            else:
                                movie.add_tmdb_id(tmdb_id)
                                LibraryTrailerIndex.add(movie)

                        except CommunicationException:
                            pass  # Get it next time

                        self.throw_exception_on_forced_to_stop()

                    if not movie.has_trailer_path() and tmdb_id is not None:
                        self.throw_exception_on_forced_to_stop()

                        # We only want the trailer, ignore other fields.

                        rejection_reasons: List[str]
                        tmdb_trailer_data: TMDbMovie
                        rejection_reasons, tmdb_trailer_data = \
                            TMDbMovieDownloader.get_tmdb_movie(movie,
                                                               ignore_failures=True)
                        self.throw_exception_on_forced_to_stop()

                        if Constants.TOO_MANY_TMDB_REQUESTS in rejection_reasons:
                            keep_new_trailer = False
                            # Give up playing this movie this time around. It will
                            # still be available for display later.
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(movie.get_title(),
                                                          'could not get movie due to '
                                                          'TOO MANY REQUESTS')
                            return

                        elif len(rejection_reasons) > 0:
                            keep_new_trailer = False
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
                                    'Unexpected REJECTED_STATUS. Ignoring')

                        elif (tmdb_trailer_data is None
                              or not tmdb_trailer_data.get_has_trailer()):
                            keep_new_trailer = False
                            TrailerUnavailableCache.add_missing_library_trailer(
                                tmdb_id=tmdb_id,
                                library_id=movie.get_library_id(),
                                title=movie.get_title(),
                                year=movie.get_year(),
                                source=source)
                            movie.set_has_trailer(False)
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
                                    'No valid trailer found for Library movie:',
                                    movie.get_title(),
                                    'removed:',
                                    self._movie_data.get_number_of_removed_trailers() + 1,
                                    'kept:',
                                    self._playable_trailers.get_number_of_added_trailers(),
                                    'movies:',
                                    self._movie_data.get_number_of_added_movies())
                        else:  # movie does not have a trailer
                            # Keep trailer field, not entire new movie
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                clz._logger.debug_extra_verbose(f'Found remote trailer '
                                                                f'for library movie: '
                                                                f'{movie.get_title()}')
                            movie.set_trailer_path(tmdb_trailer_data.get_trailer_path())

                    LibraryTrailerIndex.add(movie) # Update

            elif source in (MovieField.ITUNES_SOURCE, MovieField.TFH_SOURCE):
                self.throw_exception_on_forced_to_stop()
                tmdb_id: int = movie.get_tmdb_id()
                if tmdb_id is None and movie.is_tmdb_id_findable():
                    if isinstance(movie, TFHMovie):
                        year = None
                    else:
                        year = str(movie.get_year())
                    try:
                        self.throw_exception_on_forced_to_stop()
                        tmdb_id: Union[
                            int, str, None]

                        tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                            movie.get_title(), year, runtime_seconds=movie.get_runtime())

                        if tmdb_id is None:
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                clz._logger.debug_verbose(
                                    f'Can not get TMDB id for {source} movie: '
                                    f'{movie.get_title()} year: '
                                    f'[{movie.get_year()}')
                            if not isinstance(movie, TFHMovie):
                                self._missing_trailers_playlist.record_played_trailer(
                                    movie, use_movie_path=True,
                                    msg=' Movie not found at TMDB')
                                movie.set_tmdb_id_findable(False)
                                if isinstance(movie, TFHMovie):
                                    TFHCache.update_movie(movie)
                            else:
                                # TFH Movie definitely has a trailer, we just can't
                                # find the TMDb movie for it, because the name is
                                # jumbled.
                                pass
                        else:
                            movie.set_tmdb_id(tmdb_id)
                            TFHCache.update_movie(movie)

                    except CommunicationException:
                        pass  # Try to get next time around

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Finished second discovery level for movie:',
                                            movie.get_title(),
                                            '(tentatively) keep:', keep_new_trailer)

        if keep_new_trailer:
            keep_new_trailer = self.consider_aggregate_trailers(movie)

        self.throw_exception_on_forced_to_stop()
        if keep_new_trailer:
            keep_new_trailer = self.cache_and_normalize_trailer(movie)
            if keep_new_trailer:
                if isinstance(movie, TMDbMovie):
                    #
                    # TODO: put this back!
                    #
                    # Record that this TMDbMovie is actively using the json files
                    # that it references. It is done here since at this point it looks
                    # like the movie has a trailer and passes all filters.
                    #
                    # Since the reverse_json caches record movies that have a
                    # reference on TMDb data, we can't record references from TFH,
                    # Library or iTunes until later, in MovieDetails where the
                    # TMDb data is used.

                    # reverse_json_index: Type[BaseReverseIndexCache]
                    # reverse_json_index = JsonCacheHelper.get_json_cache(movie)
                    # reverse_json_index.add_item(movie.get_id(), movie.get_id())
                    TMDbTrailerIndex.add(movie)
                elif isinstance(movie, LibraryMovie):
                    LibraryTrailerIndex.add(movie)

            self.throw_exception_on_forced_to_stop()

        if keep_new_trailer:
            movie.set_discovery_state(MovieField.DISCOVERY_NEARLY_COMPLETE)
            year: str = str(movie.get_year())
            if year == '0':
                year = ''
            movie_id: str = (movie.get_title() + '_' + year).lower()
            AbstractMovieData.get_aggregate_trailers_by_name_date()[movie_id] = movie
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'{movie.get_title()} '
                                                f'added to AggregateTrailers '
                                                f'movie: '
                                                f'{movie.get_optimal_trailer_path()} '
                                                f'source: {movie.get_source()}')

        else:
            self._movie_data.remove_discovered_movie(movie)

        if keep_new_trailer:
            self.throw_exception_on_forced_to_stop()
            fully_populated_trailer: AbstractMovie = MovieDetail.get_detail_info(movie)
            if fully_populated_trailer is None:
                if isinstance(movie, TFHMovie):
                    self._playable_trailers.add_to_ready_to_play_queue(movie)
                else:
                    self._movie_data.remove_discovered_movie(movie)
            else:
                self._playable_trailers.add_to_ready_to_play_queue(
                    fully_populated_trailer)

        self._stop_fetch_time = datetime.datetime.now()
        self._stop_add_ready_to_play_time = datetime.datetime.now()
        discovery_time = self._stop_fetch_time - self._start_fetch_time
        queue_time = self._stop_add_ready_to_play_time - self._stop_fetch_time
        if (clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                and clz._logger.is_trace_enabled(Trace.STATS)):
            clz._logger.debug('took:', discovery_time.microseconds / 10000,
                              'ms',
                              'QueueTime:', queue_time.microseconds / 10000,
                              'ms',
                              'movie:', movie.get_title(),
                              'type:', movie.get_trailer_type(),
                              'Kept:', keep_new_trailer, trace=Trace.STATS)

    def consider_aggregate_trailers(self, movie: AbstractMovie = None) -> bool:
        # If no trailer possible then remove it from further consideration
        clz = type(self)
        movie_id: str = None
        keep_new_trailer: bool = True
        year: str = str(movie.get_year())
        if year == '0':
            year = ''

        movie_id = (movie.get_title() + '_' + year).lower()

        self.throw_exception_on_forced_to_stop()
        with AbstractMovieData.get_aggregate_trailers_by_name_date_lock():
            if not movie.has_trailer_path():
                keep_new_trailer = False
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('Not keeping:', movie.get_title(),
                                                    'because trailer is empty')
            elif movie_id in AbstractMovieData.get_aggregate_trailers_by_name_date():
                movie_in_dictionary: BaseMovie = (
                    AbstractMovieData.get_aggregate_trailers_by_name_date()[movie_id])

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('Duplicate Movie id:', movie_id,
                                                    'source:',
                                                    movie_in_dictionary.get_source())
                    if movie.is_represents_same_instance(movie_in_dictionary):
                        clz._logger.debug_extra_verbose(f'represents identical instances')
                        keep_new_trailer = True  # Show again
                        return keep_new_trailer

                # Always prefer the local trailer
                if isinstance(movie, LibraryMovie):
                    if isinstance(movie_in_dictionary, LibraryMovie):
                        #
                        # Joy, two copies, both with trailers. Toss the new one.
                        #
                        # TODO: Consider trailer type for winner. Also, is trailer
                        #       local (not cached or downloaded) or from remote
                        #       source.

                        keep_new_trailer = False
                        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                            clz._logger.debug_extra_verbose('Not keeping:',
                                                            movie.get_title(),
                                                            'because dupe and both '
                                                            'in library')
                    else:
                        # Replace non-local version with this local one.
                        keep_new_trailer = True
                elif isinstance(movie_in_dictionary, LibraryMovie):
                    # New movie is not from Library, but old one is

                    keep_new_trailer = False

                    # TODO: Verify

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.debug_verbose('Duplicate:', movie.get_title(),
                                                  'original source:',
                                                  movie_in_dictionary.get_source(),
                                                  'new source:', movie.get_source())
                elif isinstance(movie, type(movie_in_dictionary)):
                    keep_new_trailer = False
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.debug_verbose('Not keeping:', movie.get_title(),
                                                  'because duplicate source')
                elif isinstance(movie, FolderMovie):
                    keep_new_trailer = True
                elif isinstance(movie, ITunesMovie):
                    keep_new_trailer = True
                elif isinstance(movie, TMDbMovie):
                    keep_new_trailer = True

        return keep_new_trailer

    def find_and_update_tmdb_id(self, movie: AbstractMovie) -> Union[int, None]:
        clz = type(self)
        tmdb_id: Optional[int] = MovieEntryUtils.get_tmdb_id(movie)
        if tmdb_id is not None:
            tmdb_id = int(tmdb_id)

        if (tmdb_id is None
                and (isinstance(movie, ITunesMovie) or isinstance(movie, TFHMovie))):
            self.throw_exception_on_forced_to_stop()
            if isinstance(movie, TFHMovie):
                year = None
            else:
                year = movie.get_year()
            try:
                tmdb_id = TMDBUtils.get_tmdb_id_from_title_year(
                    movie.get_title(), year,
                    runtime_seconds=movie.get_runtime())
                if tmdb_id is None:
                    movie.set_tmdb_id_findable(False)
                    if isinstance(movie, TFHMovie):
                        TFHCache.update_movie(movie)
                else:
                    changed = movie.set_tmdb_id(tmdb_id)
                    if changed and isinstance(movie, TFHMovie):
                        TFHCache.update_movie(movie)
            except CommunicationException:
                clz._logger.debug(f'CommunicationException while getting tmdb_id for: '
                                  f'{movie.get_title()} Will try again later.')
                pass  # Try to get tmdb_id next time.

        return tmdb_id

    def handle_rejection(self, rejection_reasons: List[int], movie: AbstractMovie) -> bool:
        clz = type(self)
        keep_new_trailer: bool = True
        if MovieField.REJECTED_NO_TRAILER in rejection_reasons:
            # A Large % of TMDb movies do not have a trailer (at
            # least for old movies). Don't log, unless required.
            self._missing_trailers_playlist.record_played_trailer(
                movie, use_movie_path=True, msg='No Trailer')
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                title: str = movie.get_title()
                clz._logger.debug_extra_verbose(
                    f'No trailer found for TMDB movie: '
                    f'{title} removed: '
                    f'{self._movie_data.get_number_of_removed_trailers() + 1}'
                    f' kept: '
                    f'{self._playable_trailers.get_number_of_added_trailers()} '
                    f'movies: '
                    f'{self._movie_data.get_number_of_added_movies()}')
            keep_new_trailer = False
        elif isinstance(movie, TMDbMovie) and len(rejection_reasons) > 0:
            # Ignore filtering for non-TMDb movies, under the assumption
            # that we trust the filtering for other sources

            keep_new_trailer = False
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                reasons: str = ','.join(map(lambda x:
                                            MovieField.REJECTED_REASON_MAP(x),
                                            rejection_reasons))
                clz._logger.debug_extra_verbose(f'movie: {movie.get_title()} '
                                                f'filtered out due to: '
                                                f'{reasons}')
        return keep_new_trailer

    def throw_exception_on_forced_to_stop(self, timeout: float = 0.0) -> None:
        """

        :param timeout:
        :return:
        """
        Monitor.throw_exception_if_abort_requested(timeout=timeout)
        if self._stop_thread:
            raise StopDiscoveryException()

    def cache_and_normalize_trailer(self, movie: AbstractMovie) -> bool:
        clz = type(self)
        rc: int = 0
        trailer_ok: bool = True
        self.throw_exception_on_forced_to_stop()

        if (Settings.is_use_trailer_cache() and
                (DiskUtils.is_url(movie.get_trailer_path()) or
                 not isinstance(movie, LibraryMovie))):

            if (VideoDownloader().check_too_many_requests(movie.get_title(),
                                                          movie.get_source())
                    == Constants.HTTP_TOO_MANY_REQUESTS):
                return trailer_ok

            rc = MovieDetail.download_and_cache(movie)
            if rc != 0:
                if rc != Constants.HTTP_TOO_MANY_REQUESTS:
                    trailer_ok = False

        elif not Settings.is_use_trailer_cache():
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                clz._logger.debug_verbose('Not caching:', movie.get_title(),
                                          'trailer:', movie.get_trailer_path(),
                                          'type:', type(movie).__name__,
                                          'state:', movie.get_discovery_state())

        if rc == 0:
            normalized = False
            if (Settings.is_normalize_volume_of_downloaded_trailers() or
                    Settings.is_normalize_volume_of_local_trailers()):
                self.throw_exception_on_forced_to_stop()
                normalized = self.normalize_trailer_sound(movie)
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz._logger.debug_verbose(movie.get_title(), f'audio normalized: '
                                          f'{normalized} '
                                          f'normalized movie: ' 
                                          f'{movie.get_normalized_trailer_path()} '
                                          f'path: {movie.get_trailer_path()} '
                                          f'cache_path: {movie.get_cached_trailer()} '
                                          f'has_local: {movie.has_local_trailer()} '
                                          f'type: {type(movie).__name__} '
                                                             f'RC: {trailer_ok}')
                clz._logger.debug(f'movie: {movie.get_title()} id: {movie.get_id()} ' 
                                  f'normalized: {normalized}',
                                  trace=Trace.TRACE_DISCOVERY)
        movie.validate_local_trailer()
        if movie.has_trailer_path():
            movie.set_has_trailer(True)
        if isinstance(movie, TMDbMovie):
            TMDbTrailerIndex.add(movie)
        return trailer_ok

    def normalize_trailer_sound(self, movie: AbstractMovie) -> bool:
        """
            Normalize the sound of the movie. The movie may be local
            and in the library, or may have been downloaded and placed
            in the cache.

            :param movie: Movie movie to consider normalizing
            :return: True if movie was normalized by this call
        """
        clz = type(self)

        # During startup the expense of Audio Normalization can delay showing
        # movies. Skip it if the player is starving. We can normalize this movie
        # at another time.

        if self._playable_trailers.is_starving():
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'Delaying normalization due to '
                                                f'starvation for {movie.get_title()} '
                                                f'source: {movie.get_source()}')
            return False

        normalized_trailer_path: str = ''
        normalized_used: bool = False
        start: datetime.datetime = datetime.datetime.now()
        try:
            # TODO: Add ability to normalize remote trailers
            # (occurs when caching is disabled).

            # FOLDER_SOURCE not supported at this time because a key
            # would have to be created.

            # iTunes and TFH trailers probably don't require normalization, at
            # least not due to low-quality recordings by amateurs. However,
            # maybe you want to smooth them out a bit.

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'{movie.get_title()} '
                                                f'source: {movie.get_source()} '
                                                f'video_id: '
                                                f'{Cache.get_trailer_id(movie)} '
                                                f'movie: {movie.get_trailer_path()} '
                                                f'cached movie: '
                                                f'{movie.get_cached_trailer()} '
                                                f'normalized movie: '
                                                f'{movie.get_normalized_trailer_path()}')
            if movie.get_source() not in MovieField.LIB_TMDB_ITUNES_TFH_SOURCES:
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

            if Cache.get_trailer_id(movie) is None:
                return False

            # Can not normalize remote files. MovieField.CACHED_TRAILER contains
            # the path to any downloaded trailers (by download_and_cache)

            # Verify cache was not purged

            if (movie.has_cached_trailer() and
                    not os.path.exists(movie.get_cached_trailer())):
                movie.set_cached_trailer('')
            if (movie.has_normalized_trailer() and
                    not os.path.exists(movie.get_normalized_trailer_path())):
                movie.set_normalized_trailer_path('')

            normalize: bool = False

            # Assume movie is local
            trailer_path = movie.get_trailer_path()  # Might be a URL

            # Presence of cached movie means there is no MovieField.TRAILER, or
            # that it is a url and already downloaded. So use it if present.

            if Settings.is_normalize_volume_of_downloaded_trailers():
                if movie.has_cached_trailer():
                    #
                    # If remote movie was downloaded by download_and_cache,
                    # then use it.
                    #
                    trailer_path = movie.get_cached_trailer()
                    normalize = True
                elif movie.has_normalized_trailer():
                    normalize = True  # Verify that we don't have to re-normalize

            if (isinstance(movie, LibraryMovie) and
                    Settings.is_normalize_volume_of_local_trailers() and
                    os.path.exists(trailer_path)):
                normalize = True

            if not normalize:
                return False

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('movie',
                                                movie.get_trailer_path(),
                                                'cached trailer:',
                                                movie.get_cached_trailer())

            # Populate NORMALIZED_TRAILER path, if needed.

            normalized_trailer_path = movie.get_normalized_trailer_path()
            if not movie.has_normalized_trailer():
                # trailer_path is either a cached_path or a library path.

                # Discover from cache
                normalized_trailer_path = ''
                parent_dir: str
                trailer_file_name: str

                parent_dir, trailer_file_name = os.path.split(trailer_path)
                normalized_trailer_path_pattern = \
                    Cache.get_trailer_cache_file_path_for_movie_id(
                        movie, trailer_file_name, True)

                # Not quite sure of value of this. Seems that a simple
                # normalized_trailer_path_path = normalized_trailer_path_pattern
                # would do.

                cached_normalized_trailers: List[str] = \
                    glob.glob(normalized_trailer_path_pattern)
                if len(cached_normalized_trailers) > 0:
                    # If a match, then already normalized
                    normalized_trailer_path = cached_normalized_trailers[0]
                else:
                    # No match found, movie not normalized.
                    normalized_trailer_path = normalized_trailer_path_pattern

                movie.set_normalized_trailer_path(normalized_trailer_path)

            if normalized_trailer_path != '':
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
                                    'title:', movie.get_title())

            # TODO: Handle the case where files are NOT cached

            # A bit redundant, but perhaps clearer.

            if movie.has_cached_trailer():
                trailer_path = movie.get_cached_trailer()
            else:
                trailer_path = movie.get_trailer_path()

            normalized_used = False
            if (normalized_trailer_path != ''
                    and not os.path.exists(normalized_trailer_path)):
                DiskUtils.create_path_if_needed(
                    os.path.dirname(normalized_trailer_path))

                self.throw_exception_on_forced_to_stop()

                rc = ffmpeg_normalize.normalize(
                    trailer_path, normalized_trailer_path)

                if rc == 0:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.debug_verbose(
                            f'Normalized: {movie.get_title()}',
                            f'path: {normalized_trailer_path}')
                    normalized_used = True
                else:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug('Normalize failed:',
                                          movie.get_title(),
                                          f'path: {normalized_trailer_path}')

                #
                # If source file was downloaded and cached, then just blow it away
                #
                if Cache.is_trailer_from_cache(trailer_path):
                    if os.path.exists(trailer_path):
                        os.remove(trailer_path)
                movie.set_normalized_trailer_path(normalized_trailer_path)
            elif normalized_trailer_path == '':
                movie.set_normalized_trailer_path('')

        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('Exception. Movie:', movie.get_title(),
                                  'Path:', normalized_trailer_path)
        finally:
            stop = datetime.datetime.now()
            elapsed_time = stop - start
            if normalized_used:
                #  TODO: Log in statistics module
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('time to normalize movie:',
                                                    elapsed_time.seconds)
        return normalized_used
