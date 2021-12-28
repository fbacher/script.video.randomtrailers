# -*- coding: utf-8 -*-
"""
Created on 4/13/21

@author: Frank Feuerbacher
"""
import datetime
import sys

from common.exceptions import AbortException
from common.imports import *
from common.logger import LazyLogger
from common.movie_constants import MovieField, MovieType
from common.certification import Certification, WorldCertifications
from common.settings import Settings

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)
CHECK_FOR_NULLS: bool = True


class BaseMovie:

    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = None) -> None:
        self._movie_id = None
        if movie_id is not None:
            self.set_id(movie_id)

        self._source: str = source
        self._fully_discovered: bool = False
        self._has_local_trailer = False
        self._has_trailer = False
        self._library_id: int = None
        self._folder_id: str = None
        self._tmdb_id: int = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def __str__(self) -> str:
        return None

    def get_source(self) -> str:
        return self._source

    def set_source(self, source: str) -> None:
        self._source = source

    def set_trailer_played(self, value: bool) -> None:
        pass

    def is_trailer_played(self) -> bool:
        return False

    def is_been_fully_discovered(self) -> bool:
        """
        Indicates whether this movie has every been fully discovered.

        Since movies are mostly in AbstractMovieId form to conserve space,
        it is useful to know, especially when starving, that this movie
        is (almost) guaranteed to be playable, and with caching, quickly
        playable.
        """
        return self._fully_discovered

    def set_has_been_fully_discovered(self, fully_discovered: bool) -> None:
        self._fully_discovered = fully_discovered

    def get_discovery_state(self) -> str:  # DiscoveryState:
        return MovieField.NOT_FULLY_DISCOVERED

    def get_id(self) -> str:
        """
        Gets the id appropriate for the class of movie
        :return:
        """
        return str(self._movie_id)

    def set_id(self, movie_id: str) -> None:
        self._movie_id = movie_id

    def get_title(self):
        """
        Can't get a real movie title, just return source_id
        sub-classes which implement get_title will, of course override this.
        This is meant for debugging purposes.

        :return:
        """
        source, movie_id = self.get_source_and_id()
        return f'{source}_{movie_id}'

    def has_local_trailer(self) -> Union[bool, None]:
        """
           Indicates whether a trailer on the local system exists. This trailer
           may be:

           * For movies from the library, the trailers may be in the same
             directory as the movie and known to the Kodi library
           * For trailers which are downloaded and cached
             - due to a movie from the library and with a trailer which is
               not local but a URL to a remote site
             - or for a trailer from a remote source (TMDb, TFH, etc.) then
               the trailer is also from a remote site
           * Normalized trailers, which are trailers from either local or
             remote locations, but have had the audio normalized and in
             the local cache.

          :returns True if the trailer is local, or has been downloaded and
                   in the local cache.
                   False if it is known that the trailer is not local
                   None if it has not been determined if the trailer is
                   local or remote.

        """
        return self._has_local_trailer

    def set_local_trailer(self,
                          has_local_trailer: Union[bool, None] = True) -> None:
        """
           Records whether a trailer on the local system exists. This trailer
           may be:

           * For movies from the library, the trailers may be in the same
             directory as the movie and known to the Kodi library
           * For trailers which are downloaded and cached
             - due to a movie from the library and with a trailer which is
               not local but a URL to a remote site
             - or for a trailer from a remote source (TMDb, TFH, etc.) then
               the trailer is also from a remote site
           * Normalized trailers, which are trailers from either local or
             remote locations, but have had the audio normalized and in
             the local cache.

          :param has_local_trailer: The values have the following meanings:
             True if the trailer is local, or has been downloaded and
                in the local cache.
            False if it is known that the trailer is not local
            None if it has not been determined if the trailer is
                local or remote. This is the case when a movie does not
                have a local trailer, but we have not yet determined if
                there is a trailer remotely (which requires a TMDb query)

        """
        self._has_local_trailer = has_local_trailer

    def get_has_trailer(self) -> bool:
        return self._has_trailer

    def set_has_trailer(self, has_trailer: bool = True) -> None:
        self._has_trailer = has_trailer

    def get_library_id(self) -> Union[int, None]:
        return self._library_id

    def set_library_id(self, library_id: int = None) -> None:
        self._library_id = library_id

    def set_folder_id(self, folder_id: str = None) -> None:
        self._folder_id = folder_id

    def get_tmdb_id(self) -> int:
        return self._tmdb_id

    def set_tmdb_id(self, tmdb_id: int = None) -> bool:
        if self._tmdb_id != tmdb_id:
            self._tmdb_id = tmdb_id
            return True
        return False

    def is_library_movie(self) -> bool:
        return isinstance(self, (LibraryMovieId, LibraryMovie))

    def is_tmdb_movie(self) -> bool:
        return isinstance(self, (TMDbMovie, TMDbMovieId))

    def serialize(self) -> Dict[str, Any]:
        clz = type(self)
        clz._logger.debug(f'default serializer type: {type(self)} '
                          f'class: {type(self).__name__} '
                          f'source: {self.get_source()} '
                          f'id: {self.get_id()} ')
        clz._logger.dump_stack(msg=f'default serializer source: {self.get_source()}',
                               heading='dummy header')
        return None

    @classmethod
    def de_serialize(cls, data: Dict[str, Any]) -> ForwardRef('TMDbMoviePageData'):
        return None

    @classmethod
    def convert_to_movie(cls,
                         movies: Union['BaseMovie', MovieType,
                                       Iterable['BaseMovie'],
                                       Iterable['MovieType']]) -> List['BaseMovie']:
        """

        :param movies:
        :return:
        """

        if not isinstance(movies, Iterable):
            temp: Union[BaseMovie, MovieType] = movies
            movies: List[BaseMovie, MovieType] = list()
            movies.append(temp)

        converted_movies: [BaseMovie] = []
        for movie in movies:
            if isinstance(movie, BaseMovie):
                converted_movies.append(movie)
            elif isinstance(movie, dict):
                tmp: MovieType = movie
                source: str = tmp[MovieField.SOURCE]
                if source == MovieField.TMDB_SOURCE:
                    converted_movies.append(TMDbMovie(movie_info=tmp))
                elif source == MovieField.LIBRARY_SOURCE:
                    converted_movies.append(LibraryMovie(movie_info=tmp))
                elif source == MovieField.TFH_SOURCE:
                    converted_movies.append(TFHMovie(movie_info=tmp))
                elif source == MovieField.ITUNES_SOURCE:
                    converted_movies.append(ITunesMovie(movie_info=tmp))

        return converted_movies

    def get_source_and_id(self) -> Tuple[str, str]:
        source: str = self.get_source()
        movie_id: str = self.get_id()
        return source, movie_id

    @staticmethod
    def get_rejection_reasons_str(failure_reasons_int: List[int]) -> List[str]:
        printable_reasons: List[str] = []
        reason_code: int
        for reason_code in failure_reasons_int:
            reason_str = MovieField.REJECTED_REASON_MAP[reason_code]
            printable_reasons.append(reason_str)

        return printable_reasons


