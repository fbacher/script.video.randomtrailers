import sys
import time
from datetime import datetime

from common.exceptions import AbortException
from common.imports import *
from common.logger import LazyLogger
from common.movie import LibraryMovie
from common.movie_constants import MovieField
from common.certification import Certification, WorldCertifications

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ParseLibrary:
    _logger: LazyLogger = None

    def __init__(self, library_entry: Dict[str, Any]) -> None:
        type(self).class_init()
        self._library_entry: Dict[str, Any] = library_entry
        library_id: int = self._library_entry[MovieField.MOVIEID]
        self._movie: LibraryMovie = LibraryMovie(None)
        self._movie.set_library_id(library_id)
        self._movie.set_source(MovieField.LIBRARY_SOURCE)

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_movie(self) -> LibraryMovie:
        return self._movie

    def parse_title(self) -> str:
        title: str = self._library_entry[MovieField.TITLE]
        self._movie.set_title(title)
        return title

    def parse_last_played(self) -> None:
        last_played: str = self._library_entry.get(MovieField.LAST_PLAYED,
                                                   '1900-01-01 01:01:01')

        if last_played == '':
            last_played = '1900-01-01 01:01:01'
        pd = time.strptime(last_played, '%Y-%m-%d %H:%M:%S')
        pd = time.mktime(pd)
        last_played_time: datetime = datetime.fromtimestamp(pd)
        self._movie.set_last_played(last_played_time)

    def parse_certification(self) -> None:
        clz = type(self)
        is_adult = str(self._library_entry.get(MovieField.ADULT, False)).lower() == 'true'

        certification: Certification
        raw_certification_id = self._library_entry.get('mpaa', '')
        certification = WorldCertifications.get_certification_by_id(
            raw_certification_id,
            is_adult=is_adult,
            default_unrated=True)

        certification_id = certification.get_preferred_id()
        self._movie.set_certification_id(certification_id)
        return

    def parse_trailer_path(self) -> None:
        trailer_path: str = self._library_entry.get(MovieField.TRAILER, '')
        self._movie.set_trailer(trailer_path)

    def parse_trailer_type(self) -> None:
        trailer_type: str = self._library_entry.get(MovieField.TRAILER_TYPE, '')
        self._movie.set_trailer_type(trailer_type)

    def parse_plot(self) -> None:
        plot: str = self._library_entry.get(MovieField.PLOT, '')
        self._movie.set_plot(plot)

    def parse_writers(self) -> None:
        writers: List[str] = self._library_entry.get(MovieField.WRITER, [])
        self._movie.set_writers(writers)

    def parse_fanart(self) -> None:
        fanart_path: str = self._library_entry.get(MovieField.FANART, '')
        self._movie.set_fanart(fanart_path)

    def parse_directors(self) -> None:
        directors: List[str] = self._library_entry.get(MovieField.DIRECTOR, [])
        self._movie.set_directors(directors)

    def parse_actors(self) -> None:
        """
        "cast": [{"thumbnail": "image://%2fmovies%2f...Norma_Shearer.jpg/",
          "role": "Dolly",
          "name": "Norma Shearer",
          "order": 0},
         {"thumbnail": ... "order": 10}],
        :return:
        """

        duplicate_check: Set[str] = set()

        cast: List[Dict[str, Union[str, int]]] = self._library_entry.get('cast', [])
        actors: List[str] = []
        # Create list of actors, sorted by "order".
        # Sort map entries by "order"

        entries: List[Dict[str, Union[str, int]]] = sorted(cast,
                                                           key=lambda i: i['order'])

        entry: Dict[str, str]
        for entry in entries:
            actor: str = entry['name']
            if actor not in duplicate_check:
                duplicate_check.add(actor)
                actors.append(actor)

        self._movie.set_actors(actors)

    def parse_studios(self) -> None:
        studios: List[str] = self._library_entry.get(MovieField.STUDIO, [])
        self._movie.set_studios(studios)

    def parse_movie_path(self) -> str:
        #   TODO: Is this needed?
        movie_path: str = self._library_entry.get(MovieField.FILE)
        self._movie.set_movie_path(movie_path)
        return movie_path

    def parse_year(self) -> int:
        year: int = self._library_entry.get(MovieField.YEAR, 0)
        self._movie.set_year(year)
        return year

    def parse_genres(self) -> None:
        # Genre labels are unconstrained by kodi. They are simply imported from
        # whatever movie scraper is in effect. TMDb and IMDb are frequent sources.
        # May not be English. GenreUtils gets Genre Labels from TMDb and can
        # convert to language neutral ids.

        genres: List[str] = self._library_entry.get(MovieField.GENRE_NAMES, [])
        self._movie.set_genre_names(genres)

    def parse_runtime(self) -> None:
        movie_seconds: int = self._library_entry.get(MovieField.RUNTIME, 0)
        self._movie.set_runtime(movie_seconds)

    def parse_thumbnail(self) -> None:
        thumbnail_path: str = self._library_entry.get(MovieField.THUMBNAIL, '')
        self._movie.set_thumbnail(thumbnail_path)

    def parse_original_title(self) -> None:
        original_title: str = self._library_entry.get(MovieField.ORIGINAL_TITLE, '')
        self._movie.set_original_title(original_title)

    def parse_vote_average(self) -> None:
        vote_average: int = 0
        try:
            vote_average = int(self._library_entry.get(MovieField.RATING, 0))
        except ValueError:
            pass

        self._movie.set_rating(vote_average)

    def parse_unique_ids(self) -> None:
        unique_ids: Dict[str, str] = self._library_entry.get(MovieField.UNIQUE_ID, {})
        self._movie.set_unique_ids(unique_ids)

    def parse_votes(self) -> None:
        votes: int = self._library_entry.get(MovieField.VOTES, 0)
        self._movie.set_votes(votes)

    def parse_tags(self) -> None:
        tags: List[str] = self._library_entry.get(MovieField.TAG, [])
        self._movie.set_tags(tags)

    @classmethod
    def parse_movie(cls,
                    is_sparse: bool = True,
                    raw_movie: MovieType = None) -> LibraryMovie:
        movie: LibraryMovie = None
        try:
            movie_parser: ParseLibrary = ParseLibrary(raw_movie)
            movie_parser.parse_title()
            movie_parser.parse_unique_ids()
            movie_parser.parse_year()
            movie_parser.parse_trailer_path()
            movie_parser.parse_last_played()
            movie_parser.parse_certification()
            movie_parser.parse_vote_average()

            if not is_sparse:
                movie_parser.parse_trailer_type()
                movie_parser.parse_plot()
                movie_parser.parse_writers()
                movie_parser.parse_fanart()
                movie_parser.parse_directors()
                movie_parser.parse_actors()
                movie_parser.parse_studios()
                movie_parser.parse_movie_path()
                movie_parser.parse_genres()
                movie_parser.parse_runtime()
                movie_parser.parse_thumbnail()
                movie_parser.parse_original_title()
                movie_parser.parse_votes()
                movie_parser.parse_tags()

            movie: LibraryMovie = movie_parser.get_movie()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            cls._logger.exception('')
            movie = None

        return movie
