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

from backend.movie_entry_utils import MovieEntryUtils
from backend.tmdb_utils import TMDBUtils
from cache.tfh_cache import TFHCache
from cache.tmdb_cache_index import CacheIndex
from cache.trailer_unavailable_cache import TrailerUnavailableCache
# from cache.unprocessed_tmdb_page_data import UnprocessedTMDbPages
from common.constants import Constants
from common.debug_utils import Debug
from common.imports import *

from backend.video_downloader import VideoDownloader
from cache.cache import Cache
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, CommunicationException, reraise
from common.logger import LazyLogger, Trace
from common.monitor import Monitor
from common.movie import AbstractMovie, ITunesMovie, TFHMovie, TMDbMovie, LibraryMovie
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
           movie entry has been updated with any found info. (See TrailerFetcher,
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
                raw_movie: MovieType = DBAccess.get_movie_details(query)
                fully_populated_movie = ParseLibrary.parse_movie(is_sparse=False,
                                                                 raw_movie=raw_movie)
                movie = fully_populated_movie

            if isinstance(movie, TMDbMovie) or isinstance(movie, TFHMovie):
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
                            query = DBAccess.create_title_date_query(title=movie.get_title(),
                                                                    year=str(movie.get_year()))
                            raw_movies: List[MovieType] = DBAccess.get_movie_details(query)
                            if len(raw_movies) > 0:
                                if len(raw_movies) > 1:
                                    # Bad decision, but always take the first entry.
                                    cls._logger.debug_verbose(f'multiple movies returned from query '
                                                              f'title: {movie.get_title()} '
                                                              f'year: {movie.get_year()}')

                                kodi_movie = ParseLibrary.parse_movie(is_sparse=True,
                                                                      raw_movie=raw_movies[0])
                            if kodi_movie is not None:
                                cls._logger.debug(f'Kodi movie found!')
                            else:
                                cls._logger.debug(f'Kodi movie NOT found')
                        except Exception:
                            cls._logger.exception()

                if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                            and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                        cls._logger.debug_extra_verbose(
                            f'{movie.get_title()}: '
                            f' source: {movie.get_source()}'
                            f' tmdbId: {str(tmdb_id)}'
                            f' MovieId: {movie.get_library_id()}')

            movie.set_discovery_state(MovieField.DISCOVERY_READY_TO_DISPLAY)
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
        tmdb_id: Optional[int] = MovieEntryUtils.get_tmdb_id(movie)
        if tmdb_id is not None:
            tmdb_id = int(tmdb_id)

        movie.get_thumbnail(default='')
        tmdb_detail_info: TMDbMovie = None
        keep_trailer: bool = True
        if isinstance(movie, ITunesMovie):
            Monitor.throw_exception_if_abort_requested()
            rejection_reasons, tmdb_detail_info = TMDbMovieDownloader.get_tmdb_movie(
                movie.get_title(), tmdb_id, movie.get_source(), ignore_failures=True)

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
                movie.get_title(), tmdb_id, movie.get_source(), ignore_failures=True)

            if len(rejection_reasons) > 0:
                keep_trailer = False
                tmdb_detail_info = None
                if (MovieField.REJECTED_ADULT, MovieField.REJECTED_CERTIFICATION,
                        MovieField.REJECTED_FAIL) in rejection_reasons:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'Rejecting TFH movie'
                                                        f' {movie.get_title()} '
                                                        f'due to Certification')

            if tmdb_detail_info is not None:
                if (cls._logger.isEnabledFor(LazyLogger.DISABLED)
                        and cls._logger.is_trace_enabled(Trace.TRACE_DISCOVERY)):
                    from common.debug_utils import Debug
                    Debug.dump_dictionary(movie.get_as_movie_type(),
                                          heading='Dumping TFH movie_info',
                                          log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)

                cls.clone_fields(tmdb_detail_info, movie, MovieField.TFH_CLONE_FIELDS,
                                 set_default=True)

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
        return keep_trailer

    @classmethod
    def clone_fields(cls,
                     source_movie: AbstractMovie,
                     destination_movie: AbstractMovie,
                     fields_to_copy: Dict[str, Any],
                     set_default: bool = False
                     ) -> None:
        """

        :param cls:
        :param source_movie:
        :param destination_movie:
        :param fields_to_copy:
        :param set_default:
        :return:
        """
        try:
            for key, default_value in fields_to_copy.items():
                value = source_movie.get_property(key, default_value)
                destination_movie.set_property(key, value)
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
            start = datetime.datetime.now()
            movie_id = ''
            trailer_path = movie.get_trailer_path()
            is_url = DiskUtils.is_url(trailer_path)
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                cls._logger.debug_verbose(
                    f'{movie.get_title()} {movie.get_trailer_path()} url: {is_url}')

            if not is_url:
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
                return rc

            if trailer_path.startswith('plugin'):
                video_id = re.sub(r'^.*video_?id=', '', trailer_path)
                # plugin://plugin.video.youtube/play/?video_id=
                # DEPRECATED plugin://plugin.video.youtube/?action=play_video&videoid=
                new_path = 'https://youtu.be/' + video_id
                trailer_path = new_path

            if movie.get_source() not in MovieField.LIB_TMDB_ITUNES_TFH_SOURCES:
                return 0

            movie_id = Cache.get_video_id(movie)

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
                cached_trailers = glob.glob(cached_path)
                if len(cached_trailers) != 0:
                    already_normalized = False
                    for cached_trailer in cached_trailers:
                        if 'normalized' in cached_trailer:
                            already_normalized = True
                            if movie.get_normalized_trailer_path() == '':
                                movie.set_normalized_trailer_path(cached_trailer)

                    if not already_normalized:
                        movie.set_cached_trailer(cached_trailers[0])
                        stop = datetime.datetime.now()
                        locate_time = stop - start
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose('time to locate movie:',
                                                            locate_time.seconds, 'path:',
                                                            movie.get_cached_trailer())
                else:
                    #
                    # Not in cache, download
                    #
                    downloaded_trailer: MovieType
                    error_code: int
                    trailer_folder = xbmcvfs.translatePath('special://temp')
                    video_downloader = VideoDownloader()
                    error_code, downloaded_trailer = \
                        video_downloader.get_video(
                            trailer_path, trailer_folder, movie_id,
                            movie.get_title(), movie.get_source(), block=False)
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

                    if downloaded_trailer is not None:
                        download_path = downloaded_trailer[MovieField.TRAILER]
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'Successful Download path: '
                                                            f'{download_path}')

                    """
                       To save json data from downloaded for debugging, uncomment
                       the following.
    
                    temp_file = os.path.join(trailer_folder, str(movie_id) + '.json')
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

        return rc

    @classmethod
    def trailer_permanently_unavailable(cls, movie: AbstractMovie, error_code: int = 0):
        tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
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
                              f'class: {type(movie)}')
            Debug.dump_dictionary(movie.get_as_movie_type(),
                                  log_level=LazyLogger.DISABLED)
        missing_trailers_playlist: Playlist = Playlist.get_playlist(
                Playlist.MISSING_TRAILERS_PLAYLIST, append=False,
                rotate=True)
        missing_trailers_playlist.record_played_trailer(
            movie, use_movie_path=False, msg=msg)


MovieDetail.class_init()