class AbstractMovieId(BaseMovie):

    _logger: LazyLogger = None

    def __init__(self, movie_id: str, source: str) -> None:
        super().__init__(movie_id, source)

    def __str__(self) -> str:
        return str(self._movie_id)

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_id(self) -> str:
        return str(self._movie_id)

    def get_tmdb_id(self) -> Union[int, None]:
        """

        :return:
        """
        return self._tmdb_id

    def set_tmdb_id(self, tmdb_id: int = None) -> None:
        self._tmdb_id = tmdb_id

    def get_library_id(self) -> Union[None, int]:
        return self._library_id

    def get_has_trailer(self) -> bool:
        return self._has_trailer

    def set_has_trailer(self, has_trailer: bool = True) -> None:
        self._has_trailer = has_trailer

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            clz = type(self)
            clz._logger.debug(f'instances dose not match self: {type(self)} '
                              f'other: {type(other)}')
            raise NotImplementedError()

        if other.get_id() == self.get_id():
            return True
        return False

    def __ne__(self, other):
        if not isinstance(other, type(self)):
            raise True

        return not self.__eq__(other)

    def __hash__(self):
        return self.get_id().__hash__()

    def serialize(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            MovieField.CLASS: type(self).__name__,
            MovieField.MOVIEID: self._movie_id,
            MovieField.LIBRARY_ID: self._library_id,
            MovieField.TMDB_ID: self._tmdb_id,
            MovieField.HAS_LOCAL_TRAILER: self._has_local_trailer,
            MovieField.HAS_TRAILER: self._has_trailer
        }

        return data

    @classmethod
    def de_serialize(cls, data: Dict[str, Any]) -> ForwardRef('AbstractMovieId'):
        class_type = data.get(MovieField.CLASS, None)
        if class_type is None:
            cls._logger.warning(f'Could not deserialize: {data}')
            return None
        if class_type == TMDbMovieId.__name__:
            movie = TMDbMovieId(movie_id=data[MovieField.MOVIEID])
            movie.set_local_trailer(data.get(MovieField.HAS_LOCAL_TRAILER))
            movie.set_has_trailer(data.get(MovieField.HAS_TRAILER))
            movie.set_library_id(data.get(MovieField.LIBRARY_ID))
            movie.set_tmdb_id(data.get(MovieField.TMDB_ID))
        elif class_type == LibraryMovieId.__name__:
            movie = LibraryMovieId(movie_id=data[MovieField.MOVIEID])
            movie.set_local_trailer(data.get(MovieField.HAS_LOCAL_TRAILER))
            movie.set_has_trailer(data.get(MovieField.HAS_TRAILER))
            movie.set_library_id(data.get(MovieField.LIBRARY_ID))
            movie.set_tmdb_id(data.get(MovieField.TMDB_ID))
        elif class_type == TFHMovieId.__name__:
            movie = TFHMovieId(movie_id=data[MovieField.MOVIEID])
            movie.set_local_trailer(data.get(MovieField.HAS_LOCAL_TRAILER))
            movie.set_has_trailer(data.get(MovieField.HAS_TRAILER))
            movie.set_tmdb_id(data.get(MovieField.TMDB_ID))
        elif class_type == ITunesMovieId.__name__:
            movie = ITunesMovieId(movie_id=data[MovieField.MOVIEID])
            movie.set_local_trailer(data.get(MovieField.HAS_LOCAL_TRAILER))
            movie.set_has_trailer(data.get(MovieField.HAS_TRAILER))
            movie.set_tmdb_id(data.get(MovieField.TMDB_ID))
        else:
            cls._logger.warning(f'Unrecognized Movie class: {class_type}')
            return None
        return movie


class TMDbMovieId(AbstractMovieId):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str) -> None:
        super().__init__(movie_id, MovieField.TMDB_SOURCE)
        self._has_trailer = False
        #
        # To keep consistent with other AbstractMovieId's
        #
        self.set_tmdb_id(int(movie_id))

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_tmdb_id(self) -> Union[int, None]:
        """
            Expensive operation if remote TMDB is consulted.
            Can throw CommunicationException
        :return:
        """
        return int(self._movie_id)

    def get_source(self) -> str:
        return MovieField.TMDB_SOURCE

    def set_library_id(self, library_id: str = None) -> None:
        self._library_id = library_id


class TMDbMoviePageData(TMDbMovieId):

    def __init__(self, movie_id: str = None, movie_info: MovieType = None):
        """
        TMDbMoviePageData is different from other movie ID types in that
        it has movie_info in addition to just the id. To be consistent with
        the other types, we need the ID, either through the movie_id field,
        or from movie_info.

        :param movie_id:
        :param movie_info:
        """

        # Assume movie_id was passed
        if movie_id is None:
            movie_id = str(movie_info['id'])
        super().__init__(movie_id)
        self._cached: bool = False
        if movie_info is None:
            self._movie_info = {}
        else:
            self._movie_info = movie_info
        self.set_id(int(movie_id))

    def get_certification_id(self) -> str:
        return self._movie_info[MovieField.CERTIFICATION_ID]

    def set_certification_id(self, certification_id: str) -> None:
        self._movie_info[MovieField.CERTIFICATION_ID] = certification_id

    def get_discovery_state(self) -> str:  # DiscoveryState:
        return self._movie_info.setdefault(MovieField.DISCOVERY_STATE,
                                           MovieField.NOT_INITIALIZED)

    def set_discovery_state(self, state: str) -> None:   # DiscoveryState):
        self._movie_info[MovieField.DISCOVERY_STATE] = state

    def get_genre_ids(self) -> List[str]:
        return self._movie_info.setdefault(MovieField.TMDB_GENRE_IDS, [])

    def set_genre_ids(self, genre_ids: List[int]) -> None:
        self._movie_info[MovieField.TMDB_GENRE_IDS] = genre_ids

    def get_original_title(self) -> str:
        return self._movie_info.setdefault(MovieField.ORIGINAL_TITLE, '')

    def set_original_title(self, original_title: str) -> None:
        self._movie_info[MovieField.ORIGINAL_TITLE] = original_title

    def is_source(self, source: str) -> bool:
        return self.get_source() == source

    # def set_source(self, source: str) -> None:
    #     super().set_source()

    def get_title(self) -> str:
        return self._movie_info.get(MovieField.TITLE)

    def set_title(self, title: str) -> None:
        self._movie_info[MovieField.TITLE] = title

    def get_year(self) -> int:
        return self._movie_info.get(MovieField.YEAR, 0)

    def set_year(self, year: int) -> None:
        try:
            int_year: int = int(year)
        except:
            clz = type(self)
            clz._logger.error(f'Invalid year: {year} for movie: {self.get_title()} '
                              f'source: {self.get_source()}')
            return
        if year is not None:
            self._movie_info[MovieField.YEAR] = year

    def is_cached(self) -> bool:
        return self._cached

    def set_cached(self, cached: bool) -> None:
        self._cached = cached

    def get_original_language(self) -> str:
        return self._movie_info.setdefault(MovieField.ORIGINAL_LANGUAGE, '')

    def set_original_language(self, original_language: str) -> None:
        self._movie_info[MovieField.ORIGINAL_LANGUAGE] = original_language

    def is_original_language_matches(self, language_to_compare: str) -> bool:
        return self.get_original_language().lower == language_to_compare.lower()

    def is_original_language_matches_current_language(self) -> bool:
        lang = Settings.get_lang_iso_639_1().lower()
        return self.is_original_language_matches(lang)

    def is_original_language_present(self) -> bool:
        return self.get_original_language() != ''

    def is_language_information_found(self) -> bool:
        return self._movie_info.setdefault(MovieField.LANGUAGE_INFORMATION_FOUND, False)

    def is_original_language_found(self) -> bool:
        return self._movie_info.setdefault(MovieField.LANGUAGE_MATCHES, False)

    def set_is_original_language_found(self, is_original_language_found: bool) -> None:
        self._movie_info[MovieField.LANGUAGE_MATCHES] = is_original_language_found

    def set_buffer_number(self, page_number: int) -> int:
        self._movie_info[MovieField.TMDB_BUFFER_NUMBER] = page_number
        return page_number

    def get_buffer_number(self) -> int:
        return self._movie_info.setdefault(MovieField.TMDB_BUFFER_NUMBER, 0)

    def get_popularity(self) -> float:
        return self._movie_info.get(MovieField.TMDB_POPULARITY, 0.0)

    def set_popularity(self, popularity: float) -> None:
        self._movie_info[MovieField.TMDB_POPULARITY] = popularity

    def get_rating(self) -> float:  # 0 .. 10
        return self._movie_info.setdefault(MovieField.RATING, 0.0)

    def set_rating(self, rating: float) -> None:
        self._movie_info[MovieField.RATING] = float(rating)

    def get_runtime(self) -> int:
        return self._movie_info.setdefault(MovieField.RUNTIME, 0)

    def set_runtime(self, seconds: int) -> None:
        self._movie_info[MovieField.RUNTIME] = seconds

    def set_total_pages(self, total_pages: int) -> int:
        self._movie_info[MovieField.TMDB_TOTAL_PAGES] = total_pages
        return total_pages

    def get_total_pages(self) -> int:
        return self._movie_info[MovieField.TMDB_TOTAL_PAGES]

    def get_tmdb_id_not_found(self) -> Union[bool, None]:
        return self._movie_info.get(MovieField.TMDB_ID_FINDABLE, None)

    def is_tmdb_id_findable(self) -> bool:
        """
        Returns False IFF this movie is marked as not having a TMDB_ID
        :return:
        """
        return self._movie_info.get(MovieField.TMDB_ID_FINDABLE, True)

    def set_tmdb_id_findable(self, findable: bool) -> None:
        self._movie_info[MovieField.TMDB_ID_FINDABLE] = findable

    def update(self, imported_movie_data: Union[MovieType,
                                                'AbstractMovie']):
        if isinstance(imported_movie_data, AbstractMovie):
            self._movie_info.update(imported_movie_data._movie_info)
        else:
            self._movie_info.update(imported_movie_data)

    def get_votes(self) -> int:
        return self._movie_info.setdefault(MovieField.VOTES, 0)

    def set_votes(self, votes: int) -> None:
        self._movie_info[MovieField.VOTES] = votes

    def set_id(self, tmdb_id: int):
        self._movie_id = str(tmdb_id)

    def get_id(self) -> str:
        return str(self._movie_id)

    def get_trailer_type(self) -> str:
        """
        Trailer type is unknown, return ''
        :return:
        """
        return ''

    def get_as_movie_type(self) -> Dict[str, Any]:
        return self._movie_info

    def serialize(self) -> Dict[str, Any]:
        data: Dict[str, Any] = self.get_as_movie_type().copy()
        data[MovieField.CLASS] = type(self).__name__
        data['id'] = self.get_id()
        return data

    @classmethod
    def de_serialize(cls, data: Dict[str, Any]) -> ForwardRef('TMDbMoviePageData'):
        class_type = data.get(MovieField.CLASS, None)
        if class_type is None:
            cls._logger.warning(f'Could not deserialize: {data}')
            # TODO: Remove Hack
            return None
            # class_type = 'TMDbMoviePageData'
        if class_type == TMDbMoviePageData.__name__:
            return TMDbMoviePageData(movie_info=data)
        else:
            cls._logger.warning(f'Unrecognized Movie class: {class_type}')
            return None

    def get_source(self) -> str:
        return MovieField.TMDB_SOURCE


