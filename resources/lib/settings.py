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
from kodi65.kodiaddon import Addon
from kodi65 import utils
from common.rt_constants import Constants, Movie, RemoteTrailerPreference
from common.logger import Logger

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
    _movieTags = []

    @staticmethod
    def getAddon():
        if Settings._addonSingleton is None:
            Settings._addonSingleton = Addon()
        return Settings._addonSingleton

    @staticmethod
    def getAdjustVolume():
        return xbmcaddon.Addon().getSettingBool(u'do_volume')

    @staticmethod
    def getAllowForeignLanguages():
        allowForeignLanguages = xbmcaddon.Addon().getSettingBool(
            u'allow_foreign_languages')
        return allowForeignLanguages

    @staticmethod
    def getAvgVotePreference():
        voteComparison = xbmcaddon.Addon().getSetting(u'vote_filter')
        voteValue = xbmcaddon.Addon().getSetting(u'vote_value')
        if voteValue < 0 or voteValue > 10:
            xbmc.log(u'Vote filter value must be in range 0..10', xbmc.LOGWARNING)
            voteValue = 6

        return voteComparison, voteValue

    @staticmethod
    def getCloseCurtainPath():
        return xbmc.translatePath(os.path.join(
            Settings.getMediaPath(), u'CurtainClosingSequence.flv')).decode(u'utf-8')

    @staticmethod
    def getDoNotRatedSetting():
        do_nr = xbmcaddon.Addon().getSettingBool(u'do_nr')
        return do_nr

    @staticmethod
    def getFilterGenres():
        if len(sys.argv) == 2:
            return False
        else:
            return xbmcaddon.Addon().getSettingBool(u'do_genre')

    @staticmethod
    def getGenre(genreName):
        try:
            setting = xbmcaddon.Addon().getSettingBool(genreName)
        except Exception as e:
            setting = False
            Logger.logException(e, msg=u'setting: ' + genreName)
        return setting

    @staticmethod
    def getGenreAction():
        return xbmcaddon.Addon().getSettingBool(u'g_action')

    @staticmethod
    def getGenreAdventure():
        return xbmcaddon.Addon().getSettingBool(u'g_adventure')

    @staticmethod
    def getGenrAnimation():
        return xbmcaddon.Addon().getSettingBool(u'g_animation')

    @staticmethod
    def getGenreBiography():
        return xbmcaddon.Addon().getSettingBool(u'g_biography')

    @staticmethod
    def getGenreComedy():
        return xbmcaddon.Addon().getSettingBool(u'g_comedy')

    @staticmethod
    def getGenreCrime():
        return xbmcaddon.Addon().getSettingBool(u'g_crime')

    @staticmethod
    def getGenreDarkComedy():
        return xbmcaddon.Addon().getSettingBool(u'g_black_comedy')

    @staticmethod
    def getGenreDocumentary():
        return xbmcaddon.Addon().getSettingBool(u'g_docu')

    @staticmethod
    def getGenreDrama():
        return xbmcaddon.Addon().getSettingBool(u'g_drama')

    @staticmethod
    def getGenreEpic():
        return xbmcaddon.Addon().getSettingBool(u'g_epic')

    @staticmethod
    def getGenreFamily():
        return xbmcaddon.Addon().getSettingBool(u'g_family')

    @staticmethod
    def getGenreFantasy():
        return xbmcaddon.Addon().getSettingBool(u'g_fantasy')

    @staticmethod
    def getGenreFilmNoir():
        return xbmcaddon.Addon().getSettingBool(u'g_film_noir')

    # A number of non-English trailers are marked foreign
    @staticmethod
    def getGenreForeign():
        return xbmcaddon.Addon().getSettingBool(u'g_foreign')

    @staticmethod
    def getGenreHistory():
        return xbmcaddon.Addon().getSettingBool(u'g_history')

    @staticmethod
    def getGenreHorror():
        return xbmcaddon.Addon().getSettingBool(u'g_horror')

    @staticmethod
    def getGenreMelodrama():
        return xbmcaddon.Addon().getSettingBool(u'g_melodrama')

    @staticmethod
    def getGenreMusic():
        return xbmcaddon.Addon().getSettingBool(u'g_music')

    @staticmethod
    def getGenreMusical():
        return xbmcaddon.Addon().getSettingBool(u'g_musical')

    @staticmethod
    def getGenreMystery():
        return xbmcaddon.Addon().getSettingBool(u'g_mystery')

    @staticmethod
    def getGenrePreCode():
        return xbmcaddon.Addon().getSettingBool(u'g_pre_code')

    @staticmethod
    def getGenreRomance():
        return xbmcaddon.Addon().getSettingBool(u'g_romance')

    @staticmethod
    def getGenreSatire():
        return xbmcaddon.Addon().getSettingBool(u'g_satire')

    @staticmethod
    def getGenreSciFi():
        return xbmcaddon.Addon().getSettingBool(u'g_scifi')

    @staticmethod
    def getGenreScrewBall():
        return xbmcaddon.Addon().getSettingBool(u'g_screwball')

    @staticmethod
    def getGenreSwashBuckler():
        return xbmcaddon.Addon().getSettingBool(u'g_swashbuckler')

    @staticmethod
    def getGenreThriller():
        return xbmcaddon.Addon().getSettingBool(u'g_thriller')

    @staticmethod
    def getGenreTVMovie():
        return xbmcaddon.Addon().getSettingBool(u'g_tv_movie')

    @staticmethod
    def getGenreWar():
        return xbmcaddon.Addon().getSettingBool(u'g_war')

    @staticmethod
    def getGenreWarDocumentary():
        return xbmcaddon.Addon().getSettingBool(u'g_war_documentary')

    @staticmethod
    def getGenreWestern():
        return xbmcaddon.Addon().getSettingBool(u'g_western')

    '''
        Get group_delay setting in milliseconds
    '''

    @staticmethod
    def getGroupDelay():
        return xbmcaddon.Addon().getSettingInt(u'group_delay') * 60

    @staticmethod
    def getHideWatchedMovies():
        return xbmcaddon.Addon().getSettingBool(u'hide_watched')

    @staticmethod
    def getIncludeAdult():
        return xbmcaddon.Addon().getSettingBool(u'include_adult')

    @staticmethod
    def getIncludeClips():
        return xbmcaddon.Addon().getSettingBool(u'do_clips')

    @staticmethod
    def getIncludeFeaturettes():
        return xbmcaddon.Addon().getSettingBool(u'do_featurettes')

    @staticmethod
    def getIncludeItunesTrailers():
        return xbmcaddon.Addon().getSettingBool(u'do_itunes')

    @staticmethod
    def getIncludeItunesTrailerType():
        # "Coming Soon|Just Added|Popular|Exclusive|All"
        # See Constants.iTunes

        trailerType = xbmcaddon.Addon().getSettingInt(u'itunes_trailer_type')
        return trailerType

    @staticmethod
    def getIncludeLibraryNoTrailerInfo():
        return xbmcaddon.Addon().getSettingBool(u'do_library_no_trailer_info')

    @staticmethod
    def getIncludeLibraryTrailers():
        return xbmcaddon.Addon().getSettingBool(u'do_library')

    @staticmethod
    def getIncludeNotYetRatedTrailers():
        return xbmcaddon.Addon().getSettingBool(u'do_notyetrated')

    @staticmethod
    def getIncludeLibraryRemoteTrailers():
        return xbmcaddon.Addon().getSettingBool(u'do_library_remote_trailers')

    @staticmethod
    def getIncludeRemoteTrailers():
        return xbmcaddon.Addon().getSettingBool(u'do_remote_trailers')

    @staticmethod
    def getIncludeTMDBTrailers():
        return xbmcaddon.Addon().getSettingBool(u'do_tmdb')

    @staticmethod
    def getIncludeTrailerFolders():
        return xbmcaddon.Addon().getSettingBool(u'do_folder')

    @staticmethod
    def getLang_iso_639_1():
        iso_639_1_name = xbmc.getLanguage(xbmc.ISO_639_1)
        return iso_639_1_name

    @staticmethod
    def getLang_iso_639_2():
        iso_639_2_name = xbmc.getLanguage(xbmc.ISO_639_2)
        return iso_639_2_name

    @staticmethod
    def getLang_iso_3166_1():
        '''
            We have to 'roll your own' here. Sigh

            TODO: Make a setting. Since this is used (at least part of 
            the time) to determine the certification body (mpaa) then
            should change name. Also, only US is supported.
        '''
        return u'US'

    @staticmethod
    def getMaxTopActors():
        return xbmcaddon.Addon().getSettingInt(u'max_top_actors')

    @staticmethod
    def getMaxTrailerLength():
        return xbmcaddon.Addon().getSettingInt(u'max_trailer_length')

    @staticmethod
    def getMediaPath():
        return xbmc.translatePath(os.path.join(
            Settings.getResourcesPath(), u'media')).decode(u'utf-8')

    @staticmethod
    def getMovieTags():
        return Settings._movieTags

    @staticmethod
    def getMinimumDaysSinceWatched():
        return xbmcaddon.Addon().getSetting(u'watched_days')

    @staticmethod
    def getNumberOfTrailersToPlay():
        return xbmcaddon.Addon().getSettingInt(u'numberOfTrailersToPlay')

    @staticmethod
    def getOpenCurtainPath():
        return xbmc.translatePath(os.path.join(
            Settings.getMediaPath(), u'CurtainOpeningSequence.flv')).decode(u'utf-8')

    @staticmethod
    def promptForSettings():
        return xbmcaddon.Addon().getSettingBool(u'prompt_for_settings')

    @staticmethod
    def getQuality():
        qualityIndex = xbmcaddon.Addon().getSettingInt(u'quality')
        return ["480p", "720p", "1080p"][qualityIndex]

    @staticmethod
    def getRatingLimitSetting():
        rating_limit = xbmcaddon.Addon().getSetting(u'rating_limit')
        return rating_limit

    @staticmethod
    def getRemoteTrailerPreference():

        # RemoteTrailerPreference.NEWEST
        # RemoteTrailerPrefence.OLDEST
        # RemoteTrailerPrefence.HIGHEST_RATED
        # RemoteTrailerPrefence.LOWEST_RATED
        # RemoteTrailerPrefence.MOST_VOTES
        # RemoteTrailerPrefence.LEAST_VOTES
        return RemoteTrailerPreference.LEAST_VOTES

    @staticmethod
    def getTMDBTrailerPreference():
        trailerPreference = Settings.getRemoteTrailerPreference()
        if trailerPreference == RemoteTrailerPreference.NEWEST:
            return u'release_date.desc'
        if trailerPreference == RemoteTrailerPreference.OLDEST:
            return u'release_date.asc'
        if trailerPreference == RemoteTrailerPreference.HIGHEST_RATED:
            return u'vote_average.desc'
        if trailerPreference == RemoteTrailerPreference.LOWEST_RATED:
            return u'vote_average.asc'
        if trailerPreference == RemoteTrailerPreference.MOST_VOTES:
            return u'vote_count.desc'
        if trailerPreference == RemoteTrailerPreference.LEAST_VOTES:
            return u'vote_count.asc'

    @staticmethod
    def getResourcesPath():
        return xbmc.translatePath(
            os.path.join(Constants.ADDON_PATH, u'resources')).decode(u'utf-8')

    @staticmethod
    def getRottonTomatoesApiKey():
        ROTTON_TOMATOES_API_KEY = 'ynyq3vsaps7u8rb9nk98rcru'
        return ROTTON_TOMATOES_API_KEY

    @staticmethod
    def isScreensaverEnabled():
        enableScreensaver = xbmcaddon.Addon().getSettingBool(u'enable_screensaver')
        return enableScreensaver

    @staticmethod
    def getIdleTimeout():
        return xbmcaddon.Addon().getSettingInt(u'screensaver_activate_after_idle')

    @staticmethod
    def getShowCurtains():
        return xbmcaddon.Addon().getSettingBool(u'do_animation')

    @staticmethod
    def getShowTrailerTitle():
        showTitle = xbmcaddon.Addon().getSettingBool(u'show_title')
        return showTitle

    # TODO: Eliminate if this can be avoided in preference to iso-639-1/2.
    #       Kodi does not supply this method, further, unless it is a standard
    #       it is likely not to be universally used by the different services.
    #
    @staticmethod
    def getSpokenLanguage():
        return u'English'

    '''
        Time in seconds to display detailed movie info prior
        to playing a trailer. Default is 5 seconds
    '''

    @staticmethod
    def getTimeToDisplayDetailInfo():
        return xbmcaddon.Addon().getSettingInt(u'timeToDisplayDetailInfo')

    @staticmethod
    def getTmdbApiKey():
        TMDB_API_KEY = u'35f17ee61909355c4b5d5c4f2c967f6c'
        tmdbApiKey = xbmcaddon.Addon().getSetting(u'tmdb_api_key')
        if tmdbApiKey is None or tmdbApiKey == u'':
            tmdbApiKey = TMDB_API_KEY
        return tmdbApiKey

    @staticmethod
    def getTmdbSourceSetting():
        return xbmcaddon.Addon().getSetting("tmdb_source")

    @staticmethod
    def getTrailersPaths():
        return xbmcaddon.Addon().getSetting(u'path')

    @staticmethod
    def getVolume():
        return xbmcaddon.Addon().getSettingInt(u'volume')

    @staticmethod
    def isTraceEnabled():
        return xbmcaddon.Addon().getSetting(u'do_trace') == u'true'

    @staticmethod
    def isTraceStatsEnabled():
        return xbmcaddon.Addon().getSetting(u'do_trace_stats') == u'true'
