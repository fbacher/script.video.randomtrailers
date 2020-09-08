# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.constants import (Constants, GenreConstants, GenreEnum)
from common.messages import Messages
from common.logger import (Logger, LazyLogger, Trace)
from common.settings import Settings
from common.monitor import Monitor

"""

    GenreUtils is the primary interface 
    
    The concept of Genres and Tags is complicated by the fact that different databases
    have different concepts about what is a Tag or GenreUtils. Further, mapping genres and 
    tags from one site to the next is much less than perfect.
    
    For example, IMDB, TCM and AFI consider Film Noir a genre, but TMDB does not.Instead,
    movies are identified as "Film Nor" by user-defined tags which is roughly "Film-Nor,
    brit-noir, neo-noir, classic-noir" and others. 
    
    To accommodate this mess, a _RandomTrailersGenre contains the "equivalent" genre
    on multiple sites; TMDB, IMDB and ITunes. Each of these is represented by an
    implementation based on _KodiToExternalDBMapping which has which GenreUtils or Tags the 
    external site uses to represent the _RandomTrailersGenre. Usually a _RandomTrailersGenre
    maps to either a site-specific genre or tags, but sometimes both.
"""

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'backend.genreutils')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class _KodiToExternalDBMapping(object):
    """
        The internal representation of a GenreUtils or Tag is the same:
        each consists of a kodi and external representation.
        The kodi representation is the value used in the Kodi database.
        The external representation is the value used in the remote
        database (IMDB, TMDB, etc.).
    """

    def __init__(self, kodi_id, external_id=None):
        # type: (str, str) -> None
        """
            Constructor Mapping a Kodi GenreUtils to an external
            database Tag or GenreUtils. If external_id is None,
            then will be set to kodi_id

        :param kodi_id: Kodi
        :param external_id:
        """
        self._kodi_id = kodi_id
        if external_id is None:
            self._external_id = kodi_id
        else:
            self._external_id = external_id

    def get_kodi_id(self):
        # type: () -> TextType
        """
        Gets the Kodi database representation of this Tag or GenreUtils
        :return: str  Kodi database ID
        """
        return self._kodi_id

    def get_external_id(self):
        # type: () -> TextType
        """
        Gets the external database representation of this Tag or GenreUtils

        :return:  str  External database ID
        """
        return self._external_id


# noinspection Annotator
class _TagEntry(_KodiToExternalDBMapping):
    """
        Contains the Kodi and external (IMDB, TMDB, etc.) representations
        of a keyword/tag.
    """

    def __init__(self, kodi_id, external_id=None):
        # type:  (TextType, Optional[TextType]) -> None
        """
            Constructor Mapping a Kodi GenreUtils to an external
            database Tag.

            Note that if external_id is None, then will be set to kodi_id

        :param kodi_id: str Kodi database ID
        :param external_id: str External database ID
        """
        super().__init__(kodi_id, external_id)


# noinspection Annotator,PyInitNewSignature
class _GenreEntry(_KodiToExternalDBMapping):
    """
        Contains the Kodi and external (IMDB, TMDB, etc.) representations
        of a genre
    """

    def __init__(self, kodi_id, external_id=None):
        # type: (Union[str, unicode], Union[str, unicode]) -> None
        """
            Constructor Mapping a Kodi GenreUtils to an external
            database Tag.

            Note that if external_id is None, then will be set to kodi_id

        :param kodi_id: str Kodi database ID
        :param external_id: str External database ID
        """
        super().__init__(kodi_id, external_id)


class _BaseGenreEntry(object):
    """
        Represents a conceptual genre that is mapped to external tags and genres.

        Represents a conceptual genre which is mapped to zero or more external database
        genres and possibly zero or more external database tags/keywords. An example
        is "Film Noir" which can be represented in TMDB by the keywords: film noir,
        classic noir, etc.

        At the time of this writing there is at most one external genre, but this is
        not a requirement.
    """

    def __init__(self, genre_entries=None, tag_entries=None):
         # type: ( Union[_GenreEntry, List[_GenreEntry], None] ,
         # Union[_TagEntry, List[_TagEntry], None]) -> None
        """
                Constructor Mapping a Kodi GenreUtils to an external
                database genre.

            :param kodi_id: str Kodi database ID
            :param external_id: str External database ID
        """
        if genre_entries is None:
            genre_entries = []

        self._genre_entries = []
        if isinstance(genre_entries, list):
            if genre_entries is not None:
                self._genre_entries.extend(genre_entries)
        elif isinstance(genre_entries, _GenreEntry):
            self._genre_entries.append(genre_entries)

        if tag_entries is None:
            tag_entries = []

        self._tag_entries = []
        if isinstance(tag_entries, list):
            self._tag_entries.extend(tag_entries)
        else:
            self._tag_entries.append(tag_entries)

    def get_genres(self):
        # type: () -> List[_GenreEntry]
        """
            Gets the list of Genre_Entries that this this Kodi genre is mapped  to

        :return: List(_GenreEntry)
        """
        return self._genre_entries

    def get_genre_ids_for_external_search(self):
        # type: () -> List[Union[str, unicode]]
        """
            Gets the list of external database genre ids for searching

            Used to query the external database.

        :return: List[str]
        """
        external_ids = []
        for genre in self._genre_entries:
            external_ids.append(genre.get_external_id())
        return external_ids

    def get_tags(self):
        # type: () -> List[_TagEntry]
        """
            Gets the list of Tag_Entries that this Kodi genre is mapped to

        :return: List[_TagEntry]
        """

        return self._tag_entries