class TFHMovieId(AbstractMovieId):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str) -> None:
        super().__init__(movie_id, MovieField.TFH_SOURCE)

    def get_source(self) -> str:
        return MovieField.TFH_SOURCE

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)


class LibraryMovieId(AbstractMovieId):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str) -> None:
        super().__init__(movie_id, MovieField.LIBRARY_SOURCE)
        self.set_library_id(int(movie_id))

    def get_source(self) -> str:
        return MovieField.LIBRARY_SOURCE

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)


class FolderMovieId(AbstractMovieId):
    _logger: LazyLogger = None

    '''
    For a Folder movie, the id is the file name. We know nothing else
    about the movie.
    '''
    def __init__(self, movie_id: str) -> None:
        super().__init__(movie_id, MovieField.FOLDER_SOURCE)
        self.set_folder_id(movie_id)

    def get_source(self) -> str:
        return MovieField.FOLDER_SOURCE

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)


class ITunesMovieId(AbstractMovieId):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str) -> None:
        super().__init__(movie_id, MovieField.ITUNES_SOURCE)

    def get_source(self) -> str:
        return MovieField.ITUNES_SOURCE

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)


class RawMovie(BaseMovie):

    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = None,
                 movie_info: MovieType = None) -> None:
        #
        # Nasty circular dependency here. BaseMovie.__init__() calls
        # self.setId, which some classes override to save into _movie_info.
        # Define _movie_info here, but BaseMovie may alter it, so we
        # have to preserve any changes.

        self._movie_info: MovieType = {}
        super().__init__(movie_id, source)
        if movie_info is None:
            movie_info = {}
        temp_movie_info: MovieType = movie_info.copy()
        for key, value in self._movie_info.items():
            temp_movie_info[key] = value

        self._movie_info = temp_movie_info
        self.set_source(source)  # Force sync to movie_info

    def __str__(self) -> str:
        return self.get_title()

    def null_check(self) -> None:
        clz = type(self)
        nulls_found: List[str] = []
        for (key, value) in self._movie_info.items():
            if value is None:
                nulls_found.append(key)

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if len(nulls_found) > 0:
                clz._logger.debug_extra_verbose(', '.join(nulls_found))

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_property_with_default(self, property_name: str,
                                  default_value: Any = None) -> Any:
        return self._movie_info.get(property_name, default_value)

    def get_property(self, property_name: str, default=None) -> Any:
        return self._movie_info.get(property_name, default)

    def set_property(self, property_name: str, value: Any) -> None:
        self._movie_info[property_name] = value

    def del_property(self, property_name) -> None:
        if property_name in self._movie_info:
            del self._movie_info[property_name]

    def get_as_movie_type(self) -> MovieType:
        return self._movie_info

    def is_source(self, source: str) -> bool:
        return self.get_source() == source

    def set_source(self, source: str) -> None:
        """
        TODO: Rename this

        :param: source Source is the movie source (Library, TFH, etc.) that
                      requires this object. Normally this is the same as
                      the database that this object's data originated.
                      However, if a movie requires additional information,
                      such as when a TFH movie needs supplemental info
                      from TMDb, then the source of the TMDBMovie is
                      TFH.

        """
        super().set_source(source)
        self._movie_info[MovieField.SOURCE] = source

    def set_cached(self, cached: bool = True) -> None:
        self._movie_info[MovieField.CACHED] = cached

    def get_cached(self) -> bool:
        self._movie_info.setdefault(MovieField.CACHED, False)
        return self._movie_info[MovieField.CACHED]

    def serialize(self) -> Dict[str, Any]:
        data: Dict[str, Any] = self.get_as_movie_type().copy()
        data[MovieField.CLASS] = type(self).__name__
        return data

    @classmethod
    def de_serialize(cls, data: Dict[str, Any]) -> ForwardRef('AbstractMovie'):
        class_type = data.get(MovieField.CLASS, None)
        if class_type is None:
            cls._logger.warning(f'Could not deserialize: {data}')
            return None
        if class_type == LibraryMovie.__name__:
            return LibraryMovie(movie_info=data)
        if class_type == TMDbMovie.__name__:
            return TMDbMovie(movie_info=data)
        if class_type == TFHMovie.__name__:
            return TFHMovie(movie_info=data)
        if class_type == ITunesMovie.__name__:
            return ITunesMovie(movie_info=data)
        if class_type == FolderMovie.__name__:
            return FolderMovie(movie_info=data)
        if class_type == RawMovie.__name__:
            return RawMovie(movie_info=data)
        else:
            cls._logger.warning(f'Unrecognized Movie class: {class_type}')
            return None


