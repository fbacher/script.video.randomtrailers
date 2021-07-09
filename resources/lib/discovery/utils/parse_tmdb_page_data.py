# -*- coding: utf-8 -*-

import datetime

from common.imports import *
from common.logger import LazyLogger
from common.movie import TMDbMoviePageData
from common.movie_constants import MovieField
from common.certification import WorldCertifications, Certification

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ParseTMDbPageData:
    '''
    Parses data returned from TMDb discover API. The movie data is summary
    information. An additional query must be made for individual movies to
    get full information.

    '''

    _logger: LazyLogger = None

    def __init__(self, movie_entry: Dict[str, Any]):
        type(self).class_init()
        self._movie_entry: Dict[str, Any] = movie_entry
        self._tmdb_movie: TMDbMoviePageData = TMDbMoviePageData()
        self._tmdb_movie.set_cached(False)

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def parse_tmdb_id(self) -> int:
        tmdb_id: int = self._movie_entry.get('id')
        if tmdb_id is None:
            raise ValueError

        self._tmdb_movie.set_id(int(tmdb_id))
        return tmdb_id

    def parse_title(self) -> str:
        """
            Passed title can be junk:
            TFH titles are all caps, or otherwise wonky: use TMDb's title
            When only tmdb-id is known, then title is junk
            :return: parsed title
        """

        movie_title = self._movie_entry.get(MovieField.TITLE)
        if movie_title is None:
            raise ValueError

        self._tmdb_movie.set_title(movie_title)
        return movie_title

    def parse_original_title(self) -> str:
        original_title: str = self._movie_entry.get('original_title')
        if original_title is None:
            original_title = ''

        self._tmdb_movie.set_original_title(original_title)
        return original_title

    def parse_year(self) -> int:
        year: int
        try:
            release_date: str = self._movie_entry.get('release_date')
            if release_date is None:
                raise ValueError

            year_str = release_date[:-6]
            year = int(year_str)
        except Exception:
            year = datetime.datetime.now().year

        self._tmdb_movie.set_year(year)
        return year

    def parse_popularity(self) -> float:
        popularity: float = self._movie_entry.get('popularity')
        if popularity is None:
            popularity = 0.0

        popularity = float(popularity)
        self._tmdb_movie.set_popularity(popularity)
        return popularity

    def parse_votes(self) -> int:
        votes_str: str = self._movie_entry.get('vote_count')
        if votes_str is None:
            votes_str = 0

        votes: int
        try:
            votes = int(votes_str)
        except Exception:
            votes= 0

        self._tmdb_movie.set_votes(votes)
        return votes

    def parse_is_video(self) -> bool:
        #
        # Not used
        #
        raise NotImplemented
        # is_video: bool = self._movie_entry.get('video', 'false') == 'true'
        # return is_video

    def parse_certification(self) -> str:
        #
        # TMDb Page data ONLY tells us if a movie is adult or not.
        # This throw-away certification is therefore used to crudely filter
        # out adult movies.

        clz = type(self)
        adult: str = self._movie_entry.get('adult')
        if adult is None:
            adult = 'false'
        is_adult: bool = (adult == 'true')

        certification: Certification
        certification = WorldCertifications.get_certification_by_id(is_adult=is_adult,
                                                                    default_unrated=True)
        certification_id: str = certification.get_preferred_id()
        self._tmdb_movie.set_certification_id(certification_id)
        return certification_id

    def parse_vote_average(self) -> float:
        vote_average_str: str = self._movie_entry.get('vote_average')
        if vote_average_str is None:
            vote_average_str = '0.0'

        vote_average: float
        try:
            vote_average = float(vote_average_str)
        except:
            vote_average = 0.0

        self._tmdb_movie.set_rating(vote_average)
        return vote_average

    def parse_genre_ids(self) -> List[int]:
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
        tmdb_genre_ids: List[int] = self._movie_entry.get('genre_ids')
        if tmdb_genre_ids is None:
            tmdb_genre_ids = []

        self._tmdb_movie.set_genre_ids(tmdb_genre_ids)
        return tmdb_genre_ids

    def parse_original_language(self) -> str:
        clz = type(self)

        original_language: str = self._movie_entry.get('original_language')
        if original_language is None:
            original_language = ''

        self._tmdb_movie.set_original_language(original_language.lower())
        return original_language

    def parse_page_number(self):
        page_number: int = self._movie_entry.get('')

    def parse_total_number_of_pages(self):
        pass

    def get_movie(self) -> TMDbMoviePageData:
        return self._tmdb_movie
