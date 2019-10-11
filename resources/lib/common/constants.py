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

from kodi65 import addon
from kodi65.kodiaddon import Addon
from kodi_six import xbmc, utils


class Constants(object):
    """
        Constants common to all Random Trailers plugins
    """
    INCLUDE_MODULE_PATH_IN_LOGGER = False
    TOO_MANY_TMDB_REQUESTS = 25
    addonName = 'script.video.randomtrailers'
    CURRENT_ADDON_NAME = None
    CURRENT_ADDON_SHORT_NAME = None
    ADDON_UTIL = None
    ADDON = None
    BACKEND_ADDON = None
    BACKEND_ADDON_UTIL = None
    FRONTEND_ADDON = None
    FRONTEND_ADDON_UTIL = None
    ADDON_PATH = None
    MEDIA_PATH = None
    SCRIPT_PATH = None
    REJECTED_STATUS = 1
    YOUTUBE_DL_ADDON_LIB_PATH = None
    TRAILER_INFO_DISPLAY_SECONDS = 60
    TRAILER_INFO_DISPLAY_MILLISECONDS = 6000
    SECONDS_BEFORE_RESHUFFLE = 1 * 60
    PLAY_LIST_LOOKBACK_WINDOW_SIZE = 10
    MAX_PLAY_TIME_WARNING_TIME = 5  # seconds
    # BACKEND_SERVICE = 'randomTrailers.backend'
    FRONTEND_SERVICE = 'randomTrailers.frontend'
    BACKEND_SERVICE = FRONTEND_SERVICE
    SCREENSAVER_SERVICE = 'randomTrailers.screensaver.service'
    FRONTEND_ID = 'script.video.randomtrailers'
    # BACKEND_ID = 'service.randomtrailers.backend'
    BACKEND_ID = FRONTEND_ID

    FRONTEND_DATA_PATH = None
    COUCH_POTATO_ID = 'plugin.video.couchpotato'
    InitialGarbageCollectionTime = 10 * 60  # Ten minutes in seconds
    # Run daily garbage collection at 04:13 in the morning.
    DailyGarbageCollectionTime = datetime.time(hour=04, minute=13)
    TRACEBACK = 'LEAK Traceback StackTrace StackDump'
    TRAILER_CACHE_FLUSH_SECONDS = 300  # Five minutes with changes
    TRAILER_CACHE_FLUSH_UPDATES = 10  # Flush cache after n updates

    # Altered to one month ago in static_init
    CACHE_FILE_EXPIRED_TIME = datetime.MAXYEAR

    plugin_short_names = {'service.randomtrailers.backend': 'randomtrailers.backend',
                          'script.video.randomtrailers.screensaver': 'randomtrailers.screensaver',
                          'script.video.randomtrailers': 'randomtrailers.frontend'}

    @staticmethod
    def static_init():
        # type: () -> None
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
        except (Exception) as e:
            pass

        Constants.YOUTUBE_DL_ADDON_UTIL = Addon(
            'script.module.youtube.dl')
        Constants.YOUTUBE_DL_ADDON = Constants.YOUTUBE_DL_ADDON_UTIL.addon
        Constants.YOUTUBE_DL_ADDON_PATH = Constants.YOUTUBE_DL_ADDON.getAddonInfo(
            'path').decode('utf-8')
        Constants.YOUTUBE_DL_ADDON_LIB_PATH = os.path.join(
            Constants.YOUTUBE_DL_ADDON_PATH, 'lib')

        try:
            Constants.FRONTEND_ADDON_UTIL = Addon(Constants.FRONTEND_ID)
            Constants.FRONTEND_ADDON = Constants.FRONTEND_ADDON_UTIL.addon
        except (Exception):
            pass

        Constants.ADDON_PATH = utils.py2_decode(Constants.ADDON.getAddonInfo(
            'path').decode('utf-8'))
        Constants.USER_DATA_PATH = xbmc.translatePath("special://userdata")
        Constants.MEDIA_PATH = addon.MEDIA_PATH
        Constants.SCRIPT_PATH = os.path.join(
            Constants.ADDON_PATH, 'resources', 'skins', 'Default', '720p')
        now = datetime.datetime.now()
        secondsInMonth = datetime.timedelta(30)
        Constants.CACHE_FILE_EXPIRED_TIME = now - secondsInMonth
        Constants.FRONTEND_DATA_PATH = xbmc.translatePath(
            "special://profile/addon_data/%s" % Constants.FRONTEND_ID).decode("utf-8")
        Constants.PLAYLIST_PATH = Constants.USER_DATA_PATH + '/playlists/video'
        LOCALE = locale.getdefaultlocale()


