# -*- coding: utf-8 -*-
"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import os
import sys
import threading
from contextlib import closing
import xmltodict
import xbmcvfs

from common.exceptions import AbortException
from common.constants import Constants, GenreEnum
from common.imports import *
from common.logger import LazyLogger
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings

"""

    GenreUtils is the primary interface 
    
    The concept of Genres and Tags is complicated by the fact that different databases
    have different concepts about what is a Tag or Genre. Further, mapping genres and 
    tags from one site to the next is much less than perfect.
    
    For example, IMDB, TCM and AFI consider Film Noir a genre, but TMDB does not.
    Instead, on TMDB movies are identified as "Film Nor" by user-defined tags 
    which is roughly "Film-Nor, brit-noir, neo-noir, classic-noir" and others. 
    
    To accommodate this mess, a _RandomTrailersGenre defines a genre which wraps
    the equivalent genres/tags from TMDB, IMDB and ITunes. Usually a 
    _RandomTrailersGenre maps to either a site-specific genre or tag(s), but
    sometimes both (Film Noir).
"""

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

TMDB_SOURCE: Final[str] = 'tmdb'
IMDB_SOURCE: Final[str] = 'imdb'
ITUNES_SOURCE: Final[str] = 'itunes'


class _KodiToExternalDBMapping:
    """
        The internal representation of a Genre or Tag is the same:
        each consists of a kodi and external representation.
        The kodi representation is the value used in the Kodi database.
        The external representation is the value used in the remote
        database (IMDB, TMDB, etc.).
    """

    def __init__(self, kodi_id: str, external_id: str = None):
        """
            Constructor Mapping a Kodi Genre to an external
            database Tag or Genre. If external_id is None,
            then will be set to kodi_id

        :param kodi_id: Kodi
        :param external_id:
        """
        self._kodi_id = kodi_id
        if external_id is None:
            self._external_id = kodi_id
        else:
            self._external_id = external_id

    def get_kodi_id(self) -> str:
        """
        Gets the Kodi database representation of this Tag or Genre
        :return: str  Kodi database ID
        """
        return self._kodi_id

    def get_external_id(self) -> str:
        """
        Gets the external database representation of this Tag or Genre

        :return:  str  External database ID
        """
        return self._external_id


class _TagEntry(_KodiToExternalDBMapping):
    """
        Contains the Kodi and external (IMDB, TMDB, etc.) representations
        of a keyword/tag.
    """

    def __init__(self, kodi_id: str,
                 external_id: str = None) -> None:
        """
            Constructor Mapping a Kodi Genre  to an external
            database Tag.

            Note that if external_id is None, then will be set to kodi_id

        :param kodi_id: str Kodi database ID
        :param external_id: str External database ID
        """
        super().__init__(kodi_id, external_id)


class _GenreEntry(_KodiToExternalDBMapping):
    """
        Contains the Kodi and external (IMDB, TMDB, etc.) representations
        of a genre
    """

    def __init__(self, kodi_id: str,
                 external_id: str = None) -> None:
        """
            Constructor Mapping a Kodi Genre to an external
            database Tag.

            Note that if external_id is None, then will be set to kodi_id

        :param kodi_id: str Kodi database ID
        :param external_id: str External database ID
        """
        super().__init__(kodi_id, external_id)


class _BaseGenreEntry:
    """
        Represents a conceptual genre that is mapped to external tags and genres.

        Represents a conceptual genre which is mapped to zero or more external database
        genres and possibly zero or more external database tags/keywords. An example
        is "Film Noir" which can be represented in TMDB by the keywords: film noir,
        classic noir, etc.

        At the time of this writing there is at most one external genre, but this is
        not a requirement.
    """

    def __init__(self, genre_id: str,
                 genre_name: str,
                 genre_name_id: str) -> None:
        """
                Constructor Mapping a Kodi Genre to an external
                database genre.
        """
        self._genre_id = genre_id
        self._genre_name = genre_name
        self._genre_name_id = genre_name_id
        self._genre_entries = []
        self._tag_entries = []

    def add_external_tag(self, tag: _TagEntry) -> None:
        self._tag_entries.append(tag)

    def add_external_genre(self, genre: _GenreEntry) -> None:
        self._genre_entries.append(genre)

    def get_genre_id(self) -> str:
        return self._genre_id

    def get_name_id(self) -> str:
        return self._genre_name_id

    def get_label(self) -> str:
        label = Messages.get_msg(self._genre_name_id)
        if label == self._genre_name_id:
            label = self._genre_name

        return label

    def get_genres(self) -> List[_GenreEntry]:
        """
            Gets the list of Genre_Entries that this this Kodi genre is mapped  to

        :return: List[_GenreEntry]
        """
        return self._genre_entries

    def get_genre_ids_for_external_search(self) -> List[str]:
        """
            Gets the list of external database genre ids for searching

            Used to query the external database.

        :return: List[str]
        """
        external_ids = []
        for genre in self._genre_entries:
            external_ids.append(genre.get_external_id())
        return external_ids

    def get_tags(self) -> List[_TagEntry]:
        """
            Gets the list of Tag_Entries that this Kodi genre is mapped to

        :return: List[_TagEntry]
        """

        return self._tag_entries


