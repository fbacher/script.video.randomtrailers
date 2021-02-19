# -*- coding: utf-8 -*-
"""
Created on Feb 28, 2019

@author: fbacher
"""

import xbmcaddon
from common.imports import *
from common.constants import Movie, Constants
from common.logger import LazyLogger

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Messages:
    """
    Provides methods, message tags and default messages for accessing translated
    messages.
    """

    TRAILER_EXCEEDS_MAX_PLAY_TIME = 'This trailer exceeds the maximum play time.' \
                                    ' Terminating'
    TMDB_LABEL = 'TMDb'  # Offical name
    ITUNES_LABEL = 'iTunes'  # VERIFY
    MISSING_TITLE = 'Missing movie title'
    MISSING_DETAIL = 'Unavailable'
    CAN_NOT_READ_FILE = 'Can not read file: %s'
    CAN_NOT_WRITE_FILE = 'Can not write file: %s'
    NO_TRAILERS_TO_PLAY = 'There are no trailers to play'
    HEADING_INFO = 'Info'
    NO_MOVIE_TO_PLAY = 'There is no movie associated with this trailer to play'
    HEADER_IDLE = 'Idle'
    PLAYER_IDLE = 'Waiting to play next group of trailers'
    UNLIMITED = 'unlimited'
    NO_MORE_MOVIE_HISTORY = 'No previous movie to play'
    PLAYING_PREVIOUS_MOVIE = 'Playing: %s'
    GENRE_LABEL = 'Genre: '
    MINUTES_DETAIL = '{} [B]Minutes[/B] - '
    RUNTIME_GENRE = '{} [B]Genre:[/B]'
    TITLE_LABEL = 'Title'
    DIRECTOR_LABEL = 'Director'
    WRITER_LABEL = 'Writer'
    STARS_LABEL = 'Stars'
    PLOT_LABEL = 'Plot'
    LICENSE_LABEL = 'Random Trailers is powered by:'
    TFH_LICENSE = 'TFH_LICENSE'
    TMDB_LICENSE = 'TMDB_LICENSE'

    GENRE_ACTION = 'Action'
    GENRE_ALEGORY = 'Allegory'
    GENRE_ANTHOLOGY = 'Anthology'
    GENRE_ADVENTURE = 'Adventure'
    GENRE_ANIMATION = 'Animation'
    GENRE_BIOGRAPHY = 'Biography'
    GENRE_BLACK_COMEDY = 'Black Comedy'
    GENRE_CHILDRENS = 'Children\'s'
    GENRE_COMEDY = 'Comedy'
    GENRE_COMEDY_DRAMA = 'Comedy Drama'
    GENRE_CRIME = 'Crime'
    GENRE_DOCUMENTARY = 'Documentary'
    GENRE_DRAMA = 'Drama'
    GENRE_EPIC = 'Epic'
    GENRE_EXPERIMENTAL = 'Experimental'
    GENRE_FAMILY = 'Family'
    GENRE_FANTASY = 'Fantasy'
    GENRE_FILM_NOIR = 'Film Noir'
    GENRE_GAME_SHOW = 'Game Show'
    GENRE_HISTORY = 'History'
    GENRE_HORROR = 'Horror'
    GENRE_MELODRAMA = 'Melodrama'
    GENRE_MUSIC = 'Music'
    GENRE_MUSICAL = 'Musical'
    GENRE_MUSICAL_COMEDY = 'Musical Comedy'
    GENRE_MYSTERY = 'Mystery'
    GENRE_PERFORMANCE = 'Performance'
    GENRE_PRE_CODE = 'Pre-Code'
    GENRE_ROMANCE = 'Romance'
    GENRE_ROMANCE_COMEDY = 'Romance Comedy'
    GENRE_SATIRE = 'Satire'
    GENRE_SCIENCE_FICTION = 'Science Fiction'
    GENRE_SCREWBALL_COMEDY = 'Screwball Comedy'
    GENRE_SWASHBUCKLER = 'Schwashbuckler'
    GENRE_THRILLER = 'Thriller'
    GENRE_TV_MOVIE = 'TV Movie'
    GENRE_VARIETY = 'Variety'
    GENRE_WAR = 'War'
    GENRE_WAR_DOCUMENTARY = 'War Documentary'
    GENRE_WESTERN = 'Western'
    MOVIE_ADDED_TO_PLAYLIST = 'Movie added to playlist: {}'
    MOVIE_ALREADY_ON_PLAYLIST = 'Movie already in playlist: {}'
    SETTING_INCLUDE_THREAD_INFORMATION = "Include thread information"
    RATING = 'Rating {}'
    RATING_G = 'G'
    RATING_PG = 'PG'
    RATING_PG_13 = 'PG-13'
    RATING_R = 'R'
    RATING_NC_17 = 'NC-17'
    RATING_NR = 'Unrated'

    # VOICED messages are spoken via TTS engine when available

    VOICED_CERTIFICATION = 'MPAA rating {}'
    VOICED_STARS = '{} out of five stars'

    _msg_id_for_name = {
        TRAILER_EXCEEDS_MAX_PLAY_TIME: 32180,
        TMDB_LABEL: 32181,
        ITUNES_LABEL: 32182,
        MISSING_TITLE: 32183,
        MISSING_DETAIL: 32184,
        CAN_NOT_READ_FILE: 32185,
        CAN_NOT_WRITE_FILE: 32186,
        NO_TRAILERS_TO_PLAY: 32187,
        HEADING_INFO: 32188,
        NO_MOVIE_TO_PLAY: 32189,
        HEADER_IDLE: 32190,
        PLAYER_IDLE: 32191,
        UNLIMITED: 32192,
        NO_MORE_MOVIE_HISTORY: 32193,
        PLAYING_PREVIOUS_MOVIE: 32194,
        GENRE_LABEL: 32195,
        MINUTES_DETAIL: 32196,
        RUNTIME_GENRE: 32197,
        TITLE_LABEL: 32175,
        DIRECTOR_LABEL: 32176,
        WRITER_LABEL: 32177,
        STARS_LABEL: 32178,
        PLOT_LABEL: 32179,
        GENRE_ACTION: 32198,
        GENRE_ALEGORY: 32199,
        GENRE_ANTHOLOGY: 32200,
        GENRE_ADVENTURE: 32201,
        GENRE_ANIMATION: 32202,
        GENRE_BIOGRAPHY: 32203,
        GENRE_BLACK_COMEDY: 32204,
        GENRE_CHILDRENS: 32205,
        GENRE_COMEDY: 32206,
        GENRE_COMEDY_DRAMA: 32207,
        GENRE_CRIME: 32208,
        GENRE_DOCUMENTARY: 32209,
        GENRE_DRAMA: 32210,
        GENRE_EPIC: 32211,
        GENRE_EXPERIMENTAL: 32212,
        GENRE_FAMILY: 32213,
        GENRE_FANTASY: 32214,
        GENRE_FILM_NOIR: 32215,
        GENRE_GAME_SHOW: 32216,
        GENRE_HISTORY: 32217,
        GENRE_HORROR: 32218,
        GENRE_MELODRAMA: 32219,
        GENRE_MUSIC: 32220,
        GENRE_MUSICAL: 32221,
        GENRE_MUSICAL_COMEDY: 32222,
        GENRE_MYSTERY: 32223,
        GENRE_PERFORMANCE: 32225,
        GENRE_PRE_CODE: 32226,
        GENRE_ROMANCE: 32227,
        GENRE_ROMANCE_COMEDY: 32228,
        GENRE_SATIRE: 32229,
        GENRE_SCIENCE_FICTION: 32230,
        GENRE_SCREWBALL_COMEDY: 32231,
        GENRE_SWASHBUCKLER: 32232,
        GENRE_THRILLER: 32233,
        GENRE_TV_MOVIE: 32234,
        GENRE_VARIETY: 32235,
        GENRE_WAR: 32236,
        GENRE_WAR_DOCUMENTARY: 32237,
        GENRE_WESTERN: 32238,
        MOVIE_ADDED_TO_PLAYLIST: 32239,
        MOVIE_ALREADY_ON_PLAYLIST: 32240,
        SETTING_INCLUDE_THREAD_INFORMATION: 32241,
        RATING: 32242,
        RATING_G: 32243,
        RATING_PG: 32244,
        RATING_PG_13: 32245,
        RATING_R: 32246,
        RATING_NC_17: 32247,
        RATING_NR: 32248,
        VOICED_CERTIFICATION: 32249,
        VOICED_STARS: 32250,
        TFH_LICENSE: 32283,
        TMDB_LICENSE: 32281,
        LICENSE_LABEL: 32282
    }

    _instance = None
    _debug_dump = False
    _logger = None

    def __init__(self) -> None:
        """

        """
        type(self)._logger = module_logger.getChild(type(self).__name__)

    @staticmethod
    def get_instance():
        #  type: () -> Messages
        """

        :return:
        """
        if Messages._instance is None:
            Messages._instance = Messages()
        return Messages._instance

    @classmethod
    def get_msg(cls, msg_key: str) -> str:
        """

        :param msg_key:
        :return:
        """

        return cls.get_formatted_msg(msg_key)

    @classmethod
    def get_formatted_msg(cls, msg_key: str,
                          *args: str) -> str:
        """

        :param msg_key:
        :param args
        :return:
        """
        if Messages._debug_dump:
            for msg_number in range(32000, 32300):
                unformatted_msg = xbmcaddon.Addon(Constants.ADDON_ID).getLocalizedString(
                    msg_number)
                if (unformatted_msg != ""
                        and cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                    cls._logger.debug_extra_verbose('found msg:', msg_number,
                                                    unformatted_msg)
            Messages._debug_dump = False

        unformatted_msg = 'Message not defined'
        try:
            msg_id = int(msg_key)
        except Exception:
            msg_id = None

        if msg_id is None:
            msg_id = Messages._msg_id_for_name.get(msg_key, None)
        if msg_id is None:
            if cls._logger.isEnabledFor(LazyLogger.ERROR):
                cls._logger.error(
                    'Can not find msg_id_for_name for message key: {}'.format(msg_key))
                unformatted_msg = msg_key
        else:
            unformatted_msg = xbmcaddon.Addon(
                Constants.ADDON_ID).getLocalizedString(msg_id)
            if unformatted_msg == '':
                unformatted_msg = msg_key
                if cls._logger.isEnabledFor(LazyLogger.ERROR):
                    cls._logger.error(
                        'Can not find message from strings for message id: {} msg_key: {}'
                        .format(msg_id, msg_key))
                    unformatted_msg = msg_key
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                        unformatted_msg += '_dm'

        try:
            msg = unformatted_msg.format(*args)
        except Exception as e:
            cls._logger.exception(e)
            msg = unformatted_msg

        return msg

    @classmethod
    def get_formated_title(cls, movie: MovieType) -> str:
        """

        :param movie:
        :return:
        """
        trailer_type = movie.get(Movie.TRAILER_TYPE, '')

        year = str(movie.get(Movie.YEAR, ''))
        if year != '':
            year = '(' + year + ')'

        # A movie from a remote source (tmdb) may also be in local library.

        sources = movie[Movie.SOURCE]
        if movie[Movie.SOURCE] != Movie.LIBRARY_SOURCE and movie.get(Movie.MOVIEID, None):
            sources += ' / ' + Movie.LIBRARY_SOURCE

        title_string = (movie[Movie.TITLE] + ' ' + year + ' - ' +
                        sources + ' ' + trailer_type)
        return title_string


# Initialize logger
message_instance = Messages.get_instance()