# noinspection Annotator
class _TMDBGenre(_BaseGenreEntry):
    """
        Encapulates data from TMDB that represents a searchable
        Random Trailers genre.

        Contains the underlying TMDB genre and tag entries. For example:
        TMDB does not have a formal  "Film Noir" genre. Rather, users have
        used various user-defined tags to indicate "Film Noir": classic noir,
        film noir, french noir, brit noir,and others.

        Other examples include:
        pre-code, short, anthology, biography, all black cast, epic,
        melodrama, musical,romantic comedy, satire, screwball, screwball comedy,
        swashbuckler, gangster, b movie, world war II, murder, suspense,
        prison, detective, world war i, love triangle, romance, spy,
        newspaper, ship, train, nightclub, gambling, hospital, blackmail,
        nurse, boston blackie, broadway, historical figure, nazi,
        private detetive, amnesia, the falcon, navy, ghost, bulldog drummond,
        philo vance, prostitute, korean war, gold digger, scotland yard,
        cult film, lone wolf, epic, the saint, nazis, the whistler,
        corruption, organized crime, golddigger, espionage, bootlegger,
        sherlock holmes,

    """

    def __init__(self, genre_entries=None, tag_entries=None):
        # type: ( Union[_GenreEntry, List[_GenreEntry], None] ,
        # Union[_TagEntry, List[_TagEntry], None]) ->None
        """
        :param genre_entries: _GenreEntry or list of entries
        :param tag_entries: _TagEntry or list of entries
        """
        super().__init__(genre_entries, tag_entries)


class _TMDBGenres(object):
    """
        Define all of the TMDB genres which Random Trailers supports
    """

    @classmethod
    def init_class(cls):
        # type: () -> None
        """
            Define all of the TMDB genres

            The external_id is the required database key that must be specified
            for queries into their database.

            Kept separate from _TMDBGenre to avoid namespace litter during
            debugging of _TMDBGenre

        :return: None
        """
        cls.TMDB_Action = _TMDBGenre(
            genre_entries=_GenreEntry('Action', external_id='28'))
        cls.TMDB_Adventure = _TMDBGenre(
            genre_entries=_GenreEntry('Adventure', external_id='12'))
        cls.TMDB_Animation = _TMDBGenre(
            genre_entries=_GenreEntry('Animation', external_id='16'))
        cls.TMDB_Antholgy = _TMDBGenre(
            tag_entries=_TagEntry('anthology', external_id='9706'))
        cls.TMDB_Biograpy = _TMDBGenre(genre_entries=None,
                                       tag_entries=_TagEntry('biography', external_id='5565'))
        cls.TMDB_Comedy = _TMDBGenre(
            genre_entries=_GenreEntry('Comedy', external_id='35'))
        cls.TMDB_Crime = _TMDBGenre(
            genre_entries=_GenreEntry('Crime', external_id='80'))
        cls.TMDB_Dark_Comedy = _TMDBGenre(
            tag_entries=_TagEntry('dark comedy', external_id='10123'))
        cls.TMDB_DOCUMENTARY = _TMDBGenre(
            genre_entries=_GenreEntry('Documentary', external_id='99'))
        cls.TMDB_Drama = _TMDBGenre(
            genre_entries=_GenreEntry('Drama', external_id='18'))
        cls.TMDB_Epic = _TMDBGenre(genre_entries=None,
                                   tag_entries=_TagEntry('epic', external_id='6917'))
        cls.TMDB_Family = _TMDBGenre(
            genre_entries=_GenreEntry('Family', external_id='10751'))
        cls.TMDB_Fantasy = _TMDBGenre(
            genre_entries=_GenreEntry('Fantasy', '14'))
        cls.TMDB_Film_Noir = _TMDBGenre(genre_entries=None,
                                        tag_entries=[_TagEntry('noir', external_id='9807'),
                                                     _TagEntry(
                                                     'film noir', external_id='195402'),
                                                     _TagEntry(
                                                     'french noir', external_id='155845'),
                                                     _TagEntry(
                                                     'brit noir', external_id='155451'),
                                                     _TagEntry(
                                                     'british noir', external_id='229206'),
                                                     _TagEntry('neonoir', external_id='207268')])
        '''
          {
      "id": 9807,
      "name": "noir"
    },
    {
      "id": 155845,
      "name": "french noir"
    },
    {
      "id": 155451,
      "name": "brit noir"
    },
    {
      "id": 180533,
      "name": "japanese noir"
    },
    {
      "id": 195402,
      "name": "film noir"
    },
    {
      "id": 247245,
      "name": "action noir"
    },
    {
      "id": 191820,
      "name": "nordic noir"
    },
    {
      "id": 211067,
      "name": "country noir"
    },
    {
      "id": 231989,
      "name": "monochrome noir"
    },
    {
      "id": 222827,
      "name": "swamp noir"
    },
    {
      "id": 229206,
      "name": "british noir"
    },
    {
      "id": 178657,
      "name": "tech noir"
    },
    {
      "id": 236189,
      "name": "future noir"
    },
    {
      "id": 238044,
      "name": "matière noir"
    },
    {
      "id": 246824,
      "name": "mexican noir"
    },
    {
      "id": 207268,
      "name": "neonoir"
    },
    {
      "id": 230784,
      "name": "noir & blanc"
    },
    {
      "id": 249631,
      "name": "scandi noir"
    }
  ],
  '''
        cls.TMDB_History = _TMDBGenre(
            genre_entries=_GenreEntry('History', external_id='36'))
        cls.TMDB_Horror = _TMDBGenre(
            genre_entries=_GenreEntry('Horror', external_id='27'))
        cls.TMDB_Melodrama = _TMDBGenre(genre_entries=None,
                                        tag_entries=_TagEntry('melodrama',
                                                              external_id='241094'))
        cls.TMDB_Music = _TMDBGenre(
            genre_entries=_GenreEntry('Music', '10402'))
        cls.TMDB_Musical = _TMDBGenre(genre_entries=None,
                                      tag_entries=_TagEntry('musical', external_id='4344'))
        cls.TMDB_Mystery = _TMDBGenre(
            genre_entries=_GenreEntry('Mystery', external_id='9648'))
        cls.TMDB_Pre_Code = _TMDBGenre(genre_entries=None,
                                       tag_entries=[_TagEntry('pre-code', external_id='156764'),
                                                    _TagEntry('hayscode', external_id='1315')])

        cls.TMDB_Romance = _TMDBGenre(
            genre_entries=_GenreEntry('Romance', '10749'))
        cls.TMDB_Romantic_Comedy = _TMDBGenre(genre_entries=None,
                                              tag_entries=_TagEntry('romantic comedy',
                                                                    external_id='9799'))
        cls.TMDB_Satire = _TMDBGenre(genre_entries=None,
                                     tag_entries=_TagEntry('satire', external_id='8201'))
        cls.TMDB_Science_Fiction = _TMDBGenre(genre_entries=_GenreEntry(
            'Science Fiction', external_id='878'))
        cls.TMDB_Screwball_Comedy = _TMDBGenre(genre_entries=None,
                                               tag_entries=[_TagEntry('screwball', external_id='160362'),
                                                            _TagEntry('screwball comedy', external_id='155457')])
        cls.TMDB_Swashbuckler = _TMDBGenre(genre_entries=None,
                                           tag_entries=_TagEntry('swashbuckler', external_id='157186'))
        cls.TMDB_Thriller = _TMDBGenre(
            genre_entries=_GenreEntry('Thriller', external_id='53'))
        cls.TMDB_TV_Movie = _TMDBGenre(
            genre_entries=_GenreEntry('TV Movie', external_id='10770'))
        cls.TMDB_War = _TMDBGenre(
            genre_entries=_GenreEntry('War', external_id='10752'))
        cls.TMDB_Western = _TMDBGenre(
            genre_entries=_GenreEntry('Western', external_id='37'))


