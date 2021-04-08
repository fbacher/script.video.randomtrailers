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
    InitialGarbageCollectionTime: Final[int] = 10 * 60  # Ten minutes in seconds
    # Run daily garbage collection at 04:13 in the morning.
    DailyGarbageCollectionTime: datetime.time = datetime.time(hour=4, minute=13)
    HTTP_TOO_MANY_REQUESTS: Final[int] = 429
    HTTP_UNAUTHORIZED: Final[int] = 401
    TRACEBACK: Final[str] = 'LEAK Traceback StackTrace StackDump'
    TRAILER_CACHE_FLUSH_SECONDS: Final[int] = 300  # Five minutes with changes
    TRAILER_CACHE_FLUSH_UPDATES: Final[int] = 10  # Flush cache after n updates

    PLAY_STATISTICS_REPORT_PATH: str = None

    # Altered to one month ago in static_init
    CACHE_FILE_EXPIRED_TIME: int = datetime.MAXYEAR
    PLAYLIST_PATH: str = ''
    LOCALE: str = ''

    plugin_short_names: Final[Dict[str, str]] = {
        'service.randomtrailers.backend': 'randomtrailers.backend',
        'script.video.randomtrailers.screensaver': 'randomtrailers.screensaver',
        'script.video.randomtrailers': 'randomtrailers'
    }

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


