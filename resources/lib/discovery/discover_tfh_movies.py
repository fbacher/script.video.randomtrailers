# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import datetime
import re
import sys

from backend.backend_constants import TFHConstants
from cache.tfh_cache import TFHCache
from common.constants import Constants, TFH
from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, reraise
from common.imports import *
from common.logger import *
from common.monitor import Monitor
from common.movie import TFHMovie
from common.movie_constants import MovieField, MovieType
from common.settings import Settings

from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.restart_discovery_exception import StopDiscoveryException
from discovery.tfh_movie_data import TFHMovieData
from backend.video_downloader import VideoDownloader
from discovery.utils.parse_tfh import ParseTFH

module_logger: Final[BasicLogger] = BasicLogger.get_module_logger(module_path=__file__)


class DiscoverTFHMovies(BaseDiscoverMovies):
    """
        TFH, like iTunes, provides trailers. Query TFH for trailers
        and manufacture trailer entries for them.
    """
    FORCE_TFH_REDISCOVERY: Final[bool] = False  # For development use

    _singleton_instance = None
    logger: BasicLogger = None

    def __init__(self) -> None:
        """

        """
        clz = DiscoverTFHMovies
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)
        thread_name = 'Disc TFH'
        kwargs = {MovieField.SOURCE: MovieField.TFH_SOURCE}

        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=kwargs)
        self._movie_data = TFHMovieData()
        self._unique_trailer_ids = set()
        self.number_of_trailers_on_site = 0

    def discover_basic_information(self) -> None:
        """
            Starts the discovery thread

        :return:
        """
        clz = DiscoverTFHMovies

        self.start()
        self.setName('Disc TFH')

        # self._parent_trailer_fetcher.start_fetchers(self)

        if clz.logger.isEnabledFor(DEBUG):
            clz.logger.debug(': started')

    def on_settings_changed(self) -> None:
        """
            Rediscover trailers if the changed settings impacts this manager.

            By being here, TMDB discover is currently running. Only restart
            if there is a change.
        """
        clz = DiscoverTFHMovies

        clz.logger.debug('enter')

        if Settings.is_tfh_loading_settings_changed():
            stop_thread = not Settings.is_include_tfh_trailers()
            if stop_thread:
                self.stop_thread()

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return Settings.is_include_tfh_trailers()

    def run(self) -> None:
        """
            Thread run method that is started as a result of running
            discover_basic_information

            This method acts as a wrapper around run_worker. This
            wrapper is able to restart discovery and to handle a few
            details after discovery is complete.

        :return:
        """
        clz = DiscoverTFHMovies

        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.run_worker()
                    used_memory: int = self._movie_data.get_size_of()
                    used_mb: float = float(used_memory) / 1000000.0
                    self.logger.debug(f'movie_data size: {used_memory} MB: {used_mb}')

                    self.wait_until_restart_or_shutdown()
                except StopDiscoveryException:
                    if clz.logger.isEnabledFor(DEBUG):
                        clz.logger.debug('Stopping discovery')
                    # self.destroy()
                    finished = True

            # TODO: Move before wait_until_restart_or_shutdown()

            self.finished_discovery()
            duration = datetime.datetime.now() - start_time
            if clz.logger.isEnabledFor(DEBUG):
                clz.logger.debug(f'Time to discover: {duration.seconds} seconds',
                                 trace=Trace.STATS)

        except AbortException:
            return
        except Exception as e:
            clz.logger.exception('')

    def run_worker(self) -> None:
        """
            Examines the settings that impact the discovery and then
            calls discover_movies which initiates the real work

        :return:
        """
        clz = DiscoverTFHMovies

        try:
            Monitor.throw_exception_if_abort_requested()

            self.discover_movies()
        except (AbortException, StopDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

    def discover_movies(self) -> None:
        """
        :return: (Lower code uses add_to_discovered_movies).
        """

        """
        youtube-dl --ignore-errors --skip-download --get-id 
        https://www.youtube.com/user/trailersfromhell/videos 
        gives ids. Extract movies via id by:
        
        time youtube-dl --ignore-errors --skip-download 
        https://www.youtube.com/watch?v=YbqC0b_jfxQ

        or
        
       youtube-dl --flat-playlist -J --skip-download  
       https://www.youtube.com/user/trailersfromhell/videos 
        
        Returns:
         {
          "_type": "playlist",
              "entries": [
                    {
                      "_type": "url_transparent",
                      "ie_key": "Youtube",
                      "id": "1rPbXlQFJCw",
                      "url": "1rPbXlQFJCw",
                      "title": "Michael Schlesinger on TOUGH GUYS DON'T DANCE",
                      "description": null,
                      "duration": null,
                      "view_count": 1722,
                      "uploader": null
                        }
                    ]
                }
            
            ydl_opts = {
                'forcejson': True,
                'noplaylist': False,
                'extract_flat': True,
                'skip_download': True,
                'logger': tfh_index_logger,
                'sleep_interval': 1,
                'max_sleep_interval': 8,
                #  'playlist_items': trailers_to_download,
                'playlistrandom': True,
                'progress_hooks': [TFHIndexProgressHook(self).status_hook],
                # 'debug_printtraffic': True
            }
                
           or-
            Get JSON for TFH entire trailers in playlist:
            youtube-dl --ignore-errors --skip-download --playlist-random  
                --print-json https://www.youtube.com/user/trailersfromhell/videos >>downloads2
            Each line is a separate JSON "file" for a single movie.
                 
                 -J --dump-single-json: -> dump_single_json
                 --skip-download: -> skip_download
                 
            ydl_opts = {
                    'forcejson': True,
                    'noplaylist': False,
                    # 'extract_flat': 'in_playlist',
                    'skip_download': True,
                    'logger': tfh_index_logger,
                    'sleep_interval': 10,
                    'max_sleep_interval': 240,
                    #  'playlist_items': trailers_to_download,
                    'playlistrandom': True,
                    'progress_hooks': [TFHIndexProgressHook(self).status_hook],
                    # 'debug_printtraffic': True
                           
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
        clz = type(self)

        cache_expiration_time = datetime.timedelta(
            float(Settings.get_tfh_cache_expiration_days()))
        cache_expiration_time = datetime.datetime.now() - cache_expiration_time
        if TFHCache.get_creation_date() > cache_expiration_time:
            cached_trailers = TFHCache.get_cached_movies()
            clz.logger.debug(f'Trailers {len(cached_trailers)} '
                             f'Using tfh cache creation_date:'
                             f' {TFHCache.get_creation_date():%Y-%m-%d %H:%M} '
                             f'expiration: {cache_expiration_time:%Y-%m-%d %H:%M}')
        else:
            cached_trailers: Dict[str, TFHMovie] = {}

        max_trailers = Settings.get_max_number_of_tfh_trailers()
        trailer_list = list(cached_trailers.values())
        del cached_trailers
        DiskUtils.RandomGenerator.shuffle(trailer_list)

        # Limit trailers added by settings, but don't throw away what
        # we have discovered.

        if max_trailers < len(trailer_list):
            del trailer_list[max_trailers:]

        if clz.FORCE_TFH_REDISCOVERY:
            for tfh_trailer in trailer_list:

                # TODO: Remove patch to clean up cache

                try:
                    dirty: bool = Debug.validate_detailed_movie_properties(tfh_trailer,
                                                                           stack_trace=False,
                                                                           force_check=True)
                    if (tfh_trailer.get_title() == tfh_trailer.get_tfh_title()
                            or dirty or tfh_trailer.get_year() == 0):
                        title, year = self.fix_title(tfh_trailer)
                        tfh_trailer.set_title(title)
                        tfh_trailer.set_year(year)
                        tfh_trailer.set_discovery_state(MovieField.NOT_FULLY_DISCOVERED)
                        if dirty:
                            tfh_trailer.set_fanart('')
                            tfh_trailer.set_writers([])
                            tfh_trailer.set_genre_names([])
                            tfh_trailer.set_unique_ids({})

                    # Mostly to protect against cached entries produced by bugs which
                    # are now fixed, reset certain fields to force rediscovery.

                    if clz.FORCE_TFH_REDISCOVERY:
                        tfh_trailer.set_discovery_state(MovieField.NOT_FULLY_DISCOVERED)
                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    clz.logger.exception(e)

        self.add_to_discovered_movies(trailer_list)

        # Entire TFH index is read, so only re-do if the cache was not
        # completely built, or expired

        rc: int = 0
        if (TFHCache.get_creation_date() < cache_expiration_time
                or not TFHCache.is_complete()):
            clz.logger.debug_verbose(f'Rediscovering TFH Index')
            video_downloader = VideoDownloader()
            url = TFHConstants.TFH_TRAILER_PLAYLIST_URL

            # trailer_handler is a callback, so adds entries to the cache

            finished = False
            while not finished:
                rc = video_downloader.get_tfh_index(
                    url, self.trailer_handler, block=True)
                if rc != Constants.HTTP_TOO_MANY_REQUESTS:  # Last entry read failed
                    complete: bool = False
                    if len(TFHCache.get_cached_movies()) > 1400:
                        # Sanity check. Sometimes Youtube gets crankie and doesn't
                        # return any entries.
                        complete = True

                    TFHCache.save_cache(flush=True, complete=complete)
                    finished = True

        clz.logger.debug(f'TFH Discovery Complete rc: {rc}')

    def fix_title(self, tfh_movie: TFHMovie) -> (str, int):
        clz = type(self)

        # This pattern captures the TITLE, not the Reviewer.
        # The TITLE must be mostly ALL CAPS, with some special characters
        # and a lower case 'c' (for names like McCLOUD, with space separators

        # title is a series of words

        # If first pattern fails, then perhaps we have one of the few cases
        # Where only a mixed case title is specified without a reviewer
        # In which case, assume the entire string is a title, but with parenthesis
        # analysis, as will be done for the above as well.


        '''
        TFH Title formats prefix the movie title with the name of the
        reviewer and the date of review (or post to Youtube). Strip this
        out to leave only the Movie Name (but in uppercase). Later, TMDb
        will be consulted to get the correct title and date.
        
        Formats handled by TITLE_RE:
            Reviewer on CAPS TITLE (most common)
            Reviewer on CAPS TITLE (1972)   embedded year
            Reviewer on [0-9]+ CAPS
            Reviewer talks TITLE
            Reviewer talks about TITLE
            Reviewer discusses TITLE
            Reviewer's TITLE
            TITLE
            Reviewer covers TITLE
            Guillermo del Toro habla sobre DEEP RED

        Not handled because of embedded comment
        Fede Alvarez on ACCION MUTANTE (MUTANT ACTION) (delete comment in parens)
        
        Not handled due to mixed case
        Allan Arkush on THE 36th CHAMBER OF THE SHAOLIN  (th suffix, same with rd)
        
        Not handled due to numbers or spelled numbers:
        Adam Rifkin on 16 CANDLES  (Should be SIXTEEN)
        
        Not handled because mixed case
            Reviewer on CAPS TITLE (commentary)   Throw away if not a year
            Reviewer In Conversation With Person

            Joe Dante introduces GREMLINS for the Cinenasty series
            John Landis explains Why We Need Monsters
            John Landis: Trailers From Fail
            TFH Exclusive: A Clip from THE MOVIE ORGY
            Grant Page's Pet Cat
            Alias St. Nick
            Allan Arkush on 8 1/2
            Hell-o
            DAUGHTER OF HORROR
            Numbers can be in number or word form
        
                           Eli Roth on EXCORCIST II: THE HERETIC
        '''
        SEPARATORS = [
            ' on ',
            ' talks about ',
            ' talks ',
            ' discusses ',
            ' covers ',
            ' '
        ]

        tfh_title = tfh_movie.get_tfh_title()
        clz.logger.debug(f'tfh_title: {tfh_title}')

        SPECIAL_CHARACTERS = 'c.!?#&@,:$ ()\'"~-'
        movie_title: str = ''
        saved_title: str = ''
        for ch in tfh_title:
            if ch.isupper() or ch.isdigit() or ch in SPECIAL_CHARACTERS:
                movie_title += ch
            else:
                if len(movie_title) > len(saved_title):
                    saved_title = movie_title
                movie_title = ''

        if len(movie_title) > len(saved_title):
            saved_title = movie_title
        movie_title = ''

        num_open_parens = saved_title.count('(')
        num_close_parens = saved_title.count(')')
        while num_open_parens > num_close_parens:
            idx = saved_title.rfind('(')
            saved_title = saved_title[:idx]
            num_open_parens -= 1

        movie_title = saved_title.strip()
        clz.logger.debug(f'tfh_title: {tfh_title} saved_title: {movie_title}')

        '''


        # First, isolate the longest segment with only valid characters in
        # it (roughly segment without lower-case characters).

        title_segments = re.split(TFH.TITLE_PASS_1_RE, tfh_title)
        clz.logger.debug(f'#segments: {len(title_segments)}')

        # segment 0 should be original title

        seg_num = 0
        for segment in title_segments:
            clz.logger.debug(f'seg: {seg_num} segment: {segment}')
            seg_num += 1

        title = title_segments[1]
        '''

        title_segments = re.split(TFH.PARENTHESIS_RE, movie_title)
        seg_num = 0
        year: int = 0
        constructed_title = ''
        separator: str = ''
        for segment in title_segments:
            segment = segment.strip()
            if re.match(TFH.YEAR_RE, segment):
                year = int(segment[1:-1])
            else:
                constructed_title += separator + segment
                separator = ' '

            clz.logger.debug(f'seg: {seg_num} segment: {segment} year: {year}')
            seg_num += 1

        clz.logger.debug(f'constructed_title: {constructed_title}')
        movie_title = constructed_title

        return movie_title, year

    def trailer_handler(self, tfh_trailer: MovieType) -> None:
        """

        :param tfh_trailer:
        :return:
        """
        clz = DiscoverTFHMovies

        Monitor.throw_exception_if_abort_requested()

        """
        
            Handle entry for one movie
            
                   "_type": "url_transparent",
                  "ie_key": "Youtube",
                  "id": "1rPbXlQFJCw",
                  "url": "1rPbXlQFJCw",
                  "title": "Michael Schlesinger on TOUGH GUYS DON'T DANCE",
                  "description": null,
                  "duration": null,
                  "view_count": 1722,
                  "uploader": null
                    }
            
        """

        parser = ParseTFH(tfh_trailer, -1)
        tfh_id: str = parser.parse_id()

        if tfh_id not in self._unique_trailer_ids:
            self._unique_trailer_ids.add(tfh_id)

            # The movie's title is embedded within the TFH title
            # The title will be extracted from it, but save the original

            title: str = parser.parse_title()
            parser.parse_tfh_title()
            parser.parse_trailer_type()
            parser.parse_trailer_path()
            parser.parse_discovery_state()

            # The following are most likely all junk and set to default
            # values.

            # Bogus value of unrated. Replace with value from TMDb, if
            # movie can be found there.

            parser.parse_certification()
            parser.parse_thumbnail()
            parser.parse_plot()
            parser.parse_rating()
            parser.parse_year()
            parser.parse_runtime()

            #  TODO: parse fields which optionally come from TMDb discovery

            movie: TFHMovie = parser.get_movie()
            title, year = self.fix_title(movie)
            movie.set_title(title)
            movie.set_year(year)

            # if (Settings.get_max_number_of_tfh_trailers()
            #        <= len(TFHCache.get_cached_trailers())):
            #    return True
            # else:
            TFHCache.add_movie(movie, flush=False)
            self.add_to_discovered_movies(movie)
            self.number_of_trailers_on_site += 1
            return

    def needs_restart(self) -> bool:
        """
            A restart is needed when settings that impact our results have
            changed.

            :returns: True if settings have changed requiring restart
                      False if relevant settings have changed or if it should
                      be allowed to die without restart
        """
        clz = type(self)
        clz.logger.debug('enter')

        restart_needed = False
        if Settings.is_include_tfh_trailers():
            restart_needed: bool = Settings.is_tfh_loading_settings_changed()

        return restart_needed
