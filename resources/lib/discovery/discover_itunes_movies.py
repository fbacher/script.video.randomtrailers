# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: fbacher
"""

import datetime
import simplejson as json
import re
import sys

# from cache.itunes_cache_index import ItunesCacheIndex
from backend.backend_constants import APPLE_URL_PREFIX
from cache.base_cache import BaseCache
from backend.backend_constants import iTunes
from common.disk_utils import DiskUtils
from common.debug_utils import Debug
from common.exceptions import AbortException, reraise
from common.imports import *
from common.monitor import Monitor
from common.movie import ITunesMovie, RawMovie
from common.movie_constants import MovieField
from common.logger import LazyLogger, Trace
from common.settings import Settings
from common.utils import Utils
from discovery.utils.itunes_filter import ITunesFilter

from discovery.restart_discovery_exception import StopDiscoveryException
from backend.genreutils import GenreUtils
from backend.json_utils_basic import JsonUtilsBasic, JsonReturnCode, Result
from backend.video_downloader import VideoDownloader

from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.itunes_movie_data import ItunesMovieData
from discovery.utils.parse_itunes import ParseITunes

STRIP_TZ_PATTERN: Final[Pattern] = re.compile(' .[0-9]{4}$')
EPOCH_TIME: Final[datetime.datetime] = datetime.datetime(1970, 1, 1, 0, 1)

module_logger: Final[LazyLogger] = LazyLogger.get_addon_module_logger(file_path=__file__)


class DiscoverItunesMovies(BaseDiscoverMovies):
    """

    """
    logger: ClassVar[LazyLogger] = None

    def __init__(self) -> None:
        """

        """
        clz = DiscoverItunesMovies
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)
        thread_name: Final[str] = 'Discover iTunes'
        kwargs = {
                 MovieField.SOURCE: MovieField.ITUNES_SOURCE
                 }
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=kwargs)
        self._movie_data = ItunesMovieData()
        self._selected_genre_ids: List[str] = []
        self._excluded_genre_ids: List[str] = []

        # Early checking of for duplicates before we query external databases
        self._duplicate_check: Set = set()

    def discover_basic_information(self) -> None:
        """

        :return:
        """
        clz = type(self)
        self.start()

    def on_settings_changed(self) -> None:
        """
            Rediscover trailers if the changed settings impacts this manager.
        """
        clz = type(self)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.enter()

        try:
            if Settings.is_itunes_loading_settings_changed():
                stop_thread = not Settings.is_include_itunes_trailers()
                if stop_thread:
                    self.stop_thread()
                self._duplicate_check.clear()

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return Settings.is_include_itunes_trailers()

    def is_duplicate(self, key):
        clz = type(self)
        result: bool = False
        if key in self._duplicate_check:
            result = True
        else:
            self._duplicate_check.add(key)

        return result

    def run(self) -> None:
        """

        :return:
        """
        clz = type(self)
        start_time: datetime.datetime = datetime.datetime.now()
        try:
            finished: bool = False
            while not finished:
                try:
                    self.run_worker()

                    # Normal return, finished discovery

                    self.finished_discovery()
                    duration: datetime.timedelta = datetime.datetime.now() - start_time
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG) and Trace.is_enabled(
                            Trace.STATS):
                        clz.logger.debug(f'Time to discover: {duration.seconds} seconds',
                                         trace=Trace.STATS)

                        used_memory: int = self._movie_data.get_size_of()
                        used_mb: float = float(used_memory) / 1000000.0
                        self.logger.debug(f'movie_data size: {used_memory} MB: {used_mb}')
                    finished = True

                    # self.wait_until_restart_or_shutdown()
                except StopDiscoveryException:
                    # Stopping discovery, probably settings changed

                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz.logger.debug_verbose('Stopping discovery')
                    # self.destroy()
                    # GarbageCollector.add_thread(self)
                    finished = True

        except AbortException:
            return  # Just exit thread
        except Exception:
            clz.logger.exception('')

    '''
    def send_cached_movies_to_discovery(self) -> None:
        """

        :return:
        """
        clz = DiscoverItunesMovies
        try:
            # Send any cached TMDB trailers to the discovered list first,
            # since they require least processing.

            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose(
                    "Sending cached TMDB trailers to discovered list")

            tmdb_trailer_ids: Set[int] = \
                ItunesCacheIndex.get_itunes_trailer_ids().copy()
            movies = []
            for tmdb_id in tmdb_trailer_ids:
                cached_movie = Cache.read_tmdb_cache_json(tmdb_id, Movie.TMDB_SOURCE,
                                                          error_msg='TMDB movie '
                                                                    'not found')
                if cached_movie is not None:
                    year = cached_movie['release_date'][:-6]
                    year = int(year)
                    movie_entry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                   Movie.SOURCE: Movie.TMDB_SOURCE,
                                   Movie.TITLE: cached_movie[Movie.TITLE],
                                   Movie.YEAR: year,
                                   Movie.ORIGINAL_LANGUAGE:
                                       cached_movie[Movie.ORIGINAL_LANGUAGE]}
                    MovieEntryUtils.set_tmdb_id(movie_entry, tmdb_id)
                    if self.pre_filter_movie(movie_entry):
                        movies.append(movie_entry)

            # Don't add found trailers to unprocessed_movies

            self.add_to_discovered_movies(movies)
            #
            # Give fetcher time to load ready_to_play list. The next add
            # will likely shuffle and mix these up with some that will take
            # longer to process.
            #
            if len(movies) > 0:
                Monitor.throw_exception_if_abort_requested(timeout=5.0)
        except Exception as e:
            clz.logger.exception('')

        try:
            # Send any unprocessed TMDB trailers to the discovered list
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose(
                    "Sending unprocessed movies to discovered list")

            discovery_complete_movies: List[MovieType] = []
            discovery_needed_movies: List[MovieType] = []
            unprocessed_movies = ItunesCacheIndex.get_unprocessed_movies()
            for movie in unprocessed_movies.values():
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    if Movie.MPAA not in movie or movie[Movie.MPAA] == '':
                        cert = movie.get(Movie.MPAA, 'none')
                        clz.logger.debug_extra_verbose('No certification. Title:',
                                                       movie[Movie.TITLE],
                                                       'year:',
                                                       movie.get(
                                                           Movie.YEAR),
                                                       'certification:', cert,
                                                       'trailer:',
                                                       movie.get(
                                                           Movie.TRAILER),
                                                       trace=Trace.TRACE_DISCOVERY)
                        movie[Movie.MPAA] = ''

                discovery_state = movie.get(Movie.DISCOVERY_STATE,
                                            Movie.NOT_FULLY_DISCOVERED)
                if (discovery_state < Movie.DISCOVERY_NEARLY_COMPLETE
                        and self.pre_filter_movie(movie)):
                    discovery_needed_movies.append(movie)
                if (discovery_state >= Movie.DISCOVERY_NEARLY_COMPLETE
                        and self.pre_filter_movie(movie)):
                    discovery_complete_movies.append(movie)
                    tmdb_id = MovieEntryUtils.get_tmdb_id(movie)
                    ItunesCacheIndex.remove_unprocessed_movies(tmdb_id)

            # Add the fully discovered movies first, this should be rare,
            # but might feed a few that can be displayed soon first.
            # There will likely be a shuffle on each call, so they will be
            # blended together anyway.

            self.add_to_discovered_movies(discovery_complete_movies)
            if len(discovery_complete_movies) > 0:
                Monitor.throw_exception_if_abort_requested(timeout=5.0)
            self.add_to_discovered_movies(discovery_needed_movies)

        except Exception as e:
            clz.logger.exception('')
    '''

    def run_worker(self) -> None:
        """

        :return:
        """
        clz = type(self)
        Monitor.throw_exception_if_abort_requested()

        self._selected_genre_ids: List[str] = []
        self._excluded_genre_ids: List[str] = []
        if Settings.get_filter_genres():
            self._selected_genre_ids = GenreUtils.get_external_genre_ids(
                GenreUtils.ITUNES_DATABASE, exclude=False)
            self._excluded_genre_ids = GenreUtils.get_external_genre_ids(
                GenreUtils.ITUNES_DATABASE, exclude=True)

        show_only_itunes_trailers_of_this_type = \
            Settings.get_include_itunes_trailer_type()
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose('iTunesTrailer_type:',
                                           show_only_itunes_trailers_of_this_type)

        # Get index of all current trailers for given type

        json_url = iTunes.get_url_for_trailer_type(
            show_only_itunes_trailers_of_this_type)
        json_url = f'{APPLE_URL_PREFIX}{json_url}'
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(f'iTunes json_url {json_url}')
        attempts: int = 0
        parsed_content: Dict[str, Any] = None
        timeout: int = 1 * 60  # one minute
        finished: bool = False
        while not finished and attempts < 60 and parsed_content is None:
            result: Result = JsonUtilsBasic.get_json(json_url)
            attempts += 1
            timeout = timeout * 2
            # Limit to 30 minutes. That is a long time
            if timeout > 30 * 60:
                timeout = 30 * 60

            status_code: JsonReturnCode = result.get_rc()
            if status_code == JsonReturnCode.OK and parsed_content is not None:
                finished = True

            if status_code == JsonReturnCode.FAILURE_NO_RETRY:
                clz.logger.debug_extra_verbose(f'iTunes call'
                                               f' FAILURE_NO_RETRY')
                finished = True

            if status_code == JsonReturnCode.UNKNOWN_ERROR:
                clz.logger.debug_extra_verbose(f'iTunes call'
                                               f' UNKNOWN_ERROR')
                finished = True

            if status_code == JsonReturnCode.RETRY:
                clz.logger.debug_extra_verbose(f'iTunes call failed RETRY')
                Monitor.throw_exception_if_abort_requested(timeout=float(timeout))
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug(f'Itunes read attempt {attempts}'
                                     f' failed waiting {timeout} seconds')

            parsed_content = result.get_data()
            if parsed_content is None:
                finished = True

        if parsed_content is None:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                clz.logger.debug(f'Failed to get trailers from iTunes.'
                                 f' giving up.')
            finished = True
            return

        DiskUtils.RandomGenerator.shuffle(parsed_content)
        # Debug.dump_json(text='parsed_content', data=parsed_content)

        """
        title":"Alita: Battle Angel",
        "releasedate":"Thu, 14 Feb 2019 00:00:00 -0800",
        "studio":"20th Century Fox",
        "poster":"http://trailers.apple.com/trailers/fox/alita-battle-angel/images
        /poster.jpg",
        "poster_2x":"http://trailers.apple.com/trailers/fox/alita-battle-angel/images
        /poster_2x.jpg",
        "location":"/trailers/fox/alita-battle-angel/",
        "rating":"Not yet rated",
        "genre":["Action and Adventure",
                "Science Fiction"],
        "directors":
                "Robert Rodriguez",
        "actors":["Rosa Salazar",
                "Christoph Waltz",
                "Jennifer Connelly",
                "Mahershala Ali",
                "Ed Skrein",
                "Jackie Earle Haley",
                "Keean Johnson"],
        "trailers":[
                {"postdate":"Tue, 13 Nov 2018 00:00:00 -0800",
                "url":"/trailers/fox/alita-battle-angel/",
                "type":"Trailer 3",
                "exclusive":false,
                "hd":true},
                 {"postdate":"Mon, 23 Jul 2018 00:00:00 -0700",
                 "url":"/trailers/fox/alita-battle-angel/","type":"Trailer 2",
                 "exclusive":false,"hd":true},
                 {"postdate":"Fri, 08 Dec 2017 00:00:00 -0800",
                 "url":"/trailers/fox/alita-battle-angel/","type":"Trailer",
                 "exclusive":false,"hd":true}]
        },
        """
        #
        # Create Kodi movie entries from what iTunes has given us.
        #
        # if clz.logger.isEnabledFor(LazyLogger.DEBUG):
        #   clz.logger.debug('Itunes parsed_content type:',
        #                type(parsed_content).__name__)

        itunes_movie: Dict[str, Any]
        for itunes_movie in parsed_content:
            try:
                Monitor.throw_exception_if_abort_requested()
                itunes_parser: ParseITunes = ParseITunes(itunes_movie)
                movie_id: str = itunes_parser.parse_itunes_id()
                title: str = itunes_parser.parse_title()

                raw_movie = RawMovie(movie_info=itunes_movie,
                                     source=MovieField.ITUNES_SOURCE)
                raw_movie.set_id(movie_id)
                raw_movie.set_property(MovieField.TITLE, title)
                BaseCache.write_cache_json(raw_movie)

                release_date: datetime.date = itunes_parser.parse_release_date()
                year: int = itunes_parser.parse_year()

                if clz.logger.isEnabledFor(LazyLogger.DISABLED):
                    clz.logger.debug_extra_verbose('value: ', itunes_movie)
                # If we have seen this before, then skip it.

                if title is None or self.is_duplicate(title):
                    continue

                studios: List[str] = itunes_parser.parse_studios()
                fanart: str = itunes_parser.parse_fanart()

                # poster_2x = itunes_movie.get('poster_2x', '')
                # clz.logger.debug('poster_2x: ', poster_2x)

                # Normalize rating
                # We expect the attribute to be named 'certification', not 'rating'

                certification_id: str = itunes_parser.parse_certification()
                genres: List[str] = itunes_parser.parse_genre_names()
                # fake_rating: float = itunes_parser.parse_rating()
                directors: List[str] = itunes_parser.parse_directors()
                actors: List[str] = itunes_parser.parse_actors()
                location: str = itunes_parser.parse_location()
                itunes_parser.parse_basic_trailer_information()
                movie: ITunesMovie = itunes_parser.get_movie()
                rejection_reasons: List[int] = ITunesFilter.filter_movie(movie)
                if len(rejection_reasons) > 0:
                    continue

                #  Finished with simple parsing and initial filtering
                #  Now need to look at trailer information for more
                #  data and opportunities to filter

                feature_url = f'{iTunes.TRAILER_BASE_URL}{location}'
                Monitor.throw_exception_if_abort_requested()
                rc: int
                movie: ITunesMovie

                # See if we can download the trailer

                rc = self.get_detailed_trailer_information(feature_url,
                                                           movie=movie,
                                                           release_date=release_date)

                if rc == 0 and movie is not None:
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        Debug.validate_basic_movie_properties(
                            movie)
                    self.add_to_discovered_movies(movie)
                    # ItunesCacheIndex.cache_movie(movie)

            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                clz.logger.exception('')
        return

    def get_detailed_trailer_information(self,
                                         feature_url: str,
                                         movie: ITunesMovie,
                                         release_date: datetime.date = None
                                         ) -> int:

        """ Get additional trailer and movie information by making a second
            api call.

            Sets trailer_path, trailer_type and thumbnail
            :param feature_url:
            :param movie:
            :param release_date:

        """

        clz = type(self)
        thumb: str = ''
        rc: int = 0

        try:
            Monitor.throw_exception_if_abort_requested()
            video_downloader = VideoDownloader()
            title: str = movie.get_title()
            rc: int
            rc, downloadable_trailers = video_downloader.get_info(
                feature_url, MovieField.ITUNES_SOURCE, block=True)

            '''
            # Have a series of released promotions for a movie.
            # Each promotion can have different formats based upon
            # language, resolution, etc.
            #
            # Find the best match based upon settings.
            #
            # If a promotion does not have a format in required language(s),
            # then toss it.
            #
            # Get the best media file available:
            #  Find the best type of media based on priority and settings:
            #   Trailer, Teaser, Clip, Featurette
            #
            # Get the best image quality: 1080, 720, less
            #  "height": 720,
            #
            # Get newest
            # "upload_date": "20190405",
            #
            # To accomplish this, distill this data into a list of
            # candidate "promotions" with the attributes:
            # Title, URL, Language, Height, Type (movie/teaser/clip...),
            # Release Date,

            # After the distillation, pick the best

                fulltitle": "Announcement Video",  Ignore
               "fulltitle": "Big Game Spot",       Ignore
               "fulltitle": "Clip",
               "fulltitle": "Clip - Action Ted",
               "fulltitle": "Clip - Do You Think He's Dead?",
               "fulltitle": "Clip - Something Better I Can Do",
               "fulltitle": "Clip - Time Travel Confession",
               "fulltitle": "Featurette",
               "fulltitle": "Final Trailer",      Recognise
               "fulltitle": "Official Trailer",   Recognise
               "fulltitle": "Teaser Trailer",
               "fulltitle": "Trailer ",
               "fulltitle": "Trailer",
               "fulltitle": "Trailer 1",
               "fulltitle": "Trailer 2",
               "fulltitle": "Trailer 2 Exclusive",
               "fulltitle": "Trailer 3",

            # "fulltitle": "Featurette - The Making of Peterloo",
            #  "fulltitle": "Trailer",
            # "fulltitle": "Trailer 2",
            # "display_id": "daddy-issues-clip",
            # "fulltitle": "Clip",
            # "title": "Clip",

            # 'formats'
            # Toss every downloadable that does not meet language or
            # trailer type settings
            #
            # Then from those that pass the first filter, find the best.
            '''

            chosen_promotion = None
            current_language: str = Settings.get_lang_iso_639_1()
            media_types_map = {}
            for media_type in MovieField.TRAILER_TYPES:
                media_types_map[media_type] = []

            promotions = []
            for downloadable_trailer in downloadable_trailers:
                try:
                    '''
                        raw_movie: RawMovie
                        raw_movie = RawMovie(movie_info=downloadable_trailer,
                                             source=MovieField.ITUNES_SOURCE)
                        movie_id: str = movie.get_id() + '_X'
                        raw_movie.set_id(movie_id)
                        raw_movie.set_property(MovieField.TITLE, title)
                        BaseCache.write_cache_json(raw_movie)
                    '''
                   # Debug.dump_json('downloadable_trailer', downloadable_trailer,
                   #                  LazyLogger.DEBUG)
                    Monitor.throw_exception_if_abort_requested()
                    keep_promotion = True
                    media_type = downloadable_trailer.get(
                        'fulltitle', '')

                    # There can be trash after the trailer type

                    rt_media_type: str = None
                    for trailer_type in MovieField.TRAILER_TYPES:
                        if media_type.startswith(trailer_type):
                            media_type = trailer_type
                            rt_media_type = MovieField.TRAILER_TYPE_MAP[media_type]

                    language: str = downloadable_trailer.get('language', '')
                    thumbnail: str = downloadable_trailer['thumbnail']
                    upload_date = downloadable_trailer['upload_date']

                    if rt_media_type not in MovieField.TRAILER_TYPES:
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz.logger.debug_verbose(f'Rejecting {title} due to '
                                                     f'media-type: '
                                                     f'{media_type}')
                        continue
                    if language != '' and language != current_language:
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz.logger.debug_verbose(f'Rejecting {title} media-type: '
                                                     f'{media_type} due to language: '
                                                     f'{language}')
                        continue
                    elif (language == '' and
                            clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                        clz.logger.debug_verbose(f'Empty language specified for: {title} '
                                                 f'from media-type: {media_type}')
                    if (not Settings.get_include_clips() and
                            rt_media_type == MovieField.TRAILER_TYPE_CLIP):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                f'Rejecting {title} due to clip')
                        keep_promotion = False
                    elif not Settings.get_include_featurettes() and (
                            rt_media_type == MovieField.TRAILER_TYPE_FEATURETTE):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                f'Rejecting {title} due to Featurette')
                        keep_promotion = False
                    elif not Settings.get_include_teasers() and (
                            rt_media_type == MovieField.TRAILER_TYPE_TEASER):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz.logger.debug_verbose(
                                f'Rejecting {title} due to Teaser')
                        keep_promotion = False
                    elif ((Settings.get_include_itunes_trailer_type() ==
                           iTunes.COMING_SOON) and
                          (release_date < datetime.date.today())):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                f'Rejecting {title} due to COMING_SOON and already '
                                f'released')
                        keep_promotion = False

                    if keep_promotion:
                        for promotion_format in downloadable_trailer['formats']:
                            #Debug.dump_json('kept promotion format',
                            # promotion_format, LazyLogger.DEBUG)

                            language = promotion_format.get('language', '')
                            height = promotion_format.get('height', 0)
                            url = promotion_format.get('url', '')

                            if Utils.is_trailer_from_cache(url):
                                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                                    clz.logger.debug('test passed')

                            if language != '' and language != current_language:
                                if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                                    clz.logger.debug_verbose(f'Rejecting {title} due to '
                                                             f'language: {language} '
                                                             f'from media-type: '
                                                             f'{media_type} format: '
                                                             f'format')
                                    continue
                            elif language == '' and clz.logger.isEnabledFor(
                                    LazyLogger.DEBUG_VERBOSE):
                                clz.logger.debug_verbose('Empty language specified for:',
                                                         title, 'from media-type:',
                                                         media_type, 'format:', format)

                            promotion: MovieType = {
                                    'type': rt_media_type,
                                    'language': language,
                                    'height': height,
                                    'url': url,
                                    'title': title,
                                    'thumbnail': thumbnail,
                                    'upload_date': upload_date
                                    }
                            promotions.append(promotion)
                            media_types_map[rt_media_type].append(promotion)
                except KeyError:
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.exception()
                        clz.logger.debug('KeyError from json:',
                                         json.dumps(downloadable_trailer,
                                                    encoding='utf-8',
                                                    ensure_ascii=False,
                                                    indent=3, sort_keys=True))

            # Now have finished digesting data. Only acceptable media
            # remains. Pick the best promotional media.

            # First, pick the best requested media type match
            for media_type in MovieField.SUPPORTED_TRAILER_TYPES:
                if len(media_types_map[media_type]) > 0:
                    promotions = media_types_map[media_type]
                    break

            best_date = '0'
            best_promotions = []
            for promotion in promotions:
                # upload_date YYYYMMDD
                if promotion['upload_date'] > best_date:
                    best_date = promotion['upload_date']
                    del best_promotions[:]
                if promotion['upload_date'] == best_date:
                    best_promotions.append(promotion)

            promotions = best_promotions
            best_promotions = []
            # Get best resolution
            best_height = 0
            for promotion in promotions:
                try:
                    if promotion.get('height', 0) > best_height:
                        best_height = promotion.get('height', 0)
                        del best_promotions[:]
                    if promotion['height'] == best_height:
                        best_promotions.append(promotion)
                except:
                    pass

            if len(best_promotions) > 0:
                chosen_promotion = best_promotions[0]
                # Debug.dump_json('chosen promotion', chosen_promotion, LazyLogger.DEBUG)

                '''
                    raw_movie: RawMovie
                    raw_movie = RawMovie(movie_info=chosen_promotion,
                                         source=MovieField.ITUNES_SOURCE)
                    movie_id: str = movie.get_id() + '_C'
                    raw_movie.set_id(movie_id)
                    raw_movie.set_property(MovieField.TITLE, title)
                    BaseCache.write_cache_json(raw_movie)
                '''

                trailer_url: str = chosen_promotion['url']
                trailer_type: str = chosen_promotion['type']
                thumb: str = chosen_promotion['thumbnail']
                movie.set_trailer_path(trailer_url)
                movie.set_has_trailer(True)
                movie.set_trailer_type(trailer_type)
                movie.set_thumbnail(thumb)
            else:
                rc = 1

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')
            rc = 1

        return rc

    def needs_restart(self) -> bool:
        """
            A restart is needed when settings that impact our results have
            changed.

        :returns: True if settings have changed requiring restart
                  False if relevant settings have changed or if it should
                  be allowed to die without restart
        """

        clz = type(self)
        clz.logger.enter()

        restart_needed: bool = False
        if Settings.is_include_itunes_trailers():
            restart_needed: bool = Settings.is_itunes_loading_settings_changed()

        return restart_needed

    ''' 
    {            
       "_filename": "Featurette - The Making of 
       Peterloo-peterloo-featurettethemakingofpeterloo.mov", 
       "display_id": "peterloo-featurettethemakingofpeterloo", 
       "duration": 371.0, 
       "ext": "mov", 
       "extractor": "appletrailers", 
       "extractor_key": "AppleTrailers", 
       "format": "enus-hd1080 - 1920x1080", 
       "format_id": "enus-hd1080", # Appears to be the best resolution in group
       "formats": [
          {
             "ext": "mov", 
             "format": "enus-sd - 848x480", 
             "format_id": "enus-sd", 
             "height": 480, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "https", 
             "url": "https://movietrailers.apple.com/movies/independent/peterloo
             /peterloo-featurette-the-making-of-peterloo_h480p.mov", 
             "width": 848
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd720 - 1280x720", 
             "format_id": "enus-hd720", 
             "height": 720, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "https", 
             "url": "https://movietrailers.apple.com/movies/independent/peterloo
             /peterloo-featurette-the-making-of-peterloo_h720p.mov", 
             "width": 1280
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd1080 - 1920x1080", 
             "format_id": "enus-hd1080", 
             "height": 1080, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "https", 
             "url": "https://movietrailers.apple.com/movies/independent/peterloo
             /peterloo-featurette-the-making-of-peterloo_h1080p.mov", 
             "width": 1920
          }
       ], 
       "fulltitle": "Featurette - The Making of Peterloo", 
       "height": 1080, # Looks like best resolution in group
       "http_headers": {
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
          "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
          "Accept-Encoding": "gzip, deflate", 
          "Accept-Language": "en-us,en;q=0.5", 
          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
          Firefox/59.0"
       }, 
       "id": "peterloo-featurettethemakingofpeterloo", 
       "language": "en", 
       "n_entries": 2, 
       "playlist": "Peterloo", 
       "playlist_id": "20268", 
       "playlist_index": 1, 
       "playlist_title": "Peterloo", 
       "playlist_uploader": null, 
       "playlist_uploader_id": null, 
       "protocol": "https", 
       "requested_subtitles": null, 
       "thumbnail": "http://trailers.apple.com/trailers/independent/peterloo/images
       /thumbnail_source_28966.jpg", 
       "thumbnails": [
          {
             "id": "0", 
             "url": "http://trailers.apple.com/trailers/independent/peterloo/images
             /thumbnail_source_28966.jpg"
          }
       ], 
       "title": "Featurette - The Making of Peterloo", 
       "upload_date": "20190405", 
       "uploader_id": "independent", 
       "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo
       -featurette-the-making-of-peterloo_h1080p.mov", 
       "webpage_url": "https://trailers.apple.com/trailers/independent/peterloo/", 
       "webpage_url_basename": "peterloo", 
       "width": 1920
    }
    
    {
       "_filename": "Trailer-peterloo-movie.mov", 
       "display_id": "peterloo-movie", 
       "duration": 72.0, 
       "ext": "mov", 
       "extractor": "appletrailers", 
       "extractor_key": "AppleTrailers", 
       "format": "enus-hd1080 - 1920x1056", 
       "format_id": "enus-hd1080", 
       "formats": [
          {
             "ext": "mov", 
             "format": "enus-sd - 848x448", 
             "format_id": "enus-sd", 
             "height": 448, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "https", 
             "url": "https://movietrailers.apple.com/movies/independent/peterloo
             /peterloo-trailer-1_h480p.mov", 
             "width": 848
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd720 - 1280x688", 
             "format_id": "enus-hd720", 
             "height": 688, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "https", 
             "url": "https://movietrailers.apple.com/movies/independent/peterloo
             /peterloo-trailer-1_h720p.mov", 
             "width": 1280
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd1080 - 1920x1056", 
             "format_id": "enus-hd1080", 
             "height": 1056, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "https", 
             "url": "https://movietrailers.apple.com/movies/independent/peterloo
             /peterloo-trailer-1_h1080p.mov", 
             "width": 1920
          }
       ], 
       "fulltitle": "Trailer", 
       "height": 1056, 
       "http_headers": {
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
          "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
          "Accept-Encoding": "gzip, deflate", 
          "Accept-Language": "en-us,en;q=0.5", 
          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
          Firefox/59.0"
       }, 
       "id": "peterloo-movie", 
       "language": "en", 
       "n_entries": 2, 
       "playlist": "Peterloo", 
       "playlist_id": "20268", 
       "playlist_index": 2, 
       "playlist_title": "Peterloo", 
       "playlist_uploader": null, 
       "playlist_uploader_id": null, 
       "protocol": "https", 
       "requested_subtitles": null, 
       "thumbnail": "http://trailers.apple.com/trailers/independent/peterloo/images
       /thumbnail_source_28100.jpg", 
       "thumbnails": [
          {
             "id": "0", 
             "url": "http://trailers.apple.com/trailers/independent/peterloo/images
             /thumbnail_source_28100.jpg"
          }
       ], 
       "title": "Trailer", 
       "upload_date": "20180724", 
       "uploader_id": "independent", 
       "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo
       -trailer-1_h1080p.mov", 
       "webpage_url": "https://trailers.apple.com/trailers/independent/peterloo/", 
       "webpage_url_basename": "peterloo", 
       "width": 1920
    }
    
    {
       "_filename": "Trailer 2-spider-man-far-from-home-trailer2.mov", 
       "display_id": "spider-man-far-from-home-trailer2", 
       "duration": 175.0, 
       "ext": "mov", 
       "extractor": "appletrailers", 
       "extractor_key": "AppleTrailers", 
       "format": "enus-hd1080 - 1920x816", 
       "format_id": "enus-hd1080", 
       "formats": [
          {
             "ext": "mov", 
             "format": "enus-sd - 848x360", 
             "format_id": "enus-sd", 
             "height": 360, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "http", 
             "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far
             -from-home/spiderman-far-from-home-trailer-3_h480p.mov", 
             "width": 848
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd720 - 1280x544", 
             "format_id": "enus-hd720", 
             "height": 544, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "http", 
             "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far
             -from-home/spiderman-far-from-home-trailer-3_h720p.mov", 
             "width": 1280
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd1080 - 1920x816", 
             "format_id": "enus-hd1080", 
             "height": 816, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "http", 
             "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far
             -from-home/spiderman-far-from-home-trailer-3_h1080p.mov", 
             "width": 1920
          }
       ], 
       "fulltitle": "Trailer 2", 
       "height": 816, 
       "http_headers": {
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
          "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
          "Accept-Encoding": "gzip, deflate", 
          "Accept-Language": "en-us,en;q=0.5", 
          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
          Firefox/59.0"
       }, 
       "id": "spider-man-far-from-home-trailer2", 
       "language": "en", 
       "n_entries": 2, 
       "playlist": "Spider-Man: Far From Home", 
       "playlist_id": "20622", 
       "playlist_index": 1, 
       "playlist_title": "Spider-Man: Far From Home", 
       "playlist_uploader": null, 
       "playlist_uploader_id": null, 
       "protocol": "http", 
       "requested_subtitles": null, 
       "thumbnail": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far
       -from-home/images/thumbnail_source_29104.jpg", 
       "thumbnails": [
          {
             "id": "0", 
             "url": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far
             -from-home/images/thumbnail_source_29104.jpg"
          }
       ], 
       "title": "Trailer 2", 
       "upload_date": "20190506", 
       "uploader_id": "sony_pictures", 
       "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from
       -home/spiderman-far-from-home-trailer-3_h1080p.mov", 
       "webpage_url": "https://trailers.apple.com/trailers/sony_pictures/spider-man-far
       -from-home/", 
       "webpage_url_basename": "spider-man-far-from-home", 
       "width": 1920
    }
    
    {
       "_filename": "Trailer-spider-man-far-from-home-movie.mov", 
       "display_id": "spider-man-far-from-home-movie", 
       "duration": 158.0, 
       "ext": "mov", 
       "extractor": "appletrailers", 
       "extractor_key": "AppleTrailers", 
       "format": "enus-hd1080 - 1920x816", 
       "format_id": "enus-hd1080", 
       "formats": [
          {
             "ext": "mov", 
             "format": "enus-sd - 848x360", 
             "format_id": "enus-sd", 
             "height": 360, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "http", 
             "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far
             -from-home/spider-man-far-from-home-trailer-1_h480p.mov", 
             "width": 848
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd720 - 1280x544", 
             "format_id": "enus-hd720", 
             "height": 544, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "http", 
             "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far
             -from-home/spider-man-far-from-home-trailer-1_h720p.mov", 
             "width": 1280
          }, 
          {
             "ext": "mov", 
             "format": "enus-hd1080 - 1920x816", 
             "format_id": "enus-hd1080", 
             "height": 816, 
             "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,
                */*;q=0.8", 
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                "Accept-Encoding": "gzip, deflate", 
                "Accept-Language": "en-us,en;q=0.5", 
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
                Firefox/59.0"
             }, 
             "language": "en", 
             "protocol": "http", 
             "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far
             -from-home/spider-man-far-from-home-trailer-1_h1080p.mov", 
             "width": 1920
          }
       ], 
       "fulltitle": "Trailer", 
       "height": 816, 
       "http_headers": {
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
          "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
          "Accept-Encoding": "gzip, deflate", 
          "Accept-Language": "en-us,en;q=0.5", 
          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 
          Firefox/59.0"
       }, 
       "id": "spider-man-far-from-home-movie", 
       "language": "en", 
       "n_entries": 2, 
       "playlist": "Spider-Man: Far From Home", 
       "playlist_id": "20622", 
       "playlist_index": 2, 
       "playlist_title": "Spider-Man: Far From Home", 
       "playlist_uploader": null, 
       "playlist_uploader_id": null, 
       "protocol": "http", 
       "requested_subtitles": null, 
       "thumbnail": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far
       -from-home/images/thumbnail_28707.jpg", 
       "thumbnails": [
          {
             "id": "0", 
             "url": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far
             -from-home/images/thumbnail_28707.jpg"
          }
       ], 
       "title": "Trailer", 
       "upload_date": "20190115", 
       "uploader_id": "sony_pictures", 
       "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from
       -home/spider-man-far-from-home-trailer-1_h1080p.mov", 
       "webpage_url": "https://trailers.apple.com/trailers/sony_pictures/spider-man-far
       -from-home/", 
       "webpage_url_basename": "spider-man-far-from-home", 
       "width": 1920
    }
    
    # Working URLs:
    # https://movietrailers.apple.com/movies/wb/the-lego-movie-2-the
    # -second-part/the-lego-movie-2-clip-palace-of-infinite
    # -relection_i320.m4v
    # https://movietrailers.apple.com/movies/independent/the-final-wish
    # /the-final-wish-movie-1_i320.m4v
    # https://movietrailers.apple.com/movies/wb/shazam/shazam-teaser-1
    # -usca_i320.m4v
    '''