class AbstractMovie(RawMovie):

    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = None,
                 movie_info: MovieType = None) -> None:
        #
        # TODO: Remove if we keep RawMovie
        #
        # Nasty circular dependency here. BaseMovie.__init__() calls
        # self.setId, which some classes override to save into _movie_info.
        # Define _movie_info here, but BaseMovie may alter it, so we
        # have to preserve any changes.

        self._movie_info: MovieType = {}
        super().__init__(movie_id, source)
        if movie_info is None:
            movie_info = {}
        temp_movie_info: MovieType = movie_info.copy()
        for key, value in self._movie_info.items():
            temp_movie_info[key] = value

        self._movie_info = temp_movie_info

        # Starving is ONLY used by PlayableTrailerService to tell
        # BackEndBridge that some starvation is occurring. This allows
        # the back-end to notify the front-end.
        # This perhaps should be done by modifying the iterator which
        # PlayableTrailerService and BackEndBridge use.

        self._starving: bool = False

        self.set_source(source)  # Force sync to movie_info
        if CHECK_FOR_NULLS:
            self.null_check()

        # Fix transient data

        self.set_has_trailer(self.has_trailer_path())
        self.validate_local_trailer()
        self.set_has_trailer(self.has_trailer_path())
        self.set_has_been_fully_discovered(
            movie_info.get(MovieField.FULLY_DISCOVERED, False))

    def __str__(self) -> str:
        return self.get_title()

    def null_check(self) -> None:
        clz = type(self)
        nulls_found: List[str] = []
        for (key, value) in self._movie_info.items():
            if value is None:
                nulls_found.append(key)

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if len(nulls_found) > 0:
                clz._logger.debug_extra_verbose(', '.join(nulls_found))

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_property_with_default(self, property_name: str,
                                  default_value: Any = None) -> Any:
        return self._movie_info.get(property_name, default_value)

    def get_property(self, property_name: str, default=None) -> Any:
        return self._movie_info.get(property_name, default)

    def set_property(self, property_name: str, value: Any) -> None:
        self._movie_info[property_name] = value

    def del_property(self, property_name) -> None:
        if property_name in self._movie_info:
            del self._movie_info[property_name]

    def get_as_movie_type(self) -> MovieType:
        return self._movie_info

    def get_discovery_state(self) -> str:  # DiscoveryState:
        return self._movie_info.setdefault(MovieField.DISCOVERY_STATE,
                                           MovieField.NOT_INITIALIZED)

    def set_discovery_state(self, state: str) -> None:   # DiscoveryState):
        self._movie_info[MovieField.DISCOVERY_STATE] = state

    # def get_source(self) -> str:
    #    return self._movie_info[MovieField.SOURCE]

    def is_source(self, source: str) -> bool:
        return self.get_source() == source

    def set_source(self, source: str) -> None:
        """
        TODO: Rename this

        :param: source Source is the database which this movie data originates
                       from: (Library, TFH, etc.). Sometimes additional data is
                       needed from another database to provide enough details to
                       the user. In these cases, the code knows which alternate
                       databases to look into and the data is merged into the
                       original movie instance just prior to display to the user.
                       However, when the data is discovered from other databases,
                       additional Movie instances are created and optionally
                       cached. The knowledge of the relationship is kept in
                       BaseReverseIndexCache as well as its subclasses.

                       Additionally, the key-ids for the databases are stored
                       as part of the original Movie entry, but this does not
                       confirm that data from the other databases are used,
                       just the means to look up the same movie in another
                       database.

        """
        super().set_source(source)
        self._movie_info[MovieField.SOURCE] = source

    def get_title(self) -> str:
        return self._movie_info.get(MovieField.TITLE)

    def set_title(self, title: str) -> None:
        self._movie_info[MovieField.TITLE] = title

    def set_alt_titles(self, alt_titles: List[Tuple[str, str]]) -> None:
        # Each entry is: (Alt-title, country_code)
        self._movie_info[MovieField.ALT_TITLES] = alt_titles

    def get_year(self) -> int:
        return self._movie_info.get(MovieField.YEAR, 0)

    def set_year(self, year: int) -> None:
        try:
            int_year: int = int(year)
        except:
            clz = type(self)
            clz._logger.error(f'Invalid year: {year} for movie: {self.get_title()} '
                              f'source: {self.get_source()}')
            return
        if year is not None:
            self._movie_info[MovieField.YEAR] = year

    def set_cached(self, cached: bool = True) -> None:
        self._movie_info[MovieField.CACHED] = cached
        self.validate_local_trailer()

    def get_cached(self) -> bool:
        self._movie_info.setdefault(MovieField.CACHED, False)
        return self._movie_info[MovieField.CACHED]

    def get_cached_trailer(self) -> Union[str, None]:
        clz = type(self)
        cached_path: str = self._movie_info.setdefault(MovieField.CACHED_TRAILER, '')
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.debug_extra_verbose(f'movie: {self.get_title()} source: '
                                            f'{self.get_source()} '
                                            f'cached_path: {cached_path}')
        return cached_path

    def has_cached_trailer(self):
        clz = type(self)
        is_cached: bool = self.get_cached_trailer() != ''
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.debug_extra_verbose(f'cached: {is_cached}')
        return is_cached

    def set_cached_trailer(self, path: Union[str, None]) -> None:
        self._movie_info[MovieField.CACHED_TRAILER] = path

    def get_normalized_trailer_path(self) -> Union[str, None]:
        norm_path: str = self._movie_info.setdefault(MovieField.NORMALIZED_TRAILER, '')
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.debug_extra_verbose(f'movie: {self.get_title()} source: '
                                            f'{self.get_source()} '
                                            f'normalized path: {norm_path}')
        return norm_path

    def has_normalized_trailer(self) -> bool:
        clz = type(self)
        is_normalized = self.get_normalized_trailer_path() != ''
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.debug_extra_verbose(f'movie: {self.get_title()} source: '
                                            f'{self.get_source()} '
                                            f'is_normalized: {is_normalized}')
        return is_normalized

    def set_has_trailer(self, has_trailer: bool = True) -> None:
        self._has_trailer = has_trailer
        if self.has_trailer_path() and not self.is_trailer_url():
            self.set_local_trailer(True)

        self.validate_local_trailer()

    def validate_local_trailer(self) -> None:
        """
            Verifies that has_local_trailer value agrees with calculated value
            Calculated value is True iff at least one of the following
            is true:
                has_trailer_path() that is local
                has_normalized_trailer()
                has_cached_trailer()

            The validation is only performed if the calculated value is True.

            To properly determine value would require more expensive check
            for presence of cache file (see

        """
        # has_local_trailer calculates it's value from other settings
        # set_local_trailer sets a simple value

        local_trailer: bool = None
        if self.has_normalized_trailer():
            local_trailer = True
        if self.has_cached_trailer():
            local_trailer = True
        if self.has_trailer_path() and not self.is_trailer_url():
            local_trailer = True

        if local_trailer is not None:
            if self._has_local_trailer != local_trailer:
                clz = type(self)
                clz._logger.debug(f'calculated local trailer != set value '
                                  f'movie: {self.get_title()} '
                                  f'id: {self.get_id()} '
                                  f'set value: {self._has_local_trailer} '
                                  f'calculated: {local_trailer} '
                                  f'path: {self.get_trailer_path()}')
                LazyLogger.dump_stack(heading="calculated local trailer")

    def set_normalized_trailer_path(self, path: str) -> None:
        self._movie_info[MovieField.NORMALIZED_TRAILER] = path
        self.validate_local_trailer()

    def get_certification_id(self) -> str:
        certification_id: str = self._movie_info.get(MovieField.CERTIFICATION_ID, '')
        return certification_id

    def set_certification_id(self, certification: str) -> None:
        self._movie_info[MovieField.CERTIFICATION_ID] = certification

    def has_directors(self) -> bool:
        return len(self.get_directors()) > 0

    def get_directors(self) -> List[str]:
        return self._movie_info.setdefault(MovieField.DIRECTOR, [])

    def set_directors(self, directors: List[str]) -> None:
        # Eliminate duplicates (should be very rare)
        self._movie_info[MovieField.DIRECTOR] = list(set(directors))

    def get_detail_directors(self) -> str:
        return ', '.join(self.get_directors())

    def has_fanart(self) -> bool:
        return self.get_fanart('') != ''

    def get_fanart(self, default=None) -> Union[str, None]:
        return self._movie_info.get(MovieField.FANART, default)

    def set_fanart(self, path: str) -> None:
        self._movie_info[MovieField.FANART] = path

    def get_genre_names(self) -> List[str]:
        """
        Returns names of genres in the source database schema
        #  TODO: probably should change to internal Genre id format
        :return:
        """
        return self._movie_info.setdefault(MovieField.GENRE_NAMES, [])

    def set_genre_names(self, genres: List[str]) -> None:
        self._movie_info[MovieField.GENRE_NAMES] = genres

    def is_language_information_found(self) -> bool:
        return self._movie_info.setdefault(MovieField.LANGUAGE_INFORMATION_FOUND, False)

    def set_is_language_information_found(self, found: bool) -> None:
        self._movie_info[MovieField.LANGUAGE_INFORMATION_FOUND] = found

    def get_library_id(self) -> Union[int, None]:
        return self._movie_info.get(MovieField.MOVIEID, None)

    def set_library_id(self, library_id: int = None) -> None:
        self._movie_info[MovieField.MOVIEID] = library_id

    def has_library_id(self) -> bool:
        is_has_library_id = False
        if self.get_library_id() is not None:
            is_has_library_id = True

        return is_has_library_id

    def get_movie_path(self) -> str:
        return self._movie_info.setdefault(MovieField.FILE, '')

    def set_movie_path(self, path: str) -> None:
        self._movie_info[MovieField.FILE] = path

    def is_original_language_found(self) -> bool:
        return self._movie_info.setdefault(MovieField.LANGUAGE_MATCHES, False)

    def set_is_original_language_found(self, is_original_language_found: bool) -> None:
        self._movie_info[MovieField.LANGUAGE_MATCHES] = is_original_language_found

    def get_original_title(self) -> str:
        return self._movie_info.setdefault(MovieField.ORIGINAL_TITLE, '')

    def set_original_title(self, original_title: str) -> None:
        self._movie_info[MovieField.ORIGINAL_TITLE] = original_title

    def get_plot(self) -> str:
        return self._movie_info.setdefault(MovieField.PLOT, '')

    def set_plot(self, plot: str) -> None:
        self._movie_info[MovieField.PLOT] = plot

    def get_rating(self) -> float:  # 0 .. 10
        return self._movie_info.setdefault(MovieField.RATING, 0.0)

    def set_rating(self, rating: float) -> None:
        self._movie_info[MovieField.RATING] = float(rating)

    def get_runtime(self) -> int:
        if self._movie_info.get(MovieField.RUNTIME) is None:
            x = 1
        return self._movie_info.setdefault(MovieField.RUNTIME, 0)

    def set_runtime(self, seconds: int) -> None:
        if seconds is None:
            seconds = 0

        self._movie_info[MovieField.RUNTIME] = seconds

    def has_studios(self) -> bool:
        return len(self.get_studios()) > 0

    def get_studios(self) -> List[str]:
        return self._movie_info.setdefault(MovieField.STUDIO, [])

    def set_studios(self, studios_arg: List[str]) -> None:

        if len(studios_arg) > MovieField.MAX_STUDIOS:
            studios = studios_arg[:MovieField.MAX_STUDIOS - 1]
        else:
            studios = studios_arg

        self._movie_info[MovieField.STUDIO] = studios

    def get_detail_studios(self) -> str:
        return ', '.join(self.get_studios())

    def set_unique_ids(self, ids: Dict[str, str]):
        self._movie_info[MovieField.UNIQUE_ID] = ids

    def is_tmdb_id_findable(self) -> bool:
        """
        Returns False IFF we have tried to find the TMDB ID in the past
        and failed. (No point in repeatedly trying.)

        :return:
        """
        return self._movie_info.get(MovieField.TMDB_ID_FINDABLE, True)

    def set_tmdb_id_findable(self, findable: bool) -> None:
        self._movie_info[MovieField.TMDB_ID_FINDABLE] = findable

    def get_tag_names(self) -> List[str]:  # TODO: eliminate!
        return self._movie_info.setdefault(MovieField.TMDB_TAG_NAMES, [])

    def set_tag_names(self, keywords: List[str]) -> None:
        self._movie_info[MovieField.TMDB_TAG_NAMES] = keywords

    def get_tag_ids(self) -> List[str]:  # TODO: eliminate!
        return self._movie_info.setdefault(MovieField.TMDB_TAG_IDS, [])

    def set_tag_ids(self, keywords: List[str]) -> None:
        self._movie_info[MovieField.TMDB_TAG_IDS] = keywords

    def has_thumbnail(self) -> bool:
        return self.get_thumbnail('') != ''

    def get_thumbnail(self, default: str = None) -> Union[str, None]:
        return self._movie_info.get(MovieField.THUMBNAIL, default)

    def set_thumbnail(self, path: str) -> None:
        self._movie_info[MovieField.THUMBNAIL] = path

    def get_trailer_path(self) -> str:
        return self._movie_info.setdefault(MovieField.TRAILER, '')

    def set_trailer_path(self, path: str) -> None:
        #
        # TODO: This is nuts. Need to rework these xxtrailerxx methods
        #
        self._movie_info[MovieField.TRAILER] = path
        # clz = type(self)
        # clz._logger.debug(f'path: {path} '
        #                   f'get_trailer_path: {self.get_trailer_path()}')
        # clz._logger.debug(f'has_trailer_path: {self.has_trailer_path()}')
        self.set_has_trailer(self.has_trailer_path())
        # clz._logger.debug(f'has_trailer_path: {self.has_trailer_path()}')
        if self.has_trailer_path() and not self.is_trailer_url():
            # clz._logger.debug(f'setting local_trailer')
            self.set_local_trailer(True)
            # clz._logger.debug(f'has_local_trailer: {self._has_local_trailer} '
            #                   f'has_local_trailer: {self.has_local_trailer()}')

        self.validate_local_trailer()

    def get_optimal_trailer_path(self) -> Tuple[bool, bool, str]:
        """
        Get the best path available, in order of preference:
            - normalized path
            - cached path
            - path (best path)

        :return: (is_normalized, is_cached, path)
        """
        clz = type(self)
        is_normalized: bool = False
        is_cached: bool = False
        trailer_path: str = None
        if self.has_normalized_trailer():
            trailer_path = self.get_normalized_trailer_path()
            is_normalized = True
        elif self.has_cached_trailer():
            trailer_path = self.get_cached_trailer()
            is_cached = True
        else:
            trailer_path = self.get_trailer_path()

        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.debug_extra_verbose(f'normalized: {is_normalized} cached: '
                                            f'{is_cached} path: {trailer_path}')
        return is_normalized, is_cached, trailer_path

    def is_trailer_url(self) -> bool:
        trailer_path = self.get_trailer_path()
        return trailer_path.startswith('plugin://') or trailer_path.startswith('http')

    def is_trailer_played(self) -> bool:
        return self._movie_info[MovieField.TRAILER_PLAYED]

    def is_tfh(self) -> bool:
        return isinstance(self, TFHMovie)

    def is_folder_source(self) -> bool:
        return isinstance(self, FolderMovie)

    def set_trailer_played(self, value: bool) -> None:
        self._movie_info[MovieField.TRAILER_PLAYED] = value

    def has_trailer_path(self) -> bool:
        return self.get_trailer_path() != ''

    def get_trailer_type(self) -> str:  # TODO: Change to TrailerType
        return self._movie_info.get(MovieField.TRAILER_TYPE,
                                    MovieField.TRAILER_TYPE_TRAILER)

    def set_trailer_type(self, trailer_type: str) -> None:
        clz = type(self)
        if trailer_type not in MovieField.TRAILER_TYPES:
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                clz._logger.debug_extra_verbose(f'trailer_type {trailer_type}'
                                                f' not found. Movie:'
                                                f' {self.get_title()} source:'
                                                f' {self.get_source()}')
            trailer_type = MovieField.TRAILER_TYPE_TRAILER

        self._movie_info[MovieField.TRAILER_TYPE] = trailer_type

    def update(self, imported_movie_data: Union[AbstractMovieId,
                                                'AbstractMovie']):
        if isinstance(imported_movie_data, AbstractMovie):
            self._movie_info.update(imported_movie_data._movie_info)
        else:
            self._movie_info.update(imported_movie_data)

    def get_votes(self) -> int:
        return self._movie_info.setdefault(MovieField.VOTES, 0)

    def set_votes(self, votes: int) -> None:
        self._movie_info[MovieField.VOTES] = votes

    def has_actors(self) -> bool:
        return len(self.get_actors()) > 0

    def get_actors(self) -> List[str]:
        """
        Gets ordered list of actors for this movies, in order of billing.
        Maximum of MovieField.MAX_DISPLAYED_ACTORS returned.
        :return:
        """
        return self._movie_info.get(MovieField.ACTORS, [])

    def set_actors(self, actors: List[str]) -> None:
        if len(actors) > MovieField.MAX_ACTORS:
            actors = actors[:MovieField.MAX_ACTORS - 1]

        self._movie_info[MovieField.ACTORS] = actors

    def has_writers(self) -> bool:
        return len(self.get_writers()) > 0

    def get_detail_actors(self) -> str:
        return', '.join(self.get_actors())

    def get_writers(self) -> List[str]:
        return self._movie_info.setdefault(MovieField.WRITER, [])

    def set_writers(self, writers_arg: List[str]) -> None:
        # There can be duplicates (script, book, screenplay...)
        duplicate_writers: Set[str] = set()
        writers: List[str] = []
        writer: str
        for writer in writers_arg:
            if writer not in duplicate_writers:
                duplicate_writers.add(writer)
                writers.append(writer)

        if len(writers) > MovieField.MAX_WRITERS:
            writers = writers[:MovieField.MAX_WRITERS - 1]

        self._movie_info[MovieField.WRITER] = writers

    def get_detail_writers(self) -> str:
        movie_writers = ', '.join(self.get_writers())
        return movie_writers

    def get_voiced_detail_writers(self) -> List[str]:
        writers = self.get_writers()
        if len(writers) > MovieField.MAX_VOICED_WRITERS:
            writers = writers[:(MovieField.MAX_VOICED_WRITERS - 1)]

        return writers

    def get_voiced_actors(self) -> List[str]:
            #  TODO: change set to loop
        actors: List[str] = list(set(self.get_actors()))  # In case not unique

        if len(actors) > MovieField.MAX_VOICED_ACTORS:
            actors = actors[:MovieField.MAX_VOICED_ACTORS - 1]
        return actors

    def get_voiced_directors(self) -> List[str]:
        #  TODO: change set to loop
        directors: List[str] = list(set(self.get_directors()))  # In case not unique

        if len(directors) > MovieField.MAX_VOICED_DIRECTORS:
            directors = directors[:MovieField.MAX_VOICED_DIRECTORS - 1]
        return directors

    def get_detail_certification(self) -> str:
        certification: Certification = \
            WorldCertifications.get_certification_by_id(self.get_certification_id())
        return certification.get_label()

    def get_certification_image_path(self) -> str:
        certification: Certification = \
            WorldCertifications.get_certification_by_id(
                self.get_certification_id(), default_unrated=True)

        cert_path: str = f'{certification.get_country_id()}/{certification.get_image()}'
        return cert_path

    def get_detail_genres(self) -> str:
        return ' / '.join(self.get_genre_names())

    def get_detail_runtime(self) -> str:
        runtime: int = self.get_runtime()
        delta_time: datetime.timedelta = datetime.timedelta(seconds=runtime)
        hours: int = int(delta_time.total_seconds() // 3600)
        minutes: int = int((delta_time.total_seconds() % 3600) // 60)
        seconds: int = int(delta_time.total_seconds() % 60)
        return f'{hours:}:{minutes:02}:{seconds:02}'

    def get_detail_title(self) -> str:
        # Avoid circular dependency
        from common.messages import Messages
        trailer_type = self.get_trailer_type()
        trailer_type_msg = Messages.get_msg(trailer_type)

        year: str = str(self.get_year())
        if year != '' and year != '0':
            year = ' (' + year + ')'
        else:
            year = ''

        # A movie from a remote source (tmdb) may also be in local library.

        sources = self.get_source()
        if not isinstance(self, LibraryMovie) and self.has_library_id():
            sources += ' / ' + MovieField.LIBRARY_SOURCE

        title_string: str = f'{self.get_title()}{year} - {sources} {trailer_type_msg}'
        return title_string

    def set_voiced_detail_directors(self, directors: List[str]) -> None:
        if len(directors) > MovieField.MAX_VOICED_DIRECTORS:
            self._movie_info[MovieField.VOICED_DIRECTORS] = \
                directors[:MovieField.MAX_VOICED_DIRECTORS - 1]
        else:
            self._movie_info[MovieField.VOICED_DIRECTORS] = directors

    def get_voiced_studios(self) -> List[str]:
        studios: List[str] = self.get_studios()
        if len(studios) > MovieField.MAX_VOICED_STUDIOS:
            studios = studios[:MovieField.MAX_VOICED_STUDIOS - 1]
        return studios

    def get_itunes_id(self) -> str:
        return self._movie_info.get(MovieField.ITUNES_ID)

    def set_itunes_id(self, itunes_id: str) -> None:
        self._movie_info[MovieField.ITUNES_ID] = itunes_id

    def get_tfh_id(self) -> str:
        return self._movie_info.get(MovieField.TFH_ID)

    def set_tfh_id(self, tfh_id: str) -> None:
        self._movie_info[MovieField.TFH_ID] = tfh_id

    def get_id(self) -> str:
        raise NotImplemented

    def get_tmdb_id(self) -> Union[int, None]:
        try:
            tmdb_id_str: str = self.get_unique_id(MovieField.UNIQUE_ID_TMDB)
            tmdb_id: int = None
            if tmdb_id_str is not None:
                try:
                    tmdb_id = int(tmdb_id_str)
                except ValueError:
                    pass
            return tmdb_id
        except Exception as e:
            clz = type(self)
            clz._logger.log_exception()

    def set_tmdb_id(self, tmdb_id: int = None) -> bool:
        super().set_tmdb_id(tmdb_id)
        return self.add_unique_id(MovieField.UNIQUE_ID_TMDB, str(tmdb_id))

    def get_unique_id(self, key: str) -> str:
        clz = type(self)
        try:
            return self.get_unique_ids().get(key, None)
        except Exception as e:
            clz._logger.log_exception()

    def get_unique_ids(self) -> Dict[str, str]:
        clz = type(self)
        # TODO: Change to Dict[UniqueIdType]
        #  TODO: See movie_entry_utils. It checks for imdb in tmdb field
        #  Also fetches tmdb on demand

        try:
            return self._movie_info.setdefault(MovieField.UNIQUE_ID, {})
        except Exception as e:
            clz._logger.log_exception()

    def add_unique_id(self, id_type: str, value: str) -> bool:
        clz = type(self)
        old_value: Any = None
        try:
            old_value: Union[str, None] = self.get_unique_ids().get(id_type, None)
            self.get_unique_ids()[id_type] = value
            if id_type == MovieField.UNIQUE_ID_TMDB:
                tmdb_id: int = None
                try:
                    tmdb_id = int(value)
                except ValueError:
                    pass
                except Exception:
                    clz._logger.exception()
                super().set_tmdb_id()
        except Exception as e:
            clz._logger.log_exception()

        changed: bool = False
        if old_value is None and value is not None:
            changed = True
        elif old_value != value:
            changed = True

        return changed

    def add_tmdb_id(self, tmdb_id: int) -> bool:
        try:
            return self.set_tmdb_id(tmdb_id)
        except Exception as e:
            clz = type(self)
            clz._logger.log_exception()

    def get_imdb_id(self) -> int:
        try:
            imdb_id: int = None
            imdb_id_str = self.get_unique_id(MovieField.UNIQUE_ID_IMDB)
            if imdb_id_str is not None and not imdb_id_str.startswith('tt'):
                imdb_id_str = None
            if imdb_id_str is None:
                imdb_id_str = self.get_unique_id(MovieField.UNIQUE_ID_UNKNOWN)
            if imdb_id_str is not None and not imdb_id_str.startswith('tt'):
                imdb_id_str = None

            if imdb_id_str is not None:
                try:
                    imdb_id = int(imdb_id_str[2:])
                except ValueError:
                    pass

            return imdb_id
        except Exception as e:
            clz = type(self)
            clz._logger.log_exception()

    def is_starving(self, reset: bool = True) -> bool:
        """
            Used ONLY to inform BackEndBridge that discovery is slow at the moment
            and that a recently played trailer may be sent to avoid black-screen
            in front-end.

            :param reset: Clears starving flag once read. Not persisted
        """
        starving: bool = self._starving
        if reset:
            self._starving = False
        return starving

    def set_starving(self, starving: bool):
        """
           Used ONLY to inform BackEndBridge that discovery is slow at the moment
           and that a recently played trailer may be sent to avoid black-screen
           in front-end.
        """
        self._starving = starving

    def get_serializable(self) -> Dict[str, Any]:
        data: Dict[str, Any] = self.get_as_movie_type().copy()
        data[MovieField.CLASS] = type(self).__name__
        data[MovieField.FULLY_DISCOVERED] = self.is_been_fully_discovered()
        return data

    @classmethod
    def de_serialize(cls, data: Dict[str, Any]) -> ForwardRef('AbstractMovie'):
        class_type = data.get(MovieField.CLASS, None)
        if class_type is None:
            cls._logger.warning(f'Could not deserialize: {data}')
            return None
        if class_type == LibraryMovie.__name__:
            return LibraryMovie(movie_info=data)
        if class_type == TMDbMovie.__name__:
            return TMDbMovie(movie_info=data)
        if class_type == TFHMovie.__name__:
            return TFHMovie(movie_info=data)
        if class_type == ITunesMovie.__name__:
            return ITunesMovie(movie_info=data)
        if class_type == FolderMovie.__name__:
            return FolderMovie(movie_info=data)
        else:
            cls._logger.warning(f'Unrecognized Movie class: {class_type}')
            return None

    def is_sane(self, sane_values: MovieType) -> bool:
        clz = type(self)
        if not clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            return True

        sane = True
        title: str = self.get_title()
        missing_keys: List[str] = []
        missing_values: List[str] = []
        wrong_types: List[str] = []
        for key in sane_values:
            if key not in self._movie_info:
                sane = False
                missing_keys.append(key)
            elif self._movie_info.get(key) is None and sane_values.get(key) is not None:
                missing_values.append(key)
                sane = False
            else:
                try:
                    if not isinstance(sane_values[key], type(self._movie_info[key])):
                        x = type(sane_values[key])
                        y = type(self._movie_info[key])
                        wrong_types.append(f'{x} {y} {key}')
                        sane = False
                except Exception:
                    clz._logger.exception(f'type mismatch for movie: {title} '
                                          f'{self._movie_id} key: {key}')

        if len(missing_keys) > 0 or len(missing_values) > 0 or len(wrong_types) > 0:
            clz._logger.debug_extra_verbose(f'movie: {title} {self._movie_id}')
        if len(missing_keys) > 0:
            clz._logger.debug_extra_verbose(f'  Missing values:'
                                            f' {", ".join(missing_keys)}')
        if len(missing_values) > 0:
            clz._logger.debug_extra_verbose(f'None values for: '
                                            f'{", ".join(missing_values)}')
        if len(wrong_types) > 0:
            clz._logger.debug_extra_verbose(f'Wrong value type: {", ".join(wrong_types)}')
        return sane

    def is_represents_same_instance(self, other: BaseMovie) -> bool:
        same: bool = False
        if self is other:
            return True
        if self.get_id() != other.get_id():
            return False
        if self.get_source() == other.get_source():
            return True
        return False


class MovieWrapper(AbstractMovie):
    '''
    Provides a simple wrapper around the older MovieType dict and type
    it so that it can be passed as a normal Movie (by extending
    AbstractMovie). Likely, the data is minimally property and may
    not represent a movie at all.
    '''
    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = None,
                 movie_info: MovieType = None) -> None:
        if movie_info is not None:
            movie_id = movie_info.get(MovieField.MOVIEID, None)
        super().__init__(movie_id, source, movie_info)

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)


