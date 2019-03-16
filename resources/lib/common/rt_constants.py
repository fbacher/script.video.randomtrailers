'''
Created on Feb 10, 2019

@author: fbacher
'''
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from multiprocessing.pool import ThreadPool
from kodi65 import addon
from kodi65 import utils
import sys
import datetime
import io
import json
import os
import queue
import random
import re
import requests
import resource
import threading
import time
import traceback
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
import xbmcdrm
import string


class Constants:
    TOO_MANY_TMDB_REQUESTS = 25
    addonName = u'script.video.randomtrailers'
    ADDON = None
    ADDON_PATH = None
    MEDIA_PATH = None
    SCRIPT_PATH = None
    TRAILER_INFO_DISPLAY_SECONDS = 60
    TRAILER_INFO_DISPLAY_MILLISECONDS = 6000
    SECONDS_BEFORE_RESHUFFLE = 1 * 60
    PLAY_LIST_LOOKBACK_WINDOW_SIZE = 10
    MAX_PLAY_TIME_WARNING_TIME = 5  # seconds

    @staticmethod
    def staticInit():
        Constants.ADDON = xbmcaddon.Addon()  # Constants.addonName)
        Constants.ADDON_PATH = unicode(Constants.ADDON.getAddonInfo(
            u'path').decode(u'utf-8'))
        Constants.MEDIA_PATH = addon.MEDIA_PATH
        Constants.SCRIPT_PATH = os.path.join(
            Constants.ADDON_PATH, u'resources', u'skins', u'Default', u'720p')


Constants.staticInit()


class RemoteTrailerPreference:
    NEWEST = 0
    OLDEST = 1
    HIGHEST_RATED = 2
    LOWEST_RATED = 3
    MOST_VOTES = 4
    LEAST_VOTES = 5

    AVERAGE_VOTE_DONT_CARE = 0
    AVERAGE_VOTE_GREATER_OR_EQUAL = 1
    AVERAGE_VOTE_LESS_OR_EQUAL = 2


class Movie:
    # Movie information dictionary keys:

    '''
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



    '''
    TITLE = u'title'
    ORIGINAL_TITLE = u'originaltitle'
    TRAILER = u'trailer'
    YEAR_KEY = u'year'
    LAST_PLAYED = u'lastplayed'
    MPAA = u'mpaa'
    FANART = u'fanart'
    THUMBNAIL = u'thumbnail'
    FILE = u'file'
    YEAR = u'year'
    WRITER = u'writer'
    DIRECTOR = u'director'
    CAST = u'cast'
    PLOT = u'plot'
    GENRE = u'genre'
    STUDIO = u'studio'
    MOVIEID = u'movieid'
    LABEL = u'label'
    RUNTIME = u'runtime'
    TAG = u'tag'
    UNIQUE_ID = u'uniqueid'

    # From iTunes
    # From Tmdb
    ADULT = u'adult'

    RELEASE_DATE = u'releasedate'
    POSTER = u'poster'
    POSTER_2X = u'poster_2x'
    LOCATION = u'location'
    RATING = u'rating'
    ACTORS = u'actors'
    VOTES = u'votes'

    # Properties invented by this plugin:

    TYPE = u'trailerType'
    # TODO rename to trailerSource
    SOURCE = u'source'

    # Processed values for InfoDialog
    DETAIL_ACTORS = u'rts.actors'
    DETAIL_DIRECTORS = u'rts.directors'
    DETAIL_GENRES = u'rts.genres'
    DETAIL_RATING = u'rts.rating'
    DETAIL_RATING_IMAGE = u'rts.ratingImage'
    DETAIL_RUNTIME = u'rts.runtime'
    DETAIL_STUDIOS = u'rts.studios'
    DETAIL_TITLE = u'rts.title'
    DETAIL_WRITERS = u'rts.writers'
    DETAIL_TAGS = u'rts.tags'

    # Reference to corresponding movie dict entry
    DETAIL_ENTRY = u'rts.movie.entry'

    # Source Values:
    FOLDER_SOURCE = u'folder'
    LIBRARY_SOURCE = u'library'
    ITUNES_SOURCE = u'iTunes'
    TMDB_SOURCE = u'TMDb'

    DISCOVERY_STATE = u'trailerDiscoveryState'
    NOT_FULLY_DISCOVERED = u'notFullyDiscovered'
    TRAILER_DISCOVERY_IN_PROGRESS = u'discoveryInProgress'
    DISCOVERY_COMPLETE = u'discoveryComplete'
    DISCOVERY_READY_TO_DISPLAY = u'discoveryReadyToDisplay'
    TRAILER_PLAYED = u'trailerPlayed'
    TRAILER_PLAY_ORDER_KEY = u'trailerPlayOrder'

    # Some values for UNIQUE_ID field:
    UNIQUE_ID_TMDB = u'tmdb'
    UNIQUE_ID_UNKNOWN = U'unknown'
    UNIQUE_ID_imdb = u'imdb'