class Genres:
    _logger = None
    _source_map = dict()
    _allowed_genres = None
    _lock = threading.RLock()
    _initialized = False

    def __init__(self) -> None:
        pass

    @classmethod
    def add_genre(cls, source: str, genre: _BaseGenreEntry) -> None:
        map_for_source = cls._source_map.get(source, None)
        if map_for_source is None:
            map_for_source = dict()
            cls._source_map[source] = map_for_source

        map_for_source[genre.get_genre_id()] = genre

    @classmethod
    def get_genres(cls, genre_id: str,
                   sources: List[str]) -> List[_BaseGenreEntry]:
        result: List[_BaseGenreEntry] = []
        for source in sources:
            result.extend(cls._source_map[source][genre_id])

        return result

    @classmethod
    def get_allowed_genres(cls) -> List[_BaseGenreEntry]:
        with cls._lock:
            if cls._allowed_genres is None:
                try:
                    LoadGenreDefinitions()
                    allowed_genres: List[_BaseGenreEntry] = []
                    for source in cls._source_map.keys():
                        allowed_genres.extend(cls._source_map[source].values())

                    cls._allowed_genres = allowed_genres
                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    cls._logger.exception()
                    cls._allowed_genres = []  # To prevent hang

        return cls._allowed_genres

    @classmethod
    def get_genre_ids(cls) -> List[str]:
        genre_ids = []

        for genre in cls.get_allowed_genres():
            genre_ids.append(genre.get_genre_id())

        return list(set(genre_ids))

    @classmethod
    def get_genre_and_source_by_id(cls,
                                   genre_id: str) -> List[Tuple[str, _BaseGenreEntry]]:
        genre_and_source = []
        for source in cls._source_map.keys():
            genre = cls._source_map[source].get(genre_id, None)
            if genre is not None:
                genre_and_source.append((source, genre))

        return genre_and_source


class LoadGenreDefinitions:
    '''
    Load certification information from XML files. Each file contains the
    certifications used by typically one country (although certifications
    for multiple countries can be in the same file).
    '''

    _logger = None

    def __init__(self) -> None:
        cls = type(self)
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            try:
                path = os.path.join(Constants.ADDON_PATH,
                                    'resources', 'genres')
                for file in os.listdir(path):
                    xml_file = os.path.join(path, file)
                    if (file.endswith('.xml') and
                            os.path.isfile(xml_file)):
                        try:
                            with closing(xbmcvfs.File(xml_file)) as content_file:
                                rules = xmltodict.parse(
                                    bytes(content_file.readBytes()))
                                cls._create_genres(xml_file, rules)
                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            cls._logger.exception('Failed to parse {}'
                                                  .format(file))
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.exception(e)

        pass

    @classmethod
    def _create_genres(cls,
                       pathname: str, rules: dict) -> None:
        if rules is None:
            cls._logger.error('{} contains invalid XML.'.format(pathname))
            return

        genres_element = rules.get('genres', None)
        if genres_element is None:
            cls._logger.error('Can not find "genres" entity in {}'
                              .format(pathname))
            return

        source_attribute = genres_element.get('@source', None)
        if source_attribute is None:
            cls._logger.error('Can not find "source attribute" entity in {}'
                              .format(pathname))
            return

        genre_elements = genres_element.get('genre', None)
        if genre_elements is None:
            cls._logger.error('Can not find "genre element" entity in {}'
                              .format(pathname))
            return

        for genre_element in genre_elements:

            genre_id = genre_element.get('@id', None)
            if genre_id is None:
                cls._logger.error('Missing genre "id" attribute in {}'
                                  .format(pathname))
                genre_id = 'Missing'

            genre_name = genre_element.get('@name', None)
            if genre_name is None:
                cls._logger.error('Missing "genre name" attribute in {}'
                                  .format(pathname))
                genre_name = 'Missing'

            genre_name_id = genre_element.get('@name_id', None)
            if genre_name_id is None:
                cls._logger.error('Missing "genre name_id" attribute in {}'
                                  .format(pathname))
                genre_name_id = 'Missing'

            genre = _BaseGenreEntry(genre_id, genre_name, genre_name_id)
            external_genre_element = genre_element.get(
                'external_genre', None)

            if external_genre_element is not None:
                if not isinstance(external_genre_element, list):
                    external_genre_element = [external_genre_element]

                for external_genre in external_genre_element:
                    external_genre_id = external_genre.get('@id', None)
                    external_id = external_genre.get('@external_id', None)

                    genre.add_external_genre(
                        _GenreEntry(external_genre_id, external_id))

            external_tag_element = genre_element.get('external_tag', None)

            if external_tag_element is not None:
                if not isinstance(external_tag_element, list):
                    external_tag_element = [external_tag_element]

                for external_tag in external_tag_element:
                    external_tag_id = external_tag.get('@id', None)
                    external_id = external_tag.get('@external_id', None)

                    genre.add_external_tag(
                        _TagEntry(external_tag_id, external_id))

            Genres.add_genre(source_attribute, genre)


