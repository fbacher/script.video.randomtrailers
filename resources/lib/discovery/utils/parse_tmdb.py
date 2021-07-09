# -*- coding: utf-8 -*-
"""
Created on 4/25/21

@author: Frank Feuerbacher
"""
import sys

from backend.backend_constants import YOUTUBE_URL_PREFIX
from cache.tmdb_cache_index import CacheIndex
from cache.trailer_unavailable_cache import TrailerUnavailableCache
# from cache.unprocessed_tmdb_page_data import UnprocessedTMDbPages
from common.imports import *
from common.logger import LazyLogger
from common.movie import TMDbMovie
from common.movie_constants import MovieField
from common.certification import Certification, Certifications, WorldCertifications
from common.settings import Settings

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)

DOWNLOAD_SITE_PREFIXES: Dict[str, str] = {
    'YouTube': YOUTUBE_URL_PREFIX,
    'Vimeo': 'https://vimeo.com/'
    }


class ParseTMDb:

    _logger: LazyLogger = None

    def __init__(self, tmdb_result: Dict[str, Any], library_id: int) -> None:
        type(self).class_init()
        self._tmdb_result: Dict[str, Any] = tmdb_result
        self._tmdb_movie: TMDbMovie = TMDbMovie()
        self._tmdb_movie.set_cached(False)
        self._current_lang = Settings.get_lang_iso_639_1().lower()
        self._library_id: int = library_id
        self._image_base_url: str = 'http://image.tmdb.org/t/p/'
        self._country_id: str = Settings.get_country_iso_3166_1().lower()
        self._certifications: Certifications = \
                    WorldCertifications.get_certifications(self._country_id)
        self._adult_certification: Certification = \
            self._certifications.get_adult_certification()
        self._include_adult: bool = self._certifications.filter(self._adult_certification)
        self._vote_comparison, self._vote_value = Settings.get_tmdb_avg_vote_preference()

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_movie(self) -> TMDbMovie:
        return self._tmdb_movie

    def parse_id(self) -> int:
        tmdb_id: int = self._tmdb_result['id']
        return tmdb_id

    def parse_title(self) -> str:
        """
            Passed title can be junk:
            TFH titles are all caps, or otherwise wonky: use TMDb's title
            When only tmdb-id is known, then title is junk
            :return: parsed title
        """

        movie_title = self._tmdb_result[MovieField.TITLE]
        self._tmdb_movie.set_title(movie_title)
        return movie_title

    def parse_year(self) -> int:
        year: int
        try:
            year_str = self._tmdb_result['release_date'][:-6]
            year = int(year_str)
        except Exception:
            year = 0

        self._tmdb_movie.set_year(year)
        return year

    def parse_trailer(self) -> bool:
        """
        Parses video information from TMDb to find trailers, clips, featurettes,
        etc. and to return the best available given the settings.

        :return:
        """
        clz = type(self)
        trailer_type: str
        is_success = True

        try:

            # Map of longest video of each type: trailer, featurette, clip, etc.
            # Afterwords, choose the most desirable video type: trailer, etc.

            best_size_map: Dict[str, Dict[str, str]] = {}
            for trailer_type in MovieField.TRAILER_TYPES:
                best_size_map[trailer_type] = None

            tmdb_video: Dict[str, str] = None
            site: str = ''
            for tmdb_video in self._tmdb_result.get('videos', {'results': []}).get(
                    'results', []):
                site: str = tmdb_video['site']
                if site not in DOWNLOAD_SITE_PREFIXES.keys():
                    clz._logger.debug_extra_verbose(f'video not from Youtube nor Vimeo:'
                                                    f' {self._tmdb_movie.get_title()} '
                                                    f'site: {tmdb_video["site"]} '
                                                    f'type: {tmdb_video["type"]} '
                                                    f'size: {tmdb_video["size"]} '
                                                    f'size_type: '
                                                    f'{type(tmdb_video["size"])} '
                                                    f'key: {tmdb_video["key"]}')
                    continue

                if tmdb_video['iso_639_1'].lower() != self._current_lang:
                    continue

                trailer_type = tmdb_video['type']
                size = tmdb_video['size']
                if trailer_type not in Settings.is_allowed_trailer_types():
                    continue

                if trailer_type not in best_size_map:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug(f'Unrecognized trailer type: '
                                          f'{trailer_type}')
                    continue

                if best_size_map.get(trailer_type, None) is None:
                    best_size_map[trailer_type] = tmdb_video

                if best_size_map[trailer_type]['size'] < size:
                    best_size_map[trailer_type] = tmdb_video

            # Prefer trailer over other types

            trailer_key: Union[str, None] = None
            trailer_type: str = None
            for trailer_type in MovieField.TRAILER_TYPES:
                if best_size_map[trailer_type] is not None:
                    trailer_key = best_size_map[trailer_type]['key']
                    break

            # Do NOT update TFH_cache or local DB until this movie is
            # accepted by caller (this may be being used for supplemental
            # info

            # No point going on if we don't have a movie
            # TODO: Need common methods in cache to do this clean up

            tmdb_id_int: int = self._tmdb_movie.get_tmdb_id()
            if trailer_key is not None:
                tmdb_video = best_size_map[trailer_type]

                trailer_url = DOWNLOAD_SITE_PREFIXES[site] + tmdb_video['key']
                self._logger.debug_extra_verbose(f'movie: {self._tmdb_movie.get_title()} '
                                                 f'has trailer: '
                                                 f'{trailer_url}')
                self._tmdb_movie.set_trailer(trailer_url)
                self._tmdb_movie.set_trailer_type(trailer_type)
                CacheIndex.add_tmdb_id_with_trailer(tmdb_id_int)
            else:
                TrailerUnavailableCache.add_missing_tmdb_trailer(
                    tmdb_id=tmdb_id_int,
                    library_id=self._library_id,
                    title=self._tmdb_movie.get_title(),
                    year=self._tmdb_movie.get_year(),
                    source=self._tmdb_movie.get_source())
                if self._tmdb_movie.get_source() == MovieField.LIBRARY_SOURCE:
                    TrailerUnavailableCache.add_missing_library_trailer(
                        tmdb_id=tmdb_id_int,
                        library_id=self._library_id,
                        title=self._tmdb_movie.get_title(),
                        year=self._tmdb_movie.get_year(),
                        source=self._tmdb_movie.get_source())

                #  TODO: Movie to caller, or some other central location

                CacheIndex.remove_unprocessed_movie(tmdb_id_int)
                is_success = False
        except Exception as e:
            reraise(*sys.exc_info())

        return is_success

    def parse_certification(self) -> str:
        clz = type(self)
        is_adult: bool = self._tmdb_result.get('adult', 'false') == 'true'

        tmdb_countries: List[Dict[str, str]] = []
        try:
            tmdb_countries = self._tmdb_result['releases']['countries']
        except Exception as e:
            clz._logger.exception()

        certification_id: str = ''
        for c in tmdb_countries:
            if c.get('iso_3166_1', '').lower() == self._country_id:
                certification_id = c.get('certification', '')

        certification: Certification
        certification = WorldCertifications.get_certification_by_id(
                                                            certification_id,
                                                            is_adult=is_adult,
                                                            country_id=self._country_id,
                                                            default_unrated=True)

        certification_id = certification.get_preferred_id()
        self._tmdb_movie.set_certification_id(certification_id)
        return certification_id

    def parse_fanart(self) -> str:
        # fanart = image_base_url + 'w380' + \
        #     str(tmdb_result['backdrop_path'])
        backdrop_path: str = self._tmdb_result.get('backdrop_path')
        if backdrop_path is None:
            backdrop_path = ''
            fanart: str = ''
        else:
            fanart: str = f'{self._image_base_url}original{backdrop_path}'

        self._tmdb_movie.set_fanart(fanart)
        return fanart

    def parse_thumbnail(self) -> str:
        poster_path: str = self._tmdb_result.get('poster_path')
        if poster_path is None:
            thumbnail: str = ''
        else:
            thumbnail: str = f'{self._image_base_url}original{poster_path}'
        self._tmdb_movie.set_thumbnail(thumbnail)
        return thumbnail

    def parse_plot(self) -> str:
        plot: str = self._tmdb_result.get('overview', '')
        if plot is None:
            plot = ''

        self._tmdb_movie.set_plot(plot)
        return plot

    def parse_runtime(self) -> int:
        runtime: int = self._tmdb_result.get(MovieField.RUNTIME, 0)
        if runtime is None:
            runtime = 0
        runtime = runtime * 60 # seconds
        self._tmdb_movie.set_runtime(runtime)
        return runtime

    def parse_studios(self) -> List[str]:
        production_companies = self._tmdb_result['production_companies']
        if production_companies is None:
            production_companies = []
        studios: List[str] = []
        for s in production_companies:
            studios.append(s['name'])

        self._tmdb_movie.set_studios(studios)
        return studios

    def parse_actors(self) -> List[str]:
        '''
        "cast": [{"thumbnail": "image://%2fmovies%2f...Norma_Shearer.jpg/",
          "role": "Dolly",
          "name": "Norma Shearer",
          "order": 0},
         {"thumbnail": ... "order": 10}],
        :return:
        '''
        cast: List[Dict[str, Union[str, int]]] = self._tmdb_result['credits']['cast']
        actors: List[str] = []
        # Create list of actors, sorted by "order".
        # Sort map entries by "order"

        entries: List[Dict[str, Union[str, int]]] = sorted(cast, key=lambda i: i['order'])

        duplicate_check: Set[str] = set()

        entry: Dict[str, str]
        for entry in entries:
            actor: str = entry['name']
            if actor not in duplicate_check:
                duplicate_check.add(actor)
                actors.append(actor)

        self._tmdb_movie.set_actors(actors)
        return actors

    def parse_directors(self) -> List[str]:
        tmdb_crew_members = self._tmdb_result['credits']['crew']
        directors: List[str] = []
        for crew_member in tmdb_crew_members:
            if crew_member['job'] == 'Director':
                directors.append(crew_member['name'])

        # Duplicates (rare) removed
        self._tmdb_movie.set_directors(directors)
        return self._tmdb_movie.get_directors()

    def parse_writers(self) -> List[str]:
        tmdb_crew_members = self._tmdb_result['credits']['crew']
        writers: List[str] = []
        for crew_member in tmdb_crew_members:
            if crew_member['department'] == 'Writing':
                writers.append(crew_member['name'])

        # Duplicates removed (playwrite, book, writer, ...)

        self._tmdb_movie.set_writers(writers)
        return self._tmdb_movie.get_writers()

    def parse_vote_average(self) -> float:
        """
        Rating in Kodi is float 0 .. 10
        Rating in TMDb is vote_average 0 .. 10
        We only need int precision (gives .5 accuracy on 5-star scale)
        :return:
        """
        # Vote is float on a 0-10 scale

        vote_average: float = self._tmdb_result.get('vote_average')

        if vote_average is None:
            vote_average = 0.0
        else:
            vote_average = float(vote_average)

        self._tmdb_movie.set_rating(vote_average)
        return vote_average

    def parse_votes(self) -> int:
        """
        Vote is on scale of 0 - 10
        :return:
        """
        # Vote is float on a 0-10 scale

        votes = self._tmdb_result.get('vote_count')

        if votes is None:
            votes = 0
        else:
            votes = int(votes)

        self._tmdb_movie.set_votes(votes)
        return votes

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
        tmdb_genres: List[Dict[str, str]] = self._tmdb_result['genres']
        kodi_movie_genre_names: List[str] = []

        for tmdb_genre in tmdb_genres:
            kodi_movie_genre_names.append(tmdb_genre['name'])

        self._tmdb_movie.set_genre_names(kodi_movie_genre_names)
        return kodi_movie_genre_names

    def parse_keyword_names(self) -> List[str]:
        """
        Interesting structure: ['keywords']['keywords']

        See parse_keyword_ids
        """

        keywords = self._tmdb_result.get('keywords', [])
        tmdb_keywords = keywords.get('keywords', [])
        kodi_movie_tags: List[str] = []  # Kodi calls them tags

        for tmdb_keyword in tmdb_keywords:
            kodi_movie_tags.append(tmdb_keyword['name'])

        self._tmdb_movie.set_tag_names(kodi_movie_tags)
        return kodi_movie_tags

    def parse_genre_ids(self) -> List[str]:
        """
        Parse genre information from TMDb:
            genre names, which kodi uses to identify genres and stored in it's
            database.
            genre ids, which TMDb uses to identify genres. The names may be
            translated.

            GenreUtils uses the ids as the identifier and translates to the names
            as necessary.
        :return:
        """
        tmdb_genres: List[Dict[str, str]] = self._tmdb_result['genres']
        tmdb_genre_ids: List[str] = []

        for tmdb_genre in tmdb_genres:
            tmdb_genre_ids.append(str(tmdb_genre['id']))

        self._tmdb_movie.set_genre_ids(tmdb_genre_ids)
        return tmdb_genre_ids

    def parse_keyword_ids(self) -> List[str]:
        # Interesting structure: ['keywords']['keywords']

        keyword_dict: Dict[str, List[Dict[str, str]]]
        keyword_dict = self._tmdb_result.get('keywords', {})

        tmdb_keyword_list = keyword_dict.get('keywords', [])
        # On TMDb, keyword_id is an unique integer representing a
        # keyword. A keyword_name is a translated representation of
        # the keyword_id.

        tmdb_keyword_ids: List[str] = [] # Actually ints

        for tmdb_keyword in tmdb_keyword_list:
            tmdb_keyword_ids.append(str(tmdb_keyword['id']))

        self._tmdb_movie.set_tag_ids(tmdb_keyword_ids)
        return tmdb_keyword_ids

    def parse_original_language(self) -> str:
        clz = type(self)

        original_language = self._tmdb_result.get('original_language', '').lower()
        self._tmdb_movie.set_original_language(original_language)
        lang_matches: bool = original_language == self._current_lang
        self._tmdb_movie.set_is_original_language_found(lang_matches)
        self._logger.debug_extra_verbose(f'movie: {self._tmdb_movie.get_title()} '
                                         f'original_lang: {original_language}')
        return original_language

    def parse_original_title(self) -> str:
        original_title = self._tmdb_result.get('original_title', None)
        self._tmdb_movie.set_original_title(original_title)
        return original_title

    def get_discovery_state(self) -> str:
        discovery_state = self._tmdb_result.get(MovieField.DISCOVERY_STATE,
                                                MovieField.NOT_FULLY_DISCOVERED)
        self._tmdb_movie.set_discovery_state(discovery_state)
        return discovery_state