class LibraryMovie(AbstractMovie):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = None,
                 movie_info: MovieType = None) -> None:
        if movie_info is not None:
            movie_id = movie_info.get(MovieField.MOVIEID, None)
        super().__init__(movie_id, MovieField.LIBRARY_SOURCE, movie_info)

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_id(self) -> str:
        return str(self.get_property(MovieField.MOVIEID))

    def set_id(self, library_id: str):
        self.set_library_id(int(library_id))
        self._movie_id = library_id

    def add_unique_id(self, id_type: str, value: str) -> bool:
        changed: bool = super().add_unique_id(id_type, value)

        # We found an id from TMDB, update Kodi database
        # so that we don't have to go through this again

        if changed and Settings.get_update_tmdb_id():
            from backend.movie_entry_utils import MovieEntryUtils
            MovieEntryUtils.update_database_unique_id(self)
        return changed

    def get_last_played(self) -> datetime.datetime:
        return self._movie_info.get(MovieField.LAST_PLAYED)

    def get_days_since_last_played(self) -> int:
        """
            Get the number of days since this movie (not the trailer)
            was last played. For invalid or missing values, -1 will be
            returned.
        """
        clz = type(self)
        days_since_played = 365
        try:
            last_play = datetime.datetime.now() - self.get_last_played()
            days_since_played = last_play.days
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')

        return days_since_played

    def set_last_played(self, last_played: datetime.datetime) -> None:
        self._movie_info[MovieField.LAST_PLAYED] = last_played

    # This is for a movie's tags/keywords from Kodi. Kodi does not care
    # about the representation, it is just whatever was downloaded by the
    # scraper. Most likely this is a TMDb or IMDb tag.
    #
    # Note that for movie info downloaded by this plugin from TMDb that
    # there are the methods get_tmdb_tag_ids and get_tmdb_tag_names.

    # GenreUtils handles genres and keywords and is sensitive to where
    # the keyword/genre originated from.

    def get_tags(self) -> List[str]:
        tags: List[str] = self._movie_info.get(MovieField.TAG, [])
        return tags

    def set_tags(self, tags: List[str]) -> None:
        self._movie_info[MovieField.TAG] = tags
        return

    def get_source(self) -> str:
        return MovieField.LIBRARY_SOURCE

    def get_as_movie_id_type(self) -> LibraryMovieId:
        clz = type(self)
        movie_id: LibraryMovieId = LibraryMovieId(self.get_id())
        movie_id.set_tmdb_id(self.get_tmdb_id())
        movie_id.set_local_trailer(self.has_local_trailer())
        movie_id.set_has_trailer(self.get_has_trailer())
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(f'movie_id: {movie_id} '
                                            f'type: {type(movie_id)} '
                                            f'id: {movie_id.get_id()} '
                                            f'tmdb_id: {movie_id.get_tmdb_id()} '
                                            f'has_local_trailer: '
                                            f'{movie_id.has_local_trailer()} '
                                            f'get_has_trailer: '
                                            f'{movie_id.get_has_trailer()}')
        return movie_id


