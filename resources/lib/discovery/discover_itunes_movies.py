# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import datetime
import re
import string

from common.constants import Constants, Movie, iTunes
from common.disk_utils import DiskUtils
from common.debug_utils import Debug
from common.exceptions import AbortException, ShutdownException
from common.messages import Messages
from common.monitor import Monitor
from common.logger import (Logger, LazyLogger, Trace)
from common.settings import Settings
from common.utils import Utils

from discovery.restart_discovery_exception import RestartDiscoveryException
from backend.rating import Rating
from backend.genreutils import GenreUtils
from backend import backend_constants
from backend.itunes import ITunes
from backend.json_utils_basic import JsonUtilsBasic
from backend.json_utils import JsonUtils
from backend.yd_stream_extractor_proxy import YDStreamExtractorProxy

from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.itunes_movie_data import ItunesMovieData

STRIP_TZ_PATTERN = ' .[0-9]{4}$'

# noinspection Annotator,Annotator,PyArgumentList

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.discover_itunes_movies')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class DiscoverItunesMovies(BaseDiscoverMovies):
    """

    """

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        thread_name = type(self).__name__
        kwargs = {}
        kwargs[Movie.SOURCE] = Movie.ITUNES_SOURCE
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = ItunesMovieData()
        self._selected_genres = None
        self._excluded_genres = None

        # Early checking of for duplicates before we query external databases
        self._duplicate_check = set()

    def discover_basic_information(self):
        # type: () -> None
        """

        :return:
        """
        self.start()

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(': started')

    def on_settings_changed(self):
        # type: () -> None
        """
            Rediscover trailers if the changed settings impacts this manager.
        """

        self._logger.enter()

        try:
            if Settings.is_itunes_loading_settings_changed():
                stop_thread = not Settings.get_include_itunes_trailers()
                self.restart_discovery(stop_thread)
                self._duplicate_check.clear()

        except (Exception) as e:
            self._logger.exception('')

    def is_duplicate(self, key):
        result = False
        if key in self._duplicate_check:
            result = True
        else:
            self._duplicate_check.add(key)

        return result

    def run(self):
        # type: () -> None
        """

        :return:
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
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.get_include_itunes_trailers():
                        finished = True
                        self.remove_self()

        except (AbortException, ShutdownException):
            return  # Just exit thread
        except (Exception):
            self._logger.exception('')

        self.finished_discovery()
        duration = datetime.datetime.now() - start_time
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Time to discover:', duration.seconds, 'seconds',
                               trace=Trace.STATS)

    def run_worker(self):
        # type: () -> None
        """

        :return:
        """
        Monitor.get_instance().throw_exception_if_shutdown_requested()

        # self._keywords = ''
        self._selected_genres = set('')
        self._excluded_genres = set('')
        if Settings.get_filter_genres():
            self._selected_genres = set(GenreUtils.get_instance().get_external_genre_ids(
                GenreUtils.ITUNES_DATABASE, exclude=False))
            self._excluded_genres = set(GenreUtils.get_instance().get_external_genre_ids(
                GenreUtils.ITUNES_DATABASE, exclude=True))

        show_only_itunes_trailers_of_this_type = \
            Settings.get_include_itunes_trailer_type()
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('iTunesTrailer_type:',
                               show_only_itunes_trailers_of_this_type)

        json_url = iTunes.get_url_for_trailer_type(
            show_only_itunes_trailers_of_this_type)
        json_url = backend_constants.APPLE_URL_PREFIX + json_url
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('iTunes json_url', json_url)
        status_code, parsed_content = JsonUtilsBasic.get_json(json_url)
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
        # if self._logger.isEnabledFor(Logger.DEBUG):
        #   self._logger.debug('Itunes parsed_content type:',
        #                type(parsed_content).__name__)

        DiskUtils.RandomGenerator.shuffle(parsed_content)
        for itunes_movie in parsed_content:
            try:
                Monitor.get_instance().throw_exception_if_shutdown_requested()

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('value: ', itunes_movie)
                # If we have seen this before, then skip it.

                title = itunes_movie.get(Movie.TITLE, None)
                if title is None or self.is_duplicate(title):
                    continue

                title = itunes_movie.get(
                    Movie.TITLE, Messages.get_instance().get_msg(Messages.MISSING_TITLE))

                # TODO: DELETE ME!

                release_date_string = itunes_movie.get('releasedate', '')
                # if self._logger.isEnabledFor(Logger.DEBUG):
                # self._logger.debug('release_date_string: ',
                #            release_date_string)
                if release_date_string != '':
                    strip_tz_pattern = re.compile(STRIP_TZ_PATTERN)
                    release_date_string = strip_tz_pattern.sub(
                        '', release_date_string)

                    # "Thu, 14 Feb 2019 00:00:00 -0800",
                    release_date = datetime.datetime.strptime(
                        release_date_string, '%a, %d %b %Y %H:%M:%S')
                    if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
                        self._logger.debug_extra_verbose('title:', title, 'release_date_string:',
                                                         release_date_string, 'release_date:',
                                                         release_date.strftime('%d-%m-%Y'))
                    #
                else:
                    release_date = datetime.date.today()

                if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
                    EPOCH_TIME = datetime.datetime(1970, 1, 1, 0, 1)
                    if abs((release_date - EPOCH_TIME).total_seconds()) < 3600 * 25:
                        self._logger.debug_extra_verbose('Suspicious looking release date:',
                                                         release_date.strftime('%d-%m-%Y'))
                        #
                        # Force date to be today since it looks like it was never
                        # set
                        release_date = datetime.date.today()

                studio = itunes_movie.get('studio', '')
                if isinstance(studio, str):
                    studio = [studio]

                # self._logger.debug('studio:', studio)

                poster = itunes_movie.get('poster', '')

                # self._logger.debug('poster:', poster)

                thumb = poster.replace(
                    'poster.jpg', 'poster-xlarge.jpg')
                fanart = poster.replace('poster.jpg', 'background.jpg')

                # self._logger.debug('thumb:', thumb, ' fanart:', fanart)

                # poster_2x = itunes_movie.get('poster_2x', '')
                # self._logger.debug('poster_2x: ', poster_2x)

                # location = itunes_movie.get('location', '')
                # self._logger.debug('location: ', location)

                # Normalize rating
                # We expect the attribute to be named 'mpaa', not 'rating'

                itunes_movie[Movie.MPAA] = itunes_movie['rating']
                rating = Rating.get_mpa_rating(
                    itunes_movie.get(Movie.MPAA), itunes_movie.get('adult'))
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('rating: ', rating)

                genres = itunes_movie.get('genre', '')
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('genres: ', genres)

                directors = itunes_movie.get('directors', [])
                if isinstance(directors, str):
                    directors = [directors]
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('directors: ', directors)

                actors = itunes_movie.get('actors', [])
                if isinstance(actors, str):
                    actors = [actors]
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('actors: ', actors)
                cast = []
                for actor in actors:
                    fake_cast_entry = {}
                    fake_cast_entry['name'] = actor
                    fake_cast_entry['character'] = ''
                    cast.append(fake_cast_entry)

                """
                    "trailers":[
                        {"postdate":"Tue, 13 Nov 2018 00:00:00 -0800",
                        "url":"/trailers/fox/alita-battle-angel/",
                        "type":"Trailer 3",
                        "exclusive":false,
                         "hd":true},
        
                         {"postdate":"Mon, 23 Jul 2018 00:00:00 -0700",
                          "url":"/trailers/fox/alita-battle-angel/",
                          "type":"Trailer 2","exclusive":false,"hd":true},
                         {"postdate":"Fri, 08 Dec 2017 00:00:00 -0800",
                           "url":"/trailers/fox/alita-battle-angel/",
                           "type":"Trailer","exclusive":false,"hd":true}]
                """
                exclude_types_set = ITunes.get_excluded_types()
                itunes_trailers_list = itunes_movie.get('trailers', [])

                # if self._logger.isEnabledFor(Logger.DEBUG):
                #   self._logger.debug('itunes_trailers_list: ',
                #                itunes_trailers_list)
                for itunes_trailer in itunes_trailers_list:
                    try:
                        Monitor.get_instance().throw_exception_if_shutdown_requested()

                        keep_promotion = True
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug(
                                'itunes_trailer: ', itunes_trailer)

                        # post_date = itunes_trailer.get('postdate', '')
                        # self._logger.debug('post_date: ', post_date)

                        url = itunes_trailer.get('url', '')
                        adult = itunes_trailer.get('adult', False)
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('url: ', url)

                        trailer_type = itunes_trailer.get('type', '')
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('type: ', trailer_type)

                        if trailer_type.startswith('Clip') and not Settings.get_include_clips():
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Rejecting due to clip')
                            keep_promotion = False
                        elif trailer_type in exclude_types_set:
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    'Rejecting due to exclude Trailer Type')
                            keep_promotion = False
                        elif not Settings.get_include_featurettes() and (
                                trailer_type == 'Featurette'):
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    'Rejecting due to Featurette')
                            keep_promotion = False
                        elif ((Settings.get_include_itunes_trailer_type() ==
                                iTunes.COMING_SOON) and
                              (release_date < datetime.date.today())):
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug(
                                    'Rejecting due to COMING_SOON and already released')
                            keep_promotion = False

                        elif Settings.get_filter_genres():
                            # iTunes has no keywords

                            if set(self._selected_genres).isdisjoint(set(genres)):
                                keep_promotion = False
                                if self._logger.isEnabledFor(Logger.DEBUG):
                                    self._logger.debug(
                                        'Rejecting due to genre')
                            if set(self._excluded_genres).intersection(set(genres)):
                                keep_promotion = False
                                if self._logger.isEnabledFor(Logger.DEBUG):
                                    self._logger.debug(
                                        'Rejecting due to excluded genre')
                        elif not Rating.check_rating(rating):
                            keep_promotion = False
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Rejecting due to rating:',
                                                   rating)
                        if keep_promotion:
                            feature_url = 'https://trailers.apple.com' + \
                                itunes_movie.get('location')
                            movie = self.get_trailer_url(feature_url,
                                                         title=title,
                                                         trailer_type=trailer_type,
                                                         rating=rating,
                                                         adult=adult,
                                                         release_date=release_date,
                                                         genres=genres,
                                                         directors=directors,
                                                         cast=cast,
                                                         studio=studio,
                                                         fanart=fanart)

                            if movie is not None:
                                if self._logger.isEnabledFor(Logger.DEBUG):
                                    self._logger.debug(
                                        'Adding iTunes trailer: ', movie[Movie.TITLE])
                                    Debug.validate_basic_movie_properties(
                                        movie)
                                self.add_to_discovered_trailers(movie)
                    except (Exception) as e:
                        self._logger.exception('')

            except (Exception) as e:
                self._logger.exception('')
        return

    def get_trailer_url(self,
                        feature_url,  # type: TextType
                        title='',  # type: TextType
                        trailer_type='',  # type: TextType
                        rating='',  # type: TextType
                        adult=False,  # type: bool
                        release_date=None,  # type: datetime.datetime
                        genres=[],  # type: List[TextType]
                        directors=[],  # type: List[TextType]
                        cast=[],  # type: List[Dict]
                        studio='',  # type: TextType
                        fanart=''  # type: TextType
                        ):

        # type: (...) -> MovieType
        """
        """

        movie = None
        trailer_url = ''
        trailer_type = ''
        thumb = ''

        try:

            youtube_data_stream_extractor_proxy = \
                YDStreamExtractorProxy.get_instance()
            downloadable_trailers = youtube_data_stream_extractor_proxy.get_info(
                feature_url)

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
            # Title, URL, Language, Height, Type (trailer/teaser/clip...),
            # Release Date,

            # After the distillation, pick the best

            # "fulltitle": "Featurette - The Making of Peterloo",
            #  "fulltitle": "Trailer",
            # "fulltitle": "Trailer 2",
            # "display_id": "daddy-issues-clip",
            # "fulltitle": "Clip",
            # "title": "Clip",

            # 'formats'
            # Toss every downloadable that does not meet language settings

            chosen_promotion = None
            DOWNLOADABLE_TYPES = ('trailer', 'clip', 'featurette', 'teaser')
            media_types_map = {}
            for media_type in DOWNLOADABLE_TYPES:
                media_types_map[media_type] = []

            promotions = []
            for downloadable_trailer in downloadable_trailers:
                keep_promotion = True
                media_type = downloadable_trailer.get(
                    'title', '').lower()
                media_type = media_type.split(' ')[0]

                # title = downloadable_trailer.get('title', '')
                language = downloadable_trailer.get('language', '')
                thumbnail = downloadable_trailer['thumbnail']
                upload_date = downloadable_trailer['upload_date']

                if media_type not in DOWNLOADABLE_TYPES:
                    continue
                if language != '' and language != Settings.getLang_iso_639_1():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Rejecting:', title, 'media-type:',
                                           media_type, 'due to language:',
                                           language)
                    continue
                elif language == '' and self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Empty language specified for:',
                                       title, 'from media-type:', media_type)
                if (not Settings.get_include_clips() and
                        media_type == 'clip'):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Rejecting due to clip')
                    keep_promotion = False
                elif not Settings.get_include_featurettes() and (
                        media_type == 'featurette'):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Rejecting due to Featurette')
                    keep_promotion = False
                elif not Settings.get_include_teasers() and (
                        media_type == 'teaser'):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Rejecting due to Teaser')
                    keep_promotion = False
                elif ((Settings.get_include_itunes_trailer_type() ==
                       iTunes.COMING_SOON) and
                      (release_date < datetime.date.today())):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'Rejecting due to COMING_SOON and already released')
                    keep_promotion = False

                if keep_promotion:
                    for promotion_format in downloadable_trailer['formats']:
                        language = promotion_format.get('language', '')
                        height = promotion_format.get('height', 0)
                        url = promotion_format.get('url', '')

                        # TODO: DELETE ME

                        if self._logger.isEnabledFor(Logger.DEBUG):
                            if type(url).__name__ not in ('unicode', 'newstr'):
                                self._logger.debug('LEAK: trailer not unicode:',
                                                   type(url).__name__)

                        if Utils.is_trailer_from_cache(url):
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('test passed')

                        # TODO: End DELETE ME

                        if language != '' and language != Settings.getLang_iso_639_1():
                            if self._logger.isEnabledFor(Logger.DEBUG):
                                self._logger.debug('Rejecting:', title,
                                                   'due to language:',
                                                   language, 'from media-type:',
                                                   media_type, 'format:',
                                                   format)
                                continue
                        elif language == '' and self._logger.isEnabledFor(
                                Logger.DEBUG):
                            self._logger.debug('Empty language specified for:',
                                               title, 'from media-type:',
                                               media_type, 'format:', format)

                        promotion = {}
                        promotion['type'] = media_type
                        promotion['language'] = language
                        promotion['height'] = height
                        promotion['url'] = url
                        promotion['title'] = title
                        promotion['thumbnail'] = thumbnail
                        promotion['upload_date'] = upload_date
                        promotions.append(promotion)
                        media_types_map[media_type].append(promotion)

            # Now have finished digesting data. Only acceptable media
            # remains. Pick the best promotional media.

            # First, pick the best requested media type match
            for media_type in DOWNLOADABLE_TYPES:
                if len(media_types_map[media_type]) > 0:
                    promotions = media_types_map[media_type]
                    break

            best_date = 0
            best_promotions = []
            for promotion in promotions:
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
                if promotion['height'] > best_height:
                    best_height = promotion['height']
                    del best_promotions[:]
                if promotion['height'] == best_height:
                    best_promotions.append(promotion)

            if len(best_promotions) > 0:
                chosen_promotion = best_promotions[0]
                trailer_url = chosen_promotion['url']
                trailer_type = chosen_promotion['type']
                thumb = chosen_promotion['thumbnail']

            """             
           "_filename": "Featurette - The Making of Peterloo-peterloo-featurettethemakingofpeterloo.mov", 
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
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "https", 
                 "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-featurette-the-making-of-peterloo_h480p.mov", 
                 "width": 848
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd720 - 1280x720", 
                 "format_id": "enus-hd720", 
                 "height": 720, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "https", 
                 "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-featurette-the-making-of-peterloo_h720p.mov", 
                 "width": 1280
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd1080 - 1920x1080", 
                 "format_id": "enus-hd1080", 
                 "height": 1080, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "https", 
                 "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-featurette-the-making-of-peterloo_h1080p.mov", 
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
              "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
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
           "thumbnail": "http://trailers.apple.com/trailers/independent/peterloo/images/thumbnail_source_28966.jpg", 
           "thumbnails": [
              {
                 "id": "0", 
                 "url": "http://trailers.apple.com/trailers/independent/peterloo/images/thumbnail_source_28966.jpg"
              }
           ], 
           "title": "Featurette - The Making of Peterloo", 
           "upload_date": "20190405", 
           "uploader_id": "independent", 
           "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-featurette-the-making-of-peterloo_h1080p.mov", 
           "webpage_url": "https://trailers.apple.com/trailers/independent/peterloo/", 
           "webpage_url_basename": "peterloo", 
           "width": 1920
        }
        
        {
           "_filename": "Trailer-peterloo-trailer.mov", 
           "display_id": "peterloo-trailer", 
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
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "https", 
                 "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-trailer-1_h480p.mov", 
                 "width": 848
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd720 - 1280x688", 
                 "format_id": "enus-hd720", 
                 "height": 688, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "https", 
                 "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-trailer-1_h720p.mov", 
                 "width": 1280
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd1080 - 1920x1056", 
                 "format_id": "enus-hd1080", 
                 "height": 1056, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "https", 
                 "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-trailer-1_h1080p.mov", 
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
              "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
           }, 
           "id": "peterloo-trailer", 
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
           "thumbnail": "http://trailers.apple.com/trailers/independent/peterloo/images/thumbnail_source_28100.jpg", 
           "thumbnails": [
              {
                 "id": "0", 
                 "url": "http://trailers.apple.com/trailers/independent/peterloo/images/thumbnail_source_28100.jpg"
              }
           ], 
           "title": "Trailer", 
           "upload_date": "20180724", 
           "uploader_id": "independent", 
           "url": "https://movietrailers.apple.com/movies/independent/peterloo/peterloo-trailer-1_h1080p.mov", 
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
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "http", 
                 "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spiderman-far-from-home-trailer-3_h480p.mov", 
                 "width": 848
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd720 - 1280x544", 
                 "format_id": "enus-hd720", 
                 "height": 544, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "http", 
                 "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spiderman-far-from-home-trailer-3_h720p.mov", 
                 "width": 1280
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd1080 - 1920x816", 
                 "format_id": "enus-hd1080", 
                 "height": 816, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "http", 
                 "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spiderman-far-from-home-trailer-3_h1080p.mov", 
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
              "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
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
           "thumbnail": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far-from-home/images/thumbnail_source_29104.jpg", 
           "thumbnails": [
              {
                 "id": "0", 
                 "url": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far-from-home/images/thumbnail_source_29104.jpg"
              }
           ], 
           "title": "Trailer 2", 
           "upload_date": "20190506", 
           "uploader_id": "sony_pictures", 
           "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spiderman-far-from-home-trailer-3_h1080p.mov", 
           "webpage_url": "https://trailers.apple.com/trailers/sony_pictures/spider-man-far-from-home/", 
           "webpage_url_basename": "spider-man-far-from-home", 
           "width": 1920
        }
        
        {
           "_filename": "Trailer-spider-man-far-from-home-trailer.mov", 
           "display_id": "spider-man-far-from-home-trailer", 
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
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "http", 
                 "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spider-man-far-from-home-trailer-1_h480p.mov", 
                 "width": 848
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd720 - 1280x544", 
                 "format_id": "enus-hd720", 
                 "height": 544, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "http", 
                 "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spider-man-far-from-home-trailer-1_h720p.mov", 
                 "width": 1280
              }, 
              {
                 "ext": "mov", 
                 "format": "enus-hd1080 - 1920x816", 
                 "format_id": "enus-hd1080", 
                 "height": 816, 
                 "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", 
                    "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7", 
                    "Accept-Encoding": "gzip, deflate", 
                    "Accept-Language": "en-us,en;q=0.5", 
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
                 }, 
                 "language": "en", 
                 "protocol": "http", 
                 "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spider-man-far-from-home-trailer-1_h1080p.mov", 
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
              "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0"
           }, 
           "id": "spider-man-far-from-home-trailer", 
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
           "thumbnail": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far-from-home/images/thumbnail_28707.jpg", 
           "thumbnails": [
              {
                 "id": "0", 
                 "url": "http://trailers.apple.com/trailers/sony_pictures/spider-man-far-from-home/images/thumbnail_28707.jpg"
              }
           ], 
           "title": "Trailer", 
           "upload_date": "20190115", 
           "uploader_id": "sony_pictures", 
           "url": "http://movietrailers.apple.com/movies/sony_pictures/spider-man-far-from-home/spider-man-far-from-home-trailer-1_h1080p.mov", 
           "webpage_url": "https://trailers.apple.com/trailers/sony_pictures/spider-man-far-from-home/", 
           "webpage_url_basename": "spider-man-far-from-home", 
           "width": 1920
        }
            """
            # Working URLs:
            # https://movietrailers.apple.com/movies/wb/the-lego-movie-2-the
            # -second-part/the-lego-movie-2-clip-palace-of-infinite
            # -relection_i320.m4v
            # https://movietrailers.apple.com/movies/independent/the-final-wish
            # /the-final-wish-trailer-1_i320.m4v
            # https://movietrailers.apple.com/movies/wb/shazam/shazam-teaser-1
            # -usca_i320.m4v

            itunes_id = title + '_' + str(release_date.year)
            movie = {Movie.TITLE: title,
                     Movie.TRAILER: trailer_url,
                     Movie.FILE: '',
                     # It looks like TrailerType is simply "trailer-" +
                     # trailer number
                     Movie.TYPE: trailer_type,
                     Movie.MPAA: rating,
                     Movie.ADULT: adult,
                     Movie.YEAR: str(release_date.year),
                     Movie.THUMBNAIL: thumb,
                     Movie.FANART: fanart,
                     Movie.GENRE: genres,
                     Movie.DIRECTOR: directors,
                     Movie.CAST: cast,
                     Movie.STUDIO: studio,
                     Movie.SOURCE:
                     Movie.ITUNES_SOURCE,
                     Movie.ITUNES_ID: itunes_id}
        except (Exception) as e:
            self._logger.exception('')

        return movie
