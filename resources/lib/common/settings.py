# -*- coding: utf-8 -*-
"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
import datetime
import locale
import os

import xbmc
import xbmcvfs

from common.movie_constants import MovieField
from kutils.kodiaddon import Addon

from common.imports import *
from common.constants import (Constants,
                              RemoteTrailerPreference)
from common.logger import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class Settings:
    """

    """
    _addon_singleton = None
    _logger: BasicLogger = module_logger.getChild('Settings')
    _previous_settings: Dict[str, Any] = {}
    DEFAULT_ROTTEN_TOMATOES_API_KEY: str = 'ynyq3vsaps7u8rb9nk98rcr'
    DEFAULT_TMDB_API_KEY = '35f17ee61909355c4b5d5c4f2c967f6c'

    ADJUST_VOLUME = 'do_volume'
    TMDB_ALLOW_FOREIGN_LANGUAGES = 'tmdb_allow_foreign_languages'
    TMDB_VOTE_FILTER = 'tmdb_vote_filter'
    TMDB_VOTE_VALUE = 'tmdb_vote_value'
    COUNTRY_CODE = 'country_code'
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
    GENRE_DOCUMENTARY = 'g_documentary'
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
    GENRE_SCREW_BALL = 'g_screwball_comedy'
    GENRE_SWASH_BUCKLER = 'g_swashbuckler'
    GENRE_THRILLER = 'g_thriller'
    GENRE_TV_MOVIE = 'g_tv_movie'
    GENRE_WAR = 'g_war'
    GENRE_WAR_DOCUMENTARY = 'g_war_documentary'
    GENRE_WESTERN = 'g_western'
    GROUP_TRAILERS = 'group_trailers'
    GROUP_DELAY = 'group_delay'
    TRAILERS_PER_GROUP = 'trailers_per_group'
    LIBRARY_HIDE_WATCHED_MOVIES = 'hide_watched'
    LOGGING_LEVEL = 'log_level'
    INCLUDE_CLIPS = 'do_clips'
    INCLUDE_FEATURETTES = 'do_featurettes'
    INCLUDE_TEASERS = 'do_teasers'
    INCLUDE_ITUNES_TRAILERS = 'do_itunes'
    ITUNES_TRAILER_TYPE = 'itunes_trailer_type'
    INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO = 'do_library_no_trailer_info'
    INCLUDE_LIBRARY_TRAILERS = 'do_library'
    INCLUDE_NOT_YET_RATED = 'do_notyetrated'
    INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS = 'do_library_remote_trailers'
    INCLUDE_TMDB_TRAILERS = 'do_tmdb'
    INCLUDE_TRAILER_FOLDERS = 'do_folder'
    INCLUDE_TFH_TRAILERS = 'include_tfh_trailers'
    MAX_TFH_TRAILERS = 'max_tfh_trailers'
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
    FFMPEG_PATH = 'ffmpeg_path'
    REPORT_ACTOR_STATS = 'report_actor_stats'
    REPORT_TAG_STATS = 'report_tag_stats'
    REPORT_MAXIMUM_NUMBER_OF_TOP_ACTORS = 'max_report_top_actors'
    REPORT_GENRE_STATS = 'report_genre_stats'
    MAXIMUM_TRAILER_PLAY_SECONDS = 'maximum_trailer_play_seconds'
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
    TFH_CACHE_EXPIRATION_DAYS = 'tfh_cache_expiration_days'
    LICENSE_DISPLAY_SECONDS = 'license_display_seconds'
    EXPIRE_TRAILER_CACHE_DAYS = 'trailer_cache_expiration_days'
    CACHE_TRAILER_CHECK_DAYS = 'trailer_existence_cache_check_days'
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

    YOUTUBE_USERNAME: Final[str] = 'youtube_username'
    YOUTUBE_PASSWORD: Final[str] = 'youtube_password'
    YOUTUBE_USE_NETRC: Final[str] = 'youtube_use_netrc'

    # HIDDEN SETTINGS

    YOUTUBE_DL_COOKIE_PATH = 'youtube_dl_cookie_path'
    YOUTUBE_DL_CACHE_PATH = 'youtube_dl_cache_path'

    ALL_SETTINGS: List[str] = [
        ADJUST_VOLUME,
        COUNTRY_CODE,
        TMDB_ALLOW_FOREIGN_LANGUAGES,
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
        LIBRARY_HIDE_WATCHED_MOVIES,
        LOGGING_LEVEL,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_NOT_YET_RATED,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_TMDB_TRAILERS,
        INCLUDE_TRAILER_FOLDERS,
        LIMIT_CACHED_TRAILERS,
        LIMIT_NUMBER_OF_CACHED_TRAILERS,
        MAX_NUMBER_OF_CACHED_TRAILERS,
        TMDB_MAX_NUMBER_OF_TRAILERS,
        INCLUDE_TFH_TRAILERS,

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
        FFMPEG_PATH,
        REPORT_ACTOR_STATS,
        REPORT_TAG_STATS,
        REPORT_MAXIMUM_NUMBER_OF_TOP_ACTORS,
        REPORT_GENRE_STATS,
        MAXIMUM_TRAILER_PLAY_SECONDS,
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
        PLAYLIST_10,
        YOUTUBE_USERNAME,
        YOUTUBE_PASSWORD,
        YOUTUBE_USE_NETRC,
        YOUTUBE_DL_COOKIE_PATH,
        YOUTUBE_DL_CACHE_PATH,
    ]

    TRAILER_LOADING_SETTINGS: List[str] = [
        COUNTRY_CODE,
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
        LIBRARY_HIDE_WATCHED_MOVIES,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_NOT_YET_RATED,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_TMDB_TRAILERS,
        INCLUDE_TFH_TRAILERS,
        INCLUDE_TRAILER_FOLDERS,
        MINIMUM_DAYS_SINCE_WATCHED,
        # ITUNES_QUALITY,
        RATING_LIMIT,
        TMDB_SORT_ORDER,
        TMDB_ENABLE_SELECT_BY_YEAR_RANGE,
        TMDB_YEAR_RANGE_MINIMUM,
        TMDB_YEAR_RANGE_MAXIMUM,
        TMDB_TRAILER_TYPE,
        TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        TMDB_MAX_DOWNLOAD_MOVIES]

    COMMON_TRAILER_LOADING_SETTINGS: List[str] = [
        COUNTRY_CODE,
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
        INCLUDE_NOT_YET_RATED,
        MINIMUM_DAYS_SINCE_WATCHED,
        RATING_LIMIT]

    ITUNES_SPECIFIC_SETTINGS: List[str] = [
        # ITUNES_QUALITY,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        INCLUDE_ITUNES_TRAILERS,
        ITUNES_TRAILER_TYPE]

    LIBRARY_SPECIFIC_SETTINGS: List[str] = [
        LIBRARY_HIDE_WATCHED_MOVIES,
        INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO,
        INCLUDE_LIBRARY_TRAILERS,
        INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS,
        INCLUDE_TRAILER_FOLDERS]

    TMDB_SPECIFIC_SETTINGS: List[str] = [
        TMDB_ALLOW_FOREIGN_LANGUAGES,
        TMDB_SORT_ORDER,
        TMDB_TRAILER_TYPE,
        INCLUDE_TMDB_TRAILERS,
        INCLUDE_CLIPS,
        INCLUDE_FEATURETTES,
        INCLUDE_TEASERS,
        TMDB_SORT_ORDER,
        TMDB_ENABLE_SELECT_BY_YEAR_RANGE,
        TMDB_VOTE_VALUE,
        TMDB_VOTE_FILTER,
        TMDB_YEAR_RANGE_MINIMUM,
        TMDB_YEAR_RANGE_MAXIMUM,
        TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        TMDB_MAX_DOWNLOAD_MOVIES
    ]

    TFH_SPECIFIC_SETTINGS: List[str] = [
        INCLUDE_TFH_TRAILERS,
        MAX_TFH_TRAILERS]

    @staticmethod
    def get_addon() -> Addon:
        """

        :return:
        """

        if Settings._addon_singleton is None:
            # Protect against case where Random Trailers is partially
            # installed, such that script.video.randomtrailers doesn't
            # exist
            try:
                Settings._addon_singleton = Addon(Constants.ADDON_ID)
            except Exception:
                pass

        return Settings._addon_singleton

    @staticmethod
    def on_settings_changed() -> None:
        """

        :return:
        """
        Settings.save_settings()
        Settings.reload_settings()

    @staticmethod
    def reload_settings() -> None:
        """

        :return:
        """
        Settings._addon_singleton = None
        Settings.get_addon()
        Settings.get_changed_settings(Settings.ALL_SETTINGS)

    @staticmethod
    def save_settings() -> None:
        """

        :return:
        """
        try:
            Settings._previous_settings.clear()
            for setting in Settings.ALL_SETTINGS:
                Settings._previous_settings[setting] = Settings.get_addon(
                ).setting(setting)
        except Exception:
            pass

    @staticmethod
    def get_saved_settings() -> Dict[str, str]:
        """

        :return:
        """
        return Settings._previous_settings

    @staticmethod
    def get_changed_settings(settings_to_check: List[str]) -> List[str]:
        """

        :param settings_to_check:
        :return:
        """

        Settings._logger.debug('entered')
        changed_settings = []
        for setting in settings_to_check:
            previous_value = Settings._previous_settings.get(setting, None)
            try:
                current_value = Settings.get_addon().setting(setting)
            except Exception:
                current_value = previous_value

            if previous_value != current_value:
                changed = True
                if module_logger.isEnabledFor(DEBUG):
                    Settings._logger.debug(f'setting changed: {setting} '
                                           f'previous_value: {previous_value} '
                                           f'current_value: {current_value}')
            else:
                changed = False

            if changed:
                changed_settings.append(setting)

        return changed_settings

    @staticmethod
    def is_common_trailer_loading_settings_changed() -> bool:
        """

        :return:
        """
        if len(Settings.get_changed_settings(
                Settings.COMMON_TRAILER_LOADING_SETTINGS)) > 0:
            result = True
        else:
            result = False

        if module_logger.isEnabledFor(DEBUG):
            Settings._logger.debug(f'changed: {result}')

        return result

    @staticmethod
    def is_library_loading_settings_changed() -> bool:
        """

        :return:
        """
        if len(Settings.get_changed_settings(Settings.LIBRARY_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_common_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(DEBUG):
            Settings._logger.debug(f'changed: {result}')
        return result

    @staticmethod
    def is_itunes_loading_settings_changed() -> bool:
        """

        :return:
        """
        result = False
        if len(Settings.get_changed_settings(Settings.ITUNES_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_common_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(DEBUG):
            Settings._logger.debug(f'changed: {result}')

        return result

    @staticmethod
    def is_tmdb_loading_settings_changed() -> bool:
        """

        :return:
        """
        if len(Settings.get_changed_settings(Settings.TMDB_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_common_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(DEBUG):
            Settings._logger.debug(f'changed: {result}')

        return result

    @staticmethod
    def is_tfh_loading_settings_changed() -> bool:
        """

        :return:
        """
        if len(Settings.get_changed_settings(Settings.TFH_SPECIFIC_SETTINGS)) > 0:
            result = True
        else:
            result = Settings.is_common_trailer_loading_settings_changed()

        if module_logger.isEnabledFor(DEBUG):
            Settings._logger.debug(f'changed: {result}')

        return result

    @staticmethod
    def get_max_number_of_tfh_trailers() -> int:
        """

        :return:
        """

        return Settings.get_setting_int(Settings.MAX_TFH_TRAILERS)

    '''
    @staticmethod
    def get_adjust_volume() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.VOLUME)
    '''

    @staticmethod
    def is_allow_foreign_languages() -> bool:
        """

        :return:
        """
        allow_foreign_languages = Settings.get_setting_bool(
            Settings.TMDB_ALLOW_FOREIGN_LANGUAGES)
        return allow_foreign_languages

    @staticmethod
    def get_tmdb_avg_vote_preference() -> (int, int):
        """

        :return:
        """
        vote_comparison = Settings.get_setting_int(Settings.TMDB_VOTE_FILTER)
        vote_value = Settings.get_setting_int(Settings.TMDB_VOTE_VALUE)
        if vote_value < 0 or vote_value > 10:
            xbmc.log('Vote filter value must be in range 0..10', xbmc.LOGWARNING)
            vote_value = int(6)

        return vote_comparison, vote_value

    @staticmethod
    def get_close_curtain_path() -> str:
        """

        :return:
        """
        return xbmcvfs.translatePath(os.path.join(
            Settings.get_media_path(), 'CurtainClosingSequence.flv'))

    @staticmethod
    def get_playlist_name(playlist_number: int) -> Union[str, None]:
        """

        :return:
        """
        playlist_id = f'playlist_name_{str(playlist_number)}'
        playlist_name = Settings.get_addon().addon.getSetting(playlist_id)
        if playlist_name is None:
            playlist_name = ''

        return playlist_name

    @staticmethod
    def is_debug() -> bool:

        do_debug = Settings.get_setting_bool(Settings.DO_DEBUG)
        return do_debug

    @staticmethod
    def get_do_not_rated_setting() -> bool:
        """

        :return:
        """
        do_nr = Settings.get_setting_bool(Settings.DO_NOT_RATED)
        return do_nr

    @staticmethod
    def get_filter_genres() -> bool:
        """

        :return:
        """

        return Settings.get_setting_bool(Settings.FILTER_GENRES)

    @staticmethod
    def get_genre(genre_name: str) -> int:
        """

        :param genre_name:
        :return:
        """
        value = 0
        try:
            # All genres are 0 (Ignore) if filtering ('do_genre') is False

            if Settings.get_filter_genres():
                value = Settings.get_setting_int(genre_name)
        except Exception as e:
            module_logger.exception(f'setting: {genre_name}')
        return value

    @staticmethod
    def get_genre_action() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_ACTION)

    @staticmethod
    def get_genre_adventure() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_ADVENTURE)

    @staticmethod
    def get_genre_animation() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_ANIMATION)

    @staticmethod
    def get_genre_biography() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_BIOGRAPY)

    @staticmethod
    def get_genre_comedy() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_COMEDY)

    @staticmethod
    def get_genre_crime() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_CRIME)

    @staticmethod
    def get_genre_dark_comedy() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_DARK_COMEDY)

    @staticmethod
    def get_genre_documentary() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_DOCUMENTARY)

    @staticmethod
    def get_genre_drama() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_DRAMA)

    @staticmethod
    def get_genre_epic() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_EPIC)

    @staticmethod
    def get_genre_family() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_FAMILY)

    @staticmethod
    def get_genre_fantasy() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_FANTASY)

    @staticmethod
    def get_genre_film_noir() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_FILM_NOIR)

    # A number of non-English trailers are marked foreign
    @staticmethod
    def get_genre_foreign() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_FOREIGN)

    @staticmethod
    def get_genre_history() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_HISTORY)

    @staticmethod
    def get_genre_horror() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_HORROR)

    @staticmethod
    def get_genre_melodrama() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_MELODRAMA)

    @staticmethod
    def get_genre_music() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_MUSIC)

    @staticmethod
    def get_genre_musical() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_MUSICAL)

    @staticmethod
    def get_genre_mystery() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_MYSTERY)

    @staticmethod
    def get_genre_pre_code() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_PRE_CODE)

    @staticmethod
    def get_genre_romance() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_ROMANCE)

    @staticmethod
    def get_genre_satire() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_SATIRE)

    @staticmethod
    def get_genre_sci_fi() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_SCI_FI)

    @staticmethod
    def get_genre_screw_ball() -> int:
        """

        :return:
        """
        return Settings.get_genre(Settings.GENRE_SCREW_BALL)

    @staticmethod
    def get_genre_swash_buckler() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_SWASH_BUCKLER)

    @staticmethod
    def get_genre_thriller() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_THRILLER)

    @staticmethod
    def get_genre_tv_movie() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_TV_MOVIE)

    @staticmethod
    def get_genre_war() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_WAR)

    @staticmethod
    def get_genre_war_documentary() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_WAR_DOCUMENTARY)

    @staticmethod
    def get_genre_western() -> int:
        """
            Returns an "enum' indicating whether to:
                0 - Ignore this genre in filtering movies
                1 - Include movies with this genre in an OR manner
                2 - Exclude movies with this genre in an OR manner
        :return:
        """
        return Settings.get_genre(Settings.GENRE_WESTERN)

    @staticmethod
    def is_group_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.GROUP_TRAILERS)

    '''
        Get group_delay setting in milliseconds
    '''

    @staticmethod
    def get_group_delay() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.GROUP_DELAY) * 60

    @staticmethod
    def get_trailers_per_group() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.TRAILERS_PER_GROUP)

    @staticmethod
    def get_hide_watched_movies() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIBRARY_HIDE_WATCHED_MOVIES)

    @staticmethod
    def get_include_clips() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_CLIPS)

    @staticmethod
    def get_include_featurettes() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_FEATURETTES)

    @classmethod
    def get_include_teasers(cls) -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TEASERS)

    @classmethod
    def is_allowed_trailer_types(cls) -> List[str]:
        allowed_trailer_types: List[str] = []

        allowed_trailer_types.append(MovieField.TRAILER_TYPE_TRAILER)
        if cls.get_include_featurettes():
            allowed_trailer_types.append(MovieField.TRAILER_TYPE_FEATURETTE)

        if cls.get_include_teasers():
            allowed_trailer_types.append(MovieField.TRAILER_TYPE_TEASER)
        return allowed_trailer_types

    @staticmethod
    def is_include_itunes_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_ITUNES_TRAILERS)

    @staticmethod
    def get_include_itunes_trailer_type() -> int:
        """

        :return:
        """
        # "Coming Soon|Just Added|Popular|Exclusive|All"
        # See Constants.iTunes

        trailer_type = Settings.get_setting_int(Settings.ITUNES_TRAILER_TYPE)
        return trailer_type

    @staticmethod
    def is_include_library_no_trailer_info() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(
            Settings.INCLUDE_LIBRARY_ENTRIES_WITHOUT_TRAILER_INFO)

    @staticmethod
    def is_include_library_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_LIBRARY_TRAILERS)

    @staticmethod
    def get_include_not_yet_rated_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_NOT_YET_RATED)

    @staticmethod
    def is_include_library_remote_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(
            Settings.INCLUDE_LIBRARY_ENTRIES_WITH_REMOTE_TRAILERS)

    @staticmethod
    def is_include_tmdb_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TMDB_TRAILERS)

    @staticmethod
    def is_include_trailer_folders() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TRAILER_FOLDERS)

    @staticmethod
    def is_include_tfh_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.INCLUDE_TFH_TRAILERS)

    @staticmethod
    def get_tfh_cache_expiration_days() -> int:
        return Settings.get_setting_int(Settings.TFH_CACHE_EXPIRATION_DAYS)

    @staticmethod
    def get_license_display_seconds() -> int:
        return Settings.get_setting_int(Settings.LICENSE_DISPLAY_SECONDS)

    @staticmethod
    def is_set_fullscreen_when_screensaver() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.SET_FULLSCREEN_WHEN_SCREENSAVER)

    @staticmethod
    def get_lang_iso_639_1() -> str:
        """
        Gets two-character language code (ex: 'en')

        :return:_included_genres
        """

        iso_639_1_name = xbmc.getLanguage(format=xbmc.ISO_639_1, region=True)
        iso_639_1_name = iso_639_1_name[0:2]

        return iso_639_1_name

    @staticmethod
    def get_lang_iso_639_2() -> str:
        """
        Gets three-character language code. Not sure if this is
        ISO 639-2/T or ISO 639-2/B, but it may not matter for our purposes

        Example: 'eng'

        :return:
        """
        iso_639_2_name = xbmc.getLanguage(xbmc.ISO_639_2)
        return iso_639_2_name

    @staticmethod
    def get_country_iso_3166_1() -> str:
        """
        Country code

        :return:

            We have to 'roll your own' here. Sigh

            TODO: Make a setting. Since this is used (at least part of
            the time) to determine the certification body (mpaa) then
            should change name. Also, only US is supported.

            Currently broken due to Kodi NLS bug (not passing locale
            to addons).
        """
        country_code = Settings.get_setting_str(Settings.COUNTRY_CODE)
        return country_code

        '''
        language_code = Settings.get_locale()
        # en_US
        # Settings._logger.debug(f'language: {language_code}')
        # Settings._logger.debug(f'split: {language_code.split("_")}')
        elements = language_code.split('_')
        if len(elements) == 2:
            country: str = elements[1]
        else:
            Settings._logger.warning(f'Invalid country code: {elements}')
            country = 'US'
        Settings._logger.debug(f'Country code: {country}')
        return country
        '''

    @staticmethod
    def get_locale() -> str:
        """

        :return:
        """
        # locale.setlocale(locale.LC_ALL, 'en_US')
        language_code, encoding = locale.getdefaultlocale()
        if language_code is None:
            language_code = ''
        '''
        Settings._logger.debug(f'default language_code: {language_code} '
                               f'encoding: {encoding}')
        envars = ['LC_ALL', 'LC_CTYPE', 'LANG', 'LANGUAGE']
        for var in envars:
            language_code, encoding = locale.getdefaultlocale((var,))
            Settings._logger.debug(f'getdefaultlocale({var})')
            Settings._logger.debug(f'language_code default: {language_code} '
                                   f'encoding: {encoding}')
            Settings._logger.debug(f'langauge_code: {locale.getlocale()}')
            Settings._logger.debug(f'langauge_code set null: '
                                   f'{locale.setlocale(locale.LC_ALL)}')
            Settings._logger.debug(f'language_code set empty: '
                                   f'{locale.setlocale(locale.LC_ALL, "")}')

        if language_code is None:
            language_code, encoding = locale.getlocale()
            Settings._logger.debug(f'language_code from locale.getlocale: {language_code}')
        '''

        return language_code

    @staticmethod
    def get_max_tmdb_trailers() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.TMDB_MAX_NUMBER_OF_TRAILERS)

    @staticmethod
    def is_report_actor_stats() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.REPORT_ACTOR_STATS)

    @staticmethod
    def get_report_max_top_actors() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.REPORT_MAXIMUM_NUMBER_OF_TOP_ACTORS)

    @staticmethod
    def is_enable_movie_stats() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_MOVIE_STATS)

    @staticmethod
    def disable_movie_stats() -> None:
        """
        Used to disable generating reports on next run of Kodi. User must
        set each time they want new reports.

        :return:
        """
        Settings.set_setting_bool(Settings.ENABLE_MOVIE_STATS, False)

    @staticmethod
    def is_report_genre_stats() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.REPORT_GENRE_STATS)

    @staticmethod
    def is_report_tag_stats() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.REPORT_TAG_STATS)

    @staticmethod
    def get_max_trailer_play_seconds() -> float:
        """
            Maximum seconds to play a trailer
        :return:
        """
        return Settings.get_setting_int(Settings.MAXIMUM_TRAILER_PLAY_SECONDS)

    @staticmethod
    def get_media_path() -> str:
        """

        :return:
        """
        return xbmcvfs.translatePath(os.path.join(
            Settings.get_resources_path(), 'media'))

    @staticmethod
    def get_minimum_days_since_watched() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.MINIMUM_DAYS_SINCE_WATCHED)

    @staticmethod
    def is_normalize_volume_of_downloaded_trailers() -> bool:
        """

        :return:
        """
        normalize = Settings.get_setting_bool(
            Settings.NORMALIZE_VOLUME_OF_DOWNLOADED_TRAILERS)
        return normalize

    @staticmethod
    def is_normalize_volume_of_local_trailers() -> bool:
        """

        :return:
        """
        normalize = Settings.get_setting_bool(
            Settings.NORMALIZE_VOLUME_OF_LOCAL_TRAILERS)
        return normalize

    @staticmethod
    def get_ffmpeg_path() -> str:
        path = Settings.get_setting_str(Settings.FFMPEG_PATH)
        return path

    @staticmethod
    def get_number_of_trailers_to_play() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.NUMBER_OF_TRAILERS_TO_PLAY)

    @staticmethod
    def get_open_curtain_path() -> str:
        """

        :return:
        """
        return xbmcvfs.translatePath(os.path.join(
            Settings.get_media_path(), 'CurtainOpeningSequence.flv'))

    @staticmethod
    def prompt_for_settings() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.PROMPT_FOR_SETTINGS)

    '''
    @staticmethod
    def get_itunes_quality():
        # type: () -> List[str][int]
        """

        :return:
        """
        quality_index = Settings.get_setting_int(Settings.ITUNES_QUALITY)
        return ["480p", "720p", "1080p"][quality_index]
    '''

    @staticmethod
    def get_rating_limit_setting() -> int:
        """
        Gets the maximum (maturity) certification index configured
        :return:
        """
        try:
            rating_limit = Settings.get_setting_int(Settings.RATING_LIMIT)
        except Exception:
            rating_limit = 0

        return rating_limit

    @staticmethod
    def get_youtube_username() -> str:
        return Settings.get_setting_str(Settings.YOUTUBE_USERNAME)


    @staticmethod
    def get_youtube_password() -> str:
        return Settings.get_setting_str(Settings.YOUTUBE_PASSWORD)

    @staticmethod
    def is_youtube_use_netrc() -> bool:
        return Settings.get_setting_bool(Settings.YOUTUBE_USE_NETRC)

    @staticmethod
    def get_tmdb_trailer_preference() -> str:
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
    def get_resources_path() -> str:
        """

        :return:
        """
        return xbmcvfs.translatePath(
            os.path.join(Constants.ADDON_PATH, 'resources'))

    @staticmethod
    def get_rotten_tomatoes_api_key() -> str:
        """

        :return:
        """
        return Settings.DEFAULT_ROTTEN_TOMATOES_API_KEY

    @staticmethod
    def is_tmdb_select_by_year_range() -> bool:
        """

        :return:
        """
        select_by_year_range = Settings.get_setting_bool(
            Settings.TMDB_ENABLE_SELECT_BY_YEAR_RANGE)
        return select_by_year_range

    @staticmethod
    def get_tmdb_minimum_year() -> int:
        """

        :return:
        """
        minimum_year: int = 0
        if Settings.is_tmdb_select_by_year_range():
            try:
                minimum_year = Settings.get_setting_int(
                    Settings.TMDB_YEAR_RANGE_MINIMUM)
            except Exception:
                minimum_year = 1928  # Practical start of Talkies

            minimum_year = max(minimum_year, 1901) # Start of Silents
            this_year: int = datetime.date.today().year
            minimum_year = min(minimum_year, this_year)

        return minimum_year

    @staticmethod
    def get_tmdb_maximum_year() -> int:
        """

        :return:
        """
        maximum_year: int = 0
        if Settings.is_tmdb_select_by_year_range():
            try:
                maximum_year = Settings.get_setting_int(
                    Settings.TMDB_YEAR_RANGE_MAXIMUM)
            except Exception:
                maximum_year = 3000
            this_year: int = datetime.date.today().year
            maxiumum_year = max(maximum_year, this_year)
            maxiumum_year = min(maximum_year, 1901)

        return maximum_year

    @staticmethod
    def get_setting_str(setting_name: str) -> str:
        value = Settings.get_addon().setting(setting_name)
        return value

    @staticmethod
    def get_setting_bool(setting: str) -> bool:
        """

        :return:
        """
        # Kodi returns a bool as a -1 | 0
        try:
            value = Settings.get_addon().bool_setting(setting)
        except Exception:
            value = False

        return bool(value)

    @staticmethod
    def set_setting_bool(setting: str, value: bool) -> None:
        """
        :setting:
        :value:
        :return:
        """
        try:
            Settings.get_addon().addon.setSettingBool(setting, value)
        except Exception:
            value = False

        return

    @staticmethod
    def get_setting_float(setting: str) -> float:
        """

        :return:
        """
        try:
            value = Settings.get_addon().addon.getSettingNumber(setting)
        except:
            Settings._logger.error(f'Setting: {setting} '
                                   f'value is not a float. Setting to 0.0')
            value = 0.0
        return value

    @staticmethod
    def get_setting_int(setting: str) -> int:
        """

        :return:
        """
        try:
            value = Settings.get_addon().addon.getSettingInt(setting)
        except Exception as e:
            Settings._logger.error(f'Setting: {setting} value is not an integer.'
                                   f' Setting to 0')
            value = 0
        return value

    @staticmethod
    def get_show_curtains() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.SHOW_CURTAINS)

    @staticmethod
    def get_show_movie_title() -> bool:
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
    def getSpokenLanguage() -> str:
        """

        :return:
        """
        return 'English'

    '''
        Time in seconds to display detailed movie info prior
        to playing a movie. Default is 5 seconds
    '''

    @staticmethod
    def get_time_to_display_detail_info() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.TIME_TO_DISPLAY_DETAIL_INFO)

    @staticmethod
    def get_tmdb_api_key() -> str:
        """

        :return:
        """
        try:
            tmdb_api_key = Settings.get_addon().setting(Settings.TMDB_API_KEY)
        except Exception as e:
            tmdb_api_key = None

        if tmdb_api_key is None or tmdb_api_key == '':
            tmdb_api_key = Settings.DEFAULT_TMDB_API_KEY
        return tmdb_api_key

    @staticmethod
    def get_tmdb_trailer_type() -> str:
        """

        :return:
        """
        try:
            trailer_type = Settings.get_addon().setting(Settings.TMDB_TRAILER_TYPE)
        except Exception as e:
            trailer_type = None

        return trailer_type

    @staticmethod
    def get_trailers_paths() -> str:
        """

        :return:
        """
        try:
            trailer_path = Settings.get_addon().setting('path')
        except Exception as e:
            trailer_path = None

        return trailer_path

    @staticmethod
    def get_update_tmdb_id() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.UPDATE_TMDB_ID)

    '''
        Not used because we can't query Kodi for current volume (needed to
        restore to previous volume).
        
    @staticmethod
    def get_volume() -> int:
        """

        :return:
        """
        volume = 100
        if Settings.get_adjust_volume():
            volume = Settings.get_setting_int(Settings.VOLUME)

        return volume
    '''

    @staticmethod
    def get_tmdb_include_old_movie_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.TMDB_INCLUDE_OLD_MOVIE_TRAILERS)

    @staticmethod
    def get_tmdb_max_download_movies() -> int:
        """
        :return:
        """
        return Settings.get_setting_int(Settings.TMDB_MAX_DOWNLOAD_MOVIES)

    @staticmethod
    def is_trace_enabled() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_TRACE)

    @staticmethod
    def is_trace_stats_enabled() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_TRACE_STATS)

    @staticmethod
    def is_use_tmdb_cache() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_REMOTE_DATA_CACHE)

    @staticmethod
    def is_use_trailer_cache() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.ENABLE_TRAILER_CACHE)

    @staticmethod
    def get_expire_remote_db_cache_entry_days() -> int:
        """

        :return:
        """

        return Settings.get_setting_int(Settings.CACHE_EXPIRATION_DAYS)

    @staticmethod
    def get_expire_remote_db_trailer_check_days() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.CACHE_TRAILER_CHECK_DAYS)

    @staticmethod
    def get_expire_trailer_cache_days() -> int:
        """

        :return:
        """
        return Settings.get_setting_int(Settings.EXPIRE_TRAILER_CACHE_DAYS)

    @staticmethod
    def get_downloaded_trailer_cache_path() -> str:
        """

        :return:
        """
        try:
            path = xbmcvfs.translatePath(
                Settings.get_addon().setting(Settings.TRAILER_CACHE_PATH))
        except Exception as e:
            path = None

        return path

    @staticmethod
    def get_remote_db_cache_path() -> str:
        """

        :return:
        """
        try:
            path = xbmcvfs.translatePath(
                Settings.get_addon().setting(Settings.CACHE_PATH))
        except Exception as e:
            path = None
            Settings._logger.exception('')

        return path

    @staticmethod
    def is_limit_cached_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIMIT_CACHED_TRAILERS)

    @staticmethod
    def is_limit_number_of_cached_trailers() -> bool:
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_trailers():
            value = Settings.get_setting_bool(
                Settings.LIMIT_NUMBER_OF_CACHED_TRAILERS)
        return value

    @staticmethod
    def get_max_number_of_cached_trailers() -> int:
        """

        :return:
        """
        value = None
        if Settings.is_limit_number_of_cached_trailers():
            value = Settings.get_setting_int(
                Settings.MAX_NUMBER_OF_CACHED_TRAILERS)
        return value

    @staticmethod
    def is_limit_size_of_cached_trailers() -> bool:
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_trailers():
            value = Settings.get_setting_bool(
                Settings.LIMIT_SIZE_OF_CACHED_TRAILERS)

        return value

    @staticmethod
    def get_max_size_of_cached_trailers_mb() -> int:
        """

        :return:
        """
        value = None
        if Settings.is_limit_size_of_cached_trailers():
            value = Settings.get_setting_int(
                Settings.MAX_SIZE_OF_CACHED_TRAILERS)
        return value

    @staticmethod
    def is_limit_percent_of_cached_trailers() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIMIT_PERCENT_OF_CACHED_TRAILERS)

    @staticmethod
    def get_max_percent_of_cached_trailers() -> float:
        """

        :return:
        """
        value = None
        if Settings.is_limit_percent_of_cached_trailers():
            value = float(Settings.get_setting_int(
                Settings.MAX_PERCENT_OF_CACHED_TRAILERS)) / 100.0
        return value

    @staticmethod
    def is_limit_cached_json() -> bool:
        """

        :return:
        """
        return Settings.get_setting_bool(Settings.LIMIT_CACHED_JSON)

    @staticmethod
    def is_limit_number_of_cached_json() -> bool:
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_json():
            value = Settings.get_setting_bool(
                Settings.LIMIT_NUMBER_OF_CACHED_JSON)
        return value

    @staticmethod
    def get_max_number_of_cached_json() -> int:
        """

        :return:
        """
        value = 0
        if Settings.is_limit_number_of_cached_json():
            value = Settings.get_setting_int(
                Settings.MAX_NUMBER_OF_CACHED_JSON)
        return value

    @staticmethod
    def is_limit_size_of_cached_json() -> bool:
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_json():
            value = Settings.get_setting_bool(
                Settings.LIMIT_SIZE_OF_CACHED_JSON)
        return value

    @staticmethod
    def get_max_size_of_cached_json_mb() -> int:
        """

        :return:
        """
        value = 0
        if Settings.is_limit_size_of_cached_json():
            value = Settings.get_setting_int(
                Settings.MAX_SIZE_OF_CACHED_JSON)
        return value

    @staticmethod
    def is_limit_percent_of_cached_json() -> bool:
        """

        :return:
        """
        value = False
        if Settings.is_limit_cached_json():
            value = Settings.get_setting_bool(
                Settings.LIMIT_PERCENT_OF_CACHED_JSON)
        return value

    @staticmethod
    def get_max_percent_of_cached_json() -> float:
        """

        :return:
        """
        value = None
        if Settings.is_limit_percent_of_cached_json():
            value = float(Settings.get_setting_int(
                Settings.MAX_PERCENT_OF_CACHED_JSON)) / 100.0
        return value

    '''
    HIDDEN Settings
    '''

    @staticmethod
    def get_youtube_dl_cookie_path() -> str:
        value = Settings.get_addon().addon.getSetting(Settings.YOUTUBE_DL_COOKIE_PATH)

        return value

    @staticmethod
    def get_youtube_dl_cache_path() -> str:
        value = Settings.get_addon().addon.getSetting(Settings.YOUTUBE_DL_CACHE_PATH)

        return value
