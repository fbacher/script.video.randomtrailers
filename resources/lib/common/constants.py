# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import datetime
import locale
import os
import re

import xbmcaddon
import xbmcvfs
from kodi65 import addon
from kodi65.kodiaddon import Addon

from common.imports import *


class Constants:
    """
        Constants common to all Random Trailers plugins
    """
    INCLUDE_MODULE_PATH_IN_LOGGER: Final[bool] = True
    TOO_MANY_TMDB_REQUESTS: Final[int] = 25
    addonName: Final[str] = 'script.video.randomtrailers'
    CURRENT_ADDON_NAME: str = None
    CURRENT_ADDON_SHORT_NAME: str = None
    ADDON_UTIL: Addon = None
    ADDON: xbmcaddon.Addon = None
    BACKEND_ADDON: Addon = None
    BACKEND_ADDON_UTIL: Addon = None
    FRONTEND_ADDON: Addon = None
    FRONTEND_ADDON_UTIL: Addon = None
    ADDON_PATH: str = None
    PYTHON_ROOT_PATH: str = None
    MEDIA_PATH: str = None
    SCRIPT_PATH: str = None
    YOUTUBE_DL_ADDON_LIB_PATH: str = None
    SAVE_MEMORY: bool = True
    TRAILER_INFO_DISPLAY_SECONDS: Final[int] = 60
    TRAILER_INFO_DISPLAY_MILLISECONDS: Final[int] = 6000
    SECONDS_BEFORE_RESHUFFLE: Final[int] = 1 * 60
    PLAY_LIST_LOOKBACK_WINDOW_SIZE: Final[int] = 10
    MAX_PLAY_TIME_WARNING_TIME: Final[int] = 5  # seconds
    # BACKEND_SERVICE = 'randomTrailers.backend'
    FRONTEND_SERVICE: Final[str] = 'randomTrailers'
    BACKEND_SERVICE: Final[str] = FRONTEND_SERVICE
    SCREENSAVER_SERVICE: Final[str] = 'randomTrailers.screensaver.service'
    ADDON_ID: Final[str] = 'script.video.randomtrailers'
    FRONTEND_ID: Final[str] = ADDON_ID
    # BACKEND_ID = 'service.randomtrailers.backend'
    BACKEND_ID: Final[str] = FRONTEND_ID
    BLACK_VIDEO: str = ''

    FRONTEND_DATA_PATH: str = None
    COUCH_POTATO_ID: Final[str] = 'plugin.video.couchpotato'
    COUCH_POTATO_URL: Final[str] = 'plugin://plugin.video.couchpotato_manager/movies/add'

    #  Start first garbage collection X time after Kodi starts
    InitialGarbageCollectionTime: Final[int] = 60 * 60 * 4  # Four Hours in seconds
    # Run daily garbage collection at 04:13 in the morning.
    DailyGarbageCollectionTime: datetime.time = datetime.time(hour=4, minute=13)
    HTTP_TOO_MANY_REQUESTS: Final[int] = 429
    HTTP_UNAUTHORIZED: Final[int] = 401
    TRACEBACK: Final[str] = 'LEAK Traceback StackTrace StackDump'
    TRAILER_CACHE_FLUSH_SECONDS: Final[int] = 300  # Five minutes with changes
    TRAILER_CACHE_FLUSH_UPDATES: Final[int] = 40  # Flush cache after n updates

    PLAY_STATISTICS_REPORT_PATH: str = None

    # For better response, give local trailers a bit of a head start by
    # delaying other discovery a bit. Other discovery blocked while both
    # of these are true

    EXCLUSIVE_LIBRARY_DISCOVERY_SECONDS: int = 45
    NUMBER_OF_LIBRARY_MOVIES_TO_DISCOVER_DURING_EXCLUSIVE_DISCOVERY = 50

    # Altered to one month ago in static_init
    CACHE_FILE_EXPIRED_TIME: int = datetime.MAXYEAR
    PLAYLIST_PATH: str = ''
    LOCALE: str = ''

    plugin_short_names: Final[Dict[str, str]] = {
        'service.randomtrailers.backend': 'randomtrailers.backend',
        'script.video.randomtrailers.screensaver': 'randomtrailers.screensaver',
        'script.video.randomtrailers': 'randomtrailers'
    }

    # File patterns to find cached files

    TRAILER_PATTERN: Pattern = re.compile(r'^.*-movie\..*$')
    TRAILER_GLOB_PATTERN: str = '**/*-movie.*'
    JSON_PATTERN: Pattern =    re.compile(r'^.*\.json$')
    JSON_GLOB_PATTERN: str = '**/*.json'
    TFH_PATTERN: Pattern =     re.compile(r'^.*-movie\..*$')
    TFH_GLOB_PATTERN: str = '**/*-movie.*'

    TMDB_GLOB_JSON_PATTERN: str = '**/tmdb_[0-9]*.json'
    TMDB_ID_PATTERN: Pattern = re.compile(r'^tmdb_([0-9]+).json')

    @staticmethod
    def static_init() -> None:
        """
            Assign calculated values

        :return:
        """
        # Constants.addonName)
        Constants.ADDON_UTIL = Addon()
        Constants.CURRENT_ADDON_NAME = Constants.ADDON_UTIL.ID
        Constants.CURRENT_ADDON_SHORT_NAME = Constants.plugin_short_names[
            Constants.CURRENT_ADDON_NAME]
        Constants.ADDON = Constants.ADDON_UTIL.addon
        # Backend may not be defined
        try:
            Constants.BACKEND_ADDON_UTIL = Addon(Constants.BACKEND_ID)
            Constants.BACKEND_ADDON = Constants.BACKEND_ADDON_UTIL.addon
        except Exception as e:
            pass

        Constants.YOUTUBE_DL_ADDON_UTIL = Addon('script.module.youtube.dl')
        Constants.YOUTUBE_DL_ADDON = Constants.YOUTUBE_DL_ADDON_UTIL.addon
        Constants.YOUTUBE_DL_ADDON_PATH = \
            xbmcvfs.translatePath(Constants.YOUTUBE_DL_ADDON_UTIL.PATH)
        Constants.YOUTUBE_DL_ADDON_LIB_PATH = os.path.join(
            Constants.YOUTUBE_DL_ADDON_PATH, 'lib')

        try:
            Constants.FRONTEND_ADDON_UTIL = Addon(Constants.FRONTEND_ID)
            Constants.FRONTEND_ADDON = Constants.FRONTEND_ADDON_UTIL.addon
        except Exception:
            pass

        Constants.ADDON_PATH = Constants.ADDON.getAddonInfo('path')
        Constants.PYTHON_ROOT_PATH = os.path.join(Constants.ADDON_PATH,
                                                  'resources',
                                                  'lib')
        Constants.USER_DATA_PATH = xbmcvfs.translatePath("special://userdata")
        Constants.MEDIA_PATH = addon.MEDIA_PATH
        Constants.SCRIPT_PATH = os.path.join(
            Constants.ADDON_PATH, 'resources', 'skins', 'Default', '720p')
        now = datetime.datetime.now()
        seconds_in_month = datetime.timedelta(30)
        Constants.CACHE_FILE_EXPIRED_TIME = now - seconds_in_month
        Constants.FRONTEND_DATA_PATH = xbmcvfs.translatePath(
            f'special://profile/addon_data/{Constants.FRONTEND_ID}')
        Constants.PLAYLIST_PATH = os.path.join(Constants.USER_DATA_PATH,
                                               'playlists/video')
        Constants.PLAY_STATISTICS_REPORT_PATH = \
            os.path.join(Constants.FRONTEND_DATA_PATH,
                        'debug', 'play_stats.txt')
        Constants.LOCALE = locale.getdefaultlocale()
        Constants.BLACK_VIDEO = \
            os.path.join(Constants.MEDIA_PATH, 'solid-black.mkv')


