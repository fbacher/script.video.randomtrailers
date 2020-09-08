# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

from common.imports import *

import sys
import datetime
import json
import xbmc

from cache.tfh_cache import (TFHCache)
from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import (LazyLogger, Trace)
from common.settings import Settings

from discovery.restart_discovery_exception import RestartDiscoveryException
from common.rating import Rating
from discovery.base_discover_movies import BaseDiscoverMovies
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
        if type(self).logger is None:
            type(self).logger = module_logger.getChild(type(self).__name__)
        thread_name = type(self).__name__
        kwargs = {}
        kwargs[Movie.SOURCE] = Movie.TMDB_SOURCE

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = TFHMovieData()
        self._unique_trailer_ids = set()

    @classmethod
    def get_instance(cls):
        # type: () -> DiscoverTFHMovies
        """

        :return:
        """
        return super(DiscoverTFHMovies, cls).get_instance()

    def discover_basic_information(self):
        # type: () -> None
        """
            Starts the discovery thread

        :return: # type: None
        """
        self.start()
        # self._trailer_fetcher.start_fetchers(self)

        if type(self).logger.isEnabledFor(LazyLogger.DEBUG):
            type(self).logger.debug(': started')

    def on_settings_changed(self):
        # type: () -> None
        """
            Rediscover trailers if the changed settings impacts this manager.

            By being here, TMDB discover is currently running. Only restart
            if there is a change.
        """
        type(self).logger.enter()

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
        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    self.wait_until_restart_or_shutdown()
                except (RestartDiscoveryException):
                    # Restart discovery
                    if type(self).logger.isEnabledFor(LazyLogger.DEBUG):
                        type(self).logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.is_include_tfh_trailers():
                        finished = True
                        self.remove_self()

            self.finished_discovery()
            duration = datetime.datetime.now() - start_time
            if type(self).logger.isEnabledFor(LazyLogger.DEBUG):
                type(self).logger.debug('Time to discover:', duration.seconds, ' seconds',
                                   trace=Trace.STATS)

        except AbortException:
            return
        except Exception as e:
            type(self).logger.exception('')

    def run_worker(self):
        # type: () -> None
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return: #type: None
        """
        try:
            Monitor.throw_exception_if_abort_requested()

            self.discover_movies()
        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            type(self).logger.exception('')

    def discover_movies(self):
        # type: () -> None
        """
            Calls configure_search_parameters as many times as appropriate to
            discover movies based on the filters specified by the settings.

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

        download_info = None

        cache_complete = TFHCache.load_trailer_cache()
        cached_trailers = TFHCache.get_cached_trailers()
        max_trailers = Settings.get_max_number_of_tfh_trailers()
        if len(cached_trailers) > max_trailers:
            del cached_trailers[max_trailers:]
            cache_complete = True
            TFHCache.save_trailers_to_cache(
                None, flush=True, cache_complete=True)
        self.add_to_discovered_trailers(cached_trailers)

        if not cache_complete:
            # Recreates entire cache

            youtube_data_stream_extractor_proxy = \
                YDStreamExtractorProxy.get_instance()
            trailer_folder = xbmc.translatePath(
                'special://temp')
            url = "https://www.youtube.com/user/trailersfromhell/videos"
            success = youtube_data_stream_extractor_proxy.get_tfh_index(
                url, self.trailer_handler)
            if success:
                TFHCache.save_trailers_to_cache(
                    None, flush=True, cache_complete=True)

    def trailer_handler(self, json_text):
        #  type: (str) -> bool
        """

        :param json_text:
        :return:
        """

        tfh_trailer = json.loads(json_text)
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
            trailer_entry = {Movie.SOURCE: Movie.TFH_SOURCE,
                             Movie.TFH_ID: trailer_id,
                             Movie.TITLE: movie_title,
                             Movie.YEAR: year,
                             Movie.ORIGINAL_LANGUAGE: original_language,
                             Movie.TRAILER: trailer_url,
                             Movie.PLOT: description,
                             Movie.THUMBNAIL: thumbnail,
                             Movie.DISCOVERY_STATE: Movie.NOT_FULLY_DISCOVERED,
                             Movie.MPAA: Rating.RATING_NR,
                             Movie.ADULT: False
                             }
            if Settings.get_max_number_of_tfh_trailers() <= len(TFHCache.get_cached_trailers()):
                return True
            else:
                TFHCache.save_trailers_to_cache(
                    trailer_entry, flush=False, cache_complete=False)
                self.add_to_discovered_trailers(trailer_entry)
                return False
