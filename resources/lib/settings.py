'''
Created on Feb 10, 2019

@author: fbacher
'''
from __future__ import print_function  # @NoMove
from __future__ import division  # @NoMove
from __future__ import absolute_import  # @NoMove
from __future__ import unicode_literals  # @NoMove
from future import standard_library  # @NoMove
standard_library.install_aliases()  # @NoMove
from builtins import str  # @NoMove
from builtins import range  # @NoMove
from builtins import unicode  # @NoMove
from multiprocessing.pool import ThreadPool
from kodi65.kodiaddon import Addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie

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
import time
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
import xbmcdrm
import string


class Settings:

    _addonSingleton = None

    @staticmethod
    def getAddon():
        if Settings._addonSingleton is None:
            Settings._addonSingleton = Addon()
        return Settings._addonSingleton

    @staticmethod
    def getNumberOfTrailersToPlay():
        numberOfTrailersToPlayStr = Constants.ADDON.getSetting(
            'numberOfTrailersToPlay')
        if numberOfTrailersToPlayStr == u'':
            return 0
        else:
            return int(numberOfTrailersToPlayStr)

    @staticmethod
    def getShowCurtains():
        return Constants.ADDON.getSetting(u'do_animation') == u'true'

    # do_genre
    @staticmethod
    def getFilterGenres():
        if len(sys.argv) == 2:
            return False
        else:
            return Constants.ADDON.getSetting(u'do_genre') == u'true'

    @staticmethod
    def getAdjustVolume():
        if Settings.getVolume() > 100:
            return False
        else:
            return Constants.ADDON.getSetting(u'do_volume') == u'true'

    @staticmethod
    def getVolume():
        return int(Constants.ADDON.getSetting(u'volume'))

    @staticmethod
    def getIncludeLibraryTrailers():
        return Constants.ADDON.getSetting(u'do_library') == u'true'

    @staticmethod
    def getIncludeLibraryRemoteTrailers():
        return Constants.ADDON.getSetting(u'do_library_remote_trailers') == u'true'

    @staticmethod
    def getIncludeLibraryNoTrailerInfo():
        return Constants.ADDON.getSetting(u'do_library_no_trailer_info') == u'true'

    @staticmethod
    def getIncludeTrailerFolders():
        return Constants.ADDON.getSetting(u'do_folder') == u'true'

    @staticmethod
    def getIncludeItunesTrailers():
        return Constants.ADDON.getSetting(u'do_itunes') == u'true'

    @staticmethod
    def getIncludeTMDBTrailers():
        return Constants.ADDON.getSetting(u'do_tmdb') == u'true'

    @staticmethod
    def getIncludeNotYetRatedTrailers():
        return Constants.ADDON.getSetting(u'do_notyetrated') == u'true'

    @staticmethod
    def getIncludeClips():
        return Constants.ADDON.getSetting(u'do_clips') == u'true'

    @staticmethod
    def getIncludeFeaturettes():
        return Constants.ADDON.getSetting(u'do_featurettes') == u'true'

    @staticmethod
    def getLanguage():
        return u'en'

    @staticmethod
    def getSpokenLanguage():
        return u'English'

    @staticmethod
    def getQuality():
        qualityIndex = int(Constants.ADDON.getSetting(u'quality'))
        return ["480p", "720p", "1080p"][qualityIndex]

    @staticmethod
    def getIncludeAdult():
        return False

    @staticmethod
    def getIncludeItunesTrailerType():
        # "Coming Soon|Just Added|Popular|Exclusive|All"
        # See Constants.iTunes
        return int(Constants.ADDON.getSetting(u'trailer_type'))

    @staticmethod
    def getShowTrailerTitle():
        showTitle = Constants.ADDON.getSetting(u'hide_title') != u'true'
        return showTitle

    @staticmethod
    def getHideWatchedMovies():
        return Constants.ADDON.getSetting(u'hide_watched') == u'true'

    @staticmethod
    def getMinimumDaysSinceWatched():
        return Constants.ADDON.getSetting(u'watched_days')

    @staticmethod
    def getResourcesPath():
        return xbmc.translatePath(
            os.path.join(Constants.ADDON_PATH, u'resources')).decode(u'utf-8')

    @staticmethod
    def getMediaPath():
        return xbmc.translatePath(os.path.join(
            Settings.getResourcesPath(), u'media')).decode(u'utf-8')

    @staticmethod
    def getOpenCurtainPath():
        return xbmc.translatePath(os.path.join(
            Settings.getMediaPath(), u'CurtainOpeningSequence.flv')).decode(u'utf-8')

    @staticmethod
    def getCloseCurtainPath():
        return xbmc.translatePath(os.path.join(
            Settings.getMediaPath(), u'CurtainClosingSequence.flv')).decode(u'utf-8')

    @staticmethod
    def getTrailersPaths():
        return Constants.ADDON.getSetting(u'path')

    @staticmethod
    def getGenreAction():
        return Constants.ADDON.getSetting(u'g_action') == u'true'

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

    @staticmethod
    def getTmdbApiKey():
        TMDB_API_KEY = u'99e8b7beac187a857152f57d67495cf4'
        TMDB_API_KEY = u'35f17ee61909355c4b5d5c4f2c967f6c'
        return TMDB_API_KEY

    @staticmethod
    def getRottonTomatoesApiKey():
        ROTTON_TOMATOES_API_KEY = 'ynyq3vsaps7u8rb9nk98rcru'
        return ROTTON_TOMATOES_API_KEY

    '''
        Get group_delay setting in milliseconds
    '''

    @staticmethod
    def getGroupDelay():
        return int(Constants.ADDON.getSetting(u'group_delay')) * 60

    @staticmethod
    def getTmdbSourceSetting():
        return Constants.ADDON.getSetting("tmdb_source")

    @staticmethod
    def getRatingLimitSetting():
        rating_limit = Constants.ADDON.getSetting(u'rating_limit')
        return rating_limit

    @staticmethod
    def getDoNotRatedSetting():
        do_nr = Constants.ADDON.getSetting(u'do_nr') == u'true'
        return do_nr

    @staticmethod
    def getMaxTopActors():
        return int(Constants.ADDON.getSetting(u'max_top_actors'))

    '''
        Time in seconds to display detailed movie info prior
        to playing a trailer. Default is 5 seconds
    '''

    @staticmethod
    def getTimeToDisplayDetailInfo():
        timeToDisplayDetailInfo = Constants.ADDON.getSetting(
            u'timeToDisplayDetailInfo')
        if timeToDisplayDetailInfo is None or str(timeToDisplayDetailInfo) == u'':
            timeToDisplayDetailInfo = 0

        return int(timeToDisplayDetailInfo)

    @staticmethod
    def getMaxTrailerLength():
        return int(Constants.ADDON.getSetting(u'max_trailer_length'))

    @staticmethod
    def isTraceEnabled():
        return Constants.ADDON.getSetting(u'do_trace') == u'true'

    @staticmethod
    def isTraceStatsEnabled():
        return Constants.ADDON.getSetting(u'do_trace_stats') == u'true'