class Movie:
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
    TITLE: Final[str] = 'title'
    ORIGINAL_TITLE: Final[str] = 'originaltitle'
    TRAILER: Final[str] = 'trailer'
    LAST_PLAYED: Final[str] = 'lastplayed'
    MPAA: Final[str] = 'mpaa'
    FANART: Final[str] = 'fanart'
    THUMBNAIL: Final[str] = 'thumbnail'
    FILE: Final[str] = 'file'
    YEAR: Final[str] = 'year'
    WRITER: Final[str] = 'writer'
    DIRECTOR: Final[str] = 'director'
    CAST: Final[str] = 'cast'
    PLOT: Final[str] = 'plot'
    GENRE: Final[str] = 'genre'
    STUDIO: Final[str] = 'studio'
    MOVIEID: Final[str] = 'movieid'
    LABEL: Final[str] = 'label'
    RUNTIME: Final[str] = 'runtime'
    TAG: Final[str] = 'tag'
    UNIQUE_ID: Final[str] = 'uniqueid'

    # Some values for UNIQUE_ID field:
    UNIQUE_ID_TMDB: Final[str] = 'tmdb'
    UNIQUE_ID_UNKNOWN: Final[str] = 'unknown'
    UNIQUE_ID_IMDB: Final[str] = 'imdb'

    RELEASE_DATE: Final[str] = 'releasedate'
    POSTER: Final[str] = 'poster'
    POSTER_2X: Final[str] = 'poster_2x'
    LOCATION: Final[str] = 'location'
    RATING: Final[str] = 'rating'
    ACTORS: Final[str] = 'actors'
    VOTES: Final[str] = 'votes'

    # Properties invented by this plugin:

    # From iTunes
    # From TMDb

    # Probably don't need this field in kodi movie dict
    ADULT: Final[str] = 'adult'

    TRAILER_TYPE: Final[str] = 'trailerType'
    # TODO rename to trailerSource
    SOURCE: Final[str] = 'source'
    CACHED_TRAILER: Final[str] = 'cached_trailer'
    NORMALIZED_TRAILER: Final[str] = 'normalized_trailer'
    ORIGINAL_LANGUAGE: Final[str] = 'original_language'
    LANGUAGE_INFORMATION_FOUND: Final[str] = 'language_information_found'
    LANGUAGE_MATCHES: Final[str] = 'language_matches'

    VIDEO_TYPE_TRAILER: Final[str] = 'Trailer'
    VIDEO_TYPE_FEATURETTE: Final[str] = 'Featurette'
    VIDEO_TYPE_CLIP: Final[str] = 'Clip'

    ITUNES_ID: Final[str] = 'rts.appleId'
    YOUTUBE_ID: Final[str] = 'rts.youtubeId'
    TFH_ID: Final[str] = 'rts.tfhId'
    TFH_TITLE: Final[str] = 'rts.tfh_title'
    YOUTUBE_PLAYLIST_INDEX: Final[str] = 'rts.youtube_index'
    YOUTUBE_TRAILERS_IN_PLAYLIST: Final[str] = 'rts.youtube.trailers_in_index'

    # Processed values for InfoDialog
    DETAIL_ACTORS: Final[str] = 'rts.actors'
    MAX_DISPLAYED_ACTORS: Final[int] = 6
    DETAIL_DIRECTORS: Final[str] = 'rts.directors'
    DETAIL_GENRES: Final[str] = 'rts.genres'
    DETAIL_CERTIFICATION: Final[str] = 'rts.certification'
    DETAIL_CERTIFICATION_IMAGE: Final[str] = 'rts.certificationImage'
    DETAIL_RUNTIME: Final[str] = 'rts.runtime'
    DETAIL_STUDIOS: Final[str] = 'rts.studios'
    DETAIL_TITLE: Final[str] = 'rts.title'
    DETAIL_WRITERS: Final[str] = 'rts.writers'

    # For use with speech synthesis
    MAX_VOICED_ACTORS: Final[int] = 3
    VOICED_DETAIL_ACTORS: Final[str] = 'rts.voiced.actors'
    MAX_VOICED_DIRECTORS: Final[int] = 2
    VOICED_DETAIL_DIRECTORS: Final[str] = 'rts.voiced.directors'
    MAX_VOICED_WRITERS: Final[int] = 2
    VOICED_DETAIL_WRITERS: Final[str] = 'rts.voiced.writers'
    MAX_VOICED_STUDIOS: Final[int] = 2
    VOICED_DETAIL_STUDIOS: Final[str] = 'rts.voiced.studios'

    # Reference to corresponding movie dict entry
    DETAIL_ENTRY: Final[str] = 'rts.movie.entry'

    # Source Values. Used to identify source database of movies. Also used to
    # identify discovery modules.

    FOLDER_SOURCE: Final[str] = 'folder'
    LIBRARY_SOURCE: Final[str] = 'library'
    ITUNES_SOURCE: Final[str] = 'iTunes'
    TMDB_SOURCE: Final[str] = 'TMDb'
    TFH_SOURCE: Final[str] = 'TFH'

    LIB_TMDB_ITUNES_SOURCES: Tuple[str] = (
        LIBRARY_SOURCE, TMDB_SOURCE, ITUNES_SOURCE, TFH_SOURCE)

    # In addition to above source values, these are used to identify
    # discovery modules

    LIBRARY_NO_TRAILER: Final[str] = 'library_no_trailer'
    LIBRARY_URL_TRAILER: Final[str] = 'library_url_trailer'

    # Trailer Type values:
    TMDB_TYPE: Final[str] = 'TMDB_type'
    TMDB_PAGE: Final[str] = 'TMDB_page'  # For statistics, remember download page
    TMDB_TOTAL_PAGES: Final[str] = 'TMDB_TOTAL_PAGES'  # For statistics

    TMDB_TAGS: Final[str] = 'rts.tags'
    TMDB_GENRE_IDS: Final[str] = 'rts.genre_ids'
    TMDB_VOTE_AVERAGE: Final[str] = 'rts.tmdb_vote_average'
    TMDB_IS_VIDEO: Final[str] = 'rts.tmdb_video'
    TMDB_POPULARITY: Final[str] = 'rts.tmdb_popularity'


    # DISCOVERY_STATE element contains an ordered list of
    # states.The numeric prefix makes the values comparable like an
    # (poor man's) enum.

    DISCOVERY_STATE: Final[str] = 'trailerDiscoveryState'
    NOT_INITIALIZED: Final[str] = '00_not_initialized'
    NOT_FULLY_DISCOVERED: Final[str] = '01_notFullyDiscovered'
    TRAILER_DISCOVERY_IN_PROGRESS: Final[str] = '02_discoveryInProgress'
    DISCOVERY_COMPLETE: Final[str] = '03_discoveryComplete'
    DISCOVERY_READY_TO_DISPLAY: Final[str] = '04_discoveryReadyToDisplay'

    # IN_FETCH_QUEUE is a boolean
    IN_FETCH_QUEUE: Final[str] = 'in_fetch_queue'

    # TRAILER_PLAYED is a boolean field
    TRAILER_PLAYED: Final[str] = 'trailerPlayed'

    # TMDB_ID_NOT_FOUND is a boolean that is always True,
    # If present, then the TMDB id could not be found. Used to suppress
    # repeated checks. An alternative solution would be to have a special
    # TMDB_ID value < 1, but at the time the refactoring would be too
    # disruptive.

    TMDB_ID_NOT_FOUND: Final[str] = 'rts.tmdb_id_not_found'

    # Indicates whether this entry is from the TMDb cache

    CACHED: Final[str] = 'cached'

    # Reasons a TMDB movie was rejected

    REJECTED: Final[str] = 'rts.rejected'  # Value is a List of the following reasons:
    REJECTED_NO_TRAILER: Final[int] = 1
    REJECTED_FILTER_GENRE: Final[int] = 2
    REJECTED_FAIL: Final[int] = 3  # Request to TMDB failed
    REJECTED_FILTER_DATE: Final[int] = 4
    REJECTED_LANGUAGE: Final[int] = 5
    REJECTED_CERTIFICATION: Final[int] = 6
    REJECTED_ADULT: Final[int] = 7
    REJECTED_VOTE: Final[int] = 8
    REJECTED_TOO_MANY_TMDB_REQUESTS: Final[int] = 9

    DEFAULT_MOVIE: Dict[str, Any] = {
        DISCOVERY_STATE: NOT_INITIALIZED,
        TITLE: 'default_' + TITLE,
        ORIGINAL_TITLE: 'default_' + ORIGINAL_TITLE,
        YEAR: 0,
        STUDIO: [],
        MPAA: '',
        THUMBNAIL: 'default_' + THUMBNAIL,
        TRAILER: 'default_' + TRAILER,
        FANART: 'default_' + FANART,
        FILE: 'default_' + FILE,
        DIRECTOR: ['default_' + DIRECTOR],
        WRITER: ['default_' + WRITER],
        PLOT: 'default_' + PLOT,
        CAST: [],  # Cast is a list of Dict entries
        RUNTIME: 0,
        GENRE: [],
        TMDB_TAGS: ['default_' + TMDB_TAGS],
        RATING: 0.0,
        VOTES: 0,
        ADULT: False,
        SOURCE: 'default_' + SOURCE,
        TRAILER_TYPE: 'default_' + TRAILER_TYPE,
        DETAIL_DIRECTORS: ['default_' + DETAIL_DIRECTORS],
        DETAIL_TITLE: 'default_' + TITLE,
        DETAIL_ACTORS: ['default_' + DETAIL_ACTORS],
        DETAIL_GENRES: ['default_' + DETAIL_GENRES],
        DETAIL_CERTIFICATION: ['default_' + DETAIL_CERTIFICATION],
        DETAIL_CERTIFICATION_IMAGE: 'default_' + DETAIL_CERTIFICATION_IMAGE,
        DETAIL_RUNTIME: 0,
        DETAIL_WRITERS: ['default_' + DETAIL_WRITERS],
        DETAIL_STUDIOS: ['default_' + DETAIL_STUDIOS],
    }

    TMDB_PAGE_DATA_FIELDS: Final[List[str]] = [
        TRAILER,
        SOURCE,
        TITLE,
        YEAR,
        TMDB_POPULARITY,
        VOTES,
        TMDB_IS_VIDEO,
        ADULT,
        TMDB_VOTE_AVERAGE,
        TMDB_GENRE_IDS,
        ORIGINAL_LANGUAGE,
        TMDB_PAGE,
        TMDB_TOTAL_PAGES]

    TMDB_ENTRY_FIELDS: Final[List[str]] = [
        ADULT,
        #  "alternative_titles",
        "backdrop_path",
        #  "belongs_to_collection",
        #  "budget",
        "credits",
        "genres",
        #  "homepage",
        "id",
        "imdb_id",
        "keywords",
        "original_language",
        "original_title",
        "overview",
        "popularity",
        "poster_path",
        "production_companies",
        #  "production_countries",
        "release_date",
        "releases",
        #  "revenue",
        "runtime",
        "spoken_languages",
        #  "status",
        "tagline",
        TITLE,
        "video",
        "videos",
        "vote_average",
        "vote_count",
        CACHED
    ]


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

    _trailerForTypeMap: Final[Dict[str, str]] =\
        {COMING_SOON: COMING_SOON_URL,
         JUST_ADDED: JUST_ADDED_URL,
         POPULAR: POPULAR_URL,
         EXCLUSIVE: EXCLUSIVE_URL,
         ALL: ALL_URL}

    @staticmethod
    def get_url_for_trailer_type(trailer_type: Final[str]) -> str:
        url: str = iTunes._trailerForTypeMap.get(trailer_type, None)
        return url


class TFH:
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
    DOCUMENTARY: Final[str] = 'g_docu'
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
    SCREWBALL_COMEDY: Final[str] = 'g_screwball'
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