Constants.static_init()


class RemoteTrailerPreference:
    """
        A few constants useful for trailers from remote sources (iTunes or
        TMDB). They likely should be moved to those classes.
    """
    NEWEST: Final[int] = 0
    OLDEST: Final[int] = 1
    HIGHEST_RATED: Final[int] = 2
    LOWEST_RATED: Final[int] = 3
    MOST_VOTES: Final[int] = 4
    LEAST_VOTES: Final[int] = 5

    AVERAGE_VOTE_DONT_CARE: Final[int] = 0
    AVERAGE_VOTE_GREATER_OR_EQUAL: Final[int] = 1
    AVERAGE_VOTE_LESS_OR_EQUAL: Final[int] = 2


class iTunes:
    """
        Defines constants that apply to iTunes
    """
    #"Coming Soon|Just Added|Popular|Exclusive|All"
    COMING_SOON: Final[int] = 0
    JUST_ADDED: Final[int] = 1
    POPULAR: Final[int] = 2
    EXCLUSIVE: Final[int] = 3
    ALL: Final[int] = 4

    COMING_SOON_URL: Final[str] = '/trailers/home/feeds/studios.json'
    JUST_ADDED_URL: Final[str] = '/trailers/home/feeds/just_added.json'
    POPULAR_URL: Final[str] = '/trailers/home/feeds/most_pop.json'
    EXCLUSIVE_URL: Final[str] = '/trailers/home/feeds/exclusive.json'
    ALL_URL: Final[str] = '/trailers/home/feeds/studios.json'

    _trailerForTypeMap: Final[Dict[int, str]] =\
        {COMING_SOON: COMING_SOON_URL,
         JUST_ADDED: JUST_ADDED_URL,
         POPULAR: POPULAR_URL,
         EXCLUSIVE: EXCLUSIVE_URL,
         ALL: ALL_URL}

    @staticmethod
    def get_url_for_trailer_type(trailer_type: int) -> str:
        url: str = iTunes._trailerForTypeMap.get(trailer_type, None)
        return url


