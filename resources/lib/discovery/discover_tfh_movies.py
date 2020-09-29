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
from common.exceptions import AbortException
from common.imports import *
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor
from common.rating import WorldCertifications
from common.settings import Settings

from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.tfh_movie_data import TFHMovieData
from backend.yd_stream_extractor_proxy import YDStreamExtractorProxy

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
        local_class = DiscoverTFHMovies
        if local_class.logger is None:
            local_class.logger = module_logger.getChild(local_class.__name__)
        thread_name = local_class.__name__
        kwargs = {Movie.SOURCE: Movie.TMDB_SOURCE}

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=kwargs)
        self._movie_data = TFHMovieData()
        self._unique_trailer_ids = set()

    def discover_basic_information(self):
        # type: () -> None
        """
            Starts the discovery thread

        :return: # type: None
        """
        local_class = DiscoverTFHMovies

        self.start()
        # self._trailer_fetcher.start_fetchers(self)

        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug(': started')

    def on_settings_changed(self):
        # type: () -> None
        """
            Rediscover trailers if the changed settings impacts this manager.

            By being here, TMDB discover is currently running. Only restart
            if there is a change.
        """
        local_class = DiscoverTFHMovies

        local_class.logger.enter()

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
        local_class = DiscoverTFHMovies

        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    self.wait_until_restart_or_shutdown()
                except (RestartDiscoveryException):
                    # Restart discovery
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                        local_class.logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.is_include_tfh_trailers():
                        finished = True
                        self.remove_self()

            self.finished_discovery()
            duration = datetime.datetime.now() - start_time
            if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                local_class.logger.debug('Time to discover:', duration.seconds, ' seconds',
                                   trace=Trace.STATS)

        except AbortException:
            return
        except Exception as e:
            local_class.logger.exception('')

    def run_worker(self):
        # type: () -> None
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return: #type: None
        """
        local_class = DiscoverTFHMovies

        try:
            Monitor.throw_exception_if_abort_requested()

            self.discover_movies()
        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')

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
        local_class = DiscoverTFHMovies

        cached_trailers = TFHCache.get_cached_trailers()
        max_trailers = Settings.get_max_number_of_tfh_trailers()
        trailer_list = list(cached_trailers.values())

        # Limit trailers added by settings, but don't throw away what
        # we have discovered.

        if max_trailers < len(trailer_list):
            del trailer_list[max_trailers:]
        self.add_to_discovered_trailers(trailer_list)

        if len(trailer_list) < max_trailers:
            # Get the entire index again and replace the cache.
            # This can take perhaps 20 minutes, which is why we seed the
            # fetcher with any previously cached data. This will fix itself
            # the next time the cache is read.

            youtube_data_stream_extractor_proxy = YDStreamExtractorProxy()
            url = 'https://www.youtube.com/user/trailersfromhell/videos'

            # trailer_handler is a callback, so adds entries to the cache

            finished = False
            while not finished:
                wait = youtube_data_stream_extractor_proxy.get_youtube_wait_seconds()
                if wait > 0:
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        local_class.logger.debug_verbose(f'Waiting {wait} seconds) due to '
                                                 'TOO MANY REQUESTS')
                    Monitor.throw_exception_if_abort_requested(timeout=float(wait))
                rc = youtube_data_stream_extractor_proxy.get_tfh_index(
                    url, self.trailer_handler)
                if rc == 0: # All Entries passed
                    pass
                if rc != 429:  # Last entry read failed
                    finished = True

                # In case any were read. Note, any read already added to
                # discovered_trailers

                TFHCache.save_cache(flush=True)

    def trailer_handler(self, json_text):
        #  type: (str) -> bool
        """

        :param json_text:
        :return:
        """
        local_class = DiscoverTFHMovies

        Monitor.throw_exception_if_abort_requested()
        try:
            tfh_trailer = json.loads(json_text)
        except Exception as e:
            local_class.logger.exception(e)
            local_class.logger.warning('Offending json:', json_text)
            return False

        trailer_id = tfh_trailer['id']
        if trailer_id not in self._unique_trailer_ids:
            self._unique_trailer_ids.add(trailer_id)

            # TFH trailers are titled: <reviewer> on <MOVIE_TITLE_ALL_CAPS>
            # Here we can try to get just the movie title and then look up
            # a likely match in TMDB (with date, and other info).

            # TFH may not like changing the title, however.

            title = tfh_trailer['title']
            #title_segments = title.split(' on ')
            #real_title_index = len(title_segments) - 1
            #movie_title = title_segments[real_title_index]
            movie_title = title
            trailer_url = 'https://youtu.be/' + trailer_id
            upload_date = tfh_trailer['upload_date']  # 20120910
            year = upload_date[0:4]
            year = int(year)
            thumbnail = tfh_trailer['thumbnail']
            original_language = ''
            description = tfh_trailer['description']
            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            unrated_id = certifications.get_unrated_certification().get_preferred_id()
            trailer_entry = {Movie.SOURCE: Movie.TFH_SOURCE,
                             Movie.TFH_ID: trailer_id,
                             Movie.TITLE: movie_title,
                             Movie.YEAR: year,
                             Movie.ORIGINAL_LANGUAGE: original_language,
                             Movie.TRAILER: trailer_url,
                             Movie.PLOT: description,
                             Movie.THUMBNAIL: thumbnail,
                             Movie.DISCOVERY_STATE: Movie.NOT_FULLY_DISCOVERED,
                             Movie.MPAA: unrated_id,
                             Movie.ADULT: False,
                             Movie.RATING: 0.0
                             }
            # if (Settings.get_max_number_of_tfh_trailers()
            #        <= len(TFHCache.get_cached_trailers())):
            #    return True
            # else:
            TFHCache.add_trailer(trailer_entry, flush=False)
            cached_trailers = TFHCache.get_cached_trailers()
            max_trailers = Settings.get_max_number_of_tfh_trailers()
            if len(cached_trailers) <= max_trailers:
                self.add_to_discovered_trailers(trailer_entry)
            return False