class TMDbMovie(AbstractMovie):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = None,
                 movie_info: MovieType = None) -> None:
        # self.set_id(movie_id) called by constructor
        # self.set_id calls self.set_tmdb_id

        if movie_info is None:
            movie_info: MovieType = MovieField.DEFAULT_MOVIE.copy()

        super().__init__(movie_id, MovieField.TMDB_SOURCE, movie_info)
        if self._movie_id is None:
            self._movie_id = self.get_tmdb_id()  # If already in movie_info

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_id(self) -> str:
        return str(self.get_tmdb_id())

    def set_id(self, tmdb_id: str):
        self.set_tmdb_id(int(tmdb_id))
        self._movie_id = tmdb_id

    def get_as_movie_id_type(self) -> TMDbMovieId:
        clz = type(self)
        tmdb_movie_id: TMDbMovieId = TMDbMovieId(self.get_id())
        tmdb_movie_id.set_library_id(self.get_library_id())
        tmdb_movie_id.set_local_trailer(self.has_local_trailer())
        tmdb_movie_id.set_has_trailer(self.get_has_trailer())
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug(f'tmdb_movie_id: {tmdb_movie_id} '
                              f'type: {type(tmdb_movie_id)} '
                              f'id: {tmdb_movie_id.get_id()} '
                              f'has_local_trailer: '
                              f'{tmdb_movie_id.has_local_trailer()} '
                              f'get_has_trailer: '
                              f'{tmdb_movie_id.get_has_trailer()}')
        return tmdb_movie_id

    def get_original_language(self) -> str:
        return self._movie_info.setdefault(MovieField.ORIGINAL_LANGUAGE, '')

    def set_original_language(self, original_language: str) -> None:
        self._movie_info[MovieField.ORIGINAL_LANGUAGE] = original_language

    def is_original_language_matches(self, language_to_compare: str) -> bool:
        return self.get_original_language().lower == language_to_compare.lower()

    def is_original_language_matches_current_language(self) -> bool:
        lang = Settings.get_lang_iso_639_1().lower()
        return self.is_original_language_matches(lang)

    def is_original_language_present(self) -> bool:
        return self.get_original_language() != ''

    def get_genre_ids(self) -> List[str]:
        return self._movie_info.setdefault(MovieField.TMDB_GENRE_IDS, [])

    def set_genre_ids(self, genre_ids: List[str]) -> None:
        self._movie_info[MovieField.TMDB_GENRE_IDS] = genre_ids

    def get_source(self) -> str:
        return MovieField.TMDB_SOURCE

    '''
    def is_raw_tmdb_data(self) -> bool:
        #
        # This method distinguishes between old and new cache formats
        #
        # TODO:  Remove temp hack
        #
        # Old cache stored raw data from TMDb, now save TMDbLibrary
        # entry, mostly to reduce size of .json files
        #
        if MovieField.LAST_PLAYED in self._movie_info:
            return False
        return True
    '''