_TMDBGenres.init_class()


# noinspection Annotator
class _iTunesGenre(_BaseGenreEntry):
    """
        Encapulates data from iTunes that represents a searchable
        Random Trailers genre.

        At least for the APIs used by Random Trailers, queries use human friendly
        values and not some index, as in the case of TMDB. Therefore,
        kodi_id and external_ids are the same. (Kodi_id is the string value
        stored in Kodi's database and comes directly from iTunes).

        iTunes has a number of Foreign films that are not english. I don't
        see any language indication, but perhaps we are not doing the
        query correctly.
      """

    def __init__(self, itunes_search_id=None, itunes_keyword=None):
        # type: ( Union[str, unicode, None], Union[str, unicode, None]) ->None
        """
            :param itunes_search_id: _GenreEntry or list of entries
            :param itunes_keyword: _TagEntry or list of entries
        """
        genre_entry = None
        if itunes_search_id is not None:
            genre_entry = _GenreEntry(itunes_search_id, itunes_search_id)
        tag_entry = None

        if itunes_keyword is not None:
            tag_entry = _TagEntry(itunes_keyword, itunes_keyword)

        super().__init__(genre_entry, tag_entry)


class _ITunesGenres(object):
    """
        Define all of the iTunes genres which Random Trailers supports
    """
    @classmethod
    def init_class(cls):
        # type: () -> None
        """
            Define all of the iTunes genres

            Kept separate from _TMDBGenre to avoid namespace litter during
            debugging of _itunes_genre

        :return: None
        """
        # Probably incomplete
        cls.iTunes_Action_And_Adventure = _iTunesGenre('Action and Adventure')
        cls.iTunes_Comedy = _iTunesGenre('Comedy')
        cls.iTunes_Documentary = _iTunesGenre('Documentary')
        cls.iTunes_Drama = _iTunesGenre('Drama')
        cls.iTunes_Family = _iTunesGenre('Family')
        cls.iTunes_History = _iTunesGenre('Foreign')
        cls.iTunes_Horror = _iTunesGenre('Horror')
        cls.iTunes_Romance = _iTunesGenre('Romance')
        cls.iTunes_Science_Fiction = _iTunesGenre('Science Fiction')
        cls.iTunes_Thriller = _iTunesGenre('Thriller')


_ITunesGenres.init_class()


# noinspection Annotator
class _IMDBGenre(_BaseGenreEntry):
    """
        Encapulates data from IMDB that represents a searchable Random
        Trailers genre.

        Even though Random Trailers does not query TMDB, one of Kodi's
        popular scrapers populates Kodi's database with data from TMDB.
        Therefore, local-database searches frequently contain these
        values.
      """

    def __init__(self, imdb_search_id=None, imdb_keywords=None):
        # type: ( Optional[TextType], Optional[TextType]) ->None
        """
            :param imdb_search_id:
            :param imdb_keywords: _
        """
        genre_entry = None
        if imdb_search_id is not None:
            genre_entry = _GenreEntry(imdb_search_id, imdb_search_id)

        tag_entry = None
        if imdb_keywords is not None:
            tag_entry = _TagEntry(imdb_keywords, imdb_keywords)

        super().__init__(genre_entry, tag_entry)


