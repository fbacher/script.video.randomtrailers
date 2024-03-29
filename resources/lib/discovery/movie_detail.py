# -*- coding: utf-8 -*-

"""
Created on July 7, 2021

@author: Frank Feuerbacher
"""
import datetime
import glob
import os
import re
import shutil
import sys
from pathlib import Path

import xbmcvfs

from backend.backend_constants import YOUTUBE_URL
from backend.movie_entry_utils import MovieEntryUtils
from backend.tmdb_utils import TMDBUtils
from cache.library_trailer_index import LibraryTrailerIndex
from cache.movie_trailer_index import MovieTrailerIndex
from cache.tfh_cache import TFHCache
from cache.tmdb_cache_index import CacheIndex
from cache.tmdb_trailer_index import TMDbTrailerIndex
from cache.trailer_unavailable_cache import TrailerUnavailableCache
from common.constants import Constants
from common.debug_utils import Debug
from common.imports import *

from backend.video_downloader import VideoDownloader
from cache.cache import Cache
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, CommunicationException, reraise
from common.logger import LazyLogger, Trace
from common.monitor import Monitor
from common.movie import AbstractMovie, ITunesMovie, TFHMovie, TMDbMovie, LibraryMovie, \
    Movies
from common.movie_constants import MovieField
from common.playlist import Playlist
from discovery.tmdb_movie_downloader import TMDbMovieDownloader
from discovery.utils.db_access import DBAccess
from discovery.utils.parse_library import ParseLibrary

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MovieDetail:
    _logger: LazyLogger = None

    @classmethod
    def class_init(cls):
        cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_detail_info(cls, movie: AbstractMovie) -> AbstractMovie:
        """
        Does final data collection and formatting of fields suitable for display
        to user.

        Assumptions:
           An attempt to discover TMDb id for this movie has been done and the
           movie entry has been updated with any found info. (See AbstractTrailerFetcher,
           this is done there because the title + year is used for a key in
           the Aggregate Trailer table).

        TODO: move extra data collection to earlier stage during fetching. Leave
        this method to simply do formatting.

        :param movie:
        :return:
        """
        keep_trailer = True

        try:
            tmdb_id: int = movie.get_tmdb_id()
            if (cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)
                    and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                cls._logger.debug_verbose(f'title: {movie.get_title()}'
                                          f' source: {movie.get_source()}'
                                          f' tmdb_id: {tmdb_id}'
                                          f' is_tmdb_id_findable: '
                                          f'{movie.is_tmdb_id_findable()}')

            if movie.is_tmdb_id_findable():
                if isinstance(movie, ITunesMovie) or isinstance(movie, TFHMovie):
                    keep_trailer = cls.merge_tmdb_info(movie)

            if isinstance(movie, LibraryMovie):
                # We only have minimal properties for Library Movies. Get the rest from
                # the Kodi database so that they can be displayed.
                # We do it here so that we don't 1) waste a ton of time at startup when
                # we only need them as a trailer is actually played and 2) We don't waste
                # the memory. We just get what we need now for display and then toss it.

                query: str = DBAccess.create_details_query(
                    movie.get_library_id())

                raw_movies: List[MovieType] = DBAccess.get_movie_details(query)
                raw_movie: MovieType = None
                if len(raw_movies) == 1:
                    raw_movie = raw_movies[0]
                else:
                    cls._logger.error(f'Could not find movie in database: '
                                      f'{movie.get_title()} ({movie.get_year()})')
                    return

                fully_populated_movie = ParseLibrary.parse_movie(is_sparse=False,
                                                                 raw_movie=raw_movie)

                # Leave movie instance from AbstractMovieData alone. Go though
                # rediscovery of fully_populated_movie on each display in order
                # to reduce memory usage. CPU cost very little given that a trailer
                # is shown only about every 3 minutes, or so.

                cls._logger.debug(f'fully_populated path: '
                                  f'{fully_populated_movie.get_trailer_path()} '
                                  f'cache: {fully_populated_movie.get_cached_trailer()} '
                                  f'normalized: {fully_populated_movie.get_normalized_trailer_path()} ')
                cls._logger.debug(f'movie path: {movie.get_trailer_path()} '
                                  f'cache: {movie.get_cached_trailer()} '
                                  f'normalized: {movie.get_normalized_trailer_path()}')
                cls.clone_fields(movie, fully_populated_movie,
                                 MovieField.DETAIL_CLONE_FIELDS)
                movie = fully_populated_movie

            if keep_trailer and isinstance(movie, (TMDbMovie, TFHMovie)):
                # If a movie was downloaded from TMDB or TFH, check to see if
                # the movie is in our library so that fact can be included in the
                # UI.
                library_id = movie.get_library_id()
                if library_id is None:
                    tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
                    if tmdb_id is not None:
                        tmdb_id = int(tmdb_id)

                    kodi_movie = TMDBUtils.get_movie_by_tmdb_id(tmdb_id)

                    if kodi_movie is not None:
                        movie.set_library_id(kodi_movie.get_kodi_id())
                        movie.set_movie_path(kodi_movie.get_kodi_file())
                    elif movie.get_year() is not None:
                        try:
                            query = DBAccess.create_title_date_query(title=
                                                                     movie.get_title(),
                                                                     year=str(
                                                                         movie.get_year())
                                                                     )
                            raw_movies: List[MovieType] = DBAccess.get_movie_details(
                                    query)
                            if len(raw_movies) > 0:
                                if len(raw_movies) > 1:
                                    # Bad decision, but always take the first entry.
                                    cls._logger.debug_verbose(f'multiple movies returned '
                                                              f'from query title: '
                                                              f'{movie.get_title()} '
                                                              f'year: {movie.get_year()}')

                                kodi_movie = ParseLibrary.parse_movie(is_sparse=True,
                                                                      raw_movie=
                                                                      raw_movies[0])
                            if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                                if kodi_movie is not None:
                                    cls._logger.debug(f'Kodi movie found!')
                                else:
                                    cls._logger.debug(f'Kodi movie NOT found')
                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception:
                            cls._logger.exception()

                if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                            and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                        cls._logger.debug_extra_verbose(
                            f'{movie.get_title()}: '
                            f' source: {movie.get_source()}'
                            f' tmdbId: {str(tmdb_id)}'
                            f' MovieId: {movie.get_library_id()}')

            if keep_trailer:
                movie.set_discovery_state(MovieField.DISCOVERY_READY_TO_DISPLAY)
                movie.set_has_been_fully_discovered(True)

            if tmdb_id is not None:
                CacheIndex.remove_unprocessed_movie(tmdb_id)

            if not keep_trailer:
                movie = None
                if tmdb_id is not None:
                    CacheIndex.remove_tmdb_id_with_trailer(tmdb_id)
            else:
                if (cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)
                        and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                    cls._logger.debug_verbose('Fully discovered and ready to play:',
                                              movie.get_title(),
                                              movie.get_detail_title(),
                                              trace=Trace.TRACE_DISCOVERY)
                if isinstance(movie, TFHMovie):
                    TFHCache.update_movie(movie)

            return movie
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
            return None

    @classmethod
    def merge_tmdb_info(cls, movie: AbstractMovie):
        """
        Merges information from TMDb for the given TFH or ITunes movie, which have
        sparse information.

        KLUDGE: See TODO

        TODO: Revisit policy of merging DUMMY TMDb information when no TMDb movie
              found for TFH movies.

        param: movie

        returns: True when TMDb data was found, merged, and determined not
                 to exclude the movie from viewing due to certification,
                 etc.

                 False, when either corresponding TMDb movie not found or
                 the filter on the TMDb movie indicates that the trailer
                 should not be displayed
        """
        tmdb_id: Optional[int] = MovieEntryUtils.get_tmdb_id(movie)
        movie.set_tmdb_id(tmdb_id)
        if tmdb_id is not None:
            tmdb_id = int(tmdb_id)

        movie.get_thumbnail(default='')
        tmdb_detail_info: TMDbMovie = None
        keep_trailer: bool = True
        if isinstance(movie, ITunesMovie):
            Monitor.throw_exception_if_abort_requested()
            rejection_reasons, tmdb_detail_info = TMDbMovieDownloader.get_tmdb_movie(
                movie, ignore_failures=True)

            if len(rejection_reasons) > 0:
                # There is some data which is normally considered a deal-killer.
                # Examine the fields that we are interested in to see if
                # some of it is usable

                # We don't care if TMDB does not have movie, or if it does
                # not have this movie registered at all (it could be very
                # new).

                if (tmdb_detail_info is not None
                        and not tmdb_detail_info.is_original_language_found()):
                    keep_trailer = False
            else:
                movie.set_plot(tmdb_detail_info.get_plot())
                if len(movie.get_actors()) == 0:
                    movie.set_actors(tmdb_detail_info.get_actors())
                if len(movie.get_writers()) == 0:
                    movie.set_writers(tmdb_detail_info.get_writers())
                if movie.get_runtime() == 0:
                    movie.set_runtime(tmdb_detail_info.get_runtime())

        if isinstance(movie, TFHMovie):
            Monitor.throw_exception_if_abort_requested()
            rejection_reasons, tmdb_detail_info = TMDbMovieDownloader.get_tmdb_movie(
                movie, ignore_failures=True)

            if len(rejection_reasons) > 0:
                # At this point, rejection is only due inability to get any TMDb info
                # for the movie.

                # TODO: Revisit not setting to False

                # keep_trailer = False
                tmdb_detail_info = None

                # These rejected reasons will never be present. See comment above.
                # Checked later, when returned.
                #
                # if (MovieField.REJECTED_ADULT, MovieField.REJECTED_CERTIFICATION,
                #         MovieField.REJECTED_FAIL) in rejection_reasons:
                #     if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                #         cls._logger.debug_extra_verbose(f'Rejecting TFH movie'
                #                                         f' {movie.get_title()} '
                #                                         f'due to Certification')

            if tmdb_detail_info is not None:
                if (cls._logger.isEnabledFor(LazyLogger.DISABLED)
                        and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                    from common.debug_utils import Debug
                    Debug.dump_dictionary(movie.get_as_movie_type(),
                                          heading='Dumping TFH movie_info',
                                          log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)

                cls.clone_fields(tmdb_detail_info, movie, MovieField.TFH_CLONE_FIELDS)

                if (movie.get_thumbnail(default='') == ''
                        and tmdb_detail_info.get_thumbnail(default='').startswith(
                            'http')):
                    movie.set_thumbnail(tmdb_detail_info.get_thumbnail())

                if movie.get_plot() == '':
                    movie.set_plot(tmdb_detail_info.get_plot())

                if movie.get_rating() == 0.0 and tmdb_detail_info.get_rating() != 0.0:
                    movie.set_rating(tmdb_detail_info.get_rating())

                if (cls._logger.isEnabledFor(LazyLogger.DISABLED)
                        and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                    from common.debug_utils import Debug
                    Debug.dump_dictionary(movie.get_as_movie_type(),
                                          heading='Dumping Modified movie info',
                                          log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)
            else:
                # TODO: Revisit this. Should we display when we can't filter based
                #       on user's wishes?
                #
                # TMDb movie not found for TFH movie. Take a risk and display it
                # anyway with dummy information. The risk is that the movie should
                # be filtered out due to certification (content) or other reasons.
                #
                dummy_movie = TMDbMovie()
                cls.clone_fields(dummy_movie, movie, MovieField.TFH_CLONE_FIELDS)
        return keep_trailer

    @classmethod
    def get_tmdb_trailer_url(cls, movie: AbstractMovie) -> str:
        """
        Gets only the trailer path for the TMDb movie referenced by the given movie.

        TODO: Revisit policy of merging DUMMY TMDb information when no TMDb movie
              found for TFH movies.

        param: movie

        returns: url path to the trailer for the TMDb movie.
                 None if no path found
        """

        Monitor.throw_exception_if_abort_requested()
        tmdb_detail_info: TMDbMovie
        rejection_reasons, tmdb_detail_info = TMDbMovieDownloader.get_tmdb_movie(
            movie, ignore_failures=True)

        if len(rejection_reasons) > 0:
            cls._logger.debug(f'tmdb movie rejected:{ movie.get_tmdb_id()}')
            return None
        else:
            cls._logger.debug(f'found path: {tmdb_detail_info.get_trailer_path()}')
            return tmdb_detail_info.get_trailer_path()

    @classmethod
    def clone_fields(cls,
                     source: AbstractMovie,
                     destination: AbstractMovie,
                     fields_to_copy: Dict[str, Any]
                     ) -> None:
        """

        :param cls:
        :param source:
        :param destination:
        :param fields_to_copy:
        :return:
        """
        try:
            for key, default_value in fields_to_copy.items():
                value = source.get_property(key, default_value)
                destination.set_property(key, value)

            if destination.has_trailer_path() and not destination.is_trailer_url():
                destination.set_local_trailer(True)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def download_and_cache(cls, movie: AbstractMovie) -> int:
        """

        :param cls:
        :param movie:
        :return:
        """

        # TODO: Verify Cached items cleared

        download_path: str = None
        movie_id: str = None
        cached_path: str = ''
        rc: int = 0

        try:
            if not isinstance(movie, Movies.LIB_TMDB_ITUNES_TFH_SOURCES):
                cls._logger.debug(f'Incorrect type: {type(movie)}')
                return 0

            start = datetime.datetime.now()
            movie_id = ''
            #
            # We are guaranteed to have a trailer path. Either a url or local file path
            #
            trailer_path = movie.get_trailer_path()
            is_url = movie.is_trailer_url()
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                cls._logger.debug_verbose(
                    f'{movie.get_title()} {movie.get_trailer_path()} url: {is_url}')

            if not is_url:
                # Must be a path to a local trailer (not cached, etc.).
                #
                # The meaning of set_local_trailer is that a local trailer,
                # from a download to a cache or not, is present.
                #
                movie.set_local_trailer(True)
                movie.set_has_trailer(True)
                movie.validate_local_trailer()
                MovieTrailerIndex.add(movie)
                return rc

            # If cached files purged, then remove references

            if (movie.has_cached_trailer() and
                    not os.path.exists(movie.get_cached_trailer())):
                movie.set_cached_trailer('')
            if (movie.has_normalized_trailer() and
                    not os.path.exists(movie.get_normalized_trailer_path())):
                movie.set_normalized_trailer_path('')

            # No need for cached movie if we have a cached normalized movie

            if (movie.has_normalized_trailer()
                    and os.path.exists(movie.get_normalized_trailer_path())):
                movie.set_local_trailer(True)
                MovieTrailerIndex.add(movie)
                return rc

            if trailer_path.startswith('plugin'):
                video_id = re.sub(r'^.*video_?id=', '', trailer_path)
                # plugin://plugin.video.youtube/play/?video_id=
                # DEPRECATED plugin://plugin.video.youtube/?action=play_video&videoid=
                new_path = f'{YOUTUBE_URL}{video_id}'
                trailer_path = new_path

            movie_id = Cache.get_trailer_id(movie)
            cls._logger.debug(f'movie: {movie.get_title()} movie_id: {movie_id} '
                              f'trailer_path: {trailer_path}')

            # Trailers for movies in the library are treated differently
            # from those that we don't have a local movie for:
            #  1- The library ID can be used for those from the library,
            #     otherwise an ID must be manufactured from the movie name/date
            #     or from the ID from the remote source, or some combination
            #
            #  2- Movies from the library have a known name and date. Those
            #    downloaded come with unreliable names and dates.
            #

            # Create a uniqueId that can be used in a file name

            # Find out if this has already been cached
            # Get pattern for search
            if movie_id is not None and movie_id != '':
                cached_path = Cache.get_trailer_cache_file_path_for_movie_id(
                    movie, '*-movie.*', False)
                cls._logger.debug(f'cached_path: {cached_path}')
                cached_trailers = glob.glob(cached_path)
                if len(cached_trailers) != 0:
                    #
                    # A cached trailer exists. It is either the normalized or not.
                    #
                    movie.set_local_trailer(True)
                    movie.set_has_trailer(True)
                    MovieTrailerIndex.add(movie)
                    already_normalized = False
                    for cached_trailer in cached_trailers:
                        if 'normalized' in cached_trailer:
                            already_normalized = True
                            if movie.get_normalized_trailer_path() == '':
                                movie.set_normalized_trailer_path(cached_trailer)
                            cls._logger.debug(
                                f'Already normalized trailer {movie.get_title()} '
                                f'path: {movie.get_normalized_trailer_path()}',
                                Trace.TRACE_DISCOVERY)

                    if not already_normalized:
                        movie.set_cached_trailer(cached_trailers[0])
                        stop = datetime.datetime.now()
                        locate_time = stop - start
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose('time to locate movie:',
                                                            locate_time.seconds, 'path:',
                                                            movie.get_cached_trailer())
                        cls._logger.debug(f'Already cached trailer {movie.get_title()} '
                                          f'path: {movie.get_cached_trailer()}',
                                          trace=Trace.TRACE_DISCOVERY)
                else:
                    #
                    # Not in cache, download
                    #
                    movie.set_local_trailer(False)
                    MovieTrailerIndex.add(movie)

                    downloaded_trailer: MovieType
                    error_code: int
                    trailer_folder = xbmcvfs.translatePath('special://temp')
                    video_downloader = VideoDownloader()
                    cls._logger.debug(f'downloading movie_id: {movie_id}')
                    error_code, downloaded_trailer = \
                        video_downloader.get_video(
                            trailer_path, trailer_folder, movie_id,
                            movie.get_title(), movie.get_source(), block=False)
                    cls._logger.debug(f'video_downloader returned error_code: '
                                      f'{error_code} downloaded_trailer: '
                                      f'{downloaded_trailer}')
                    if error_code == Constants.HTTP_TOO_MANY_REQUESTS:
                        rc = Constants.HTTP_TOO_MANY_REQUESTS
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                            cls._logger.debug_extra_verbose(
                                'Too Many Requests')
                            cls._logger.debug(
                                'Can not download movie for cache at this time')
                        return rc
                    if error_code == VideoDownloader.UNAVAILABLE:
                        # Account terminated, or other permanent unavailability
                        cls.trailer_permanently_unavailable(movie, error_code=error_code)

                    elif error_code == VideoDownloader.AGE_LIMIT:
                        cls._logger.debug_verbose(f'Trailer available for '
                                                  f'{movie.get_title()} but exceeds '
                                                  f'the configured Age Limit, or YouTube '
                                                  f'userid/password not configured.')
                    if downloaded_trailer is not None:
                        download_path = downloaded_trailer[MovieField.TRAILER]
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'Successful Download path: '
                                                            f'{download_path}',
                                                            trace=Trace.TRACE_DISCOVERY)

                    """
                       To save json data from downloaded for debugging, uncomment
                       the following.
    
                    temp_file = os.path.join(trailer_folder, str(tmdb_id) + '.json')
                    import io
                    with io.open(temp_file, mode='wt', newline=None,
                                 encoding='utf-8', ) as cacheFile:
                        jsonText = utils.py2_decode(json.dumps(downloaded_trailer,
                                                               encoding='utf-8',
                                                               ensure_ascii=False))
                        cacheFile.write(jsonText)
    
                    """

                    if (download_path is None or
                            error_code == VideoDownloader.UNAVAILABLE):
                        error_code = VideoDownloader.UNAVAILABLE
                        cls.trailer_permanently_unavailable(movie, error_code=error_code)
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

                        title: str = movie.get_title()
                        if isinstance(movie, TFHMovie):
                            title = movie.get_tfh_title()  # To get unmodified title

                        trailer_file_name = (title
                                             + ' (' + str(movie.get_year())
                                             + ')-movie' + '.' + trailer_file_type)

                        cached_path = Cache.get_trailer_cache_file_path_for_movie_id(
                            movie, trailer_file_name, False)

                        try:
                            if not os.path.exists(cached_path):
                                DiskUtils.create_path_if_needed(
                                    os.path.dirname(cached_path))
                                shutil.move(download_path, cached_path)
                                Path(cached_path).touch()
                            movie.set_cached_trailer(cached_path)
                            movie.set_local_trailer(True)
                            MovieTrailerIndex.add(movie)

                            stop = datetime.datetime.now()
                            locate_time = stop - start
                            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                cls._logger.debug_extra_verbose(
                                    'movie download to cache time:',
                                    locate_time.seconds)
                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                cls._logger.debug_extra_verbose(
                                    'Failed to move movie to cache.',
                                    'movie:', trailer_path,
                                    'cachePath:', download_path)
                            # cls._logger.exception(
                            #                          'Failed to move movie to
                            #                          cache: ' +
                            #                        trailer_path)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(f'Exception. Movie: {movie.get_title()}',
                                  'ID:', movie_id, 'Path:', cached_path)

        movie.validate_local_trailer()
        if isinstance(movie, TMDbMovie):
            TMDbTrailerIndex.add(movie)
        elif isinstance(movie, LibraryMovie):
            LibraryTrailerIndex.add(movie)
        return rc

    @classmethod
    def trailer_permanently_unavailable(cls, movie: AbstractMovie, error_code: int = 0):
        tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
        if not isinstance(movie, AbstractMovie):
            cls._logger.dump_stack(msg=f'movie arg incorrect type: {type(movie)}')

        if tmdb_id is None:
            cls._logger.debug_verbose(f'tmdb_id is None for {movie.get_title()} '
                                      f'source: {movie.get_source()}')
            return

        TrailerUnavailableCache.add_missing_tmdb_trailer(
                            tmdb_id=tmdb_id,
                            library_id=None,
                            title=movie.get_title(),
                            year=movie.get_year(),
                            source=movie.get_source()
                        )
        msg: str = 'Download FAILED'
        if error_code == VideoDownloader.UNAVAILABLE:
            msg = 'Download permanently unavailable'
        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            cls._logger.debug(f'Video Download failed {movie.get_title()} '
                              f'tmdb_id: {movie.get_tmdb_id()}')
            Debug.dump_dictionary(movie.get_as_movie_type(),
                                  log_level=LazyLogger.DISABLED)
        missing_trailers_playlist: Playlist = Playlist.get_playlist(
                Playlist.MISSING_TRAILERS_PLAYLIST, append=False,
                rotate=True)
        missing_trailers_playlist.record_played_trailer(
            movie, use_movie_path=False, msg=msg)


MovieDetail.class_init()
