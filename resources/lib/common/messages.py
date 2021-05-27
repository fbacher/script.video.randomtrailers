# -*- coding: utf-8 -*-
"""
Created on Feb 28, 2019

@author: fbacher
"""

import xbmcaddon
from common.imports import *
from common.constants import Constants
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Messages:
    """
    Provides methods, message tags and default messages for accessing translated
    messages.
    """

    TRAILER_EXCEEDS_MAX_PLAY_TIME: Final[str] = 'This trailer exceeds the maximum play time.' \
                                    ' Terminating'
    TMDB_LABEL: Final[str] = 'TMDb'  # Offical name
    ITUNES_LABEL: Final[str] = 'iTunes'  # VERIFY
    MISSING_TITLE: Final[str] = 'Missing movie title'
    MISSING_DETAIL: Final[str] = 'Unavailable'
    CAN_NOT_READ_FILE: Final[str] = 'Can not read file: %s'
    CAN_NOT_WRITE_FILE: Final[str] = 'Can not write file: %s'
    NO_TRAILERS_TO_PLAY: Final[str] = 'There are no trailers to play'
    HEADING_INFO: Final[str] = 'Info'
    NO_MOVIE_TO_PLAY: Final[str] = 'There is no movie associated with this trailer to play'
    HEADER_IDLE: Final[str] = 'Idle'
    PLAYER_IDLE: Final[str] = 'Waiting to play next group of trailers'
    UNLIMITED: Final[str] = 'unlimited'
    NO_MORE_MOVIE_HISTORY: Final[str] = 'No previous movie to play'
    PLAYING_PREVIOUS_MOVIE: Final[str] = 'Playing: %s'
    GENRE_LABEL: Final[str] = 'Genre: '
    MINUTES_DETAIL: Final[str] = '{} [B]Minutes[/B] - '
    RUNTIME_GENRE: Final[str] = '{}  [B]Genre: [/B]'
    TITLE_LABEL: Final[str] = 'Title'
    DIRECTOR_LABEL: Final[str] = 'Director'
    WRITER_LABEL: Final[str] = 'Writer'
    STARS_LABEL: Final[str] = 'Stars'
    PLOT_LABEL: Final[str] = 'Plot'
    LICENSE_LABEL: Final[str] = 'Random Trailers is powered by:'
    TFH_LICENSE: Final[str] = 'TFH_LICENSE'
    TMDB_LICENSE: Final[str] = 'TMDB_LICENSE'

    GENRE_ACTION: Final[str] = 'Action'
    GENRE_ALEGORY: Final[str] = 'Allegory'
    GENRE_ANTHOLOGY: Final[str] = 'Anthology'
    GENRE_ADVENTURE: Final[str] = 'Adventure'
    GENRE_ANIMATION: Final[str] = 'Animation'
    GENRE_BIOGRAPHY: Final[str] = 'Biography'
    GENRE_BLACK_COMEDY: Final[str] = 'Black Comedy'
    GENRE_CHILDRENS: Final[str] = 'Children\'s'
    GENRE_COMEDY: Final[str] = 'Comedy'
    GENRE_COMEDY_DRAMA: Final[str] = 'Comedy Drama'
    GENRE_CRIME: Final[str] = 'Crime'
    GENRE_DOCUMENTARY: Final[str] = 'Documentary'
    GENRE_DRAMA: Final[str] = 'Drama'
    GENRE_EPIC: Final[str] = 'Epic'
    GENRE_EXPERIMENTAL: Final[str] = 'Experimental'
    GENRE_FAMILY: Final[str] = 'Family'
    GENRE_FANTASY: Final[str] = 'Fantasy'
    GENRE_FILM_NOIR: Final[str] = 'Film Noir'
    GENRE_GAME_SHOW: Final[str] = 'Game Show'
    GENRE_HISTORY: Final[str] = 'History'
    GENRE_HORROR: Final[str] = 'Horror'
    GENRE_MELODRAMA: Final[str] = 'Melodrama'
    GENRE_MUSIC: Final[str] = 'Music'
    GENRE_MUSICAL: Final[str] = 'Musical'
    GENRE_MUSICAL_COMEDY: Final[str] = 'Musical Comedy'
    GENRE_MYSTERY: Final[str] = 'Mystery'
    GENRE_PERFORMANCE: Final[str] = 'Performance'
    GENRE_PRE_CODE: Final[str] = 'Pre-Code'
    GENRE_ROMANCE: Final[str] = 'Romance'
    GENRE_ROMANCE_COMEDY: Final[str] = 'Romance Comedy'
    GENRE_SATIRE: Final[str] = 'Satire'
    GENRE_SCIENCE_FICTION: Final[str] = 'Science Fiction'
    GENRE_SCREWBALL_COMEDY: Final[str] = 'Screwball Comedy'
    GENRE_SWASHBUCKLER: Final[str] = 'Schwashbuckler'
    GENRE_THRILLER: Final[str] = 'Thriller'
    GENRE_TV_MOVIE: Final[str] = 'TV Movie'
    GENRE_VARIETY: Final[str] = 'Variety'
    GENRE_WAR: Final[str] = 'War'
    GENRE_WAR_DOCUMENTARY: Final[str] = 'War Documentary'
    GENRE_WESTERN: Final[str] = 'Western'
    MOVIE_ADDED_TO_PLAYLIST: Final[str] = 'Movie added to playlist: {}'
    MOVIE_ALREADY_ON_PLAYLIST: Final[str] = 'Movie already in playlist: {}'
    SETTING_INCLUDE_THREAD_INFORMATION: Final[str] = "Include thread information"
    RATING: Final[str] = 'Rating {}'
    RATING_G: Final[str] = 'G'
    RATING_PG: Final[str] = 'PG'
    RATING_PG_13: Final[str] = 'PG-13'
    RATING_R: Final[str] = 'R'
    RATING_NC_17: Final[str] = 'NC-17'
    RATING_NR: Final[str] = 'Unrated'
    # The following Trailer type values must be the same as in movie.py
    TRAILER_TYPE_TRAILER: Final[str] = 'Trailer'
    TRAILER_TYPE_FEATURETTE: Final[str] = 'Featurette'
    TRAILER_TYPE_CLIP: Final[str] = 'Clip'
    TRAILER_TYPE_TEASER: Final[str] = 'Teaser'
    TRAILER_TYPE_BEHIND_THE_SCENES: Final[str] = 'Behind the Scenes'

    # VOICED messages are spoken via TTS engine when available

    VOICED_CERTIFICATION: Final[str] = 'MPAA rating {}'
    VOICED_STARS: Final[str] = '{} out of five stars'

    _msg_id_for_name: Final[Dict[str, int]] = {
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
        LICENSE_LABEL: 32282,
        TRAILER_TYPE_TRAILER: 32285,
        TRAILER_TYPE_FEATURETTE: 32286,
        TRAILER_TYPE_CLIP: 32287,
        TRAILER_TYPE_TEASER: 32288,
        TRAILER_TYPE_BEHIND_THE_SCENES: 32289
    }

    _instance = None
    _debug_dump: bool = False
    _logger: LazyLogger = None

    @classmethod
    def class_init(cls) -> None:
        """

        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

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
        cls.class_init()  # Ensure initialized

        if Messages._debug_dump:
            for msg_number in range(32000, 32300):
                unformatted_msg: str = xbmcaddon.Addon(Constants.ADDON_ID).getLocalizedString(
                    msg_number)
                if (unformatted_msg != ""
                        and cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                    cls._logger.debug_extra_verbose('found msg:', msg_number,
                                                    unformatted_msg)
            Messages._debug_dump = False

        unformatted_msg: str = 'Message not defined'
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


