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

    @staticmethod
    def staticInit():
        Constants.ADDON = xbmcaddon.Addon()  # Constants.addonName)
        Constants.ADDON_PATH = unicode(Constants.ADDON.getAddonInfo(
            u'path').decode(u'utf-8'))
        Constants.MEDIA_PATH = addon.MEDIA_PATH
        Constants.SCRIPT_PATH = os.path.join(
            Constants.ADDON_PATH, u'resources', u'skins', u'Default', u'720p')


Constants.staticInit()


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

    # From iTunes
    # From Tmdb
    ADULT = u'adult'

    RELEASE_DATE = u'releasedate'
    POSTER = u'poster'
    POSTER_2X = u'poster_2x'
    LOCATION = u'location'
    RATING = u'rating'
    ACTORS = u'actors'

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

    # Reference to corresponding movie dict entry
    DETAIL_ENTRY = u'rts.movie.entry'

    # Source Values:
    FOLDER_SOURCE = u'folder'
    LIBRARY_SOURCE = u'library'
    ITUNES_SOURCE = u'iTunes'
    TMDB_SOURCE = u'tmdb'

    DISCOVERY_STATE = u'trailerDiscoveryState'
    NOT_FULLY_DISCOVERED = u'notFullyDiscovered'
    TRAILER_DISCOVERY_IN_PROGRESS = u'discoveryInProgress'
    DISCOVERY_COMPLETE = u'discoveryComplete'
    TRAILER_PLAYED = u'trailerPlayed'
    TRAILER_PLAY_ORDER_KEY = u'trailerPlayOrder'


class iTunes:
    # Applies to trailer type
    #"Coming Soon|Just Added|Popular|Exclusive|All"
    COMMING_SOON = 0
    JUST_ADDED = 1
    POPULAR = 2
    EXCLUSIVE = 3
    ALL = 4
