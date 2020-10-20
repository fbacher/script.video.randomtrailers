# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import sys
import datetime
import json

import xbmcvfs

from cache.tfh_cache import (TFHCache)
from common.constants import Constants, Movie
from common.disk_utils import DiskUtils
from common.exceptions import AbortException
from common.imports import *
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor
from common.rating import WorldCertifications
from common.settings import Settings

from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.tfh_movie_data import TFHMovieData
from backend.video_downloader import VideoDownloader

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection Annotator
class DiscoverTFHMovies(BaseDiscoverMovies):
    """
        TMDB, like iTunes, provides trailers. Query TMDB for trailers
        and manufacture trailer entries for them.
    """
    _singleton_instance = None
    logger: LazyLogger = None

    def __init__(self):
        # type: () -> None
        """

        """
        clz = DiscoverTFHMovies
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)
        thread_name = 'Disc TFH'
        kwargs = {Movie.SOURCE: Movie.TMDB_SOURCE}

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=kwargs)
        self._movie_data = TFHMovieData()
        self._unique_trailer_ids = set()
        self.number_of_trailers_on_site = 0

    def discover_basic_information(self):
        # type: () -> None
        """
            Starts the discovery thread

        :return: # type: None
        """
        clz = DiscoverTFHMovies

        self.start()
        # self._trailer_fetcher.start_fetchers(self)

        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug(': started')

    def on_settings_changed(self):
        # type: () -> None
        """
            Rediscover trailers if the changed settings impacts this manager.

            By being here, TMDB discover is currently running. Only restart
            if there is a change.
        """
        clz = DiscoverTFHMovies

        clz.logger.enter()

        if Settings.is_tfh_loading_settings_changed():
            stop_thread = not Settings.is_include_tfh_trailers()
            self.restart_discovery(stop_thread)

    def run(self):
        # type: () -> None
        """
            Thread run method that is started as a result of running
            discover_basic_information

            This method acts as a wrapper around run_worker. This
            wrapper is able to restart discovery and to handle a few
            details after discovery is complete.

        :return: # type: None
        """
        clz = DiscoverTFHMovies

        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    self.wait_until_restart_or_shutdown()
                except (RestartDiscoveryException):
                    # Restart discovery
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.is_include_tfh_trailers():
                        finished = True
                        self.remove_self()

            self.finished_discovery()
            duration = datetime.datetime.now() - start_time
            if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                clz.logger.debug('Time to discover:', duration.seconds, ' seconds',
                                 trace=Trace.STATS)

        except AbortException:
            return
        except Exception as e:
            clz.logger.exception('')

    def run_worker(self):
        # type: () -> None
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return: #type: None
        """
        clz = DiscoverTFHMovies

        try:
            Monitor.throw_exception_if_abort_requested()

            self.discover_movies()
        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

    def discover_movies(self):
        # type: () -> None
        """
        :return: # type: None (Lower code uses add_to_discovered_trailers).
        """

        """
        youtube-dl --ignore-errors --skip-download --get-id https://www.youtube.com/user/trailersfromhell/videos 
        gives ids. Extract movies via id by:
        
        time youtube-dl --ignore-errors --skip-download https://www.youtube.com/watch?v=YbqC0b_jfxQ

        or-
        Get JSON for TFH entire trailers in playlist:
        youtube-dl --ignore-errors --skip-download --playlist-random  
            --print-json https://www.youtube.com/user/trailersfromhell/videos >>downloads2
        Each line is a separate JSON "file" for a single trailer.
        
        From JSON youtube download for a single trailer:
          "license": null,
           "title": "Allan Arkush on SMALL CHANGE",
           "thumbnail": "https://i.ytimg.com/vi/YbqC0b_jfxQ/maxresdefault.jpg",
           "description": "François Truffaut followed up the tragic The Story of Adele H 
        with this sunny comedy about childhood innocence and resiliency (to show just 
        how resilient, one baby falls out a window and merely bounces harmlessly off
        the bushes below). Truffaut worked with a stripped down script to allow for 
        more improvisation from his young cast. The rosy cinematography was by 
        Pierre-William Glenn (Day for Night).\n\nAs always, you can find more
        commentary, more reviews, more podcasts, and more deep-dives into the films
        you don't know you love yet over on the Trailers From Hell 
        mothership:\n\nhttp://www.trailersfromhell.com\n\n
        What's that podcast, you ask? Why, it's THE MOVIES THAT MADE ME, where 
        you can join Oscar-nominated screenwriter Josh Olson and TFH Fearless 
        Leader Joe Dante in conversation with filmmakers, comedians, and 
        all-around interesting people about the movies that made them who they are. 
        Check it out now, and please subscribe wherever podcasts can be found.
        \n\nApple Podcasts:
         https://podcasts.apple.com/us/podcast/the-movies-that-made-me/id1412094313\n
         Spotify: http://spotify.trailersfromhell.com\n
         Libsyn: http://podcast.trailersfromhell.com\n
         Google Play: http://googleplay.trailersfromhell.com\nRSS: http://goo.gl/3faeG7",
        """
        clz = DiscoverTFHMovies

        cached_trailers = TFHCache.get_cached_trailers()
        max_trailers = Settings.get_max_number_of_tfh_trailers()
        trailer_list = list(cached_trailers.values())
        DiskUtils.RandomGenerator.shuffle((trailer_list))

        # Limit trailers added by settings, but don't throw away what
        # we have discovered.

        if max_trailers < len(trailer_list):
            del trailer_list[max_trailers:]
        self.add_to_discovered_trailers(trailer_list)

        cache_expiration_time = datetime.timedelta(
            float(Settings.get_tfh_cache_expiration_days()))
        cache_expiration_time = datetime.datetime.now() - cache_expiration_time
        if (len(trailer_list) < max_trailers
                or TFHCache.get_creation_date() < cache_expiration_time):
            # Get the entire index again and replace the cache.
            # This can take perhaps 20 minutes, which is why we seed the
            # fetcher with any previously cached data. This will fix itself
            # the next time the cache is read.

            youtube_data_stream_extractor_proxy = VideoDownloader()
            url = 'https://www.youtube.com/user/trailersfromhell/videos'

            # trailer_handler is a callback, so adds entries to the cache

            # Create initial range of trailers to request. Can be adjusted as
            # we go.

            # Put first trailer at end, since we process from the end.

            finished = False
            actual_trailer_count = None
            while not finished:
                rc = youtube_data_stream_extractor_proxy.get_tfh_index(
                    url, self.trailer_handler, block=True)
                if rc == 0:  # All Entries passed
                    pass
                if rc != 429:  # Last entry read failed
                    finished = True

                # In case any were read. Note, any read already added to
                # discovered_trailers

                complete = False

                # Getting all trailer urls at once.

                # if actual_trailer_count is None:
                #     attempts = 0
                #     while self.number_of_trailers_on_site == 0 and attempts < 10:
                #         attempts += 1
                #         Monitor.throw_exception_if_abort_requested(0.5)
                #     if self.number_of_trailers_on_site == 0:
                #         if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                #             clz.logger.debug(
                #                 'Could not determine number of Trailers From Hell')
                #     trailers_to_download = list(
                #         range(1, self.number_of_trailers_on_site))
                #     DiskUtils.RandomGenerator.shuffle((trailers_to_download))
                flush = False
                if True:  # len(trailers_to_download) == 0:
                    finished = True
                    complete = True
                    flush = True
                TFHCache.set_creation_date()
                TFHCache.save_cache(flush=flush, complete=complete)

    def trailer_handler(self, tfh_trailer: Dict[str, Any]) -> bool:
        """

        :param tfh_trailer:
        :return:
        """
        clz = DiscoverTFHMovies

        Monitor.throw_exception_if_abort_requested()

        trailer_id = tfh_trailer[Movie.YOUTUBE_ID]

        if trailer_id not in self._unique_trailer_ids:
            self._unique_trailer_ids.add(trailer_id)

            # TFH trailers are titled: <reviewer> on <MOVIE_TITLE_ALL_CAPS>
            # Here we can try to get just the movie title and then look up
            # a likely match in TMDB (with date, and other info).

            # TFH may not like changing the title, however.

            tfh_trailer[Movie.SOURCE] = Movie.TFH_SOURCE
            tfh_trailer[Movie.TFH_ID] = tfh_trailer[Movie.YOUTUBE_ID]
            del tfh_trailer[Movie.YOUTUBE_ID]
            trailers_in_playlist = tfh_trailer[Movie.YOUTUBE_TRAILERS_IN_PLAYLIST]

            # if (Settings.get_max_number_of_tfh_trailers()
            #        <= len(TFHCache.get_cached_trailers())):
            #    return True
            # else:
            TFHCache.add_trailer(
                tfh_trailer, total=trailers_in_playlist, flush=False)
            cached_trailers = TFHCache.get_cached_trailers()
            max_trailers = Settings.get_max_number_of_tfh_trailers()
            self.add_to_discovered_trailers(tfh_trailer)
            self.number_of_trailers_on_site = trailers_in_playlist
            return False