class _IMDBGenres(object):
    """
        Define all of the IMDB genres which Random Trailers supports

         IMDB Genres:
            Action, Adult, Adventure, Animation, Biography, Comedy, Crime, Documentary,
            Drama, Family, Fantasy, Film Noir, Game-Show, History, Horror, Musical,
            Music, Mystery, News, Reality-TV, Romance, Sci-Fi, Short, Sport,
            Talk-Show, Thriller, War, Western
    """
    @classmethod
    def init_class(cls):
        # type: () -> None
        """
            Define all of the iTunes genres

            Kept separate from _TMDBGenre to avoid namespace litter during
            debugging of _itunes_genre

            :return: None
        """
        cls.IMDB_Action = _IMDBGenre('Action')
        cls.IMDB_Adventure = _IMDBGenre('Adventure')
        cls.IMDB_Animation = _IMDBGenre('Animation')
        cls.IMDB_Biography = _IMDBGenre('Biography')
        cls.IMDB_Comedy = _IMDBGenre('Comedy')
        cls.IMDB_Crime = _IMDBGenre('Crime')
        cls.IMDB_Documentary = _IMDBGenre('Documentary')
        cls.IMDB_Drama = _IMDBGenre('Drama')
        cls.IMDB_Family = _IMDBGenre('Family')
        cls.IMDB_Fantasy = _IMDBGenre('Fantasy')
        cls.IMDB_Film_Noir = _IMDBGenre('Film-Noir')
        cls.IMDB_Game_Show = _IMDBGenre('Game-Show')
        cls.IMDB_History = _IMDBGenre('History')
        cls.IMDB_Horror = _IMDBGenre('Horror')
        cls.IMDB_Music = _IMDBGenre('Music')
        cls.IMDB_Musical = _IMDBGenre('Musical')
        cls.IMDB_Mystery = _IMDBGenre('Mystery')
        cls.IMDB_News = _IMDBGenre('News')
        cls.IMDB_Reality_TV = _IMDBGenre('Reality-TV')
        cls.IMDB_Romance = _IMDBGenre('Romance')
        cls.IMDB_Science_Fiction = _IMDBGenre('Sci-Fi')
        cls.IMDB_Short = _IMDBGenre('Short')
        cls.IMDB_Sport = _IMDBGenre('Sport')
        cls.IMDB_Talk_Show = _IMDBGenre('Talk-Show')
        cls.IMDB_Thriller = _IMDBGenre('Thriller')
        cls.IMDB_War = _IMDBGenre('War')
        cls.IMDB_Western = _IMDBGenre('Western')


_IMDBGenres.init_class()


class _RandomTrailersGenre(object):
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

    def __init__(self,
                 genre_id,  # type: TextType
                 translatable_label_id,  # type: TextType
                 tmdb_genre,  # type: Union[_TMDBGenre, None]
                 itunes_genre,  # type:  Union[_iTunesGenre, None]
                 imdb_genre  # type: Union[_IMDBGenre, None]
                 ):
        # type: ( ...) -> None
        """
            :param genre_id:
            :param translatable_label_id:
            :param tmdb_genre:
            :param itunes_genre:
            :param imdb_genre:
        """
        self._genre_id = genre_id
        self._translatable_lable_id = translatable_label_id
        self._tmdb_genre = tmdb_genre
        self._itunes_genre = itunes_genre
        self._imdb_genre = imdb_genre
        self._is_preselected = False
        self._filter_value = False

    def get_genre_id(self):
        # type: () -> TextType
        """

        :return: unique genre id
        """
        return self._genre_id

    def get_label(self):
        # type: () -> TextType
        """
            Gets translated label for the genre

        :return:
        """
        return Messages.get_instance().get_msg(self._translatable_lable_id)

    def get_tmdb_genre(self):
        # type: () -> _TMDBGenre
        """
            Gets the TMDB specific query and database ids corresponding to this
            RandomTrailers genre.

        :return:
        """

        return self._tmdb_genre

    def get_itunes_genre(self):
        # type: () -> _iTunesGenre
        """
            Get the iTunes specific query and datbase ids corresponding to
            this RandomTrailers genre.
        :return:
        """
        return self._itunes_genre

    def get_imdb_genre(self):
        # type: () -> _IMDBGenre
        """
            Get the IMDB specific query and datbase ids corresponding to
            this RandomTrailers genre.
            :return:
        """
        return self._imdb_genre

    def get_filter_value(self):
        """
            True if this genre was selected by the user

        :return:
        """
        return self._filter_value

    def ui_select(self, selection):
        # type: (int) -> None
        """
            Provides a means to select or deselect a genre
        :param selection:
        :return: None
        """
        self._filter_value = selection

    def reset_ui_selection(self):
        # type: () -> None
        """
            Resets a genre's selection to the default value
        :return:
        """
        self._filter_value = GenreEnum.IGNORE

    def append_to_query(self, query, new_query_segment):
        # type: (TextType, TextType) -> TextType
        """
            Returns the comma seperated concatination of the given query
             and sub-query
        :param query:
        :param new_query_segment:
        :return:
        """
        separator = ''
        if len(query) > 0 and len(new_query_segment) > 0:
            separator = ', '

        return query + separator + new_query_segment

    def get_genres(self, destination):
        # type: (TextType) -> List[_GenreEntry]
        """
            Get all of the genres that apply to the given database. Note that
            when the database is the local Kodi database, then all genres for all
            databases are returned. This is because the values from all of the
            databases are imported into the local database.

            :param destination Database to get Genres for
            :return: list of the applicable genres
        """
        genres = []

        if destination == GenreUtils.TMDB_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
            if self.get_tmdb_genre() is not None:
                genres.extend(self.get_tmdb_genre().get_genres())
        if destination == GenreUtils.ITUNES_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
            if self.get_itunes_genre() is not None:
                genres.extend(self.get_itunes_genre().get_genres())
        if destination == GenreUtils.IMDB_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
            if self.get_imdb_genre() is not None:
                genres.extend(self.get_imdb_genre().get_genres())
        # if destination == GenreUtils.ROTTEN_TOMATOES_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
        #    if self.getTomatoesGenre() is not None:
        #        genres.extend(self.getTomatoesGenre().get_genres())

        return genres

    def get_tags(self, destination):
        # type: (str) -> List[_TagEntry]
        """
            Get all of the tags that apply to the given database. Note that
            when the database is the local Kodi database, then all tags for all
            databases are returned. This is because the values from all of the
            databases are imported into the local database.

        :param destination: Database to get the Tags for
        :return: list of the applicable tags
        """
        tags = []

        if destination == GenreUtils.TMDB_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
            if self.get_tmdb_genre() is not None:
                tags.extend(self.get_tmdb_genre().get_tags())
        if destination == GenreUtils.ITUNES_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
            if self.get_itunes_genre() is not None:
                tags.extend(self.get_itunes_genre().get_tags())
        if destination == GenreUtils.IMDB_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
            if self.get_imdb_genre() is not None:
                tags.extend(self.get_imdb_genre().get_tags())
        # if destination == GenreUtils.ROTTEN_TOMATOES_DATABASE or destination == GenreUtils.LOCAL_DATABASE:
        #    tags.extend(self.getTomatoesGenre().get_tags())

        return tags