class _RandomTrailersGenre:
    """
        Provides the Genres which are exposed to the user for searching.

        Kodi Genres are created from the scraping process. The scraped genres depend
        upon which site the scraper uses (imdb, tmdb, Rotten Tomatoes, among
        others). Kodi does NOT translate external Genres to some "Kodi" genre.
        The values stored in the Kodi database are taken directly from the
        external source. The classes here map a "Random Trailers" genre to the
        underlying genres and keywords/tags from the various sources that
        movies and trailers come from.

        Kodi Tags are also created from the scraping process. Some sites
        may have a specific genre (say, imdb Film-Noir) while others use a tag
        (tmdb film noir). There can be a very large number of tags, many
        which are rarely used. In addition, tag use is very subjective. At
        least on TMDB any user who can edit can define new tags. This results
        in misspellings, ('corean war') or language variations (lobor vs labour).
        Further, it is clumsy to see what is
        already defined, so you end up with different users using different
        words for the same thing. Sigh.

       """

    _logger = None
    _instances = None  # type: Dict[str, _RandomTrailersGenre]
    _lock = threading.RLock()
    _initialized = False

    def __init__(self,
                 genre_source_list: List[Tuple[str, _BaseGenreEntry]]) -> None:
        """
        """
        cls = type(self)
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
        self._tmdb_genre = None
        self._imdb_genre = None
        self._itunes_genre = None
        for source, genre in genre_source_list:
            if source == TMDB_SOURCE:
                self._tmdb_genre = genre

            elif source == IMDB_SOURCE:
                self._imdb_genre = genre
            elif source == ITUNES_SOURCE:
                self._itunes_genre = genre
            else:
                cls._logger.error('Invalid source: {}'.format(source))

        _, a_genre = genre_source_list[0]
        self._genre_id = a_genre.get_genre_id()
        self._translatable_label_id = a_genre.get_name_id()
        self._is_preselected = False
        self._filter_value = False
        if cls._instances is None:
            cls._instances: Dict[str, _RandomTrailersGenre] = {}

        cls._instances[self._genre_id] = self

    @classmethod
    def create_instances(cls) -> None:
        LoadGenreDefinitions()
        for genre_id in Genres.get_genre_ids():
            genre_source_list = Genres.get_genre_and_source_by_id(genre_id)
            _RandomTrailersGenre(genre_source_list)

    @classmethod
    def get_allowed_genres(cls):  # type: ()-> List[_RandomTrailersGenre]
        with cls._lock:
            if cls._instances is None:
                try:
                    cls.create_instances()
                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    cls._logger.exception(e)
                    # To prevent lockup/repeated failures
                    cls._instances: Dict[str, _RandomTrailersGenre] = {}

        allowed_genres: List[_RandomTrailersGenre] = list(cls._instances.values())
        return allowed_genres

    def get_id(self) -> str:
        return self._translatable_label_id

    def get_genre_id(self) -> str:
        """

        :return: unique genre id
        """
        return self._genre_id

    def get_setting_id(self) -> str:
        return 'g_' + self.get_genre_id()

    def get_label(self) -> str:
        """
            Gets translated label for the genre

        :return:
        """
        return Messages.get_msg(self._translatable_label_id)

    def get_tmdb_genre(self) -> _BaseGenreEntry:
        """
            Gets the TMDB specific query and database ids corresponding to this
            RandomTrailers genre.

        :return:
        """

        return self._tmdb_genre

    def get_itunes_genre(self) -> _BaseGenreEntry:
        """
            Get the iTunes specific query and database ids corresponding to
            this RandomTrailers genre.
        :return:
        """
        return self._itunes_genre

    def get_imdb_genre(self) -> _BaseGenreEntry:
        """
            Get the IMDB specific query and database ids corresponding to
            this RandomTrailers genre.
            :return:
        """
        return self._imdb_genre

    def get_filter_value(self) -> int:
        """
            True if this genre was selected by the user

        :return:
        """
        return self._filter_value

    def ui_select(self, selection: int) -> None:
        """
            Provides a means to select or deselect a genre
        :param selection:
        :return: None
        """
        self._filter_value = selection

    def reset_ui_selection(self) -> None:
        """
            Resets a genre's selection to the default value
        :return:
        """
        self._filter_value = GenreEnum.IGNORE

    def append_to_query(self, query: str,
                        new_query_segment: str) -> str:
        """
            Returns the comma separated concatenation of the given query
             and sub-query
        :param query:
        :param new_query_segment:
        :return:
        """
        separator = ''
        if len(query) > 0 and len(new_query_segment) > 0:
            separator = ', '

        return query + separator + new_query_segment

    def get_genres(self, destination_id: int) -> List[_GenreEntry]:
        """
            Get all of the genres that apply to the given database. Note that
            when the database is the local Kodi database, then all genres for all
            databases are returned. This is because the values from all of the
            databases are imported into the local database.

            :param destination_id Database to get Genres for
            :return: list of the applicable genres
        """
        genres = []

        if (destination_id == GenreUtils.TMDB_DATABASE
                or destination_id == GenreUtils.LOCAL_DATABASE):
            if self.get_tmdb_genre() is not None:
                genres.extend(self.get_tmdb_genre().get_genres())
        elif (destination_id == GenreUtils.ITUNES_DATABASE
              or destination_id == GenreUtils.LOCAL_DATABASE):
            if self.get_itunes_genre() is not None:
                genres.extend(self.get_itunes_genre().get_genres())
        elif (destination_id == GenreUtils.IMDB_DATABASE
              or destination_id == GenreUtils.LOCAL_DATABASE):
            if self.get_imdb_genre() is not None:
                genres.extend(self.get_imdb_genre().get_genres())
        # if (destination_id == GenreUtils.ROTTEN_TOMATOES_DATABASE
        #                    or destination_id == GenreUtils.LOCAL_DATABASE):
        #    if self.getTomatoesGenre() is not None:
        #        genres.extend(self.getTomatoesGenre().get_genre_names())

        return genres

    def get_tags(self, destination_id: int) -> List[_TagEntry]:
        """
            Get all of the tags that apply to the given database. Note that
            when the database is the local Kodi database, then all tags for all
            databases are returned. This is because the values from all of the
            databases are imported into the local database.

        :param destination_id: Database to get the Tags for
        :return: list of the applicable tags
        """
        tags = []

        if (destination_id == GenreUtils.TMDB_DATABASE
                or destination_id == GenreUtils.LOCAL_DATABASE):
            if self.get_tmdb_genre() is not None:
                tags.extend(self.get_tmdb_genre().get_tags())
        if (destination_id == GenreUtils.ITUNES_DATABASE
                or destination_id == GenreUtils.LOCAL_DATABASE):
            if self.get_itunes_genre() is not None:
                tags.extend(self.get_itunes_genre().get_tags())
        if (destination_id == GenreUtils.IMDB_DATABASE
                or destination_id == GenreUtils.LOCAL_DATABASE):
            if self.get_imdb_genre() is not None:
                tags.extend(self.get_imdb_genre().get_tags())
        # if (destination_id == GenreUtils.ROTTEN_TOMATOES_DATABASE
        #                   or destination_id == GenreUtils.LOCAL_DATABASE):
        #    tags.extend(self.getTomatoesGenre().get_tags())

        return tags


