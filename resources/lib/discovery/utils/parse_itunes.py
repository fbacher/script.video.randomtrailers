# -*- coding: utf-8 -*-
"""
Created on 4/25/21

@author: Frank Feuerbacher
"""
import datetime
import re
import sys

from backend.itunes import ITunes
from common.constants import iTunes
from common.imports import *
from common.exceptions import AbortException
from common.logger import LazyLogger
from common.messages import Messages
from common.monitor import Monitor
from common.movie import ITunesMovie
from common.movie_constants import MovieField
from common.rating import Certification, Certifications, WorldCertifications
from common.settings import Settings
from common.utils import Utils

STRIP_TZ_PATTERN: Final[Pattern] = re.compile(' .[0-9]{4}$')
# Map trailer-type strings from iTunes to what this app uses

EPOCH_TIME: Final[datetime.datetime] = datetime.datetime(1970, 1, 1, 0, 1)

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ParseITunes:

    _logger: LazyLogger = None

    def __init__(self, itunes_result: Dict[str, Any]) -> None:
        type(self).class_init()
        self._itunes_result: Dict[str, Any] = itunes_result
        self._itunes_movie: ITunesMovie = ITunesMovie()
        self._itunes_movie.set_cached(False)
        self._itunes_movie.set_movie_path('')  # No movie, just trailer
        self._lang = Settings.get_lang_iso_639_1().lower()
        self._country_id: str = Settings.get_country_iso_3166_1().lower()
        self._certifications: Certifications = \
            WorldCertifications.get_certifications(self._country_id)
        self._adult_certification: Certification = \
            self._certifications.get_adult_certification()
        self._vote_comparison, self._vote_value = Settings.get_tmdb_avg_vote_preference()

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_movie(self) -> ITunesMovie:
        return self._itunes_movie

    def parse_fanart(self) -> str:
        poster: str = self._itunes_result.get('poster', '')
        fanart = poster.replace('poster.jpg', 'background.jpg')
        self._itunes_movie.set_fanart(fanart)
        return fanart

    def parse_title(self) -> str:
        title: str = self._itunes_result.get(MovieField.TITLE,
                                             Messages.get_msg(Messages.MISSING_TITLE))
        self._itunes_movie.set_title(title)
        return title

    def parse_release_date(self) -> datetime.date:
        clz = type(self)
        release_date_string: str = self._itunes_result.get('releasedate', '')
        # if clz._logger.isEnabledFor(LazyLogger.DEBUG):
        # clz._logger.debug('release_date_string: ',
        #            release_date_string)
        if release_date_string != '':
            release_date_string = STRIP_TZ_PATTERN.sub('', release_date_string)

            # "Thu, 14 Feb 2019 00:00:00 -0800",
            release_date: datetime = Utils.strptime(release_date_string,
                                                    '%a, %d %b %Y %H:%M:%S')
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                title: str = self._itunes_movie.get_title()
                clz._logger.debug_extra_verbose(
                    f'title: {title} release_date_string: {release_date_string} '
                    f'release_date: {release_date.strftime("%d-%m-%Y")}')
            #
        else:
            release_date = datetime.date.today()

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if abs((release_date - EPOCH_TIME).total_seconds()) < 3600 * 25:
                clz._logger.debug_extra_verbose('Suspicious looking release date:',
                                               release_date.strftime('%d-%m-%Y'))
                #
                # Force date to be today since it looks like it was never
                # set
                release_date = datetime.date.today()

        self._itunes_movie.set_release_date(release_date)
        return release_date

    def parse_itunes_id(self) -> str:
        itunes_id: str = self._itunes_movie.get_title() + '_' +\
                         str(self._itunes_movie.get_release_date().year)
        self._itunes_movie.set_id(itunes_id)
        return itunes_id

    def parse_location(self) -> str:
        # Location is not persisted. Used for trailer parsing

        location: str = self._itunes_result.get('location', '')
        return location

    def parse_studios(self) -> List[str]:
        studio: str = self._itunes_result.get('studio', '')
        studios: List[str] = []
        if isinstance(studio, str):
            studios = [studio]
        self._itunes_movie.set_studios(studios)
        return studios

    def parse_year(self) -> int:
        clz = type(self)
        release_date_string: str = self._itunes_result.get('releasedate', '')
        # if clz._logger.isEnabledFor(LazyLogger.DEBUG):
        # clz._logger.debug('release_date_string: ',
        #            release_date_string)
        if release_date_string != '':
            release_date_string = STRIP_TZ_PATTERN.sub('', release_date_string)

            # "Thu, 14 Feb 2019 00:00:00 -0800",
            release_date: datetime = Utils.strptime(release_date_string,
                                                    '%a, %d %b %Y %H:%M:%S')
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                title: str = self._itunes_movie.get_title()
                clz._logger.debug_extra_verbose(
                    f'title: {title} release_date_string: {release_date_string} '
                    f'release_date: {release_date.strftime("%d-%m-%Y")}')
            #
        else:
            release_date = datetime.date.today()

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if abs((release_date - EPOCH_TIME).total_seconds()) < 3600 * 25:
                clz._logger.debug_extra_verbose('Suspicious looking release date:',
                                               release_date.strftime('%d-%m-%Y'))
                #
                # Force date to be today since it looks like it was never
                # set
                release_date = datetime.date.today()

        self._itunes_movie.set_year(release_date.year)
        return release_date.year

    def parse_basic_trailer_information(self) -> bool:
        """
        Performs initial extraction of trailer information from initial server
        api call results. After filtering some movies out by this information,
        Additional trailer information is gathered from a second api call.

        :return:
        """
        clz = type(self)
        trailer_type: str = ''
        url: str = ''
        is_success = False
        title: str = self._itunes_movie.get_title()

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
        exclude_types_set: Set[str] = ITunes.get_excluded_types()
        itunes_trailers_list: List[Dict[str, Any]] = \
            self._itunes_result.get('trailers', [])

        # if clz._logger.isEnabledFor(LazyLogger.DEBUG):
        #   clz._logger.debug('itunes_trailers_list: ',
        #                itunes_trailers_list)
        for itunes_trailer in itunes_trailers_list:
            try:
                Monitor.throw_exception_if_abort_requested()
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        'itunes_trailer: ', itunes_trailer)

                # post_date = itunes_trailer.get('postdate', '')
                # clz._logger.debug('post_date: ', post_date)

                url: str = itunes_trailer.get('url', '')
                
                if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                    clz._logger.debug_extra_verbose('url: ', url)

                """
                Note that iTunes api has movie type info here as well
                as in the entries processed in get_detailed_trailer_information. So we get
                to do this twice. AND we get to see duplicate messages,
                which can be confusing while debugging.
                """
                trailer_type = itunes_trailer.get('type', '')
                trailer_url = itunes_trailer.get('url', '')
                if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                    clz._logger.debug_extra_verbose(
                        'type: ', trailer_type)

                if trailer_type.startswith(
                        'Clip') and not Settings.get_include_clips():
                    if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                        clz._logger.debug_extra_verbose(
                            f'Rejecting {title} due to clip')
                    continue
                elif trailer_type in exclude_types_set:
                    if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                        clz._logger.debug_extra_verbose(
                            f'Rejecting {title} due to exclude Trailer Type')
                    continue
                elif not Settings.get_include_featurettes() and (
                        trailer_type == 'Featurette'):
                    if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                        clz._logger.debug_extra_verbose(
                            f'Rejecting {title} due to Featurette')
                    continue
                elif ((Settings.get_include_itunes_trailer_type() ==
                       iTunes.COMING_SOON) and
                      (self._itunes_movie.get_release_date() < datetime.date.today())):
                    if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                        clz._logger.debug_extra_verbose(
                            f'Rejecting {title} due to COMING_SOON and already '
                            f'released')
                    continue

                is_success = True
            # ItunesCacheIndex.cache_movie(movie)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                clz._logger.exception('')
                is_success = False
                
        if is_success:
            self._itunes_movie.set_trailer_type(trailer_type)
            self._itunes_movie.set_trailer_path(url)

        return is_success

    def parse_certification(self) -> str:
        # No country info from iTunes

        certification_id: str = self._itunes_result.get('rating')
        # Movie can be explicitly flagged as adult, or through certification (NC-17)
        is_adult: bool = self._itunes_result.get('adult', False)
        certification: Certification
        certification = WorldCertifications.get_certification_by_id(certification_id,
                                                                    is_adult=is_adult)
        certification_id = certification.get_preferred_id()
        self._itunes_movie.set_certification_id(certification_id)

        return certification_id

    def parse_runtime(self) -> int:
        runtime: int = self._itunes_result.get(MovieField.RUNTIME, 0) * 60 # seconds
        self._itunes_movie.set_runtime(runtime)
        return runtime

    def parse_actors(self) -> List[str]:
        actors = self._itunes_result['actors']

        # No point keeping more than what we will display
        if len(actors) > MovieField.MAX_ACTORS:
            actors = actors[:MovieField.MAX_ACTORS - 1]

        self._itunes_movie.set_actors(actors)
        return actors

    def parse_directors(self) -> List[str]:
        directors: Union[str, List[str]] = self._itunes_result.get('directors', [])
        if isinstance(directors, str):
            directors = [directors]
        self._itunes_movie.set_directors(directors)
        return directors

    def parse_genre_names(self) -> List[str]:
        """
        Parse genre information from TMDb:
            genre names, which kodi uses to identify genres and stored in it's
            database.
            genre ids, which TMDb uses to identify genres. The names may be
            translated.

            GenreUtils uses the ids as the identifier and translates to the names
            as necessary.

            See parse_genre_ids
        :return:
        """
        genres: List[str] = self._itunes_result['genre']
        self._itunes_movie.set_genre_names(genres)
        return genres

