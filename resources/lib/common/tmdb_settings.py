'''
Created on Mar 4, 2019

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
from xml.dom import minidom
from kodi65 import addon
from kodi65 import utils
from backend.genre import Genre
from backend.rating import Rating
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.exceptions import AbortException, ShutdownException
from common.rt_utils import Trace
from common.logger import Logger, logEntryExit
from common.messages import Messages
from settings import Settings
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
import urllib
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
#import xbmcwsgi
#import xbmcdrm
import string
import action_map


class TmdbSettings:
    _instance = None

    _ratingLimitStringForSetting = {u'0': Rating.RATING_NC_17,
                                    u'1': Rating.RATING_G,
                                    u'2': Rating.RATING_PG,
                                    u'3': Rating.RATING_PG_13,
                                    u'4': Rating.RATING_R,
                                    u'5': Rating.RATING_NC_17}

    _sourceStringForSourceSettingMap = {u'0': u'popular',
                                        u'1': u'top_rated',
                                        u'2': u'upcoming',
                                        u'3': u'now_playing',
                                        u'4': u'all'}

    _genreSettingMethodForGenre = {}

    @staticmethod
    def getInstance():
        if TmdbSettings._instance is None:
            TmdbSettings._instance = TmdbSettings()
        return TmdbSettings._instance

    def getAllowedGenres(self):
        selectedGenres = Genre.getAllowedGenres()
        return selectedGenres

    def getAllowedGenresString(self):
        selectedGenres = u''
        separator = u''
        for genre in Genre.getAllowedGenres():
            selectedGenres = genre.getTmdbLabel() + separator
            separator = u','

        return selectedGenres

    @staticmethod
    def getGenreComedy():
        return Constants.ADDON.getSetting(u'g_comedy') == u'true'

    @staticmethod
    def getGenreDocumentary():
        return Constants.ADDON.getSetting(u'g_docu') == u'true'

    @staticmethod
    def getGenreDrama():
        return Constants.ADDON.getSetting(u'g_drama') == u'true'

    @staticmethod
    def getGenreFamily():
        return Constants.ADDON.getSetting(u'g_family') == u'true'

    @staticmethod
    def getGenreFantasy():
        return Constants.ADDON.getSetting(u'g_fantasy') == u'true'

    @staticmethod
    def getGenreForeign():
        return Constants.ADDON.getSetting(u'g_foreign') == u'true'

    @staticmethod
    def getGenreHorror():
        return Constants.ADDON.getSetting(u'g_horror') == u'true'

    @staticmethod
    def getGenreMusical():
        return Constants.ADDON.getSetting(u'g_musical') == u'true'

    @staticmethod
    def getGenreRomance():
        return Constants.ADDON.getSetting(u'g_romance') == u'true'

    @staticmethod
    def getGenreSciFi():
        return Constants.ADDON.getSetting(u'g_scifi') == u'true'

    @staticmethod
    def getGenreThriller():
        return Constants.ADDON.getSetting(u'g_thriller') == u'true'

    def getHideWatchedMovies(self):
        return Constants.ADDON.getSetting(u'hide_watched') == u'true'

    def getIncludeAdult(self):
        return False

    def getIncludeClips(self):
        return Constants.ADDON.getSetting(u'do_clips') == u'true'

    def getIncludeFeaturettes(self):
        return Constants.ADDON.getSetting(u'do_featurettes') == u'true'

    def getIncludeOldMovieTrailers(self):
        return True

    def getMaxNumberOfTrailers(self):
        return 1000

    def getRatingLimitStringFromSetting(self):
        ratingLimit = Settings.getRatingLimitSetting()
        return TmdbSettings._ratingLimitStringForSetting[ratingLimit]

    def getSourceStringForSourceSetting(self):
        tmdbSource = Settings.getTmdbSourceSetting()
        return TmdbSettings._sourceStringForSourceSettingMap[tmdbSource]
