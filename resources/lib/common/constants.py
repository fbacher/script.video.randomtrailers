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
from kutils import addon
from kutils.kodiaddon import Addon

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
    NOTIFICATION_SECONDS: Final[int] = 5  # seconds
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

    # For Testing

    # Causes local library trailers to be ignored, thereby forcing all trailers
    # for local movies to be downloaded from TMDb

    DISABLE_LIBRARY_TRAILERS: bool = False

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


class TFH:

    # This pattern captures the TITLE, not the Reviewer.
    # The TITLE must be mostly ALL CAPS, with some special characters
    # and a lower case 'c' (for names like McCLOUD, with space separators

    # title is a series of words

    UPPER_CASE_UNICODE = r'A-Z\u00C0-\u00D6\u00D8-\u00DE\u0100\u0102\u0104\u0106' \
                         r'\u0108\u010A\u010C\u010E\u0110\u0112\u0114\u0116\u0118' \
                         r'\u011A\u011C\u011E\u0120\u0122\u0124\u0126\u0128\u012A' \
                         r'\u012C\u012E\u0130\u0132\u0134\u0136\u0139\u013B\u013D' \
                         r'\u013F\u0141\u0143\u0145\u0147\u014A\u014C\u014E\u0150' \
                         r'\u0152\u0154\u0156\u0158\u015A\u015C\u015E\u0160\u0162' \
                         r'\u0164\u0166\u0168\u016A\u016C\u016E\u0170\u0172\u0174' \
                         r'\u0176\u0178\u0179\u017B\u017D\u0181\u0182\u0184\u0186' \
                         r'\u0187\u0189-\u018B\u018E-\u0191\u0193\u0194\u0196' \
                         r'-\u0198\u019C\u019D\u019F\u01A0\u01A2\u01A4\u01A6\u01A7' \
                         r'\u01A9\u01AC\u01AE\u01AF\u01B1-\u01B3\u01B5\u01B7\u01B8' \
                         r'\u01BC\u01C4\u01C7\u01CA\u01CD\u01CF\u01D1\u01D3\u01D5' \
                         r'\u01D7\u01D9\u01DB\u01DE\u01E0\u01E2\u01E4\u01E6\u01E8' \
                         r'\u01EA\u01EC\u01EE\u01F1\u01F4\u01F6-\u01F8\u01FA\u01FC' \
                         r'\u01FE\u0200\u0202\u0204\u0206\u0208\u020A\u020C\u020E' \
                         r'\u0210\u0212\u0214\u0216\u0218\u021A\u021C\u021E\u0220' \
                         r'\u0222\u0224\u0226\u0228\u022A\u022C\u022E\u0230\u0232' \
                         r'\u023A\u023B\u023D\u023E\u0241\u0243-\u0246\u0248\u024A' \
                         r'\u024C\u024E\u0370\u0372\u0376\u037F\u0386\u0388-\u038A' \
                         r'\u038C\u038E\u038F\u0391-\u03A1\u03A3-\u03AB\u03CF\u03D2' \
                         r'-\u03D4\u03D8\u03DA\u03DC\u03DE\u03E0\u03E2\u03E4\u03E6' \
                         r'\u03E8\u03EA\u03EC\u03EE\u03F4\u03F7\u03F9\u03FA\u03FD' \
                         r'-\u042F\u0460\u0462\u0464\u0466\u0468\u046A\u046C\u046E' \
                         r'\u0470\u0472\u0474\u0476\u0478\u047A\u047C\u047E\u0480' \
                         r'\u048A\u048C\u048E\u0490\u0492\u0494\u0496\u0498\u049A' \
                         r'\u049C\u049E\u04A0\u04A2\u04A4\u04A6\u04A8\u04AA\u04AC' \
                         r'\u04AE\u04B0\u04B2\u04B4\u04B6\u04B8\u04BA\u04BC\u04BE' \
                         r'\u04C0\u04C1\u04C3\u04C5\u04C7\u04C9\u04CB\u04CD\u04D0' \
                         r'\u04D2\u04D4\u04D6\u04D8\u04DA\u04DC\u04DE\u04E0\u04E2' \
                         r'\u04E4\u04E6\u04E8\u04EA\u04EC\u04EE\u04F0\u04F2\u04F4' \
                         r'\u04F6\u04F8\u04FA\u04FC\u04FE\u0500\u0502\u0504\u0506' \
                         r'\u0508\u050A\u050C\u050E\u0510\u0512\u0514\u0516\u0518' \
                         r'\u051A\u051C\u051E\u0520\u0522\u0524\u0526\u0528\u052A' \
                         r'\u052C\u052E\u0531-\u0556\u10A0-\u10C5\u10C7\u10CD\u13A0' \
                         r'-\u13F5\u1C90-\u1CBA\u1CBD-\u1CBF\u1E00\u1E02\u1E04' \
                         r'\u1E06\u1E08\u1E0A\u1E0C\u1E0E\u1E10\u1E12\u1E14\u1E16' \
                         r'\u1E18\u1E1A\u1E1C\u1E1E\u1E20\u1E22\u1E24\u1E26\u1E28' \
                         r'\u1E2A\u1E2C\u1E2E\u1E30\u1E32\u1E34\u1E36\u1E38\u1E3A' \
                         r'\u1E3C\u1E3E\u1E40\u1E42\u1E44\u1E46\u1E48\u1E4A\u1E4C' \
                         r'\u1E4E\u1E50\u1E52\u1E54\u1E56\u1E58\u1E5A\u1E5C\u1E5E' \
                         r'\u1E60\u1E62\u1E64\u1E66\u1E68\u1E6A\u1E6C\u1E6E\u1E70' \
                         r'\u1E72\u1E74\u1E76\u1E78\u1E7A\u1E7C\u1E7E\u1E80\u1E82' \
                         r'\u1E84\u1E86\u1E88\u1E8A\u1E8C\u1E8E\u1E90\u1E92\u1E94' \
                         r'\u1E9E\u1EA0\u1EA2\u1EA4\u1EA6\u1EA8\u1EAA\u1EAC\u1EAE' \
                         r'\u1EB0\u1EB2\u1EB4\u1EB6\u1EB8\u1EBA\u1EBC\u1EBE\u1EC0' \
                         r'\u1EC2\u1EC4\u1EC6\u1EC8\u1ECA\u1ECC\u1ECE\u1ED0\u1ED2' \
                         r'\u1ED4\u1ED6\u1ED8\u1EDA\u1EDC\u1EDE\u1EE0\u1EE2\u1EE4' \
                         r'\u1EE6\u1EE8\u1EEA\u1EEC\u1EEE\u1EF0\u1EF2\u1EF4\u1EF6' \
                         r'\u1EF8\u1EFA\u1EFC\u1EFE\u1F08-\u1F0F\u1F18-\u1F1D\u1F28' \
                         r'-\u1F2F\u1F38-\u1F3F\u1F48-\u1F4D\u1F59\u1F5B\u1F5D' \
                         r'\u1F5F\u1F68-\u1F6F\u1FB8-\u1FBB\u1FC8-\u1FCB\u1FD8' \
                         r'-\u1FDB\u1FE8-\u1FEC\u1FF8-\u1FFB\u2102\u2107\u210B' \
                         r'-\u210D\u2110-\u2112\u2115\u2119-\u211D\u2124\u2126' \
                         r'\u2128\u212A-\u212D\u2130-\u2133\u213E\u213F\u2145\u2160' \
                         r'-\u216F\u2183\u24B6-\u24CF\u2C00-\u2C2E\u2C60\u2C62' \
                         r'-\u2C64\u2C67\u2C69\u2C6B\u2C6D-\u2C70\u2C72\u2C75\u2C7E' \
                         r'-\u2C80\u2C82\u2C84\u2C86\u2C88\u2C8A\u2C8C\u2C8E\u2C90' \
                         r'\u2C92\u2C94\u2C96\u2C98\u2C9A\u2C9C\u2C9E\u2CA0\u2CA2' \
                         r'\u2CA4\u2CA6\u2CA8\u2CAA\u2CAC\u2CAE\u2CB0\u2CB2\u2CB4' \
                         r'\u2CB6\u2CB8\u2CBA\u2CBC\u2CBE\u2CC0\u2CC2\u2CC4\u2CC6' \
                         r'\u2CC8\u2CCA\u2CCC\u2CCE\u2CD0\u2CD2\u2CD4\u2CD6\u2CD8' \
                         r'\u2CDA\u2CDC\u2CDE\u2CE0\u2CE2\u2CEB\u2CED\u2CF2\uA640' \
                         r'\uA642\uA644\uA646\uA648\uA64A\uA64C\uA64E\uA650\uA652' \
                         r'\uA654\uA656\uA658\uA65A\uA65C\uA65E\uA660\uA662\uA664' \
                         r'\uA666\uA668\uA66A\uA66C\uA680\uA682\uA684\uA686\uA688' \
                         r'\uA68A\uA68C\uA68E\uA690\uA692\uA694\uA696\uA698\uA69A' \
                         r'\uA722\uA724\uA726\uA728\uA72A\uA72C\uA72E\uA732\uA734' \
                         r'\uA736\uA738\uA73A\uA73C\uA73E\uA740\uA742\uA744\uA746' \
                         r'\uA748\uA74A\uA74C\uA74E\uA750\uA752\uA754\uA756\uA758' \
                         r'\uA75A\uA75C\uA75E\uA760\uA762\uA764\uA766\uA768\uA76A' \
                         r'\uA76C\uA76E\uA779\uA77B\uA77D\uA77E\uA780\uA782\uA784' \
                         r'\uA786\uA78B\uA78D\uA790\uA792\uA796\uA798\uA79A\uA79C' \
                         r'\uA79E\uA7A0\uA7A2\uA7A4\uA7A6\uA7A8\uA7AA-\uA7AE\uA7B0' \
                         r'-\uA7B4\uA7B6\uA7B8\uA7BA\uA7BC\uA7BE\uA7C2\uA7C4-\uA7C7' \
                         r'\uA7C9\uA7F5\uFF21-\uFF3A\U00010400-\U00010427\U000104B0' \
                         r'-\U000104D3\U00010C80-\U00010CB2\U000118A0-\U000118BF' \
                         r'\U00016E40-\U00016E5F\U0001D400-\U0001D419\U0001D434' \
                         r'-\U0001D44D\U0001D468-\U0001D481\U0001D49C\U0001D49E' \
                         r'\U0001D49F\U0001D4A2\U0001D4A5\U0001D4A6\U0001D4A9' \
                         r'-\U0001D4AC\U0001D4AE-\U0001D4B5\U0001D4D0-\U0001D4E9' \
                         r'\U0001D504\U0001D505\U0001D507-\U0001D50A\U0001D50D' \
                         r'-\U0001D514\U0001D516-\U0001D51C\U0001D538\U0001D539' \
                         r'\U0001D53B-\U0001D53E\U0001D540-\U0001D544\U0001D546' \
                         r'\U0001D54A-\U0001D550\U0001D56C-\U0001D585\U0001D5A0' \
                         r'-\U0001D5B9\U0001D5D4-\U0001D5ED\U0001D608-\U0001D621' \
                         r'\U0001D63C-\U0001D655\U0001D670-\U0001D689\U0001D6A8' \
                         r'-\U0001D6C0\U0001D6E2-\U0001D6FA\U0001D71C-\U0001D734' \
                         r'\U0001D756-\U0001D76E\U0001D790-\U0001D7A8\U0001D7CA' \
                         r'\U0001E900-\U0001E921\U0001F130-\U0001F149\U0001F150' \
                         r'-\U0001F169\U0001F170-\U0001F189'

    # TITLE_RE: Final[Pattern] = \
        # re.compile(r'(([A-Z0-9.!?_$#-]) ?[A-Zc0-9.!?_#&@:$\'" -]*$)')

    TITLE_PASS_1_RE: Final[Pattern] = \
        re.compile(r'('
                   r''
                   # First char of word upper case,  or special char
                   r'[' + UPPER_CASE_UNICODE +
                   r'0-9.!?$# \'"~-]+'
                   r')')

    PARENTHESIS_RE: Final[Pattern] = \
        re.compile(r'([(][^()]*[)])')

    YEAR_RE: Final[Pattern] = \
        re.compile(r'([(][0-9]{4}[)])')  # ( 4-digit year )

    '''
      re.compile(r'('
                   # First char of word upper case,  or special char
                   r'([' + UPPER_CASE_UNICODE +
                   r'0-9.!?$#\'"~-])'
                   # Followed by optional space and any number of same type
                   # char as first char.
                   r'('
                   r' ?[' + UPPER_CASE_UNICODE +
                   r'c0-9.!?#&@,:$ \'"~-]*)'
                   # Followed by the same, but including spaces, and 
                   # within a pair of parenthesis
                   r'('
                   r'[(][' + UPPER_CASE_UNICODE +
                   r'c0-9.!?#&@,:$\'"~ -]*[)]'
                   r')?'
                   r')')
'''


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