class iTunes:
    # Applies to trailer type
    #"Coming Soon|Just Added|Popular|Exclusive|All"
    COMING_SOON = 0
    JUST_ADDED = 1
    POPULAR = 2
    EXCLUSIVE = 3
    ALL = 4

    COMING_SOON_URL = u'/trailers/home/feeds/studios.json'
    JUST_ADDED_URL = u'/trailers/home/feeds/just_added.json'
    POPULAR_URL = u'/trailers/home/feeds/most_pop.json'
    EXCLUSIVE_URL = u'/trailers/home/feeds/exclusive.json'
    ALL_URL = u'/trailers/home/feeds/studios.json'

    _trailerForTypeMap = {COMING_SOON: COMING_SOON_URL,
                          JUST_ADDED: JUST_ADDED_URL,
                          POPULAR: POPULAR_URL,
                          EXCLUSIVE: EXCLUSIVE_URL,
                          ALL: ALL_URL}

    @staticmethod
    def getURLForTrailerType(trailerType):
        url = iTunes._trailerForTypeMap.get(trailerType, None)
        return url


class TMDB:
    # Applies to trailer type
    #"Coming Soon|Just Added|Popular|Exclusive|All"
    COMING_SOON = 0
    JUST_ADDED = 1
    POPULAR = 2
    EXCLUSIVE = 3
    ALL = 4

    COMING_SOON_URL = u'/trailers/home/feeds/studios.json'
    JUST_ADDED_URL = u'/trailers/home/feeds/just_added.json'
    POPULAR_URL = u'/trailers/home/feeds/most_pop.json'
    EXCLUSIVE_URL = u'/trailers/home/feeds/exclusive.json'
    ALL_URL = u'/trailers/home/feeds/studios.json'

    _trailerForTypeMap = {COMING_SOON: COMING_SOON_URL,
                          JUST_ADDED: JUST_ADDED_URL,
                          POPULAR: POPULAR_URL,
                          EXCLUSIVE: EXCLUSIVE_URL,
                          ALL: ALL_URL}

    @staticmethod
    def getURLForTrailerType(trailerType):
        url = iTunes._trailerForTypeMap.get(trailerType, None)
        return url


class GenreConstants:

    # Ids used in settings.xml
    ACTION = u'g_action'
    ALEGORY = u'g_alegory'  # NOT USED
    ANTHOLOGY = u'ganthology'  # not used
    ADVENTURE = u'g_adventure'
    ANIMATION = u'g_animation'
    BIOGRAPHY = u'g_biography'
    CHILDRENS = u'g_childrens'  # not used
    COMEDY = u'g_comedy'
    CRIME = u'g_crime'
    DARK_COMEDY = u'g_black_comedy'
    DOCUMENTARY = u'g_docu'
    DRAMA = u'g_drama'
    EPIC = u'g_epic'
    EXPERIMENTAL = u'g_experimental'  # not used
    FAMILY = u'g_family'
    FANTASY = u'g_fantasy'
    FILM_NOIR = u'g_film_noir'
    FOREIGN = u'g_foreign'  # not used
    GAME_SHOW = u'g_game_show'  # not used
    HISTORY = u'g_history'
    HORROR = u'g_horror'
    MELODRAMA = u'g_melodrama'
    MUSIC = u'g_music'
    MUSICAL = u'g_musical'
    MUSICAL_COMEDY = u'g_musical_comedy'
    MYSTERY = u'g_mystery'
    PERFORMANCE = u'g_performance'  # not used
    PRE_CODE = u'g_pre_code'
    ROMANCE = u'g_romance'
    ROMANTIC_COMEDY = u'g_romantic_comedy'
    SATIRE = u'g_satire'
    SCI_FI = u'g_scifi'
    SCREWBALL_COMEDY = u'g_screwball'
    SWASHBUCKLER = u'g_swashbuckler'
    THRILLER = u'g_thriller'
    TV_MOVIE = u'g_tv_movie'
    VARIETY = u'g_variety'  # Not used
    WAR = u'g_war'
    WAR_DOCUMENTARY = u'g_war_documentary'
    WESTERN = u'g_western'