Constants.static_init()


# noinspection PyClassHasNoInit
class RemoteTrailerPreference(object):
    """
        A few constants useful for trailers from remote sources (iTunes or
        TMDB). They likely should be moved to those classes.
    """
    NEWEST = 0
    OLDEST = 1
    HIGHEST_RATED = 2
    LOWEST_RATED = 3
    MOST_VOTES = 4
    LEAST_VOTES = 5

    AVERAGE_VOTE_DONT_CARE = 0
    AVERAGE_VOTE_GREATER_OR_EQUAL = 1
    AVERAGE_VOTE_LESS_OR_EQUAL = 2


# noinspection PyClassHasNoInit
class Movie(object):
    """
        Defines constant values for Kodi trailer dict fields. Including some
        defined for this plugin.

    """

    """
        Properties requested for initial query of library movies:
                              ["title", "lastplayed", "studio", "cast", "plot", "writer", \
                        "director", "fanart", "runtime", "mpaa", "thumbnail", "file", \
                        "year", "genre", "trailer"]\

        Values returned:
        Kodi library movie: {
         "plot": "Dolly, alias \"Angel Face,\"...
         "writer": ["Leroy Scott", "Edmund Goulding"],
         "movieid": 18338,
         "title": "A Lady of Chance",
         "fanart": "image://%2fmovies%2f...-fanart.jpg/",
         "mpaa": "",
         "lastplayed": "2019-01-29 07:16:43",
         "label": "A Lady of Chance",
         "director": ["Robert Z. Leonard"]
         "cast": [{"thumbnail": "image://%2fmovies%2f...Norma_Shearer.jpg/",
                    "role": "Dolly",
                    "name": "Norma Shearer",
                    "order": 0},
                  {"thumbnail": ... "order": 10}],
         "studio": ["Metro-Goldwyn-Mayer (MGM)"],
         "file": "/movies/XBMC/Movies/20s/A Lady of Chance (1928).avi",
         "year": 1928,
         "genre": ["Comedy", "Drama", "Romance"],
         "runtime": 4800,
         "thumbnail": "image://%2fmovi...%20(1928)-poster.jpg/",
         "trailer": "/movies/XBMC/Movies/20s/A Lady of C...ler.mkv"}

        Possible Properties from VideoLibrary.getMovies:

        Parms:
              "genreid" a Library.Id
            "genre" string
            "year" int
            "actor": string
            "director" string
            "studio": string
            "country" string
            "setid" Library.Id
            "set" string
            tag string
        results


Item.Details.Base
    string label
Media.Details.Base
    [ string fanart ]
    [ string thumbnail ]


Video Details Base
 [Media.Artwork art ]
      Global.String.NotEmpty banner ]
    [ Global.String.NotEmpty fanart ]
    [ Global.String.NotEmpty poster ]
    [ Global.String.NotEmpty thumb ]
[ integer playcount = "0" ]

Video.Details.Media
    [string title]
    [ Video.Cast cast ]
    [ Array.String country ]
    [ Array.String genre ]
    [ string imdbnumber ]
    Library.Id movieid
    [ string mpaa ]
    [ string originaltitle ]
    [ string plotoutline ]
    [ string premiered ]
    [ number rating = "0" ]
    [ mixed ratings ]
    [ string set ]
    [ Library.Id setid = "-1" ]
    [ Array.String showlink ]
    [ string sorttitle ]
    [ Array.String studio ]
    [ Array.String tag ]
    [ string tagline ]
    [ integer top250 = "0" ]
    [ string trailer ]
    [ Media.UniqueID uniqueid ]
    [ integer userrating = "0" ]
    [ string votes ]
    [ Array.String writer ]
    [ integer year = "0" ]


Video.Details.Item
    [ string dateadded ]
    [ string file ]
    [ string lastplayed ]
    [ string plot ]


Video.Details.File
    [ Array.String director ]
    [ Video.Resume resume ]
    [ integer runtime = "0" ] Runtime in seconds
    [ Video.Streams streamdetails ]

Video.Details.Movie
    [ Video.Cast cast ]
    [ Array.String country ]
    [ Array.String genre ]
    [ string imdbnumber ]
    Library.Id movieid
    [ string mpaa ]
    [ string originaltitle ]
    [ string plotoutline ]
    [ string premiered ]
    [ number rating = "0" ]
    [ mixed ratings ]
    [ string set ]
    [ Library.Id setid = "-1" ]
    [ Array.String showlink ]
    [ string sorttitle ]
    [ Array.String studio ]
    [ Array.String tag ]
    [ string tagline ]
    [ integer top250 = "0" ]
    [ string trailer ]
    [ Media.UniqueID uniqueid ]
    [ integer userrating = "0" ]
    [ string votes ]
    [ Array.String writer ]
    [ integer year = "0" ]

List.Limits

    [ List.Amount end = "-1" ] Index of the last item to return
    [ integer start = "0" ] Index of the first item to return

List.Sort

    [ boolean ignorearticle = false ]
    [ string method = "none" ]
    [ string order = "ascending" ]
    """
    TITLE = 'title'
    ORIGINAL_TITLE = 'originaltitle'
    TRAILER = 'trailer'
    YEAR_KEY = 'year'
    LAST_PLAYED = 'lastplayed'
    MPAA = 'mpaa'
    FANART = 'fanart'
    THUMBNAIL = 'thumbnail'
    FILE = 'file'
    YEAR = 'year'
    WRITER = 'writer'
    DIRECTOR = 'director'
    CAST = 'cast'
    PLOT = 'plot'
    GENRE = 'genre'
    STUDIO = 'studio'
    MOVIEID = 'movieid'
    LABEL = 'label'
    RUNTIME = 'runtime'
    TAG = 'tag'
    UNIQUE_ID = 'uniqueid'

    # Some values for UNIQUE_ID field:
    UNIQUE_ID_TMDB = 'tmdb'
    UNIQUE_ID_UNKNOWN = 'unknown'
    UNIQUE_ID_IMDB = 'imdb'

    RELEASE_DATE = 'releasedate'
    POSTER = 'poster'
    POSTER_2X = 'poster_2x'
    LOCATION = 'location'
    RATING = 'rating'
    ACTORS = 'actors'
    VOTES = 'votes'

    # Properties invented by this plugin:

    # From iTunes
    # From Tmdb

    # Probably don't need this field in kodi movie dict
    ADULT = 'adult'

    TYPE = 'trailerType'
    # TODO rename to trailerSource
    SOURCE = 'source'
    CACHED_TRAILER = 'cached_trailer'
    NORMALIZED_TRAILER = 'normalized_trailer'
    ORIGINAL_LANGUAGE = 'original_language'
    LANGUAGE_INFORMATION_FOUND = 'language_information_found'
    LANGUAGE_MATCHES = 'language_matches'

    # Used for movie trailers discovered from TMDB and not from movies in Kodi.
    # Contains TMDB Id for the movie
    #
    # TODO: change to use UNIQUE_ID structure
    #TMDB_ID = 'rts.tmdbId'
    ITUNES_ID = 'rts.appleId'

    # Processed values for InfoDialog
    DETAIL_ACTORS = 'rts.actors'
    DETAIL_DIRECTORS = 'rts.directors'
    DETAIL_GENRES = 'rts.genres'
    DETAIL_RATING = 'rts.rating'
    DETAIL_RATING_IMAGE = 'rts.ratingImage'
    DETAIL_RUNTIME = 'rts.runtime'
    DETAIL_STUDIOS = 'rts.studios'
    DETAIL_TITLE = 'rts.title'
    DETAIL_WRITERS = 'rts.writers'
    DETAIL_TAGS = 'rts.tags'

    # Reference to corresponding movie dict entry
    DETAIL_ENTRY = 'rts.movie.entry'

    # Source Values. Used to identify source database of movies. Also used to
    # identify discovery modules.

    FOLDER_SOURCE = 'folder'
    LIBRARY_SOURCE = 'library'
    ITUNES_SOURCE = 'iTunes'
    TMDB_SOURCE = 'TMDb'

    LIB_TMDB_ITUNES_SOURCES = (LIBRARY_SOURCE, TMDB_SOURCE, ITUNES_SOURCE)

    # In addition to above source values, these are used to identify
    # discovery modules

    LIBRARY_NO_TRAILER = 'library_no_trailer'
    LIBRARY_URL_TRAILER = 'library_url_trailer'

    # Trailer Type values:
    TMDB_TYPE = 'TMDB_type'
    TMDB_PAGE = 'TMDB_page'  # For statistics, remember download page
    TMDB_TOTAL_PAGES = 'TMDB_TOTAL_PAGES'  # For statistics

    # DISCOVERY_STATE element contains an ordered list of
    # states.The numeric prefix makes the values comparable like an
    # (poor man's) enum.

    DISCOVERY_STATE = 'trailerDiscoveryState'
    NOT_INITIALIZED = '00_not_initialized'
    NOT_FULLY_DISCOVERED = '01_notFullyDiscovered'
    TRAILER_DISCOVERY_IN_PROGRESS = '02_discoveryInProgress'
    DISCOVERY_COMPLETE = '03_discoveryComplete'
    DISCOVERY_READY_TO_DISPLAY = '04_discoveryReadyToDisplay'

    # IN_FETCH_QUEUE is a boolean
    IN_FETCH_QUEUE = 'in_fetch_queue'

    # TRAILER_PLAYED is a boolean field
    TRAILER_PLAYED = 'trailerPlayed'

    # TMDB_ID_NOT_FOUND is a boolean that is always True,
    # If present, then the TMDB id could not be found. Used to suppress
    # repeated checks. An alternative solution would be to have a special
    # TMDB_ID value < 1, but at the time the refactoring would be too
    # disruptive.

    TMDB_ID_NOT_FOUND = 'rts.tmdb_id_not_found'

    # Indicates whether this entry is from the Tmdb cache

    CACHED = 'cached'