class _RandomTrailersGenres(object):
    """
        Define all of the genres which Random Trailers supports
    """
    @classmethod
    def _init_class(cls):
        # type: () -> None
        """
            Define all of the Genres which Random Trailers exposes to the
            user.

            Placed in a separate class to reduce clutter during debugging

        :return:
        """
        allowed_genres = []
        cls.RANDOM_ACTION = _RandomTrailersGenre(GenreConstants.ACTION,
                                                 Messages.GENRE_ACTION,
                                                 _TMDBGenres.TMDB_Action,
                                                 _ITunesGenres.iTunes_Action_And_Adventure,
                                                 _IMDBGenres.IMDB_Action)
        allowed_genres.append(cls.RANDOM_ACTION)
        '''
        cls.RANDOM_ALEGORY = _RandomTrailersGenre(GenreConstants.ALEGORY,
                                                 Messages.GENRE_ALEGORY,
                                                 None,
                                                 None,
                                                 None)
        allowed_genres.append(cls.RANDOM_ALEGORY)
        '''
        '''
        cls.RANDOM_ANTHOLOGY = _RandomTrailersGenre(GenreConstants.ANTHOLOGY,
                                                   Messages.GENRE_ANTHOLOGY,
                                                   None,
                                                   None,
                                                   None)
        allowed_genres.append(cls.RANDOM_ANTHOLOGY)
        '''
        cls.RANDOM_ADVENTURE = _RandomTrailersGenre(GenreConstants.ADVENTURE,
                                                    Messages.GENRE_ADVENTURE,
                                                    _TMDBGenres.TMDB_Adventure,
                                                    _ITunesGenres.iTunes_Action_And_Adventure,
                                                    _IMDBGenres.IMDB_Adventure)
        allowed_genres.append(cls.RANDOM_ADVENTURE)
        cls.RANDOM_ANIMATION = _RandomTrailersGenre(GenreConstants.ANIMATION,
                                                    Messages.GENRE_ANIMATION,
                                                    _TMDBGenres.TMDB_Animation,
                                                    None,
                                                    _IMDBGenres.IMDB_Animation)
        allowed_genres.append(cls.RANDOM_ANIMATION)
        cls.RANDOM_BIOGRAPHY = _RandomTrailersGenre(GenreConstants.BIOGRAPHY,
                                                    Messages.GENRE_BIOGRAPHY,
                                                    _TMDBGenres.TMDB_Biograpy,
                                                    None,
                                                    _IMDBGenres.IMDB_Biography)
        allowed_genres.append(cls.RANDOM_BIOGRAPHY)
        cls.RANDOM_BLACK_COMEDY = _RandomTrailersGenre(GenreConstants.DARK_COMEDY,
                                                       Messages.GENRE_BLACK_COMEDY,
                                                       _TMDBGenres.TMDB_Dark_Comedy,
                                                       None,
                                                       None)
        allowed_genres.append(cls.RANDOM_BLACK_COMEDY)
        '''
        cls.RANDOM_CHILDRENS = _RandomTrailersGenre(GenreConstants.CHILDRENS,
                                                   Messages.GENRE_CHILDRENS,
                                                   None,
                                                   None,
                                                   None)
        allowed_genres.append(cls.RANDOM_CHILDRENS)
        '''
        cls.RANDOM_COMEDY = _RandomTrailersGenre(GenreConstants.COMEDY,
                                                 Messages.GENRE_COMEDY,
                                                 _TMDBGenres.TMDB_Comedy,
                                                 _ITunesGenres.iTunes_Comedy,
                                                 _IMDBGenres.IMDB_Comedy)
        allowed_genres.append(cls.RANDOM_COMEDY)
        cls.RANDOM_CRIME = _RandomTrailersGenre(GenreConstants.CRIME,
                                                Messages.GENRE_CRIME,
                                                _TMDBGenres.TMDB_Crime,
                                                None,
                                                _IMDBGenres.IMDB_Crime)
        allowed_genres.append(cls.RANDOM_CRIME)
        cls.RANDOM_DOCUMENTARY = _RandomTrailersGenre(GenreConstants.DOCUMENTARY,
                                                      Messages.GENRE_DOCUMENTARY,
                                                      _TMDBGenres.TMDB_DOCUMENTARY,
                                                      _ITunesGenres.iTunes_Documentary,
                                                      _IMDBGenres.IMDB_Documentary)
        allowed_genres.append(cls.RANDOM_DOCUMENTARY)
        cls.RANDOM_DRAMA = _RandomTrailersGenre(GenreConstants.DRAMA,
                                                Messages.GENRE_DRAMA,
                                                _TMDBGenres.TMDB_Drama,
                                                _ITunesGenres.iTunes_Drama,
                                                _IMDBGenres.IMDB_Drama)
        allowed_genres.append(cls.RANDOM_DRAMA)
        cls.RANDOM_EPIC = _RandomTrailersGenre(GenreConstants.EPIC,
                                               Messages.GENRE_EPIC,
                                               _TMDBGenres.TMDB_Epic,
                                               None,
                                               None)
        allowed_genres.append(cls.RANDOM_EPIC)
        '''
        cls.RANDOM_EXPERIMENTAL = _RandomTrailersGenre(GenreConstants.EXPERIMENTAL,
                                                      Messages.GENRE_EXPERIMENTAL,
                                                      None,
                                                      None,
                                                      None)
        allowed_genres.append(cls.RANDOM_EXPERIMENTAL)
        '''
        cls.RANDOM_FAMILY = _RandomTrailersGenre(GenreConstants.FAMILY,
                                                 Messages.GENRE_FAMILY,
                                                 _TMDBGenres.TMDB_Family,
                                                 _ITunesGenres.iTunes_Family,
                                                 _IMDBGenres.IMDB_Family)
        allowed_genres.append(cls.RANDOM_FAMILY)
        cls.RANDOM_FANTASY = _RandomTrailersGenre(GenreConstants.FANTASY,
                                                  Messages.GENRE_FANTASY,
                                                  _TMDBGenres.TMDB_Fantasy,
                                                  None,
                                                  _IMDBGenres.IMDB_Fantasy)
        allowed_genres.append(cls.RANDOM_FANTASY)
        cls.RANDOM_FILM_NOIR = _RandomTrailersGenre(GenreConstants.FILM_NOIR,
                                                    Messages.GENRE_FILM_NOIR,
                                                    _TMDBGenres.TMDB_Film_Noir,
                                                    None,
                                                    _IMDBGenres.IMDB_Film_Noir)
        allowed_genres.append(cls.RANDOM_FILM_NOIR)
        '''
        cls.RANDOM_GAME_SHOW = _RandomTrailersGenre(GenreConstants.GAME_SHOW,
                                                   Messages.GENRE_GAME_SHOW,
                                                   None,
                                                   None,
                                                   _IMDBGenres.IMDB_Game_Show)
        allowed_genres.append(cls.RANDOM_GAME_SHOW)
        '''
        cls.RANDOM_HISTORY = _RandomTrailersGenre(GenreConstants.HISTORY,
                                                  Messages.GENRE_HISTORY,
                                                  _TMDBGenres.TMDB_History,
                                                  _ITunesGenres.iTunes_History,
                                                  _IMDBGenres.IMDB_History)
        allowed_genres.append(cls.RANDOM_HISTORY)
        cls.RANDOM_HORROR = _RandomTrailersGenre(GenreConstants.HORROR,
                                                 Messages.GENRE_HORROR,
                                                 _TMDBGenres.TMDB_Horror,
                                                 _ITunesGenres.iTunes_Horror,
                                                 _IMDBGenres.IMDB_Horror)
        allowed_genres.append(cls.RANDOM_HORROR)
        cls.RANDOM_MELODRAMA = _RandomTrailersGenre(GenreConstants.MELODRAMA,
                                                    Messages.GENRE_MELODRAMA,
                                                    _TMDBGenres.TMDB_Melodrama,
                                                    None,
                                                    None)
        allowed_genres.append(cls.RANDOM_MELODRAMA)
        cls.RANDOM_MUSIC = _RandomTrailersGenre(GenreConstants.MUSIC,
                                                Messages.GENRE_MUSIC,
                                                _TMDBGenres.TMDB_Music,
                                                None,
                                                _IMDBGenres.IMDB_Music)
        allowed_genres.append(cls.RANDOM_MUSIC)
        cls.RANDOM_MUSICAL = _RandomTrailersGenre(GenreConstants.MUSICAL,
                                                  Messages.GENRE_MUSICAL,
                                                  _TMDBGenres.TMDB_Musical,
                                                  None,
                                                  _IMDBGenres.IMDB_Musical)
        allowed_genres.append(cls.RANDOM_MUSICAL)
        '''
        cls.RANDOM_MUSICAL_COMEDY = _RandomTrailersGenre(GenreConstants.MUSICAL_COMEDY,
                                                        Messages.GENRE_MUSICAL_COMEDY,
                                                        None,
                                                        None,
                                                        None)
        allowed_genres.append(cls.RANDOM_MUSICAL_COMEDY)
        '''
        cls.RANDOM_MYSTERY = _RandomTrailersGenre(GenreConstants.MYSTERY,
                                                  Messages.GENRE_MYSTERY,
                                                  _TMDBGenres.TMDB_Mystery,
                                                  None,
                                                  _IMDBGenres.IMDB_Mystery)
        allowed_genres.append(cls.RANDOM_MYSTERY)
        # Defined only in AFI
        '''
        cls.RANDOM_PERFORMANCE = _RandomTrailersGenre(GenreConstants.PERFORMANCE,
                                                     Messages.GENRE_PERFORMANCE,
                                                     None,
                                                     None,
                                                     None)
        allowed_genres.append(cls.RANDOM_PERFORMANCE)
        '''

        cls.PRE_CODE = _RandomTrailersGenre(GenreConstants.PRE_CODE,
                                            Messages.GENRE_PRE_CODE,
                                            _TMDBGenres.TMDB_Pre_Code,
                                            None,
                                            None)
        allowed_genres.append(cls.PRE_CODE)

        cls.RANDOM_ROMANCE = _RandomTrailersGenre(GenreConstants.ROMANCE,
                                                  Messages.GENRE_ROMANCE,
                                                  _TMDBGenres.TMDB_Romance,
                                                  _ITunesGenres.iTunes_Romance,
                                                  _IMDBGenres.IMDB_Romance)
        allowed_genres.append(cls.RANDOM_ROMANCE)
        '''
        cls.RANDOM_ROMANTIC_COMEDY = _RandomTrailersGenre(GenreConstants.ROMANTIC_COMEDY,
                                                         Messages.GENRE_ROMANCE_COMEDY,
                                                         _TMDBGenre.TMDB_Romantic_Comedy,
                                                         None,
                                                         None)

        allowed_genres.append(cls.RANDOM_ROMANTIC_COMEDY)
        '''
        cls.RANDOM_SATIRE = _RandomTrailersGenre(GenreConstants.SATIRE,
                                                 Messages.GENRE_SATIRE,
                                                 _TMDBGenres.TMDB_Satire,
                                                 None,
                                                 None)
        allowed_genres.append(cls.RANDOM_SATIRE)
        cls.RANDOM_SCIENCE_FICTION = _RandomTrailersGenre(GenreConstants.SCI_FI,
                                                          Messages.GENRE_SCIENCE_FICTION,
                                                          _TMDBGenres.TMDB_Science_Fiction,
                                                          _ITunesGenres.iTunes_Science_Fiction,
                                                          _IMDBGenres.IMDB_Science_Fiction)
        allowed_genres.append(cls.RANDOM_SCIENCE_FICTION)
        cls.RANDOM_SCREWBALL_COMEDY = _RandomTrailersGenre(GenreConstants.SCREWBALL_COMEDY,
                                                           Messages.GENRE_SCREWBALL_COMEDY,
                                                           _TMDBGenres.TMDB_Screwball_Comedy,
                                                           None,
                                                           None)
        allowed_genres.append(cls.RANDOM_SCREWBALL_COMEDY)
        cls.RANDOM_SWASHBUCKLER = _RandomTrailersGenre(GenreConstants.SWASHBUCKLER,
                                                       Messages.GENRE_SWASHBUCKLER,
                                                       _TMDBGenres.TMDB_Swashbuckler,
                                                       None,
                                                       None)
        allowed_genres.append(cls.RANDOM_SWASHBUCKLER)
        cls.RANDOM_THRILLER = _RandomTrailersGenre(GenreConstants.THRILLER,
                                                   Messages.GENRE_THRILLER,
                                                   _TMDBGenres.TMDB_Thriller,
                                                   _ITunesGenres.iTunes_Thriller,
                                                   _IMDBGenres.IMDB_Thriller)
        allowed_genres.append(cls.RANDOM_THRILLER)
        cls.RANDOM_TV_MOVIE = _RandomTrailersGenre(GenreConstants.TV_MOVIE,
                                                   Messages.GENRE_TV_MOVIE,
                                                   _TMDBGenres.TMDB_TV_Movie,
                                                   None,
                                                   None)
        allowed_genres.append(cls.RANDOM_TV_MOVIE)
        # more for TV
        '''
        cls.RANDOM_VARIETY = _RandomTrailersGenre(GenreConstants.VARIETY,
                                                 Messages.GENRE_VARIETY,
                                                 None,
                                                 None,
                                                 None)
        allowed_genres.append(cls.RANDOM_VARIETY)
        '''
        cls.RANDOM_WAR = _RandomTrailersGenre(GenreConstants.WAR,
                                              Messages.GENRE_WAR,
                                              _TMDBGenres.TMDB_War,
                                              None,
                                              _IMDBGenres.IMDB_War)
        allowed_genres.append(cls.RANDOM_WAR)
        cls.RANDOM_WAR_DOCUMENTARY = _RandomTrailersGenre(GenreConstants.WAR_DOCUMENTARY,
                                                          Messages.GENRE_WAR_DOCUMENTARY,
                                                          None,
                                                          None,
                                                          None)
        allowed_genres.append(cls.RANDOM_WAR_DOCUMENTARY)
        cls.RANDOM_WESTERN = _RandomTrailersGenre(GenreConstants.WESTERN,
                                                  Messages.GENRE_WESTERN,
                                                  _TMDBGenres.TMDB_Western,
                                                  None,
                                                  _IMDBGenres.IMDB_Western)
        allowed_genres.append(cls.RANDOM_WESTERN)

        _RandomTrailersGenre.ALLOWED_GENRES = allowed_genres