class TFH:
    # Pattern to isolate movie title from TFH fluff:
    # John Landis on WAY OUT WEST
    # Need to strip everything before Way. Note that not every TFH title
    # follows this pattern, but is pretty close.

    TITLE_RE: Final[Pattern] = \
        re.compile(r'(([A-Z0-9.!?_$#-]) ?[A-Zc0-9.!?_#&@:$\'" -]*$)')


"""
# noinspection PyClassHasNoInit,PyClassHasNoInit,PyClassHasNoInit
class TMDB:
    # Applies to trailer type
    #"Coming Soon|Just Added|Popular|Exclusive|All"
    COMING_SOON = 0
    JUST_ADDED = 1
    POPULAR = 2
    EXCLUSIVE = 3
    ALL = 4

    COMING_SOON_URL = '/trailers/home/feeds/studios.json'
    JUST_ADDED_URL = '/trailers/home/feeds/just_added.json'
    POPULAR_URL = '/trailers/home/feeds/most_pop.json'
    EXCLUSIVE_URL = '/trailers/home/feeds/exclusive.json'
    ALL_URL = '/trailers/home/feeds/studios.json'

    _trailerForTypeMap = {COMING_SOON: COMING_SOON_URL,
                          JUST_ADDED: JUST_ADDED_URL,
                          POPULAR: POPULAR_URL,
                          EXCLUSIVE: EXCLUSIVE_URL,
                          ALL: ALL_URL}

    @staticmethod
    def get_url_for_trailer_type(trailerType):
        url = TMDB._trailerForTypeMap.get(trailerType, None)
        return url

"""


class GenreEnum:
    # Possible values returned by settings.xml

    IGNORE: Final[int] = 0  # This Genre will be ignored in filtering
    INCLUDE: Final[int] = 1  # Genre filter will include this genre in an OR fashion
    EXCLUDE: Final[int] = 2  # Genre filter will exclude this genre in an OR fashion


class GenreConstants:
    # Ids used in settings.xml
    ACTION: Final[str] = 'g_action'
    ALEGORY: Final[str] = 'g_alegory'  # NOT USED
    ANTHOLOGY: Final[str] = 'ganthology'  # not used
    ADVENTURE: Final[str] = 'g_adventure'
    ANIMATION: Final[str] = 'g_animation'
    BIOGRAPHY: Final[str] = 'g_biography'
    CHILDRENS: Final[str] = 'g_childrens'  # not used
    COMEDY: Final[str] = 'g_comedy'
    CRIME: Final[str] = 'g_crime'
    DARK_COMEDY: Final[str] = 'g_black_comedy'
    DOCUMENTARY: Final[str] = 'g_documentary'
    DRAMA: Final[str] = 'g_drama'
    EPIC: Final[str] = 'g_epic'
    EXPERIMENTAL: Final[str] = 'g_experimental'  # not used
    FAMILY: Final[str] = 'g_family'
    FANTASY: Final[str] = 'g_fantasy'
    FILM_NOIR: Final[str] = 'g_film_noir'
    FOREIGN: Final[str] = 'g_foreign'  # not used
    GAME_SHOW: Final[str] = 'g_game_show'  # not used
    HISTORY: Final[str] = 'g_history'
    HORROR: Final[str] = 'g_horror'
    MELODRAMA: Final[str] = 'g_melodrama'
    MUSIC: Final[str] = 'g_music'
    MUSICAL: Final[str] = 'g_musical'
    MUSICAL_COMEDY: Final[str] = 'g_musical_comedy'
    MYSTERY: Final[str] = 'g_mystery'
    PERFORMANCE: Final[str] = 'g_performance'  # not used
    PRE_CODE: Final[str] = 'g_pre_code'
    ROMANCE: Final[str] = 'g_romance'
    ROMANTIC_COMEDY: Final[str] = 'g_romantic_comedy'
    SATIRE: Final[str] = 'g_satire'
    SCI_FI: Final[str] = 'g_scifi'
    SCREWBALL_COMEDY: Final[str] = 'g_screwball_comedy'
    SWASHBUCKLER: Final[str] = 'g_swashbuckler'
    THRILLER: Final[str] = 'g_thriller'
    TV_MOVIE: Final[str] = 'g_tv_movie'
    VARIETY: Final[str] = 'g_variety'  # Not used
    WAR: Final[str] = 'g_war'
    WAR_DOCUMENTARY: Final[str] = 'g_war_documentary'
    WESTERN: Final[str] = 'g_western'


class DebugLevel:
    """

    """
    FATAL: Final[str] = '00_Fatal'
    SEVERE: Final[str] = '01_Severe'
    ERROR: Final[str] = '02_Error'
    WARNING: Final[str] = '03_Warning'
    NOTICE: Final[str] = '04_Notice'
    INFO: Final[str] = '05_Info'
    DEBUG_EXTRA_VERBOSE: Final[str] = '06_Debug_Extra_Verbose'
    DEBUG_VERBOSE: Final[str] = '07_Debug_Verbose'
    DEBUG: Final[str] = '08_Debug'
