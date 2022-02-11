# -*- coding: utf-8 -*-
"""
Created on 4/25/21

@author: Frank Feuerbacher
"""
from backend.backend_constants import TMDbConstants
from common.imports import *
from common.logger import *
from common.movie import TFHMovie
from common.movie_constants import MovieField
from common.certification import Certification, Certifications, WorldCertifications
from common.settings import Settings

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class ParseTFH:

    _logger: BasicLogger = None

    def __init__(self, tfh_result: Dict[str, Any], library_id: int) -> None:
        type(self).class_init()
        self._tfh_result: Dict[str, Any] = tfh_result
        self._tfh_movie: TFHMovie = TFHMovie()
        self._tfh_movie.set_cached(False)
        self._lang = Settings.get_lang_iso_639_1().lower()
        self._library_id: int = library_id
        self._image_base_url: str = TMDbConstants.IMAGE_BASE_URL
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

    def get_movie(self) -> TFHMovie:
        return self._tfh_movie

    def parse_id(self) -> str:
        tfh_id = self._tfh_result.get(MovieField.TFH_ID, None)
        if tfh_id is None:
            tfh_id = self._tfh_result.get(MovieField.YOUTUBE_ID, None)
        if tfh_id is None:
            self._logger.debug(f'Can not get tfh_id for '
                               f'{self._tfh_result.get(MovieField.TITLE)}')
            return None

        self._tfh_movie.set_id(tfh_id)
        return tfh_id

    def parse_title(self) -> str:
        """
            Passed title can be junk:
            TFH titles are all caps, or otherwise wonky: use TMDb's title
            When only tmdb-id is known, then title is junk
            :return: parsed title
        """

        movie_title = self._tfh_result[MovieField.TITLE]
        self._tfh_movie.set_title(movie_title)

        return movie_title

    def parse_tfh_title(self) -> str:
        movie_title = self._tfh_movie.get_title()
        tfh_title = self._tfh_result.get(MovieField.TFH_TITLE, '')
        if len(tfh_title) < len(movie_title):
            tfh_title = movie_title
        self._tfh_movie.set_tfh_title(tfh_title)
        return tfh_title

    def parse_discovery_state(self) -> str:
        discovery_state: str = self._tfh_result.get(MovieField.DISCOVERY_STATE)
        self._tfh_movie.set_discovery_state(discovery_state)
        return discovery_state

    def parse_trailer_type(self) -> str:
        self._tfh_movie.set_trailer_type(MovieField.TRAILER_TYPE_TRAILER)
        return self._tfh_movie.get_trailer_type()

    def parse_trailer_path(self) -> str:
        trailer_path: str = self._tfh_result.get(MovieField.TRAILER, '')
        self._tfh_movie.set_trailer_path(trailer_path)
        return trailer_path

    def parse_year(self) -> int:
        year: int
        try:
            year_str = self._tfh_result['release_date'][:-6]
            year = int(year_str)
        except Exception:
            year = 0

        self._tfh_movie.set_year(year)
        return year

    def parse_certification(self) -> str:
        #
        # TRICKSY: This comes from TMDB. Start with hard-coded unrated value
        # from youtube downloader code. Value is Unrated_id

        bogus_certification_id: str = self._tfh_result.get(MovieField.CERTIFICATION_ID)
        self._tfh_movie.set_certification_id(bogus_certification_id)
        return bogus_certification_id

    def parse_fanart(self) -> str:
        # fanart = image_base_url + 'w380' + \
        #     str(tfh_result['backdrop_path'])
        fanart: str = f'{self._image_base_url}original' \
                      f'{str(self._tfh_result["backdrop_path"])}'
        self._tfh_movie.set_fanart(fanart)
        return fanart

    def parse_thumbnail(self) -> str:
        thumbnail_path: str = self._tfh_result.get(MovieField.THUMBNAIL)
        self._tfh_movie.set_thumbnail(thumbnail_path)
        return thumbnail_path

    def parse_plot(self) -> str:
        plot = self._tfh_result.get('overview', '')
        self._tfh_movie.set_plot(plot)
        return plot

    def parse_runtime(self) -> int:
        runtime: int = self._tfh_result.get(MovieField.RUNTIME, 0) * 60 # seconds
        self._tfh_movie.set_runtime(runtime)
        return runtime

    def parse_studios(self) -> List[str]:
        production_companies = self._tfh_result['production_companies']
        studios: List[str] = []
        for s in production_companies:
            studios.append(s['name'])

        self._tfh_movie.set_studios(studios)
        return studios

    def parse_actors(self) -> List[str]:
        tfh_cast_members = self._tfh_result['credits']['cast']
        actors: List[str] = []
        duplicate_check: Set[str] = set()

        for cast_member in tfh_cast_members:
            actor: str = cast_member['name']
            if actor not in duplicate_check:
                duplicate_check.add(actor)
                actors.append(actor)

        self._tfh_movie.set_actors(actors)
        return actors

    def parse_directors(self) -> List[str]:
        tmdb_crew_members = self._tfh_result['credits']['crew']
        directors: List[str] = []
        for crew_member in tmdb_crew_members:
            if crew_member['job'] == 'Director':
                directors.append(crew_member['name'])

        self._tfh_movie.set_directors(directors)
        return self._tfh_movie.get_directors()

    def parse_writers(self) -> List[str]:
        tmdb_crew_members = self._tfh_result['credits']['crew']
        writers: List[str] = []
        for crew_member in tmdb_crew_members:
            if crew_member['department'] == 'Writing':
                writers.append(crew_member['name'])

        # Duplicates removed (playwrite, book, writer, ...)

        self._tfh_movie.set_writers(writers)
        return self._tfh_movie.get_writers()

    def parse_rating(self) -> float:
        rating: float = self._tfh_result.get(MovieField.RATING, 0.0)

        self._tfh_movie.set_rating(rating)
        return rating

    def parse_votes(self) -> int:
        """
        Vote is on scale of 0 - 10
        :return:
        """
        # Vote is float on a 0-10 scale

        votes = self._tfh_result['vote_count']

        if votes is None:
            votes = 0

        self._tfh_movie.set_votes(votes)
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
        tmdb_genres: List[Dict[str, str]] = self._tfh_result['genres']
        genre_names: List[str] = []

        for tmdb_genre in tmdb_genres:
            genre_names.append(tmdb_genre['name'])

        self._tfh_movie.set_genre_names(genre_names)
        return genre_names

    def parse_keyword_names(self) -> List[str]:
        """
        Interesting structure: ['keywords']['keywords']

        See parse_keyword_ids
        """

        keywords = self._tfh_result.get('keywords', [])
        tmdb_keywords = keywords.get('keywords', [])
        tag_names: List[str] = []  # Kodi calls them tags

        for tmdb_keyword in tmdb_keywords:
            tag_names.append(tmdb_keyword['name'])

        self._tfh_movie.set_tag_names(tag_names)
        return tag_names

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
        tmdb_genres: List[Dict[str, str]] = self._tfh_result['genres']
        genre_ids: List[str] = []

        for tmdb_genre in tmdb_genres:
            genre_ids.append(str(tmdb_genre['id']))

        self._tfh_movie.set_genre_ids(genre_ids)
        return genre_ids

    def parse_keyword_ids(self) -> List[str]:
        # Interesting structure: ['keywords']['keywords']

        keywords = self._tfh_result.get('keywords', [])
        tmdb_keywords = keywords.get('keywords', [])
        tag_ids: List[str] = [] # Actually ints

        for tmdb_keyword in tmdb_keywords:
            tag_ids.append(str(tmdb_keyword['id']))

        return tag_ids

    def parse_original_title(self) -> str:
        original_title = self._tfh_result.get('original_title', None)
        self._tfh_movie.set_original_title(original_title)
        return original_title