class GenreUtils:
    """
        Provides methods for discovering user selected genres,
        creation of filters and other items.
    """
    LOCAL_DATABASE = 0
    TMDB_DATABASE = 1
    ITUNES_DATABASE = 2
    IMDB_DATABASE = 3
    ROTTEN_TOMATOES_DATABASE = 4

    LOCAL_DATABASE_STR = 'local'
    TMDB_DATABASE_STR = 'tmdb'
    ITUNES_DATABASE_STR = 'itunes'
    IMDB_DATABASE_STR = 'imdb'
    ROTTEN_TOMATES_DATABASE_STR = 'rotten'

    domain_str = {LOCAL_DATABASE: LOCAL_DATABASE_STR,
                  TMDB_DATABASE: TMDB_DATABASE_STR,
                  ITUNES_DATABASE: ITUNES_DATABASE_STR,
                  IMDB_DATABASE: IMDB_DATABASE_STR,
                  ROTTEN_TOMATOES_DATABASE: ROTTEN_TOMATES_DATABASE_STR}

    _logger = None
    _settings_lock = threading.RLock()
    _settings_stale = True

    @classmethod
    def init_class(cls) -> None:
        """

        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            Monitor.register_settings_changed_listener(cls.on_settings_changed)

    @classmethod
    def on_settings_changed(cls) -> None:
        """
            Notification from Monitor that settings have changed

            Remark which genres are selected

        :return:
        """

        cls._settings_stale = True

    @classmethod
    def get_all_genres(cls) -> List[_RandomTrailersGenre]:
        """
            Gets all of the Genres supported by Random Trailers
        :return:
        """
        # Ensures initialization (does not re-initialize)

        LoadGenreDefinitions()

        allowed_genres: List[_RandomTrailersGenre]
        allowed_genres = _RandomTrailersGenre.get_allowed_genres()
        genres = sorted(
            allowed_genres, key=lambda element: element.get_label())
        return genres

    @classmethod
    def get_genres(cls, genre_state: int) -> List[_RandomTrailersGenre]:
        """
            Gets all of the genres selected via settings

        :return:
        """
        with cls._settings_lock:
            if cls._settings_stale:
                try:
                    LoadGenreDefinitions()
                    cls._mark_selected_genres()
                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    cls._logger.exception('')
                finally:
                    cls._settings_stale = False

        genres = []
        for genre in cls.get_all_genres():
            if genre.get_filter_value() == genre_state:
                genres.append(genre)
        return genres

    @classmethod
    def get_include_genres(cls) -> List[_RandomTrailersGenre]:
        """

        :return:
        """
        include_genres = cls.get_genres(GenreEnum.INCLUDE)
        return include_genres

    @classmethod
    def get_exclude_genres(cls) -> List[_RandomTrailersGenre]:
        """

        :return:
        """
        return cls.get_genres(GenreEnum.EXCLUDE)

    @classmethod
    def get_domain_genres(cls,
                          generic_genres: List[_RandomTrailersGenre],
                          genre_domain_id: int) -> List[_GenreEntry]:
        """
            Return a JSON type query segment appropriate for the
            particular destination (LOCAL_DATABASE, TMDB_DATABASE,
            etc.). Different destinations use different ids for
            genres. In some cases, tags are used instead of genres,
            so both get_genre_names and get_tags must be done.
        """
        genres = []
        for genre in generic_genres:
            genres.extend(genre.get_genres(genre_domain_id))
        return genres

    @classmethod
    def get_domain_tags(cls,
                        generic_genres: List[_RandomTrailersGenre],
                        genre_domain_id: int) -> List[_TagEntry]:
        """
            Return a JSON type query segment appropriate for the
            particular destination (LOCAL_DATABASE, TMDB_DATABASE,
            etc.). Different destinations use different ids for
            genres. In some cases, tags are used instead of genres,
            so both get_genre_names and get_tags must be done.
        """
        tags = []
        for genre in generic_genres:
            tags.extend(genre.get_tags(genre_domain_id))
        return tags

    @classmethod
    def _mark_selected_genres(cls) -> None:
        """
            Marks genre selection based on Settings
        :return:
        """
        genres = cls.get_all_genres()

        for genre in genres:
            value = Settings.get_genre(genre.get_setting_id())
            genre.ui_select(value)

        return

    @classmethod
    def get_external_genre_ids(cls,
                               genre_domain_id: int,
                               exclude: bool = False) -> List[str]:
        """
            Gets all of the "external" id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain_id:
        :param exclude: If True, then return unselected Genres
        :return: List of genre ids
        """
        genre_ids = set()

        try:
            if exclude:
                filtered_genres = cls.get_exclude_genres()
            else:
                filtered_genres = cls.get_include_genres()

            domain_selected_genres = cls.get_domain_genres(
                filtered_genres, genre_domain_id)
            for genre in domain_selected_genres:
                genre_ids.add(genre.get_external_id())

            # if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            #    genre_strings = []
            #    for genre in domain_selected_genres:
            #        genre_strings.append('{}/{}'
            #                             .format(genre.get_kodi_id(),
            #                                    genre.get_external_id()))
            #
            #    domain_str = GenreUtils.domain_str[genre_domain_id]
            #    cls._logger.debug_extra_verbose('external {} exclude: {} {}'
            #                                    .format(domain_str, exclude,
            #                                            ': '.join(genre_strings)))

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

        return list(genre_ids)

    @classmethod
    def get_internal_kodi_genre_ids(cls,
                                    genre_domain_id: int,
                                    exclude: bool = False) -> List[str]:
        """
            Gets all of the kodi database id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain_id:
        :param exclude: If True, then return unselected Genres
        :return: List of genre ids
        """
        genre_ids = set()

        try:
            if exclude:
                filtered_genres = cls.get_exclude_genres()
            else:
                filtered_genres = cls.get_include_genres()

            domain_selected_genres = cls.get_domain_genres(
                filtered_genres, genre_domain_id)
            for genre in domain_selected_genres:
                genre_ids.add(genre.get_kodi_id())

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                keyword_strings = []
                for genre in domain_selected_genres:
                    keyword_strings.append('{}/{}'
                                           .format(genre.get_kodi_id(),
                                                   genre.get_external_id()))

                domain_str = GenreUtils.domain_str[genre_domain_id]
                cls._logger.debug_extra_verbose('internal {} exclude: {} {}'
                                                .format(domain_str, exclude,
                                                        ': '.join(keyword_strings)))
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

        return list(genre_ids)

    @classmethod
    def get_external_genre_ids_as_query(cls,
                                        genre_domain_id: int,
                                        exclude: bool = False,
                                        or_operator: bool = True) -> str:
        """
            Returns a query string of selected genreids.

            In the case of TMDB, the genre values are separated by commas
            when a movie must contain all of the genres. A pipe '|'
            separator is used when a movie only need to match any of
            the genres.

            Note: only supports TMDB at this time

        :param genre_domain_id:
        :param exclude: If True, then return excluded genres
        :param or_operator:
        :return:
        """

        query_string = ''
        try:
            selected_genre_ids = cls.get_external_genre_ids(
                genre_domain_id, exclude=exclude)

            if or_operator:
                separator = '|'  # OR operations
            else:
                separator = ','  # AND operations

            query_string = separator.join(selected_genre_ids)

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                domain_str = GenreUtils.domain_str[genre_domain_id]
                cls._logger.debug_extra_verbose('query {} genre ids: {}'
                                                .format(domain_str, query_string))

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
            query_string = ''

        return query_string

    @classmethod
    def get_external_keyword_ids(cls,
                                 genre_domain_id: int,
                                 exclude: bool = False) -> List[str]:
        """
            Gets all of the "external" id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain_id:
        :param exclude: If True, then return unselected keywords/tags
        :return: List[str] List of Keyword/Tag ids
        """

        keyword_ids = set()
        try:
            if exclude:
                selected_genres = cls.get_exclude_genres()
            else:
                selected_genres = cls.get_include_genres()

            domain_selected_tags = cls.get_domain_tags(
                selected_genres, genre_domain_id)

            filtered_tags = domain_selected_tags

            for tag in filtered_tags:
                keyword_ids.add(tag.get_external_id())

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                keyword_strings = []
                for genre in filtered_tags:
                    keyword_strings.append('{}/{}'
                                           .format(genre.get_kodi_id(),
                                                   genre.get_external_id()))

                domain_str = GenreUtils.domain_str[genre_domain_id]
                cls._logger.debug_extra_verbose('external {} exclude: {} {}'
                                                .format(domain_str, exclude,
                                                        ': '.join(keyword_strings)))
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

        return list(keyword_ids)

    @classmethod
    def get_internal_kodi_keyword_ids(cls,
                                      genre_domain_id: int,
                                      exclude: bool = False) -> List[str]:
        """
            Gets all of the kodi database id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain_id:
        :param exclude: If True, then return unselected keywords/tags
        :return: List[str] List of Keyword/Tag ids
        """

        keyword_ids = set()
        try:
            if exclude:
                selected_genres = cls.get_exclude_genres()
            else:
                selected_genres = cls.get_include_genres()

            domain_selected_tags = cls.get_domain_tags(
                selected_genres, genre_domain_id)

            filtered_tags = domain_selected_tags

            for tag in filtered_tags:
                keyword_ids.add(tag.get_kodi_id())

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                keyword_strings = []
                for genre in filtered_tags:
                    keyword_strings.append(genre.get_kodi_id())

                domain_str = GenreUtils.domain_str[genre_domain_id]
                cls._logger.debug_extra_verbose('internal {} exclude: {} {}'
                                                .format(domain_str, exclude,
                                                        ': '.join(keyword_strings)))
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

        return list(keyword_ids)

    @classmethod
    def get_external_keywords_as_query(cls,
                                       genre_domain_id: int,
                                       exclude: bool = False,
                                       or_operator: bool = True) -> str:
        """
            Returns a query string of selected genre ids.

            In the case of TMDB, the genre and keyword/tag values
            are separated by commas when a movie must contain all
            of the keywords/tags. A pipe '|' separator is used when a
            movie only need to match any of the keywords/tags.

            Note: only supports TMDB at this time

        :param genre_domain_id:
        :param exclude: If True, then return unselected keywords/Tags
        :param or_operator:
        :return:
        """

        query = ''
        try:
            selected_keyword_ids = cls.get_external_keyword_ids(
                genre_domain_id, exclude=exclude)

            if or_operator:
                separator = '|'  # OR operations
            else:
                separator = ',',  # AND operations
            query = separator.join(selected_keyword_ids)

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                domain_str = GenreUtils.domain_str[genre_domain_id]
                cls._logger.debug_extra_verbose('query {} keyword ids: {}'
                                                .format(domain_str, query))
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
            string_buffer = ''

        return query

    @classmethod
    def include_movie(cls,
                      genre_names: List[str] = None,
                      tag_names: List[str] = None) -> bool:
        if not Settings.get_filter_genres():
            return True

        if genre_names is None:
            genre_names = []

        if tag_names is None:
            ignore_tags = True
            tag_names = []
        else:
            # When tags is None, they haven't been discovered yet for this
            # movie. Assume that any allowed_tag will be found.

            ignore_tags = False

        allowed_genres = GenreUtils.get_external_genre_ids(
            GenreUtils.TMDB_DATABASE, exclude=False)
        allowed_tags = GenreUtils.get_external_keyword_ids(
            GenreUtils.TMDB_DATABASE, exclude=False)
        excluded_genres = GenreUtils.get_external_genre_ids(
            GenreUtils.TMDB_DATABASE, exclude=True)
        excluded_tags = GenreUtils.get_external_keyword_ids(
            GenreUtils.TMDB_DATABASE, exclude=True)

        genre_found = False
        genre_excluded = False
        for genre_id in genre_names:
            genre_id = str(genre_id)
            if genre_id in allowed_genres:
                genre_found = True
            elif genre_id in excluded_genres:
                genre_excluded = True

        tag_found = False
        tag_excluded = False
        for tag_id in tag_names:
            tag_id = str(tag_id)
            if tag_id in allowed_tags:
                tag_found = True
            elif tag_id in excluded_tags:
                tag_excluded = True

        genre_passes = True
        if genre_found or tag_found:  # Include movie
            pass
        elif genre_excluded or tag_excluded:
            genre_passes = False

        # When ignore_tags is set, then tag information has not yet been
        # discovered, so don't fail due to tags.

        elif len(allowed_genres) == 0 and ignore_tags:
            pass

        # If user specified any Included genres or tags. Then
        # Ignored items will have no impact on selection, but
        # when none are specified, then the movie is selected,
        # unless Excluded.

        elif len(allowed_genres) == 0 and len(allowed_tags) == 0:
            pass
        else:
            genre_passes = False

        return genre_passes


GenreUtils.init_class()
