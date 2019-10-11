# -*- coding: utf-8 -*-
"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import datetime
import locale
import os

from kodi65.kodiaddon import Addon
from kodi_six import xbmc

from .constants import (Constants, DebugLevel,
                        RemoteTrailerPreference, GenreEnum)
from .logger import (Logger, LazyLogger, Trace)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.settings')
else:
    module_logger = LazyLogger.get_addon_module_logger()

# noinspection PyClassHasNoInit


class Settings(object):
    """

    """
    _addon_singleton = None
    _logger = module_logger.getChild('Settings')
    _previous_settings = {}

    ADJUST_VOLUME = 'do_volume'
    ALLOW_FOREIGN_LANGUAGES = 'allow_foreign_languages'
    TMDB_VOTE_FILTER = 'tmdb_vote_filter'
    TMDB_VOTE_VALUE = 'tmdb_vote_value'
    DO_NOT_RATED = 'do_nr'
    DO_DEBUG = 'do_debug'
    FILTER_GENRES = 'do_genre'
    GENRE_ACTION = 'g_action'
    GENRE_ADVENTURE = 'g_adventure'
    GENRE_ANIMATION = 'g_animation'
    GENRE_BIOGRAPY = 'g_biography'
    GENRE_COMEDY = 'g_comedy'
    GENRE_CRIME = 'g_crime'
    GENRE_DARK_COMEDY = 'g_black_comedy'
    GENRE_DOCUMENTARY = 'g_docu'
    GENRE_DRAMA = 'g_drama'
    GENRE_EPIC = 'g_epic'
    GENRE_FAMILY = 'g_family'
    GENRE_FANTASY = 'g_fantasy'
    GENRE_FILM_NOIR = 'g_film_noir'
    GENRE_FOREIGN = 'g_foreign'
    GENRE_HISTORY = 'g_history'
    GENRE_HORROR = 'g_horror'
    GENRE_MELODRAMA = 'g_melodrama'
    GENRE_MUSIC = 'g_music'
    GENRE_MUSICAL = 'g_musical'
    GENRE_MYSTERY = 'g_mystery'
    GENRE_PRE_CODE = 'g_pre_code'
    GENRE_ROMANCE = 'g_romance'
    GENRE_SATIRE = 'g_satire'
    GENRE_SCI_FI = 'g_scifi'
    GENRE_SCREW_BALL = 'g_screwball'
    GENRE_SWASH_BUCKLER = 'g_swashbuckler'
    GENRE_THRILLER = 'g_thriller'
    GENRE_TV_MOVIE = 'g_tv_movie'
    GENRE_WAR = 'g_war'
    GENRE_WAR_DOCUMENTARY = 'g_war_documentary'
    GENRE_WESTERN = 'g_western'
    GROUP_TRAILERS = 'group_trailers'
    GROUP_DELAY = 'group_delay'
    TRAILERS_PER_GROUP = 'trailers_per_group'
    HIDE_WATCHED_MOVIES = 'hide_watched'
    INCLUDE_CLIPS = 'do_clips'
    INCLUDE_FEATURETTES = 'do_featurettes'
    INCLUDE_TEASERS = 'do_teasers'
    INCLUDE_ITUNES_TRAILERS = 'do_itunes'
    ITUNES_TRAILER_TYPE = 'itunes_trailer_type'
    INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO = 'do_library_no_trailer_info'
    INCLUDE_LIBRARY_TRAILERS = 'do_library'
    INCLUDE_NOT_YET_RATED = 'do_notyetrated'
    INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS = 'do_library_remote_trailers'
    INCLUDE_REMOTE_TRAILERS = 'do_remote_trailers'
    INCLUDE_TMDB_TRAILERS = 'do_tmdb'
    INCLUDE_TRAILER_FOLDERS = 'do_folder'
    LIMIT_CACHED_TRAILERS = 'limit_cached_trailers'
    LIMIT_NUMBER_OF_CACHED_TRAILERS = 'limit_number_of_cached_trailers'
    MAX_NUMBER_OF_CACHED_TRAILERS = 'max_number_of_cached_trailers'
    TMDB_MAX_NUMBER_OF_TRAILERS = 'tmdb_max_number_of_trailers'

    LIMIT_SIZE_OF_CACHED_TRAILERS = 'limit_size_of_cached_trailers'
    MAX_SIZE_OF_CACHED_TRAILERS = 'max_size_of_cached_trailers'
    LIMIT_PERCENT_OF_CACHED_TRAILERS = 'limit_percent_of_cached_trailers'
    MAX_PERCENT_OF_CACHED_TRAILERS = 'max_percent_of_cached_trailers'

    LIMIT_CACHED_JSON = 'limit_cached_json'
    LIMIT_NUMBER_OF_CACHED_JSON = 'limit_number_of_cached_json_files'
    MAX_NUMBER_OF_CACHED_JSON = 'max_number_of_cached_json_files'
    LIMIT_SIZE_OF_CACHED_JSON = 'limit_size_of_cached_json_disk'
    MAX_SIZE_OF_CACHED_JSON = 'max_size_of_cached_json_disk'
    LIMIT_PERCENT_OF_CACHED_JSON = 'limit_percent_of_cached_json_disk'
    MAX_PERCENT_OF_CACHED_JSON = 'max_percent_of_cached_json_disk'

    ENABLE_MOVIE_STATS = 'enable_movie_stats'
    REPORT_ACTOR_STATS = 'report_actor_stats'
    REPORT_TAG_STATS = 'report_tag_stats'
    REPORT_MAXIMUM_NUMBER_OF_TOP_ACTORS = 'max_report_top_actors'
    REPORT_GENRE_STATS = 'report_genre_stats'
    MAXIMUM_TRAILER_LENGTH = 'max_trailer_length'
    MINIMUM_DAYS_SINCE_WATCHED = 'watched_days'
    NORMALIZE_VOLUME_OF_DOWNLOADED_TRAILERS = 'normalize_volume_of_downloaded_trailers'
    NORMALIZE_VOLUME_OF_LOCAL_TRAILERS = 'normalize_volume_of_local_trailers'
    NUMBER_OF_TRAILERS_TO_PLAY = 'numberOfTrailersToPlay'
    PROMPT_FOR_SETTINGS = 'prompt_for_settings'
    # ITUNES_QUALITY = 'quality'
    RATING_LIMIT = 'rating_limit'
    TMDB_SORT_ORDER = 'tmdb_sort_order'
    TMDB_ENABLE_SELECT_BY_YEAR_RANGE = 'tmdb_enable_select_by_year_range'
    TMDB_YEAR_RANGE_MINIMUM = 'tmdb_year_range_minimum'
    TMDB_YEAR_RANGE_MAXIMUM = 'tmdb_year_range_maximum'
    SET_FULLSCREEN_WHEN_SCREENSAVER = 'set_fullscreen_when_screensaver'
    SHOW_CURTAINS = 'do_animation'
    SHOW_TITLE = 'show_title'
    TIME_TO_DISPLAY_DETAIL_INFO = 'timeToDisplayDetailInfo'
    TMDB_API_KEY = 'tmdb_api_key'
    TMDB_TRAILER_TYPE = "tmdb_trailer_type"
    UPDATE_TMDB_ID = 'updateTmdbId'
    VOLUME = 'volume'
    TMDB_INCLUDE_OLD_MOVIE_TRAILERS = 'tmdb_include_old_movie_trailers'
    TMDB_MAX_DOWNLOAD_MOVIES = 'tmdb_max_download_movies'
    ENABLE_TRACE = 'do_trace'
    ENABLE_TRACE_STATS = 'do_trace_stats'
    ENABLE_REMOTE_DATA_CACHE = 'use_remote_data_cache'
    ENABLE_TRAILER_CACHE = 'use_trailer_cache'
    CACHE_EXPIRATION_DAYS = 'json_cache_expiration_days'
    EXPIRE_TRAILER_CACHE_DAYS = 'trailer_cache_expiration_days'
    CACHE_TRAILER_CHECK_DAYS = 'trailer_exixtance_cache_check_days'
    TRAILER_CACHE_PATH = 'trailer_cache_path'
    CACHE_PATH = 'remote_db_cache_path'
    PLAYLIST_1 = "playlist_name_1"
    PLAYLIST_2 = "playlist_name_2"
    PLAYLIST_3 = "playlist_name_3"
    PLAYLIST_4 = "playlist_name_4"
    PLAYLIST_5 = "playlist_name_5"
    PLAYLIST_6 = "playlist_name_6"
    PLAYLIST_7 = "playlist_name_7"
    PLAYLIST_8 = "playlist_name_8"
    PLAYLIST_9 = "playlist_name_9"
    PLAYLIST_10 = "playlist_name_10"

    ALL_SETTINGS = [
        ADJUST_VOLUME,
        ALLOW_FOREIGN_LANGUAGES,
        TMDB_VOTE_FILTER,
        TMDB_VOTE_VALUE,
        DO_NOT_RATED,
        DO_DEBUG,
        FILTER_GENRES,
        GENRE_ACTION,
        GENRE_ADVENTURE,
        GENRE_ANIMATION,
        GENRE_BIOGRAPY,
        GENRE_COMEDY,
        GENRE_CRIME,
        GENRE_DARK_COMEDY,
        GENRE_DOCUMENTARY,
        GENRE_DRAMA,
        GENRE_EPIC,
        GENRE_FAMILY,
        GENRE_FANTASY,
        GENRE_FILM_NOIR,
        GENRE_FOREIGN,
        GENRE_HISTORY,
        GENRE_HORROR,
        GENRE_MELODRAMA,
        GENRE_MUSIC,
        GENRE_MUSICAL,
        GENRE_MYSTERY,
        GENRE_PRE_CODE,
        GENRE_ROMANCE,
        GENRE_SATIRE,
        GENRE_SCI_FI,
        GENRE_SCREW_BALL,
        GENRE_SWASH_BUCKLER,
        GENRE_THRILLER,
        GENRE_TV_MOVIE,
        GENRE_WAR,
        GENRE_WAR_DOCUMENTARY,
        GENRE_WESTERN,
        GROUP_TRAILERS,
        GROUP_DELAY,
        TRAILERS_PER_GROUP,
        HIDE_WATCHED_MOVIES,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_NOT_YET_RATED,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_REMOTE_TRAILERS,
        INCLUDE_TMDB_TRAILERS,
        INCLUDE_TRAILER_FOLDERS,
        LIMIT_CACHED_TRAILERS,
        LIMIT_NUMBER_OF_CACHED_TRAILERS,
        MAX_NUMBER_OF_CACHED_TRAILERS,
        TMDB_MAX_NUMBER_OF_TRAILERS,

        LIMIT_SIZE_OF_CACHED_TRAILERS,
        MAX_SIZE_OF_CACHED_TRAILERS,
        LIMIT_PERCENT_OF_CACHED_TRAILERS,
        MAX_PERCENT_OF_CACHED_TRAILERS,

        LIMIT_CACHED_JSON,
        LIMIT_NUMBER_OF_CACHED_JSON,
        MAX_NUMBER_OF_CACHED_JSON,
        LIMIT_SIZE_OF_CACHED_JSON,
        MAX_SIZE_OF_CACHED_JSON,
        LIMIT_PERCENT_OF_CACHED_JSON,
        MAX_PERCENT_OF_CACHED_JSON,

        ENABLE_MOVIE_STATS,
        REPORT_ACTOR_STATS,
        REPORT_TAG_STATS,
        REPORT_MAXIMUM_NUMBER_OF_TOP_ACTORS,
        REPORT_GENRE_STATS,
        MAXIMUM_TRAILER_LENGTH,
        MINIMUM_DAYS_SINCE_WATCHED,
        NORMALIZE_VOLUME_OF_DOWNLOADED_TRAILERS,
        NORMALIZE_VOLUME_OF_LOCAL_TRAILERS,
        NUMBER_OF_TRAILERS_TO_PLAY,
        PROMPT_FOR_SETTINGS,
        RATING_LIMIT,
        TMDB_SORT_ORDER,
        TMDB_ENABLE_SELECT_BY_YEAR_RANGE,
        TMDB_YEAR_RANGE_MINIMUM,
        TMDB_YEAR_RANGE_MAXIMUM,
        SET_FULLSCREEN_WHEN_SCREENSAVER,
        SHOW_CURTAINS,
        SHOW_TITLE,
        TIME_TO_DISPLAY_DETAIL_INFO,
        TMDB_API_KEY,
        TMDB_TRAILER_TYPE,
        UPDATE_TMDB_ID,
        VOLUME,
        TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        TMDB_MAX_DOWNLOAD_MOVIES,
        ENABLE_TRACE,
        ENABLE_TRACE_STATS,
        ENABLE_REMOTE_DATA_CACHE,
        ENABLE_TRAILER_CACHE,
        CACHE_EXPIRATION_DAYS,
        EXPIRE_TRAILER_CACHE_DAYS,
        CACHE_TRAILER_CHECK_DAYS,
        TRAILER_CACHE_PATH,
        CACHE_PATH,
        PLAYLIST_1,
        PLAYLIST_2,
        PLAYLIST_3,
        PLAYLIST_4,
        PLAYLIST_5,
        PLAYLIST_6,
        PLAYLIST_7,
        PLAYLIST_8,
        PLAYLIST_9,
        PLAYLIST_10
    ]

    TRAILER_LOADING_SETTINGS = [
        ALLOW_FOREIGN_LANGUAGES,
        TMDB_VOTE_FILTER,
        TMDB_VOTE_VALUE,
        DO_NOT_RATED,
        FILTER_GENRES,
        GENRE_ACTION,
        GENRE_ADVENTURE,
        GENRE_ANIMATION,
        GENRE_BIOGRAPY,
        GENRE_COMEDY,
        GENRE_CRIME,
        GENRE_DARK_COMEDY,
        GENRE_DOCUMENTARY,
        GENRE_DRAMA,
        GENRE_EPIC,
        GENRE_FAMILY,
        GENRE_FANTASY,
        GENRE_FILM_NOIR,
        GENRE_FOREIGN,
        GENRE_HISTORY,
        GENRE_HORROR,
        GENRE_MELODRAMA,
        GENRE_MUSIC,
        GENRE_MUSICAL,
        GENRE_MYSTERY,
        GENRE_PRE_CODE,
        GENRE_ROMANCE,
        GENRE_SATIRE,
        GENRE_SCI_FI,
        GENRE_SCREW_BALL,
        GENRE_SWASH_BUCKLER,
        GENRE_THRILLER,
        GENRE_TV_MOVIE,
        GENRE_WAR,
        GENRE_WAR_DOCUMENTARY,
        GENRE_WESTERN,
        HIDE_WATCHED_MOVIES,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_NOT_YET_RATED,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_REMOTE_TRAILERS,
        INCLUDE_TMDB_TRAILERS,
        INCLUDE_TRAILER_FOLDERS,
        MINIMUM_DAYS_SINCE_WATCHED,
        # ITUNES_QUALITY,
        RATING_LIMIT,
        TMDB_SORT_ORDER,
        TMDB_ENABLE_SELECT_BY_YEAR_RANGE,
        TMDB_YEAR_RANGE_MINIMUM,
        TMDB_YEAR_RANGE_MAXIMUM,
        TMDB_TRAILER_TYPE,
        CACHE_TRAILER_CHECK_DAYS,
        TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        TMDB_MAX_DOWNLOAD_MOVIES]

    COMMON_TRAILER_LOADING_SETTINGS = [
        TMDB_VOTE_FILTER,
        TMDB_VOTE_VALUE,
        DO_NOT_RATED,
        FILTER_GENRES,
        GENRE_ACTION,
        GENRE_ADVENTURE,
        GENRE_ANIMATION,
        GENRE_BIOGRAPY,
        GENRE_COMEDY,
        GENRE_CRIME,
        GENRE_DARK_COMEDY,
        GENRE_DOCUMENTARY,
        GENRE_DRAMA,
        GENRE_EPIC,
        GENRE_FAMILY,
        GENRE_FANTASY,
        GENRE_FILM_NOIR,
        GENRE_FOREIGN,
        GENRE_HISTORY,
        GENRE_HORROR,
        GENRE_MELODRAMA,
        GENRE_MUSIC,
        GENRE_MUSICAL,
        GENRE_MYSTERY,
        GENRE_PRE_CODE,
        GENRE_ROMANCE,
        GENRE_SATIRE,
        GENRE_SCI_FI,
        GENRE_SCREW_BALL,
        GENRE_SWASH_BUCKLER,
        GENRE_THRILLER,
        GENRE_TV_MOVIE,
        GENRE_WAR,
        GENRE_WAR_DOCUMENTARY,
        GENRE_WESTERN,
        HIDE_WATCHED_MOVIES,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_NOT_YET_RATED,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_REMOTE_TRAILERS,
        INCLUDE_TMDB_TRAILERS,
        INCLUDE_TRAILER_FOLDERS,
        MINIMUM_DAYS_SINCE_WATCHED,
        # ITUNES_QUALITY,
        RATING_LIMIT,
        TMDB_ENABLE_SELECT_BY_YEAR_RANGE,
        TMDB_YEAR_RANGE_MINIMUM,
        TMDB_YEAR_RANGE_MAXIMUM,
        TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        TMDB_MAX_DOWNLOAD_MOVIES]

    ITUNES_SPECIFIC_SETTINGS = [
        # ITUNES_QUALITY,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE]

    LIBRARY_SPECIFIC_SETTINGS = [
        HIDE_WATCHED_MOVIES,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_REMOTE_TRAILERS,
        INCLUDE_TRAILER_FOLDERS]

    TMDB_SPECIFIC_SETTINGS = [
        ALLOW_FOREIGN_LANGUAGES,
        TMDB_SORT_ORDER,
        TMDB_TRAILER_TYPE,
        INCLUDE_TMDB_TRAILERS,
        TMDB_SORT_ORDER
    ]

    @staticmethod
    def get_addon():
        # type: () -> Addon
        """

        :return:
        """

        if Settings._addon_singleton is None:
            # Protect against case where Random Trailers is partially
            # installed, such that script.video.randomtrailers doesn't
            # exist
            try:
                Settings._addon_singleton = Addon(
                    'script.video.randomtrailers')
            except (Exception):
                pass

        return Settings._addon_singleton

    @staticmethod
    def on_settings_changed():
        # type: () -> None
        """

        :return:
        """
        Settings.save_settings()
        Settings.reload_settings()

    @staticmethod
    def reload_settings():
        # type: () -> None
        """

        :return:
        """
        Settings._addon_singleton = None
        Settings.get_addon()
        Settings.get_changed_settings(Settings.ALL_SETTINGS)

    @staticmethod
    def save_settings():
        # type: () -> None
        """

        :return:
        """
        try:
            Settings._previous_settings.clear()
            for setting in Settings.ALL_SETTINGS:
                Settings._previous_settings[setting] = Settings.get_addon(
                ).setting(setting)
        except (Exception):
            pass

    @staticmethod
    def get_saved_settings():
        # type: () -> Dict[TextType, TextType]
        """

        :return:
        """
        return Settings._previous_settings

    @staticmethod
    def get_changed_settings(settings_to_check):
        # type: (List[TextType]) -> List[TextType]
        """

        :param settings_to_check:
        :return:
        """

        Settings._logger.enter()
        changed_settings = []
        for setting in settings_to_check:
            previous_value = Settings._previous_settings.get(setting, None)
            try:
                current_value = Settings.get_addon().setting(setting)
            except (Exception):
                current_value = previous_value

            if previous_value != current_value:
                changed = True
                if module_logger.isEnabledFor(Logger.DEBUG):
                    Settings._logger.debug('setting changed:', setting, 'previous_value:',
                                           previous_value, 'current_value:', current_value)
            else:
                changed = False

            if changed:
                changed_settings.append(setting)

        return changed_settings

    @staticmethod
    def is_trailer_loading_settings_changed():
        # type: () -> bool
        """

        :return:
        """
        if len(Settings.get_changed_settings(Settings.TRAILER_LOADING_SETTINGS)) > 0:
            result = True
        result = False

        if module_logger.isEnabledFor(Logger.DEBUG):
            Settings._logger.debug('changed:', result)

        return result

    @staticmethod
    def is_common_trailer_loading_settings_changed():
        # type: () -> bool
        """

        :return:
        """
        if len(Settings.get_changed_settings(
                Settings.COMMON_TRAILER_LOADING_SETTINGS)) > 0:
            result = True
        result = False

        if module_logger.isEnabledFor(Logger.DEBUG):
            Settings._logger.debug('changed:', result)

        return result

    @staticmethod
    def is_library_loading_settings_changed():
        # type: () -> bool
        """

        :return:
        """
        if len(Settings.get_changed_settings(Settings.LIBRARY_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(Logger.DEBUG):
            Settings._logger.debug('changed:', result)
        return result

    @staticmethod
    def is_itunes_loading_settings_changed():
        # type: () -> bool
        """

        :return:
        """
        result = False
        if len(Settings.get_changed_settings(Settings.ITUNES_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(Logger.DEBUG):
            Settings._logger.debug('changed:', result)

        return result

    @staticmethod
    def is_tmdb_loading_settings_changed():
        # type: () -> bool
        """

        :return:
        """
        if len(Settings.get_changed_settings(Settings.TMDB_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(Logger.DEBUG):
            Settings._logger.debug('changed:', result)

        return result

    @staticmethod
    def get_adjust_volume():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.VOLUME)

    @staticmethod
    def is_allow_foreign_languages():
        # type: () -> bool
        """

        :return:
        """
        allow_foreign_languages = Settings.get_setting_bool(
            Settings.ALLOW_FOREIGN_LANGUAGES)
        return allow_foreign_languages

    @staticmethod
    def get_tmdb_avg_vote_preference():
        # type: () -> (int, int)
        """

        :return:
        """
        vote_comparison = Settings.get_setting_int(Settings.TMDB_VOTE_FILTER)
        vote_value = Settings.get_setting_int(Settings.TMDB_VOTE_VALUE)
        if vote_value < 0 or vote_value > 10:
            xbmc.log('Vote filter value must be in range 0..10'.encode(
                'utf-8'), xbmc.LOGWARNING)
            vote_value = int(6)

        return vote_comparison, vote_value

    @staticmethod
    def get_close_curtain_path():
        # type: () -> TextType
        """

        :return:
        """
        return xbmc.translatePath(os.path.join(
            Settings.get_media_path(), 'CurtainClosingSequence.flv')).decode('utf-8')

    @staticmethod
    def get_playlist_name(playlist_number):
        # type: (int) -> TextType
        """

        :return:
        """
        playlist_id = "playlist_name_" + str(playlist_number)
        playlist_name = Settings.get_addon().addon.getSetting(playlist_id).decode('utf-8')

        return playlist_name

    @staticmethod
    def is_debug():

        do_debug = Settings.get_setting_bool(Settings.DO_DEBUG)
        return do_debug

    @staticmethod
    def get_do_not_rated_setting():
        # type: () -> bool
        """

        :return:
        """
        do_nr = Settings.get_setting_bool(Settings.DO_NOT_RATED)
        return do_nr

    @staticmethod
    def get_filter_genres():
        # type: () -> bool
        """

        :return:
        """

        return Settings.get_setting_bool(Settings.FILTER_GENRES)

    @staticmethod
    def get_genre(genre_name):
        # type: (TextType) -> int
        """

        :param genre_name:
        :return:
        """
        value = 0
        try:
            # All genres are 0 (Ignore) if filtering ('do_genre') is False

            if Settings.get_filter_genres():
                value = Settings.get_setting_int(genre_name)
        except (Exception) as e:
            LazyLogger.exception('setting: ' + genre_name)
        return value

    @staticmethod
    def get_genre_action():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_ACTION)

    @staticmethod
    def get_genre_adventure():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_ADVENTURE)

    @staticmethod
    def get_genre_animation():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_ANIMATION)

    @staticmethod
    def get_genre_biography():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_BIOGRAPY)

    @staticmethod
    def get_genre_comedy():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_COMEDY)

    @staticmethod
    def get_genre_crime():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_CRIME)

    @staticmethod
    def get_genre_dark_comedy():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_DARK_COMEDY)

    @staticmethod
    def get_genre_documentary():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_DOCUMENTARY)

    @staticmethod
    def get_genre_drama():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_DRAMA)

    @staticmethod
    def get_genre_epic():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_EPIC)

    @staticmethod
    def get_genre_family():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_FAMILY)

    @staticmethod
    def get_genre_fantasy():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_FANTASY)

    @staticmethod
    def get_genre_film_noir():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_FILM_NOIR)

    # A number of non-English trailers are marked foreign
    @staticmethod
    def get_genre_foreign():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_FOREIGN)

    @staticmethod
    def get_genre_history():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_HISTORY)

    @staticmethod
    def get_genre_horror():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_HORROR)

    @staticmethod
    def get_genre_melodrama():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_MELODRAMA)

    @staticmethod
    def get_genre_music():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_MUSIC)

    @staticmethod
    def get_genre_musical():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_MUSICAL)

    @staticmethod
    def get_genre_mystery():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_MYSTERY)

    @staticmethod
    def get_genre_pre_code():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_PRE_CODE)

    @staticmethod
    def get_genre_romance():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_ROMANCE)

    @staticmethod
    def get_genre_satire():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_SATIRE)

    @staticmethod
    def get_genre_sci_fi():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_SCI_FI)

    @staticmethod
    def get_genre_screw_ball():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_SCREW_BALL)

    @staticmethod
    def get_genre_swash_buckler():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_SWASH_BUCKLER)

    @staticmethod
    def get_genre_thriller():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_THRILLER)

    @staticmethod
    def get_genre_tv_movie():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_TV_MOVIE)

    @staticmethod
    def get_genre_war():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_WAR)

    @staticmethod
    def get_genre_war_documentary():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_WAR_DOCUMENTARY)

    @staticmethod
    def get_genre_western():
        # type: () -> int
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_WESTERN)

    @staticmethod
    def is_group_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.GROUP_TRAILERS)

    '''
        Get group_delay setting in milliseconds
    '''

    @staticmethod
    def get_group_delay():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.GROUP_DELAY) * 60

    @staticmethod
    def get_trailers_per_group():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.TRAILERS_PER_GROUP)

    @staticmethod
    def get_hide_watched_movies():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.HIDE_WATCHED_MOVIES)

    @staticmethod
    def get_include_clips():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_CLIPS)

    @staticmethod
    def get_include_featurettes():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_FEATURETTES)

    @staticmethod
    def get_include_teasers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TEASERS)

    @staticmethod
    def get_include_itunes_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_ITUNES_TRAILERS)

    @staticmethod
    def get_include_itunes_trailer_type():
        # type: () -> int
        """

        :return:
        """
        # "Coming Soon|Just Added|Popular|Exclusive|All"
        # See Constants.iTunes

        trailer_type = Settings.get_setting_int(Settings.ITUNES_TRAILER_TYPE)
        return trailer_type

    @staticmethod
    def get_include_library_no_trailer_info():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(
            Settings.INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO)

    @staticmethod
    def get_include_library_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_LIBRARY_TRAILERS)

    @staticmethod
    def get_include_not_yet_rated_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_NOT_YET_RATED)

    @staticmethod
    def get_include_library_remote_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(
            Settings.INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS)

    @staticmethod
    def get_include_remote_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_REMOTE_TRAILERS)

    @staticmethod
    def get_include_tmdb_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TMDB_TRAILERS)

    @staticmethod
    def get_include_trailer_folders():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TRAILER_FOLDERS)

    @staticmethod
    def is_set_fullscreen_when_screensaver():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.SET_FULLSCREEN_WHEN_SCREENSAVER)

    @staticmethod
    def getLang_iso_639_1():
        # type: () -> TextType
        """
        Gets two-character language code (ex: 'en')

        :return:_included_genres
        """
        # TODO: Resolve this Kodi bug:

        iso_639_1_name = xbmc.getLanguage(format=xbmc.ISO_639_1, region=True)
        iso_639_2_name = xbmc.getLanguage(format=xbmc.ISO_639_2, region=True)

        full_name = xbmc.getLanguage(format=xbmc.ENGLISH_NAME, region=True)

        Settings._logger.debug('iso_639_1:', iso_639_1_name)
        Settings._logger.debug('iso_639_2:', iso_639_2_name)
        Settings._logger.debug('ENGLISH_NAME:', full_name)
        # return iso_639_1_name
        return 'en'

    @staticmethod
    def getLang_iso_639_2():
        # type: () -> TextType
        """
        Gets three-character language code. Not sure if this is
        ISO 639-2/T or ISO 639-2/B, but it may not matter for our purposes

        Example: 'eng'

        :return:
        """
        iso_639_2_name = xbmc.getLanguage(xbmc.ISO_639_2)
        return iso_639_2_name

    @staticmethod
    def getLang_iso_3166_1():
        # type: () -> TextType
        """
        Country code

        :return:

            We have to 'roll your own' here. Sigh

            TODO: Make a setting. Since this is used (at least part of
            the time) to determine the certification body (mpaa) then
            should change name. Also, only US is supported.
        """
        return 'US'

    @staticmethod
    def get_locale():
        # type: () -> None
        """

        :return:
        """
        locale.setlocale(locale.LC_ALL, 'en_US')

    @staticmethod
    def get_max_tmdb_trailers():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.TMDB_MAX_NUMBER_OF_TRAILERS)

    @staticmethod
    def is_report_actor_stats():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.REPORT_ACTOR_STATS)

    @staticmethod
    def get_report_max_top_actors():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.REPORT_MAXIMUM_NUMBER_OF_TOP_ACTORS)

    @staticmethod
    def is_enable_movie_stats():
        # type() -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_MOVIE_STATS)

    @staticmethod
    def disable_movie_stats():
        # type() -> None
        """
        Used to disable generating reports on next run of Kodi. User must
        set each time they want new reports.

        :return:
        """
        Settings.set_setting_bool(Settings.ENABLE_MOVIE_STATS, False)

    @staticmethod
    def is_report_genre_stats():
        # type() -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.REPORT_GENRE_STATS)

    @staticmethod
    def is_report_tag_stats():
        # type() -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.REPORT_TAG_STATS)

    @staticmethod
    def get_max_trailer_length():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.MAXIMUM_TRAILER_LENGTH)

    @staticmethod
    def get_media_path():
        # type: () -> TextType
        """

        :return:
        """
        return xbmc.translatePath(os.path.join(
            Settings.get_resources_path(), 'media')).decode('utf-8')

    @staticmethod
    def get_minimum_days_since_watched():
        # type: () -> TextType
        """

        :return:
        """
        return Settings.get_addon().setting(Settings.MINIMUM_DAYS_SINCE_WATCHED)

    @staticmethod
    def is_normalize_volume_of_downloaded_trailers():
        # type: () -> bool
        """

        :return:
        """
        normalize = Settings.get_setting_bool(
            Settings.NORMALIZE_VOLUME_OF_DOWNLOADED_TRAILERS)
        return normalize

    @staticmethod
    def is_normalize_volume_of_local_trailers():
        # type: () -> bool
        """

        :return:
        """
        normalize = Settings.get_setting_bool(
            Settings.NORMALIZE_VOLUME_OF_LOCAL_TRAILERS)
        return normalize

    @staticmethod
    def get_number_of_trailers_to_play():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.NUMBER_OF_TRAILERS_TO_PLAY)

    @staticmethod
    def get_open_curtain_path():
        # type: () -> TextType
        """

        :return:
        """
        return xbmc.translatePath(os.path.join(
            Settings.get_media_path(), 'CurtainOpeningSequence.flv')).decode('utf-8')

    @staticmethod
    def prompt_for_settings():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.PROMPT_FOR_SETTINGS)

    '''
    @staticmethod
    def get_itunes_quality():
        # type: () -> List[TextType][int]
        """

        :return:
        """
        quality_index = Settings.get_setting_int(Settings.ITUNES_QUALITY)
        return ["480p", "720p", "1080p"][quality_index]
    '''

    @staticmethod
    def get_rating_limit_setting():
        # type: () -> TextType
        """

        :return:
        """
        try:
            rating_limit = Settings.get_addon().setting(Settings.RATING_LIMIT)
        except (Exception):
            rating_limit = ''

        return rating_limit

    @staticmethod
    def get_tmdb_trailer_preference():
        # type: () -> TextType
        """

        :return:
        """
        trailer_preference = Settings.get_setting_int(Settings.TMDB_SORT_ORDER)
        if trailer_preference == RemoteTrailerPreference.NEWEST:
            return 'release_date.desc'
        if trailer_preference == RemoteTrailerPreference.OLDEST:
            return 'release_date.asc'
        if trailer_preference == RemoteTrailerPreference.HIGHEST_RATED:
            return 'vote_average.desc'
        if trailer_preference == RemoteTrailerPreference.LOWEST_RATED:
            return 'vote_average.asc'
        if trailer_preference == RemoteTrailerPreference.MOST_VOTES:
            return 'vote_count.desc'
        if trailer_preference == RemoteTrailerPreference.LEAST_VOTES:
            return 'vote_count.asc'

    @staticmethod
    def get_resources_path():
        # type: () -> TextType
        """

        :return:
        """
        return xbmc.translatePath(
            os.path.join(Constants.ADDON_PATH, 'resources')).decode('utf-8')

    @staticmethod
    def get_rotten_tomatoes_api_key():
        # type: () -> TextType
        """

        :return:
        """
        ROTTEN_TOMATOES_API_KEY = 'ynyq3vsaps7u8rb9nk98rcr'
        return ROTTEN_TOMATOES_API_KEY

    @staticmethod
    def is_tmdb_select_by_year_range():
        # type: () -> bool
        """

        :return:
        """
        select_by_year_range = Settings.get_setting_bool(
            Settings.TMDB_ENABLE_SELECT_BY_YEAR_RANGE)
        return select_by_year_range

    @staticmethod
    def get_tmdb_minimum_year():
        # type: () -> int
        """

        :return:
        """
        try:
            minimum_year = Settings.get_setting_int(Settings.TMDB_YEAR_RANGE_MINIMUM)
        except (Exception):
            minimum_year = 1928  # Start of talkies
        return minimum_year

    @staticmethod
    def get_tmdb_maximum_year():
        # type: () -> int
        """

        :return:
        """
        try:
            maximum_year = Settings.get_setting_int(Settings.TMDB_YEAR_RANGE_MAXIMUM)
        except (Exception):
            maximum_year = datetime.datetime.now().year

        return maximum_year

    @staticmethod
    def get_setting_bool(setting):
        # type: (TextType) -> bool
        """

        :return:
        """
        # Kodi returns a bool as a -1 | 0
        try:
            value = Settings.get_addon().bool_setting(setting)
        except (Exception):
            value = False

        return bool(value)

    @staticmethod
    def set_setting_bool(setting, value):
        # type: (TextType, bool) -> None
        """
        :setting:
        :value:
        :return:
        """
        try:
            Settings.get_addon().addon.setSettingBool(setting, value)
        except (Exception):
            value = False

        return

    @staticmethod
    def get_setting_float(setting):
        # type: (TextType) -> float
        """

        :return:
        """
        try:
            value = Settings.get_addon().addon.getSetting(setting)
        except (Exception) as e:
            value = 1.0
        try:
            value = float(value)
        except (Exception) as e:
            Settings._logger.error('Setting:', setting,
                                   ' value is not an float. Setting to 0')
            value = 0
        return value

    @staticmethod
    def get_setting_int(setting):
        # type: (TextType) -> int
        """

        :return:
        """
        try:
            value = Settings.get_addon().addon.getSetting(setting)
        except (Exception) as e:
            value = 1
        try:
            value = int(value)
        except (Exception) as e:
            Settings._logger.error('Setting:', setting,
                                   ' value is not an integer. Setting to 0')
            value = 0
        return value

    @staticmethod
    def get_show_curtains():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.SHOW_CURTAINS)

    @staticmethod
    def get_show_movie_title():
        # type: () -> bool
        """

        :return:
        """
        show_title = Settings.get_setting_bool(Settings.SHOW_TITLE)
        return show_title

    # TODO: Eliminate if this can be avoided in preference to iso-639-1/2.
    #       Kodi does not supply this method, further, unless it is a standard
    #       it is likely not to be universally used by the different services.
    #
    @staticmethod
    def getSpokenLanguage():
        # type: () -> TextType
        """

        :return:
        """
        return 'English'

    '''
        Time in seconds to display detailed movie info prior
        to playing a trailer. Default is 5 seconds
    '''

    @staticmethod
    def get_time_to_display_detail_info():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.TIME_TO_DISPLAY_DETAIL_INFO)

    @staticmethod
    def get_tmdb_api_key():
        # type: () -> TextType
        """

        :return:
        """
        TMDB_API_KEY = '35f17ee61909355c4b5d5c4f2c967f6c'
        try:
            tmdb_api_key = Settings.get_addon().setting(Settings.TMDB_API_KEY)
        except (Exception) as e:
            tmdb_api_key = None

        if tmdb_api_key is None or tmdb_api_key == '':
            tmdb_api_key = TMDB_API_KEY
        return tmdb_api_key

    @staticmethod
    def get_tmdb_trailer_type():
        # type: () -> TextType
        """

        :return:
        """
        try:
            trailer_type = Settings.get_addon().setting(Settings.TMDB_TRAILER_TYPE)
        except (Exception) as e:
            trailer_type = None

        return trailer_type

    @staticmethod
    def get_trailers_paths():
        # type: () -> TextType
        """

        :return:
        """
        try:
            trailer_path = Settings.get_addon().setting('path')
        except (Exception) as e:
            trailer_path = None

        return trailer_path

    @staticmethod
    def get_update_tmdb_id():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.UPDATE_TMDB_ID)

    @staticmethod
    def get_volume():
        # type: () -> int
        """

        :return:
        """
        volume = 100
        if Settings.get_adjust_volume():
            volume = Settings.get_setting_int(Settings.VOLUME)

    @staticmethod
    def get_tmdb_include_old_movie_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.TMDB_INCLUDE_OLD_MOVIE_TRAILERS)

    @staticmethod
    def get_tmdb_max_download_movies():
        # type: () -> int
        """
        :return:
        """
        return Settings.get_setting_int(Settings.TMDB_MAX_DOWNLOAD_MOVIES)

    @staticmethod
    def is_trace_enabled():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_TRACE)

    @staticmethod
    def is_trace_stats_enabled():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_TRACE_STATS)

    @staticmethod
    def is_use_tmdb_cache():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_REMOTE_DATA_CACHE)

    @staticmethod
    def is_use_trailer_cache():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_TRAILER_CACHE)

    @staticmethod
    def get_expire_remote_db_cache_entry_days():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.CACHE_EXPIRATION_DAYS)

    @staticmethod
    def get_expire_remote_db_trailer_check_days():
        # type: () -> int
        """

        :return:
        """
        return Settings.get_setting_int(Settings.CACHE_TRAILER_CHECK_DAYS)

    @staticmethod
    def get_expire_trailer_cache_days():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_int(Settings.EXPIRE_TRAILER_CACHE_DAYS)

    @staticmethod
    def get_downloaded_trailer_cache_path():
        # type: () -> TextType
        """

        :return:
        """
        try:
            path = xbmc.translatePath(
                Settings.get_addon().setting(Settings.TRAILER_CACHE_PATH))
            path = path.decode('utf-8')
        except (Exception) as e:
            path = None

        return path

    @staticmethod
    def get_remote_db_cache_path():
        # type: () -> TextType
        """

        :return:
        """
        try:
            path = xbmc.translatePath(
                Settings.get_addon().setting(Settings.CACHE_PATH))
            path = path.decode('utf-8')
        except (Exception) as e:
            path = None
        return path

    @staticmethod
    def is_limit_cached_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIMIT_CACHED_TRAILERS)

    @staticmethod
    def is_limit_number_of_cached_trailers():
        # type: () -> bool
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_trailers():
            value = Settings.get_setting_bool(
                Settings.LIMIT_NUMBER_OF_CACHED_TRAILERS)
        return value

    @staticmethod
    def get_max_number_of_cached_trailers():
        # type: () -> int
        """

        :return:
        """
        value = None
        if Settings.is_limit_number_of_cached_trailers():
            value = Settings.get_setting_int(
                Settings.MAX_NUMBER_OF_CACHED_TRAILERS)
        return value

    @staticmethod
    def is_limit_size_of_cached_trailers():
        # type: () -> bool
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_trailers():
            value = Settings.get_setting_bool(
                Settings.LIMIT_SIZE_OF_CACHED_TRAILERS)

        return value

    @staticmethod
    def get_max_size_of_cached_trailers_mb():
        # type: () -> int
        """

        :return:
        """
        value = None
        if Settings.is_limit_size_of_cached_trailers():
            value = Settings.get_setting_int(
                Settings.MAX_SIZE_OF_CACHED_TRAILERS)
        return value

    @staticmethod
    def is_limit_percent_of_cached_trailers():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIMIT_PERCENT_OF_CACHED_TRAILERS)

    @staticmethod
    def get_max_percent_of_cached_trailers():
        # type: () -> Optional[float]
        """

        :return:
        """
        value = None
        if Settings.is_limit_percent_of_cached_trailers():
            value = Settings.get_setting_float(
                Settings.MAX_PERCENT_OF_CACHED_TRAILERS) / 100.0
        return value

    @staticmethod
    def is_limit_cached_json():
        # type: () -> bool
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIMIT_CACHED_JSON)

    @staticmethod
    def is_limit_number_of_cached_json():
        # type: () -> bool
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_json():
            value = Settings.get_setting_bool(
                Settings.LIMIT_NUMBER_OF_CACHED_JSON)
        return value

    @staticmethod
    def get_max_number_of_cached_json():
        # type: () -> int
        """

        :return:
        """
        value = 0
        if Settings.is_limit_number_of_cached_json():
            value = Settings.get_setting_int(
                Settings.MAX_NUMBER_OF_CACHED_JSON)
        return value

    @staticmethod
    def is_limit_size_of_cached_json():
        # type: () -> bool
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_json():
            value = Settings.get_setting_bool(
                Settings.LIMIT_SIZE_OF_CACHED_JSON)
        return value

    @staticmethod
    def get_max_size_of_cached_json_mb():
        # type: () -> int
        """

        :return:
        """
        value = 0
        if Settings.is_limit_size_of_cached_json():
            value = Settings.get_setting_int(
                Settings.MAX_SIZE_OF_CACHED_JSON)
        return value

    @staticmethod
    def is_limit_percent_of_cached_json():
        # type: () -> bool
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_json():
            value = Settings.get_setting_bool(
                Settings.LIMIT_PERCENT_OF_CACHED_JSON)
        return value

    @staticmethod
    def get_max_percent_of_cached_json():
        # type: () -> Optional[float]
        """

        :return:
        """
        value = None
        if Settings.is_limit_percent_of_cached_json():
            value = Settings.get_setting_float(
                Settings.MAX_PERCENT_OF_CACHED_JSON) / 100.0
        return value