# noinspection PyClassHasNoInit
class iTunes(object):
    """
        Defines constants that apply to iTunes
    """
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
        # type: (TextType) -> TextType
        url = iTunes._trailerForTypeMap.get(trailerType, None)
        return url


"""
# noinspection PyClassHasNoInit,PyClassHasNoInit,PyClassHasNoInit
class TMDB(object):
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


class GenreEnum(object):
    # Possible values returned by settings.xml

    IGNORE = 0  # This Genre will be ignored in filtering
    INCLUDE = 1  # Genre filter will include this genre in an OR fashion
    EXCLUDE = 2  # Genre filter will exclude this genre in an OR fashion

# noinspection PyClassHasNoInit


class GenreConstants(object):
    # Ids used in settings.xml
    ACTION = 'g_action'
    ALEGORY = 'g_alegory'  # NOT USED
    ANTHOLOGY = 'ganthology'  # not used
    ADVENTURE = 'g_adventure'
    ANIMATION = 'g_animation'
    BIOGRAPHY = 'g_biography'
    CHILDRENS = 'g_childrens'  # not used
    COMEDY = 'g_comedy'
    CRIME = 'g_crime'
    DARK_COMEDY = 'g_black_comedy'
    DOCUMENTARY = 'g_docu'
    DRAMA = 'g_drama'
    EPIC = 'g_epic'
    EXPERIMENTAL = 'g_experimental'  # not used
    FAMILY = 'g_family'
    FANTASY = 'g_fantasy'
    FILM_NOIR = 'g_film_noir'
    FOREIGN = 'g_foreign'  # not used
    GAME_SHOW = 'g_game_show'  # not used
    HISTORY = 'g_history'
    HORROR = 'g_horror'
    MELODRAMA = 'g_melodrama'
    MUSIC = 'g_music'
    MUSICAL = 'g_musical'
    MUSICAL_COMEDY = 'g_musical_comedy'
    MYSTERY = 'g_mystery'
    PERFORMANCE = 'g_performance'  # not used
    PRE_CODE = 'g_pre_code'
    ROMANCE = 'g_romance'
    ROMANTIC_COMEDY = 'g_romantic_comedy'
    SATIRE = 'g_satire'
    SCI_FI = 'g_scifi'
    SCREWBALL_COMEDY = 'g_screwball'
    SWASHBUCKLER = 'g_swashbuckler'
    THRILLER = 'g_thriller'
    TV_MOVIE = 'g_tv_movie'
    VARIETY = 'g_variety'  # Not used
    WAR = 'g_war'
    WAR_DOCUMENTARY = 'g_war_documentary'
    WESTERN = 'g_western'


class DebugLevel(object):
    """

    """
    FATAL = '00_Fatal'
    SEVERE = '01_Severe'
    ERROR = '02_Error'
    WARNING = '03_Warning'
    NOTICE = '04_Notice'
    INFO = '05_Info'
    DEBUG_EXTRA_VERBOSE = '06_Debug_Extra_Verbose'
    DEBUG_VERBOSE = '07_Debug_Verbose'
    DEBUG = '08_Debug'