class TFHMovie(AbstractMovie):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = MovieField.TFH_SOURCE,
                 movie_info: MovieType = None) -> None:
        # self.set_id(movie_id) called by constructor
        # self.set_id calls self.set_tfh_id

        # if movie_info is None:
        #    movie_info: MovieType = MovieField.DEFAULT_MOVIE.copy()
        super().__init__(movie_id, MovieField.TFH_SOURCE, movie_info)
        if self._movie_id is None:
            self.set_id(self.get_tfh_id())

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_id(self) -> str:
        return str(self.get_tfh_id())

    def set_id(self, tfh_id: str):
        self.set_tfh_id(tfh_id)
        self._movie_id = tfh_id

    def get_tfh_title(self) -> str:
        return self._movie_info.get(MovieField.TFH_TITLE, '')

    def set_tfh_title(self, tfh_title: str) -> None:
        self._movie_info[MovieField.TFH_TITLE] = tfh_title

    def get_genre_ids(self) -> List[str]:
        return self._movie_info.setdefault(MovieField.TMDB_GENRE_IDS, [])

    def set_genre_ids(self, genre_ids: List[str]) -> None:
        self._movie_info[MovieField.TMDB_GENRE_IDS] = genre_ids

    def get_source(self) -> str:
        return MovieField.TFH_SOURCE

    def get_as_movie_id_type(self) -> TFHMovieId:
        """
        Converts this fully-populated Movie into a MovieId.

        In the case of TFH, some data may come from TMDb, so we save
        a reference to TMDb as well
        """
        clz = type(self)
        movie_id: TFHMovieId = TFHMovieId(self.get_id())
        movie_id.set_tmdb_id(self.get_tmdb_id())
        movie_id.set_local_trailer(self.has_local_trailer())
        movie_id.set_has_trailer(self.get_has_trailer())
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug(f'movie_id: {movie_id} '
                              f'type: {type(movie_id)} '
                              f'id: {movie_id.get_id()} '
                              f'tmdb_id: {movie_id.get_tmdb_id()} '
                              f'has_local_trailer: {movie_id.has_local_trailer()} '
                              f'get_has_trailer: {movie_id.get_has_trailer()}')
        return movie_id