_RandomTrailersGenres._init_class()


class GenreUtils(object):
    """
        Provides methods for discovering user selected genres,
        creation of filters and other items.
    """
    LOCAL_DATABASE = 0
    TMDB_DATABASE = 1
    ITUNES_DATABASE = 2
    IMDB_DATABASE = 3
    ROTTEN_TOMATOES_DATABASE = 4

    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)

        self._settings_stale = True
        Monitor.register_settings_changed_listener(self.on_settings_changed)

    @staticmethod
    def get_instance():
        # type: () -> GenreUtils
        """
            Gets the singleton instance of this class

        :return:
        """
        if GenreUtils._instance is None:
            GenreUtils._instance = GenreUtils()
        return GenreUtils._instance

    def on_settings_changed(self):
        # type:() -> None
        """
            Notification from Monitor that settings have changed

            Remark which genres are selected

        :return:
        """

        self._settings_stale = True

    def get_all_genres(self):
        # type: () -> List[_RandomTrailersGenre]
        """
            Gets all of the Genres supported by Random Trailers
        :return:
        """
        allowed_genres = _RandomTrailersGenre.ALLOWED_GENRES
        genres = sorted(
            allowed_genres, key=lambda element: element.get_label())
        return genres

    def get_genres(self, genre_state):
        # type: (int) -> List[_RandomTrailersGenre]
        """
            Gets all of the genres selected via settings

        :return:
        """
        if self._settings_stale:
            self._mark_selected_genres()
            self._settings_stale = False

        genres = []
        for genre in self.get_all_genres():
            if genre.get_filter_value() == genre_state:
                genres.append(genre)
        return genres

    def get_include_genres(self):
        # type: () -> List[_RandomTrailersGenre]
        """

        :return:
        """
        return self.get_genres(GenreEnum.INCLUDE)

    def get_exclude_genres(self):
        # type: () -> List[_RandomTrailersGenre]
        """

        :return:
        """
        return self.get_genres(GenreEnum.EXCLUDE)

    def get_domain_genres(self, generic_genres, genre_domain):
        # type: (List[_RandomTrailersGenre], TextType) -> List[_GenreEntry]
        """
            Return a JSON type query segment appropriate for the
            particular destination (LOCAL_DATABASE, TMDB_DATABASE,
            etc.). Different destinations use different ids for
            genres. In some cases, tags are used instead of genres,
            so both get_genres and get_tags must be done.
        """
        genres = []
        for genre in generic_genres:
            genres.extend(genre.get_genres(genre_domain))
        return genres

    def get_domain_tags(self, generic_genres, genre_domain):
        # type: (List[_RandomTrailersGenre], TextType) -> List[_TagEntry]
        """
            Return a JSON type query segment appropriate for the
            particular destination (LOCAL_DATABASE, TMDB_DATABASE,
            etc.). Different destinations use different ids for
            genres. In some cases, tags are used instead of genres,
            so both get_genres and get_tags must be done.
        """
        tags = []
        for genre in generic_genres:
            tags.extend(genre.get_tags(genre_domain))
        return tags

    def _mark_selected_genres(self):
        # type: () -> None
        """
            Marks genre selection based on Settings
        :return:
        """
        genres = self.get_all_genres()

        for genre in genres:
            genre.ui_select(Settings.get_genre(genre.get_genre_id()))

        return

    def get_external_genre_ids(self, genre_domain, exclude=False):
        # type: (TextType, bool) -> List[TextType]
        """
            Gets all of the "external" id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain:
        :param exclude: If True, then return unselected Genres
        :return: List of genre ids
        """
        self._logger.enter()
        genre_ids = set()

        try:
            if exclude:
                filtered_genres = self.get_exclude_genres()
            else:
                filtered_genres = self.get_include_genres()

            domain_selected_genres = self.get_domain_genres(
                filtered_genres, genre_domain)
            for genre in domain_selected_genres:
                genre_ids.add(genre.get_external_id())
        except (Exception) as e:
            self._logger.exception('')

        return list(genre_ids)

    def get_internal_kodi_genre_ids(self, genre_domain, exclude=False):
        # type: (TextType, bool) -> List[TextType]
        """
            Gets all of the kodi database id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain:
        :param exclude: If True, then return unselected Genres
        :return: List of genre ids
        """
        self._logger.enter()
        genre_ids = set()

        try:
            if exclude:
                filtered_genres = self.get_exclude_genres()
            else:
                filtered_genres = self.get_include_genres()

            domain_selected_genres = self.get_domain_genres(
                filtered_genres, genre_domain)
            for genre in domain_selected_genres:
                genre_ids.add(genre.get_kodi_id())
        except (Exception) as e:
            self._logger.exception('')

        return list(genre_ids)

    def get_external_genre_ids_as_query(self, genre_domain, exclude=False,
                                        or_operator=True):
        # type: (TextType, bool, bool) -> TextType
        """
            Returns a query string of selected genreids.

            In the case of TMDB, the genre values are separated by commas
            when a movie must contain all of the genres. A pipe '|'
            separator is used when a movie only need to match any of
            the genres.

            Note: only supports TMDB at this time

        :param genre_domain:
        :param exclude: If True, then return excluded genres
        :param or_operator:
        :return:
        """

        self._logger.enter()
        query_string = ''
        try:
            selected_genre_ids = self.get_external_genre_ids(
                genre_domain, exclude=exclude)

            if or_operator:
                separator = '|'  # OR operations
            else:
                separator = ','  # AND operations

            query_string = separator.join(selected_genre_ids)

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('query:', query_string)
        except (Exception) as e:
            self._logger.exception('')
            query_string = ''

        return query_string

    def get_external_keyword_ids(self, genre_domain, exclude=False):
        # type: (TextType, bool) -> List[TextType]
        """
            Gets all of the "external" id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain:
        :param exclude: If True, then return unselected keywords/tags
        :return: List[str] List of Keyword/Tag ids
        """

        self._logger.enter()
        keyword_ids = set()
        try:
            if exclude:
                selected_genres = self.get_exclude_genres()
            else:
                selected_genres = self.get_include_genres()

            domain_selected_tags = self.get_domain_tags(
                selected_genres, genre_domain)

            filtered_tags = domain_selected_tags

            for tag in filtered_tags:
                keyword_ids.add(tag.get_external_id())
        except (Exception) as e:
            self._logger.exception('')

        return list(keyword_ids)

    def get_internal_kodi_keyword_ids(self, genre_domain, exclude=False):
        # type: (TextType, bool) -> List[TextType]
        """
            Gets all of the kodi database id values in the namespace of
            the given domain (database). An external id is typically the
            value used as a database key, perhaps an integer.

        :param genre_domain:
        :param exclude: If True, then return unselected keywords/tags
        :return: List[str] List of Keyword/Tag ids
        """

        self._logger.enter()
        keyword_ids = set()
        try:
            if exclude:
                selected_genres = self.get_exclude_genres()
            else:
                selected_genres = self.get_include_genres()

            domain_selected_tags = self.get_domain_tags(
                selected_genres, genre_domain)

            filtered_tags = domain_selected_tags

            for tag in filtered_tags:
                keyword_ids.add(tag.get_kodi_id())
        except (Exception) as e:
            self._logger.exception('')

        return list(keyword_ids)

    def get_external_keywords_as_query(self, genre_domain, exclude=False,
                                       or_operator=True):
        # type: (TextType, bool, bool) -> TextType
        """
            Returns a query string of selected genreids.

            In the case of TMDB, the genre and keyword/tag values
            are separated by commas when a movie must contain all
            of the keywords/tags. A pipe '|' separator is used when a
            movie only need to match any of the keywords/tags.

            Note: only supports TMDB at this time

        :param genre_domain:
        :param exclude: If True, then return unselected keywords/Tags
        :param or_operator:
        :return:
        """

        self._logger.enter()
        query = ''
        try:
            selected_keyword_ids = self.get_external_keyword_ids(
                genre_domain, exclude=exclude)

            if or_operator:
                separator = '|'  # OR operations
            else:
                separator = ',',  # AND opeations
            query = separator.join(selected_keyword_ids)

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('query:', query)
        except (Exception) as e:
            self._logger.exception('')
            string_buffer = ''

        return query