class ITunesMovie(AbstractMovie):
    _logger: LazyLogger = None

    def __init__(self, movie_id: str = None, source: str = MovieField.ITUNES_SOURCE,
                 movie_info: MovieType = None) -> None:
        if movie_info is None:
            movie_info: MovieType = MovieField.DEFAULT_MOVIE.copy()

        # self.set_id(movie_id) called by constructor
        # self.set_id calls self.set_itunes_id

        super().__init__(movie_id, MovieField.ITUNES_SOURCE, movie_info)
        if self._movie_id is None:
            self.set_id(self.get_itunes_id())

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_id(self) -> str:
        return str(self.get_property(MovieField.ITUNES_ID))

    def set_id(self, itunes_id: str) -> None:
        self.set_itunes_id(itunes_id)
        self._movie_id = itunes_id

    def set_release_date(self, release_date: datetime.date) -> None:
        self._movie_info[MovieField.RELEASE_DATE] = release_date

    def get_release_date(self) -> datetime.date:
        return self._movie_info.setdefault(MovieField.RELEASE_DATE,
                                           datetime.datetime.today())

    def get_file(self) -> str:
        return ''

    def get_rating(self) -> float:
        return 0.0

    def set_rating(self, rating: float) -> None:
        # This is a bogus rating, but validator likes it and it ain't too
        # hard just to make it happy.

        super().set_rating(0.0)

    def get_source(self) -> str:
        return MovieField.ITUNES_SOURCE

    def get_as_movie_id_type(self) -> ITunesMovieId:
        clz = type(self)
        movie_id: ITunesMovieId = ITunesMovieId(self.get_id())
        movie_id.set_tmdb_id(self.get_tmdb_id())
        movie_id.set_local_trailer(self.has_local_trailer())
        movie_id.set_has_trailer(self.get_has_trailer())
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug(f'movie_id: {movie_id} '
                              f'type: {type(movie_id)} '
                              f'id: {movie_id.get_id()} '
                              f'tmdb_id: {movie_id.get_tmdb_id()} '
                              f'has_local_trailer: {movie_id.has_local_trailer()} '
                              f'get_has_trailer: {movie_id.get_has_trailer()}')
        return movie_id


class FolderMovie(AbstractMovie):
    _logger: LazyLogger = None

    def __init__(self, movie_info: MovieType = None) -> None:
        super().__init__(None, MovieField.FOLDER_SOURCE, movie_info)
        if self._movie_id is None:
            self._movie_id = self.get_id()
        self.set_tmdb_id_findable(False)

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    def get_id(self) -> str:
        if self._movie_id is None:
            self._movie_id = self.get_trailer_path()

        return self.get_trailer_path()

    def get_as_movie_id_type(self) -> FolderMovieId:
        clz = type(self)
        movie_id: FolderMovieId = FolderMovieId(self.get_id())
        movie_id.set_tmdb_id(self.get_tmdb_id())
        movie_id.set_local_trailer(self.has_local_trailer())
        movie_id.set_has_trailer(self.get_has_trailer())
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(f'movie_id: {movie_id} '
                                            f'type: {type(movie_id)} '
                                            f'id: {movie_id.get_id()} '
                                            f'tmdb_id: {movie_id.get_tmdb_id()} '
                                            f'has_local_trailer: '
                                            f'{movie_id.has_local_trailer()} '
                                            f'get_has_trailer: '
                                            f'{movie_id.get_has_trailer()}')
        return movie_id

    def get_source(self) -> str:
        return MovieField.FOLDER_SOURCE


BaseMovie.class_init()
AbstractMovieId.class_init()
TMDbMovieId.class_init()
TFHMovieId.class_init()
LibraryMovieId.class_init()
ITunesMovieId.class_init()
RawMovie.class_init()
AbstractMovie.class_init()
LibraryMovie.class_init()
TMDbMovie.class_init()
TFHMovie.class_init()
ITunesMovie.class_init()
FolderMovie.class_init()


class Movies:
    LIB_TMDB_ITUNES_TFH_SOURCES = (LibraryMovie, LibraryMovieId,
                                   TMDbMovie, TMDbMovieId,
                                   ITunesMovie, ITunesMovieId,
                                   TFHMovie, TFHMovieId)
