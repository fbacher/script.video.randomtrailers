from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from xml.dom.minidom import Node
from multiprocessing.pool import ThreadPool
import datetime
import json
import os
import queue
import random
import re
import requests
import resource
import sys
import threading
import time
import traceback
import urllib.request
import urllib.parse
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xml.dom.minidom
import string

'''
    Rough outline:
        Start separate threads to discover basic information about all selected
        video sources:
            1- library
            2- trailer folders
            3- iTunes
            4- TMDB
            5- (future) IMDB
        Each of the above store the discovered info into separate queues.
        The main function here is to discover the identity of all candidates
        for playing so that a balanced mix of trailers is available for playing
        and random selection. It is important to do this quickly. Additional
        information discovery is performed later, in background threads or
        just before playing the video.

        Immediately after starting the discovery threads, the player
        thread is started. The player thread:
            * Loops playing videos until stopped
            * On each iteration it gets movie a to play from
              TrailerManager's ReadyToPlay queue
            * Listens for events:stop & exit, pause, play, playMovie, showInfo,
              Skip to next trailer, etc.

        TrailerManager holds various queues and lists:
            * Queues for each video source (library, iTunes, etc.) for
                the initial discovery from above
            * Queues for discovering additional information
            * DiscoveredTrailers, a list of all videos after filtering (genre,
                rating, etc). This list grows during initial discovery
            * A small queue (about 5 elements) for each video source so that
                required additional information can be discovered just before
                playing the video. The queues provide enough of a buffer so
                that playing will not be interrupted waiting on discovery
            * The ReadyToPlayQueue which is a small queue containing fully
                discovered trailers and awaiting play. WAs trailers are played
                it is refilled from the small final discovery queues above


'''


class Constants:
    TOO_MANY_TMDB_REQUESTS = 25
    addonName = u'script.video.randomtrailers'
    ADDON = None
    ADDON_PATH = None
    TRAILER_INFO_DISPLAY_SECONDS = 6000
    SECONDS_BEFORE_RESHUFFLE = 1 * 60
    PLAY_LIST_LOOKBACK_WINDOW_SIZE = 10

    @staticmethod
    def staticInit():
        Constants.ADDON = xbmcaddon.Addon()  # Constants.addonName)
        Constants.ADDON_PATH = Constants.ADDON.getAddonInfo(
            u'path').decode(u'utf-8')

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
    MOVIE_TITLE = u'title'
    MOVIE_TRAILER = u'trailer'
    MOVIE_YEAR_KEY = u'year'
    MOVIE_LAST_PLAYED = u'lastplayed'
    MOVIE_MPAA = u'mpaa'
    MOVIE_FANART = u'fanart'
    MOVIE_THUMBNAIL = u'thumbnail'
    MOVIE_FILE = u'file'
    MOVIE_YEAR = u'year'
    MOVIE_WRITER = u'writer'
    MOVIE_DIRECTOR = u'director'
    MOVIE_CAST = u'cast'
    MOVIE_PLOT = u'plot'
    MOVIE_GENRE = u'genre'
    MOVIE_STUDIO = u'studio'
    MOVIE_MOVIEID = u'movieid'
    MOVIE_LABEL = u'label'
    MOVIE_RUNTIME = u'runtime'

    # From iTunes
    # From Tmdb
    MOVIE_ADULT = u'adult'

    MOVIE_RELEASE_DATE = u'releasedate'
    MOVIE_POSTER = u'poster'
    MOVIE_POSTER_2X = u'poster_2x'
    MOVIE_LOCATION = u'location'
    MOVIE_RATING = u'rating'
    MOVIE_ACTORS = u'actors'

    # Properties invented by this plugin:

    # TODO- question the purpose of this
    ITUNES_TRAILER_TYPE = u'trailerType'
    # TODO rename to trailerSource
    MOVIE_SOURCE = u'source'

    # Source Values:
    MOVIE_FOLDER_SOURCE = u'folder'
    MOVIE_LIBRARY_SOURCE = u'library'
    MOVIE_ITUNES_SOURCE = u'iTunes'
    MOVIE_TMDB_SOURCE = u'tmdb'

    TRAILER_DISCOVERY_STATE = u'trailerDiscoveryState'
    MOVIE_NOT_FULLY_DISCOVERED = u'notFullyDiscovered'
    MOVIE_TRAILER_DISCOVERY_IN_PROGRESS = u'discoveryInProgress'
    TRAILER_DISCOVERY_COMPLETE = u'discoveryComplete'
    MOVIE_TRAILER_PLAYED_KEY = u'trailerPlayed'
    MOVIE_TRAILER_PLAY_ORDER_KEY = u'trailerPlayOrder'

    tmdbRequestCount = 0  # Limit is tmdbRequestLmit every 10 seconds

    # Reported in header from every request response to tmdb
    tmdbRemainingRequests = 0  # header.get(u'X-RateLimit-Remaining')
    tmdbRequestLmit = 0  # header.get('X-RateLimit-Limit')  # Was 40

    # Limit will be lifted at this time, in epoch seconds

    tmdbRequestLimitResetTime = 0  # header.get('X-RateLimit-Reset')

# ##################
#
# End Class Constants
#
# ###################


#
# Initialization
#
Constants.staticInit()
memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
xbmc.log(u'In randomtrailer init memory: ' + str(memory), xbmc.LOGNOTICE)


currentVolume = xbmc.getInfoLabel(u'Player.Volume')
currentVolume = int(
    (float(currentVolume.split(u' ')[0]) + 60.0) / 60.0 * 100.0)

selectedGenre = ''
exit_requested = False
movie_file = ''
opener = urllib.request.build_opener()
opener.addheaders = [('User-Agent', 'iTunes')]
APPLE_URL_PREFIX = "http://trailers.apple.com"
monitor = None

trailer = ''
info = ''
played = []


class Utils:
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _monitor = None
    _exitRequested = False
    _abortRequested = False

    @staticmethod
    def getMonitor():
        if (Utils._monitor is None):
            Utils._monitor = xbmc.Monitor()
        return Utils._monitor

    @staticmethod
    def getJSON(url, forcedTMDBSleep=False):
        talkingToTMDB = False
        if u'themoviedb' in url:
            talkingToTMDB = True

            # Some TMDB api calls do NOT give RATE-LIMIT info in header responses
            # In such cases we detect the failure from the status code and retry
            # with a forced sleep of 10 seconds, which is the maximum required
            # wait time.
            if forcedTMDBSleep:
                xbmc.sleep(10000)

            secondsUntilReset = Constants.tmdbRequestLimitResetTime - \
                int(time.time())
            if (Constants.tmdbRemainingRequests < 10) and (secondsUntilReset < 2):
                Debug.myLog(
                    u'Sleeping two seconds to avoid TMBD traffic limit.', xbmc.LOGINFO)
                xbmc.sleep(2000)

            Constants.tmdbRequestCount += 1

        request = requests.get(url)
        statusCode = request.status_code
        jsonText = request.json()
        header = request.headers
        # Debug.myLog(u'headers: ' + str(header), xbmc.LOGDEBUG)

        # TODO- delete or control by setting or logger

        if talkingToTMDB:
            tmp = header.get(u'X-RateLimit-Remaining')
            if tmp is not None:
                Constants.tmdbRemainingRequests = int(tmp)
                # Debug.myLog('Requests: ' +
                # str(Constants.tmdbRemainingRequests), xbmc.LOGDEBUG)

            tmp = header.get('X-RateLimit-Limit')
            if tmp is not None:
                Constants.tmdbRequestLmit = int(tmp)
                # Debug.myLog('Limit: ' + str(Constants.tmdbRequestLmit),
                #            xbmc.LOGDEBUG)

            # Limit will be lifted at this time, in epoch seconds
            tmp = header.get('X-RateLimit-Reset')
            if tmp is not None:
                Constants.tmdbRequestLimitResetTime = int(tmp)
                # Debug.myLog(
                #    'Reset: ' + str(Constants.tmdbRequestLimitResetTime), xbmc.LOGDEBUG)
            else:
                # Some calls don't return X-RateLimit-Reset, in those cases there
                # should be Retry-After indicating how many more seconds to wait
                # before traffic can resume

                retryAfterValue = 0
                tmp = header.get(u'Retry-After')
                msg = u''
                if tmp is not None:
                    retryAfterValue = int(tmp)
                    Constants.tmdbRequestLimitResetTime = int(
                        time.time()) + retryAfterValue
                    msg = u'Retry-After ' + str(retryAfterValue) + ' present.'

                Debug.myLog(
                    u'TMDB response header missing X-RateLimit info.' + msg, xbmc.LOGDEBUG)

        try:
            status = jsonText.get(u'status_code')
            if status is not None:
                statusCode = status

            #Debug.myLog(u'StatusCode from jsonText: ' + str(status), xbmc.LOGINFO)
        except Exception as e:
            pass

        Debug.myLog(u'getJSON jsonText: ' + jsonText.__class__.__name__ +
                    u' ' + json.dumps(jsonText), xbmc.LOGDEBUG)

        if statusCode == Constants.TOO_MANY_TMDB_REQUESTS:  # Too many requests,
            Debug.myLog(u'Request rate to TMDB exceeds limits ('
                        + str(Constants.tmdbRequestLmit) +
                        u' every 10 seconds). Consider getting API Key. This session\'s requests: '
                        + str(Constants.tmdbRequestCount), xbmc.LOGINFO)
            #
            # Retry only once
            #
            if not forcedTMDBSleep:
                statusCode, jsonText = Utils.getJSON(url, forcedTMDBSleep=True)
        # else:
        #    Debug.myLog(u'requests: ' + str(Constants.tmdbRequestCount))
        return statusCode, jsonText

    @staticmethod
    def getKodiJSON(query):
        jsonText = xbmc.executeJSONRPC(query)
        jsonText = json.loads(jsonText, encoding=u'utf-8')
        return jsonText

    @staticmethod
    def isAbortRequested():
        if Utils._abortRequested:
            return Utils._abortRequested
        elif Utils.getMonitor().abortRequested():
            Utils._abortRequested = True
            Debug.myLog(u'Abort requested by Kodi', xbmc.LOGINFO)
            return True

    @staticmethod
    def isShutdownRequested():
        if Utils.isAbortRequested():
            return True
        elif Utils._exitRequested:
            return True

    @staticmethod
    def setExitRequested():
        Utils._exitRequested = True
        Debug.myLog(u'Exit Requested', xbmc.LOGINFO)

    @staticmethod
    def throwExceptionIfAbortRequested():
        if Utils.getMonitor().abortRequested():
            raise AbortException()

    @staticmethod
    def throwExceptionIfShutdownRequested():
        if Utils.isShutdownRequested():
            raise AbortException()


class AbortException(Exception):
    pass


class WatchDog(threading.Thread):
    _threadsToWatch = []

    @staticmethod
    def registerThread(thread):
        WatchDog._threadsToWatch.append(thread)

    def __init__(self):
        threadName = Constants.ADDON_PATH + u'.WatchDog'
        super(WatchDog, self).__init__(group=None, target=None,
                                       name=threadName,
                                       args=(), kwargs=None, verbose=None)

    def run(self):
        while not Utils.isShutdownRequested():
            xbmc.sleep(3000)  # Wait 3 seconds

        for thread in WatchDog._threadsToWatch:
            thread.stop()

        finished = False
        delay = 0.10
        attempt = 0
        while not finished:
            attempt += 1
            finished = True
            for thread in WatchDog._threadsToWatch:
                if thread.isAlive():
                    thread.join(delay)
                if thread.isAlive():
                    finished = False

            if attempt == 5:
                delay = 0.5


class Settings:

    #@staticmethod
    # def getAddonPath():
    #    return unicode(Constants.ADDON.getAddonInfo('path'))

    @staticmethod
    def getShowInfoDetail():
        return Constants.ADDON.getSetting('hide_info') != u'true'

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
        return Constants.ADDON.getSetting('do_animation') == u'true'

    # do_genre
    @staticmethod
    def getFilterGenres():
        if len(sys.argv) == 2:
            return False
        else:
            return Constants.ADDON.getSetting('do_genre') == u'true'

    @staticmethod
    def getAdjustVolume():
        if Settings.getVolume() > 100:
            return False
        else:
            return Constants.ADDON.getSetting('do_volume') == u'true'

    @staticmethod
    def getVolume():
        return int(Constants.ADDON.getSetting(u'volume'))

    @staticmethod
    def getIncludeLibraryTrailers():
        Debug.myLog(
            'do_library:' + str(Constants.ADDON.getSetting(u'do_library')), xbmc.LOGDEBUG)
        return Constants.ADDON.getSetting(u'do_library') == u'true'

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
        return Constants.ADDON.getSetting('do_clips') == u'true'

    @staticmethod
    def getIncludeFeaturettes():
        return Constants.ADDON.getSetting('do_featurettes') == u'true'

    @staticmethod
    def getQuality():
        qualityIndex = int(Constants.ADDON.getSetting(u'quality'))
        return ["480p", "720p", "1080p"][qualityIndex]

    @staticmethod
    def getIncludeAdult():
        return False

    @staticmethod
    def getIncludeItunesTrailerType():
        return int(Constants.ADDON.getSetting(u'trailer_type'))

    @staticmethod
    def getHideTrailerTitle():
        return Constants.ADDON.getSetting(u'hide_title') != u'true'

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
        return Constants.ADDON.getSetting('path')

    @staticmethod
    def getGenreAction():
        return Constants.ADDON.getSetting('g_action') == u'true'

    @staticmethod
    def getGenreComedy():
        return Constants.ADDON.getSetting('g_comedy') == u'true'

    @staticmethod
    def getGenreDocumentary():
        return Constants.ADDON.getSetting('g_docu') == u'true'

    @staticmethod
    def getGenreDrama():
        return Constants.ADDON.getSetting('g_drama') == u'true'

    @staticmethod
    def getGenreFamily():
        return Constants.ADDON.getSetting('g_family') == u'true'

    @staticmethod
    def getGenreFantasy():
        return Constants.ADDON.getSetting('g_fantasy') == u'true'

    @staticmethod
    def getGenreForeign():
        return Constants.ADDON.getSetting('g_foreign') == u'true'

    @staticmethod
    def getGenreHorror():
        return Constants.ADDON.getSetting('g_horror') == u'true'

    @staticmethod
    def getGenreMusical():
        return Constants.ADDON.getSetting('g_musical') == u'true'

    @staticmethod
    def getGenreRomance():
        return Constants.ADDON.getSetting('g_romance') == u'true'

    @staticmethod
    def getGenreSciFi():
        return Constants.ADDON.getSetting('g_scifi') == u'true'

    @staticmethod
    def getGenreThriller():
        return Constants.ADDON.getSetting('g_thriller') == u'true'

    @staticmethod
    def getTmdbApiKey():
        TMDB_API_KEY = u'99e8b7beac187a857152f57d67495cf4'
        TMDB_API_KEY = u'35f17ee61909355c4b5d5c4f2c967f6c'
        return TMDB_API_KEY

    @staticmethod
    def getRottonTomatoesApiKey():
        ROTTON_TOMATOES_API_KEY = u'99dgtphe3c29y85m2g8dmdmt'
        return ROTTON_TOMATOES_API_KEY

    '''
        Get group_delay setting in milliseconds
    '''

    @staticmethod
    def getGroupDelay():
        return int(Constants.ADDON.getSetting('group_delay')) * 60 * 1000

    @staticmethod
    def getTmdbSourceSetting():
        return Constants.ADDON.getSetting("tmdb_source")

    @staticmethod
    def getRatingLimitSetting():
        rating_limit = Constants.ADDON.getSetting('rating_limit')
        return rating_limit

    @staticmethod
    def getDoNotRatedSetting():
        do_nr = Constants.ADDON.getSetting('do_nr') == u'true'
        return do_nr


class Genre:

    GENRE_ACTION = u'Action and Adventure'
    GENRE_COMEDY = u'Comedy'
    GENRE_DOCUMENTARY = u'Documentary'
    GENRE_DRAMA = u'Drama'
    GENRE_FAMILY = u'Family'
    GENRE_FANTASY = u'Fantasy'
    GENRE_FOREIGN = u'Foreign'
    GENRE_HORROR = u'Horror'
    GENRE_MUSICAL = u'Musical'
    GENRE_ROMANCE = u'Romance'
    GENRE_SCIFI = u'Science Fiction'
    GENRE_THRILLER = u'Thriller'

    ALLOWED_GENRES = None

    def __init__(self, genreSetting, genreMPAALabel):
        self.genreSetting = genreSetting
        self.genreMPAALabel = genreMPAALabel

    @classmethod
    def _initClass(cls):
        Genre.ALLOWED_GENRES = (Genre(Settings.getGenreAction(), Genre.GENRE_ACTION),
                                Genre(Settings.getGenreComedy(),
                                      Genre.GENRE_COMEDY),
                                Genre(Settings.getGenreDocumentary(),
                                      Genre.GENRE_DOCUMENTARY),
                                Genre(Settings.getGenreDrama(),
                                      Genre.GENRE_DRAMA),
                                Genre(Settings.getGenreFamily(),
                                      Genre.GENRE_FAMILY),
                                Genre(Settings.getGenreFantasy(),
                                      Genre.GENRE_FANTASY),
                                Genre(Settings.getGenreForeign(),
                                      Genre.GENRE_FOREIGN),
                                Genre(Settings.getGenreHorror(),
                                      Genre.GENRE_HORROR),
                                Genre(Settings.getGenreMusical(),
                                      Genre.GENRE_MUSICAL),
                                Genre(Settings.getGenreRomance(),
                                      Genre.GENRE_ROMANCE),
                                Genre(Settings.getGenreSciFi(),
                                      Genre.GENRE_SCIFI),
                                Genre(Settings.getGenreThriller(), Genre.GENRE_THRILLER))

    @classmethod
    def getAllowedMPAALabels(cls):
        labels = []
        for genre in Genre.ALLOWED_GENRES:
            labels.append(genre.genreMPAALabel)

        return labels


Genre._initClass()


class Rating:

    RATING_G = u'G'
    RATING_PG = u'PG'
    RATING_PG_13 = u'PG-13'
    RATING_R = u'R'
    RATING_NC_17 = u'NC-17'
    RATING_NR = u'NR'

    def __init__(self, pattern, mpaaRatingLabel):
        self._pattern = pattern
        self._mpaaRatingLabel = mpaaRatingLabel

    @classmethod
    def _initClass(cls):

        Rating.ALLOWED_RATINGS = (

            # General Audience
            Rating(re.compile(u'^A$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Approved$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Rating Approved$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated Approved$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Passed$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Rated Passed$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^P$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^G$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^G .*$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated G.*$'), Rating.RATING_G),
            Rating(re.compile(u'^TV-G.*$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated TV-G.*$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated$'), Rating.RATING_G),  # Hays

            # For young teens

            Rating(re.compile(u'^PG$'), Rating.RATING_PG),
            Rating(re.compile(u'^PG .*$'), Rating.RATING_PG),  # PG with comment
            Rating(re.compile(u'^Rated PG.*$'), Rating.RATING_PG),
            Rating(re.compile(u'^TV-PG.*$'), Rating.RATING_PG),
            Rating(re.compile(u'^Rated TV-PG.*$'), Rating.RATING_PG),

            # For older teens, more mature

            Rating(re.compile(u'^M$'), Rating.RATING_PG_13),  # Early MPAA
            Rating(re.compile(u'^GP$'), Rating.RATING_PG_13),  # Replaced M
            Rating(re.compile(u'^PG-13$'), Rating.RATING_PG_13),  # Replaced M
            # PG-13 with comment
            Rating(re.compile(u'^PG-13 .*$'), Rating.RATING_PG_13),
            Rating(re.compile(u'^Rated PG-13.*$'), Rating.RATING_PG_13),
            # Restricted
            Rating(re.compile(u'^R$'), Rating.RATING_R),
            Rating(re.compile(u'^R .*$'), Rating.RATING_R),  # R with comment
            Rating(re.compile(u'^Rated R.*$'),
                   Rating.RATING_R),  # R with comment
            # Adult
            Rating(re.compile(u'^NC17.*$'), Rating.RATING_NC_17),
            Rating(re.compile(u'^Rated NC17.*$'), Rating.RATING_NC_17),
            Rating(re.compile(u'^X.*$'), Rating.RATING_NC_17),

            Rating(re.compile(u'^NR$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated NR$'), Rating.RATING_NR),
            Rating(re.compile(u'^Not Rated$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated Not Rated$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated UR$'), Rating.RATING_NR),
            Rating(re.compile(u'^Unrated$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated Unrated$'), Rating.RATING_NR)
        )

    @classmethod
    def getMPAArating(cls, mpaaRating=None, adultRating=None):

        rating = cls.RATING_NR
        if adultRating is not None:
            if adultRating:
                rating = cls.RATING_NC_17

        xbmc.log(u'In randomtrailers.getMPAArating rating: ' +
                 mpaaRating + u' adult: ' + str(adultRating), xbmc.LOGNOTICE)

        foundRating = False
        for ratingPattern in Rating.ALLOWED_RATINGS:
            if ratingPattern._pattern.match(ratingPattern._mpaaRatingLabel):
                foundRating = True
                rating = ratingPattern._mpaaRatingLabel
                break

        if not foundRating:
            Debug.myLog(u'mpaa rating not found for: ' +
                        mpaaRating + u' assuming Not Rated', xbmc.LOGDEBUG)

        return rating

    @classmethod
    def getImageForRating(cls, rating):
        if rating == Rating.RATING_G:
            imgRating = 'ratings/g.png'
        elif rating == Rating.RATING_PG:
            imgRating = 'ratings/pg.png'

        elif rating == Rating.RATING_PG_13:
            imgRating = 'ratings/pg13.png'

        elif rating == Rating.RATING_R:
            imgRating = 'ratings/r.png'

        elif rating == Rating.RATING_NC_17:
            imgRating = 'ratings/nc17.png'

        elif rating == Rating.RATING_NR:
            imgRating = 'ratings/notrated.png'
        return imgRating


Rating._initClass()


class Debug:

    @staticmethod
    def myLog(*args):
        text = str('')
        for p in args[0:len(args) - 1]:
            if p is None:
                newP = str('None')
            elif isinstance(p, unicode):
                newP = p.encode('utf-8')
            elif isinstance(p, list):
                newP = str(p)
            elif isinstance(p, dict):
                newP = str(p)
            elif isinstance(p, bool):
                newP = str(p)
            elif isinstance(p, int):
                newP = str(p)
            else:
                newP = p

            xbmc.log(newP, args[len(args) - 1])

    @staticmethod
    def logException():
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)

    @staticmethod
    def dumpDictionaryKeys(d):
        for k, v in d.items():
            if isinstance(v, dict):
                Debug.dumpDictionaryKeys(v)
            else:
                xbmc.log('{0} : {1}'.format(k, v), xbmc.LOGDEBUG)

    @staticmethod
    def dumpStack(msg=u''):
        traceBack = traceback.format_stack(limit=3)
        Debug.myLog(msg, xbmc.LOGERROR)
        for line in traceBack:
            Debug.myLog(line, xbmc.LOGERROR)

    @staticmethod
    def dumpAPI():
        x = xbmc.executeJSONRPC(
            '{ "jsonrpc": "2.0", "method": "JSONRPC.Introspect", "params": { "filter": { "id": "VideoLibrary.GetMovies", "type": "method" } }, "id": 1 }')
        x = json.loads(x, encoding=u'utf-8')
        Debug.myLog('introspection: ', x, xbmc.LOGDEBUG)

    @staticmethod
    def compareMovies(trailer, newTrailer):
        for key in trailer:
            if newTrailer.get(key) is None:
                Debug.myLog(u'CompareMovies- key: ' + str(key) + u' is missing from new. Value: '
                            + str(trailer.get(key)), xbmc.LOGINFO)

            if trailer.get(key) != newTrailer.get(key):
                Debug.myLog(u'Values for: ' + str(key) + u' different: ' + str(trailer.get(key))
                            + u' new: ' + str(newTrailer.get(key)), xbmc.LOGINFO)

        for key in newTrailer:
            if trailer.get(key) is None:
                Debug.myLog(u'CompareMovies- key: ' + str(key) + u' is missing from old. Value: '
                            + str(newTrailer.get(key)), xbmc.LOGINFO)

    @staticmethod
    def validateBasicMovieProperties(movie):
        basicProperties = (
            Constants.ITUNES_TRAILER_TYPE,
            Constants.MOVIE_FANART,
            Constants.MOVIE_THUMBNAIL,
            Constants.MOVIE_TRAILER,
            Constants.MOVIE_SOURCE,
            Constants.MOVIE_FILE,
            Constants.MOVIE_YEAR,
            Constants.MOVIE_TITLE)

        for propertyName in basicProperties:
            if movie.get(propertyName) is None:
                Debug.dumpStack(u'Missing basicProperty: ' + propertyName)
                movie.setdefault(propertyName, u'default_' + propertyName)

    @staticmethod
    def validateDetailedMovieProperties(movie):

        detailsProperties = (Constants.MOVIE_WRITER,
                             Constants.MOVIE_DIRECTORS,
                             Constants.MOVIE_CAST,
                             Constants.MOVIE_PLOT,
                             Constants.MOVIE_GENRE,
                             Constants.MOVIE_STUDIO,
                             Constants.MOVIE_RUNTIME,
                             # Constants.MOVIE_ADULT,
                             Constants.MOVIE_MPAA)

        Debug.validateBasicMovieProperties(movie)
        for propertyName in detailsProperties:
            if movie.get(propertyName) is None:
                Debug.dumpStack(u'Missing detailsProperty: ' + propertyName)
                movie.setdefault(propertyName, u'default_' + propertyName)


class BaseTrailerManager(threading.Thread):
    _trailerManagers = []
    _discoveredTrailers = []
    _discoveredTrailersQueue = queue.Queue(maxsize=0)
    _discoveredTrailersQueueLock = threading.Condition()
    _trailersToFetchQueueLock = threading.Condition()
    _trailersToFetchQueue = queue.Queue(maxsize=5)
    _singletonInstance = None
    _readyToPlayQueue = queue.Queue(maxsize=3)

    '''    
        Instance variables
    
        _discoveryComplete = False
        _trailerFetcher
    '''

    _blockUntilTrailersPresent = threading.Condition()

    _iterator = None

    @staticmethod
    def getInstance():
        if BaseTrailerManager._singletonInstance is None:
            singleton = BaseTrailerManager()
            BaseTrailerManager._singletonInstance = singleton
            singleton._trailerManagers = []

        return BaseTrailerManager._singletonInstance

    @staticmethod
    def stop():
        pass
        # for manager in BaseTrailerManager._singletonInstance.getManagers():
        #    for fetcher in manager.trailerFetcher:
        #        for fetcherThread in fetcher._trailerFetchers:
        #            fetcherThread.stop()

    def joinAll(self):
        for manager in self._trailerManagers:
            if manager.isAlive(1.0):
                manager.join()

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, verbose=None):
        Debug.myLog(self.__class__.__name__ + '.__init__', xbmc.LOGDEBUG)
        Debug.dumpStack()
        if name is None or name == u'':
            name = Constants.ADDON_PATH + u'.BaseTrailerManager'
        super(BaseTrailerManager, self).__init__(group, target, name,
                                                 args, kwargs, verbose)

        Debug.myLog(self.__class__.__name__ +
                    u' set _discoveryComplete = False', xbmc.LOGDEBUG)
        WatchDog.registerThread(self)
        self._discoveryComplete = False
        self._trailersAvailable = threading.Event()

    def discoverBasicInformation(self, genre):
        pass

    def getManagers(self):
        return self._trailerManagers

    def addManager(self, manager):
        self._trailerManagers.append(manager)

    def setGenre(self, genre):
        self.genre = genre

    def finishedDiscovery(self):
        Debug.myLog(self.__class__.__name__ +
                    u' finishedDiscovery.', xbmc.LOGDEBUG)
        with self._lock:
            self.shuffleDiscoveredTrailers(markUnplayed=False)
            self._discoveryComplete = True

    # DEAD CODE
    def isDiscoveryComplete(self):
        complete = True
        Debug.myLog('# Managers: ' + len(self.getManagers()), xbmc.LOGDEBUG)
        for index in xrange(len(self.getManagers()) - 1, -1, -1):
            trailerManager = self.getManagers[index]
            if trailerManager.isAlive():
                complete = False
            else:
                trailerManager.join()

        return complete

    def addToDiscoveredTrailers(self, movie):
        METHOD_NAME = self.__class__.__name__ + u'.addToDiscoveredTrailers'
        Debug.myLog(METHOD_NAME + u': ' +
                    movie.get(Constants.MOVIE_TITLE), xbmc.LOGDEBUG)

        # Assume more discovery is required for movie details, etc.

        movie[Constants.MOVIE_TRAILER_PLAYED_KEY] = False
        movie[Constants.TRAILER_DISCOVERY_STATE] = Constants.MOVIE_NOT_FULLY_DISCOVERED

        with self._lock:
            self._discoveredTrailers.append(movie)
            secondsSinceLastShuffle = (
                datetime.datetime.utcnow() - self._lastShuffleTime).total_seconds()
            Debug.myLog('seconds: ' + str(secondsSinceLastShuffle) + ' lastShuffle: ' +
                        str(self._lastShuffleTime),
                        xbmc.LOGDEBUG)
            if self._lastShuffledIndex < ((len(self._discoveredTrailers) * 0.10)
                                          or secondsSinceLastShuffle > Constants.SECONDS_BEFORE_RESHUFFLE):
                self.shuffleDiscoveredTrailers(markUnplayed=False)
            self._lock.notify()

        Debug.myLog(METHOD_NAME + u' Added movie to _discoveredTrailers: '
                    + movie.get(Constants.MOVIE_TITLE) + u' length: '
                    + str(len(self._discoveredTrailers)), xbmc.LOGDEBUG)

    def shuffleDiscoveredTrailers(self, markUnplayed=False):
        METHOD_NAME = self.__class__.__name__ + u'.shuffleDiscoveredTrailers'
        Debug.myLog(METHOD_NAME, xbmc.LOGDEBUG)
        with self._lock:
            # Shuffle a shallow copy and then put that copy
            # into the._discoveredTrailersQueue
            shuffledTrailers = self._discoveredTrailers[:]
            Debug.myLog('ShuffledTrailers: ' +
                        str(len(shuffledTrailers)), xbmc.LOGDEBUG)

            Utils.RandomGenerator.shuffle(shuffledTrailers)
            if markUnplayed:
                for trailer in self._discoveredTrailers:
                    trailer[Constants.MOVIE_TRAILER_PLAYED_KEY] = False

            self._lastShuffledIndex = len(self._discoveredTrailers) - 1
            Debug.myLog('lastShuffledIndex: ' + str(self._lastShuffledIndex),
                        xbmc.LOGDEBUG)

            # Drain anything previously in queue
            try:
                while True:
                    self._discoveredTrailersQueue.get(block=False)
            except queue.Empty:
                pass

            Debug.myLog('reloading._discoveredTrailersQueue', xbmc.LOGDEBUG)
            for trailer in shuffledTrailers:
                if not trailer[Constants.MOVIE_TRAILER_PLAYED_KEY]:
                    self._discoveredTrailersQueue.put(trailer)
            Debug.myLog(
                'discoverdTrailerQueue length: ' +
                str(self._discoveredTrailersQueue.qsize()) +
                u'_discoveredTrailers length: '
                + str(len(self._discoveredTrailers)),
                xbmc.LOGDEBUG)

    def addToReadyToPlayQueue(self, movie):
        Debug.myLog(self.__class__.__name__ + u'.addToReadyToPlayQueue: ' +
                    movie[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)
        self._readyToPlayQueue.put(movie)
        if not BaseTrailerManager.getInstance()._trailersAvailable.isSet():
            BaseTrailerManager.getInstance()._trailersAvailable.set()

        Debug.myLog(u'_readyToPlayQueue size: ' + str(BaseTrailerManager._readyToPlayQueue.qsize()),
                    xbmc.LOGDEBUG)
        return

    def getNumberOfTrailers(self):
        return len(self._discoveredTrailers)

    def iter(self):
        return self.__iter__()

    def __iter__(self):
        Debug.myLog('BaseTrailerManager.__iter__', xbmc.LOGDEBUG)

        return self

    def next(self):
        return self.__next__()

    def __next__(self):

        Debug.myLog(u'BaseTrailerManager.next trailersAvail: ' +
                    str(BaseTrailerManager.getInstance()._trailersAvailable.isSet()), xbmc.LOGDEBUG)
        if not BaseTrailerManager.getInstance()._trailersAvailable.isSet():
            BaseTrailerManager.getInstance()._trailersAvailable.wait()

        Debug.myLog(
            'BaseTrailerManager.next after trailersAvail wait', xbmc.LOGDEBUG)
        totalNumberOfTrailers = 0

        # Considered locking all TrailerManagers here to guarantee
        # that lengths don't change while finding the right trailer
        # but that might block the readyToPlayQueue from getting
        # loaded. Besides, it doesn't matter too much if we play
        # the incorrect trailer, as long as we get one. The
        # major fear is if we have no trailers at all, but that
        # will be handled elsewhere.

        managers = BaseTrailerManager._singletonInstance.getManagers()
        for manager in managers:
            Debug.myLog('Manager: ' + manager.__class__.__name__ + ' size: '
                        + str(manager.getNumberOfTrailers()), xbmc.LOGDEBUG)
            totalNumberOfTrailers += manager.getNumberOfTrailers()

        Debug.myLog('BaseTrailerManager.next numTrailers: ' +
                    str(totalNumberOfTrailers), xbmc.LOGDEBUG)

        trailer = None
        attempts = 0
        while trailer is None and attempts < 10:
            trailerIndexToPlay = Utils.RandomGenerator.randint(
                0, totalNumberOfTrailers - 1)

            totalNumberOfTrailers = 0
            foundManager = None
            for manager in managers:
                Debug.myLog('Manager: ' + manager.__class__.__name__ + ' size: '
                            + str(manager.getNumberOfTrailers()), xbmc.LOGDEBUG)
                totalNumberOfTrailers += manager.getNumberOfTrailers()
                if trailerIndexToPlay < totalNumberOfTrailers:
                    foundManager = manager
                    break

            try:
                attempts += 1
                Debug.myLog(u'BaseTrailerManager.next Attempt: ' + str(attempts)
                            + u' manager: ' + str(foundManager), xbmc.LOGDEBUG)
                trailer = foundManager._readyToPlayQueue.get(
                    block=False, timeout=0.25)
            except queue.Empty:
                trailer = None

        title = 'No Trailer found before timeout'
        if trailer is not None:
            title = trailer[Constants.MOVIE_TITLE]
        Debug.myLog(u'BaseTrailerManager.next trailer: ' +
                    title, xbmc.LOGDEBUG)
        return trailer

    '''
        When a trailer can not be found for a movie, then we need to remove it
        so that we don't keep looking for it.
    '''

    def removeDiscoveredTrailer(self, trailer):
        METHOD_NAME = self.__class__.__name__ + u'.removeDiscoveredTrailer'
        Debug.myLog(METHOD_NAME + u' : ',
                    trailer.get(Constants.MOVIE_TITLE), xbmc.LOGDEBUG)
        with self._lock:
            self._discoveredTrailers.remove(trailer)
            self._lock.notify()

    '''
        Load the _trailersToFetchQueue from._discoveredTrailersQueue.
        
            If _trailersToFetchQueue is full, then return
            
            If discoveryComplete and _discoveredTrailers is empty, 
            then return
            
            If discoveryComplete and._discoveredTrailersQueue is empty,
            then shuffleDiscoveredTrailers and fill the _trailersToFetchQueue
            from it. If there are not enough items to fill the fetch queue, 
            then get as many as are available.
            
            Otherwise, discoveryComplete == False:
            
            If._discoveredTrailersQueue is empty and _trailersToFetchQueue
            is not empty, then return without loading any.
            
            If._discoveredTrailersQueue is empty and _trailersToFetchQueue is empty
            then block until an item becomes available or discoveryComplete == True.
            
            Finally, _trailersToFetchQueue is not full, fill it from any available
            items from._discoveredTrailersQueue.
 
    '''

    _firstLoad = True

    def loadFetchQueue(self):
        METHOD_NAME = self.__class__.__name__ + u'loadFetchQueue'
        if BaseTrailerManager._firstLoad:
            time.sleep(2)
            BaseTrailerManager._firstLoad = False

        with self._trailersToFetchQueueLock:
            Debug.myLog(
                METHOD_NAME + u' Got _trailersToFetchQueueLock', xbmc.LOGDEBUG)
            finished = False
            attempts = 0
            while not finished:
                attempts += 1
                block = False
                shuffle = False
                try:
                    Debug.myLog(METHOD_NAME + u' Attempt: ' +
                                str(attempts), xbmc.LOGDEBUG)
                    if self._trailersToFetchQueue.full():
                        Debug.myLog(METHOD_NAME + u' _trailersToFetchQueue full',
                                    xbmc.LOGDEBUG)
                        finished = True
                    elif self._discoveryComplete and len(self._discoveredTrailers) == 0:
                        Debug.myLog(METHOD_NAME +
                                    u' Discovery Complete and nothing found.', xbmc.LOGDEBUG)
                        finished = True
                    elif self._discoveryComplete and self._discoveredTrailersQueue.empty():
                        Debug.myLog(METHOD_NAME +
                                    u'_ discoveryComplete,._discoveredTrailersQueue empty',
                                    xbmc.LOGDEBUG)
                        shuffle = True
                    elif (self._discoveredTrailersQueue.empty()
                          and not self._trailersToFetchQueue.empty):
                        Debug.myLog(
                            METHOD_NAME + u' Discovery incomplete._discoveredTrailersQueue ' +
                            u'empty and _trailersToFetchQueue not empty', xbmc.LOGDEBUG)
                        finished = True
                    elif self._trailersToFetchQueue.empty():
                        # Discovery incomplete, fetch queue is empty
                        # wait until we get an item, or discovery complete

                        Debug.myLog(METHOD_NAME + u' Discovery incomplete, ' +
                                    u'_trailersToFetchQueue empty, will wait', xbmc.LOGDEBUG)
                        block = True
                        trailer = self._discoveredTrailersQueue.get(
                            timeout=0.5)
                        block = False
                        self._trailersToFetchQueue.put(trailer)

                    else:
                        # Fetch queue is not empty, nor full. Discovery
                        # is not complete. Get something from _discoveredTrailerQueue
                        # if available

                        trailer = self._discoveredTrailersQueue.get(
                            block=False)
                        Debug.myLog(
                            'Got from _discoverdTrailerQueue', xbmc.LOGINFO)
                        self._trailersToFetchQueue.put(trailer, timeout=1)
                        Debug.myLog('Put in _trailersToFetchQueue',
                                    xbmc.LOGDEBUG)
                        finished = True
                except queue.Full:
                    # Not a permanent loss. Means that we just
                    # won't show one trailer this time around.
                    # If they keep playing long enough, it will
                    # cycle back another time. Should be quite
                    # rare.
                    finished = True
                except queue.Empty:
                    #._discoveredTrailersQueue is empty

                    if block:
                        # We don't want to keep blocking on
                        # self._trailersToFetchQueueLock. Go ahead and exit loop
                        # and release lock. Then block on a regular Queue.get
                        finished = True
                if not finished:
                    Debug.myLog(self.__class__.__name__ + u'.loadFetchQueue is ' +
                                u'hung reloading from._discoveredTrailersQueue.'
                                + ' length of _discoveredTrailers: '
                                + str(len(self._discoveredTrailers))
                                + u' length of._discoveredTrailersQueue: '
                                + str(self._discoveredTrailersQueue.qsize()),
                                xbmc.LOGERROR)

                if shuffle:
                    self.shuffleDiscoveredTrailers(markUnplayed=True)
        if block:
            try:
                Debug.myLog(
                    u'FetchQueue completely empty. Blocking on get.', xbmc.LOGDEBUG)
                trailer = self._discoveredTrailersQueue.get()
                self._trailersToFetchQueue.put(trailer)
                Debug.myLog(
                    METHOD_NAME + u' got trailer afterblock', xbmc.LOGDEBUG)
            except Exception:
                Debug.logException()

    def getFromFetchQueue(self):
        Debug.myLog(self.__class__.__name__ +
                    u'.getFromFetchQueue: ', xbmc.LOGDEBUG)
        self.loadFetchQueue()
        trailer = self._trailersToFetchQueue.get()
        Debug.myLog(self.__class__.__name__ + u'.getFromFetchQueue: ' +
                    trailer[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)
        return trailer


class LibraryTrailerManager(BaseTrailerManager):

    '''
        Retrieve all movie entries from library. If specified, then limit to movies
        for the given genre. Note that entries include movies without trailers.
        Movies with local trailers or trailer URLs are immediately placed into
        BaseTrailerManager.readyToPlay. The others are placed into
        BaseTrailerManager.trailerFetchQue.
    '''

    _singletonInstance = None

    def __init__(self):
        threadName = Constants.ADDON_PATH + u'.LibraryTrailerManager'
        super(LibraryTrailerManager, self).__init__(group=None, target=None,
                                                    name=threadName,
                                                    args=(), kwargs=None, verbose=None)
        self._lastShuffleTime = datetime.datetime.fromordinal(1)
        self._lastShuffledIndex = -1
        self._trailersToFetchQueue = queue.Queue(maxsize=0)
        self._lock = threading.Condition()
        self._lastShuffledIndex = -1
        self._discoveredTrailers = []

    @staticmethod
    def getInstance():
        try:
            Debug.myLog('In LibraryTrailerManager.getInstance', xbmc.LOGDEBUG)
            if LibraryTrailerManager._singletonInstance is None:
                Debug.myLog(
                    'In LibraryTrailerManager. singletonInstance None', xbmc.LOGDEBUG)
                singleton = LibraryTrailerManager()
                Debug.myLog(
                    'In LibraryTrailerManager. new Instance', xbmc.LOGDEBUG)

                LibraryTrailerManager._singletonInstance = singleton
                Debug.myLog(
                    'In LibraryTrailerManager. set singletonInstance field', xbmc.LOGDEBUG)

                BaseTrailerManager.getInstance().addManager(singleton)
                Debug.myLog('In LibraryTrailerManager. addManager',
                            xbmc.LOGDEBUG)

                singleton.trailerFetcher = TrailerFetcher()
                Debug.myLog(
                    'In LibraryTrailerManager. Got TrailerFetcher', xbmc.LOGDEBUG)

                singleton.trailerFetcher.startFetchers(singleton)
                Debug.myLog(
                    'In LibraryTrailerManager. started Fetchers', xbmc.LOGDEBUG)

            return LibraryTrailerManager._singletonInstance
        except Exception:
            Debug.logException()

    def discoverBasicInformation(self, genre):
        METHOD_NAME = u'LibraryTrailerManager.discoverBasicInformation'
        self.setGenre(genre)
        self.start()

        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = u'LibraryTrailerManager.run'
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        Debug.myLog(METHOD_NAME + u': memory: ' + str(memory), xbmc.LOGDEBUG)
        try:
            self.runWorker()
            self.finishedDiscovery()
        except AbortException:
            return  # Shut down thread
        except Exception:
            Debug.logException()

    def runWorker(self):
        METHOD_NAME = u'LibraryTrailerManager.runWorker'
        if self.genre == '':
            #        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"properties": ["title", "lastplayed", "studio", "cast", "plot", "writer", "director", "fanart", "runtime", "mpaa", "adult", "thumbnail", "file", "year", "genre", "trailer"]}, "id": 1}'
            query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", \
                    "params": {\
                    "properties": \
                        ["title", "lastplayed", "studio", "cast", "plot", "writer", \
                        "director", "fanart", "runtime", "mpaa", "thumbnail", "file", \
                        "year", "genre", "trailer"]\
                        }, \
                         "id": 1}'

        else:
            #        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"properties": ["title", "lastplayed", "studio", "cast", "plot", "writer", "director", "fanart", "runtime", "mpaa", "adult", "thumbnail", "file", "year", "genre", "trailer"], "filter": {"field": "genre", "operator": "contains", "value": "%s"}}, "id": 1}'
            query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", \
             "params": \
             {"properties": \
             ["title", "lastplayed", "studio", "cast",  "plot", "writer",\
              "director", "fanart", "runtime", "mpaa", "thumbnail", "file",\
             "year", "genre", "trailer"],\
              "filter": {"field": "genre", "operator": "contains", "value": "%s"}\
              },\
               "id": 1}'

            query = query % self.genre

        if Utils.isShutdownRequested():
            return

        queryResult = Utils.getKodiJSON(query)

        # Debug.myLog('movies: ', json.dumps(movieString, indent=3), xbmc.LOGDEBUG)
        moviesSkipped = 0
        moviesFound = 0

        result = queryResult.get('result', {})
        for movie in result["movies"]:
            Utils.throwExceptionIfShutdownRequested()

            Debug.myLog('Kodi library movie: ' +
                        json.dumps(movie), xbmc.LOGDEBUG)
            moviesFound += 1
            if Settings.getHideWatchedMovies() and Constants.MOVIE_LAST_PLAYED in movie:
                if getDaysSinceLastPlayed(movie[Constants.MOVIE_LAST_PLAYED],
                                          movie[Constants.MOVIE_TITLE]) > 0:
                    moviesSkipped += 1
                    continue

            # Normalize rating

            Debug.myLog(METHOD_NAME + u': mpaa: ' + movie[Constants.MOVIE_MPAA] +
                        u' movie: ' + movie[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)
            rating = Rating.getMPAArating(
                movie.get(Constants.MOVIE_MPAA), movie.get(u'adult'))
            movie[Constants.MOVIE_SOURCE] = Constants.MOVIE_LIBRARY_SOURCE
            movie.setdefault(Constants.MOVIE_TRAILER, u'')
            movie[Constants.ITUNES_TRAILER_TYPE] = 'Bogus Library Movie Type'

            Debug.validateBasicMovieProperties(movie)

            if checkRating(rating):
                self.addToDiscoveredTrailers(movie)

        if Settings.getHideWatchedMovies():
            Debug.myLog(u'Omitted ' + str(moviesSkipped) +
                        u' movies', xbmc.LOGDEBUG)

        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        Debug.myLog(u'loadLibraryTrailers: exit memory: ' +
                    str(memory), xbmc.LOGDEBUG)
        Debug.myLog(METHOD_NAME + u': moviesFound: ' + str(moviesFound) + u' moviesSkipped: '
                    + str(moviesSkipped), xbmc.LOGDEBUG)


class FolderTrailerManager(BaseTrailerManager):

    '''
        The subtrees specified by the path/multipath are
        assumed to contain movie trailers.
        Create skeleton movie info for every file found,
        containing only the file and directory names.
    '''

    _singletonInstance = None

    def __init__(self):
        threadName = Constants.ADDON_PATH + u'.FolderTrailerManager'
        super(FolderTrailerManager, self).__init__(group=None, target=None,
                                                   name=threadName,
                                                   args=(), kwargs=None, verbose=None)
        self._lastShuffleTime = datetime.datetime.fromordinal(1)
        self._lastShuffledIndex = -1
        self._trailersToFetchQueue = queue.Queue(maxsize=0)
        self._lock = threading.Condition()
        self._lastShuffledIndex = -1
        self._discoveredTrailers = []

    @staticmethod
    def getInstance():
        if FolderTrailerManager._singletonInstance is None:
            singleton = FolderTrailerManager()
            FolderTrailerManager._singletonInstance = singleton
            BaseTrailerManager.getInstance().addManager(singleton)
            singleton._trailerFetcher = TrailerFetcher()
        return FolderTrailerManager._singletonInstance

    def discoverBasicInformation(self, genre):
        METHOD_NAME = u'FolderTrailerManager.discoverBasicInformation'
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)
        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = u'FolderTrailerManager.run'
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        Debug.myLog(METHOD_NAME + u': memory: ' + str(memory), xbmc.LOGDEBUG)
        try:
            self.discoverBasicInformationWorker(Settings.getTrailersPaths())
        except AbortException:
            return  # Just exit thread
        except Exception:
            Debug.logException()

    def discoverBasicInformationWorker(self, path):
        METHOD_NAME = u'FolderTrailerManager.discoverBasicInformationWorker'
        folders = []
        if str(path).startswith(u'multipath://'):
            # get all paths from the multipath
            paths = path[12:-1].split('/')
            for item in paths:
                folders.append(urllib.parse.unquote_plus(item))
        else:
            folders.append(path)
        for folder in folders:
            Utils.throwExceptionIfShutdownRequested()

            if xbmcvfs.exists(xbmc.translatePath(folder)):
                # get all files and subfolders
                dirs, files = xbmcvfs.listdir(folder)

                # Assume every file is a movie trailer. Manufacture
                # a movie name and other info from the filename.

                for item in files:
                    filePath = os.path.join(folder, item)
                    if filePath not in played:
                        title = xbmc.translatePath(filePath)
                        title = os.path.basename(title)
                        title = os.path.splitext(title)[0]
                        newTrailer = {Constants.MOVIE_TITLE: title,
                                      Constants.MOVIE_TRAILER: filePath,
                                      Constants.ITUNES_TRAILER_TYPE: u'trailer file',
                                      Constants.MOVIE_SOURCE:
                                      Constants.MOVIE_FOLDER_SOURCE,
                                      Constants.MOVIE_FANART: u'',
                                      Constants.MOVIE_THUMBNAIL: u'',
                                      Constants.MOVIE_FILE: u'',
                                      Constants.MOVIE_YEAR: u''}
                        Debug.validateBasicMovieProperties(newTrailer)
                        self.addToDiscoveredTrailers(
                            newTrailer)

                for item in dirs:
                    # recursively scan all subfolders
                    subTree = os.path.join(folder, item)
                    self.discoverBasicInformationWorker(
                        subTree)

        return


class ItunesTrailerManager(BaseTrailerManager):

    def __init__(self):
        threadName = Constants.ADDON_PATH + u'.ItunesTrailerManager'
        super(ItunesTrailerManager, self).__init__(group=None, target=None,
                                                   name=threadName,
                                                   args=(), kwargs=None, verbose=None)
        self._lastShuffleTime = datetime.datetime.fromordinal(1)
        self._lastShuffledIndex = -1
        self._trailersToFetchQueue = queue.Queue(maxsize=0)
        self._lock = threading.Condition()
        self._lastShuffledIndex = -1
        self._discoveredTrailers = []

    _singletonInstance = None

    @staticmethod
    def getInstance():
        if ItunesTrailerManager._singletonInstance is None:
            singleton = ItunesTrailerManager()
            ItunesTrailerManager._singletonInstance = singleton
            BaseTrailerManager.getInstance().addManager(singleton)
            singleton._trailerFetcher = TrailerFetcher()
        return ItunesTrailerManager._singletonInstance

    def discoverBasicInformation(self, genre):
        METHOD_NAME = u'ItunesTrailerManager.discoverBasicInformation'
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)

        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        try:
            self.runWorker()
        except AbortException:
            return  # Just exit thread
        except Exception:
            Debug.logException()

    def runWorker(self):
        Utils.throwExceptionIfShutdownRequested()

        METHOD_NAME = u'ItunesTrailerManager.run'
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        showOnlyiTunesTrailersOfThisType = Settings.getIncludeItunesTrailerType()
        xbmc.log('trailer_type: ' +
                 str(showOnlyiTunesTrailersOfThisType), xbmc.LOGINFO)
        if showOnlyiTunesTrailersOfThisType > 4:
            xbmc.log(u'Invalid iTunes Trailer Type: ' +
                     str(showOnlyiTunesTrailersOfThisType), xbmc.LOGERROR)
            return

        if showOnlyiTunesTrailersOfThisType == 0:
            jsonURL = u'/trailers/home/feeds/studios.json'
        elif showOnlyiTunesTrailersOfThisType == 1:
            jsonURL = u'/trailers/home/feeds/just_added.json'
        elif showOnlyiTunesTrailersOfThisType == 2:
            jsonURL = u'/trailers/home/feeds/most_pop.json'
        elif showOnlyiTunesTrailersOfThisType == 3:
            jsonURL = u'/trailers/home/feeds/exclusive.json'
        elif showOnlyiTunesTrailersOfThisType == 4:
            jsonURL = u'/trailers/home/feeds/studios.json'

        jsonURL = APPLE_URL_PREFIX + jsonURL
        Debug.myLog(u'iTunes jsonURL: ' + jsonURL, xbmc.LOGDEBUG)
        statusCode, parsedContent = Utils.getJSON(jsonURL)

        Debug.myLog('parsedContent type: ',
                    parsedContent[0].__class__.__name__, xbmc.LOGINFO)
        Debug.myLog(u'parsedContent: ', json.dumps(parsedContent, ensure_ascii=False,
                                                   encoding='unicode', indent=4,
                                                   sort_keys=True), xbmc.LOGINFO)
        # RESUME HERE
        '''
        title":"Alita: Battle Angel",
        "releasedate":"Thu, 14 Feb 2019 00:00:00 -0800",
        "studio":"20th Century Fox",
        "poster":"http://trailers.apple.com/trailers/fox/alita-battle-angel/images/poster.jpg",
        "poster_2x":"http://trailers.apple.com/trailers/fox/alita-battle-angel/images/poster_2x.jpg",
        "location":"/trailers/fox/alita-battle-angel/",
        "rating":"Not yet rated",
        "genre":["Action and Adventure",
                "Science Fiction"],
        "directors":
                "Robert Rodriguez",
        "actors":["Rosa Salazar",
                "Christoph Waltz",
                "Jennifer Connelly",
                "Mahershala Ali",
                "Ed Skrein",
                "Jackie Earle Haley",
                "Keean Johnson"],
        "trailers":[
                {"postdate":"Tue, 13 Nov 2018 00:00:00 -0800",
                "url":"/trailers/fox/alita-battle-angel/",
                "type":"Trailer 3",
                "exclusive":false,
                "hd":true},
                 {"postdate":"Mon, 23 Jul 2018 00:00:00 -0700",
                 "url":"/trailers/fox/alita-battle-angel/","type":"Trailer 2",
                 "exclusive":false,"hd":true},
                 {"postdate":"Fri, 08 Dec 2017 00:00:00 -0800",
                 "url":"/trailers/fox/alita-battle-angel/","type":"Trailer",
                 "exclusive":false,"hd":true}]
    },
    '''
        #
        # Create Kodi movie entries from what iTunes has given us.

        for iTunesMovie in parsedContent:
            Utils.throwExceptionIfShutdownRequested()

            Debug.myLog(u'value: ' + str(iTunesMovie), xbmc.LOGINFO)

            title = iTunesMovie.get(
                Constants.MOVIE_TITLE, u'Missing title from iTunes')
            Debug.myLog('title: ', title, xbmc.LOGINFO)

            releaseDateString = iTunesMovie.get('releasedate')
            Debug.myLog('releaseDateString: ', releaseDateString, xbmc.LOGINFO)
            if releaseDateString != '':
                STRIP_TZ_PATTERN = ' .[0-9]{4}$'

                stripTZPattern = re.compile(STRIP_TZ_PATTERN)
                releaseDateString = stripTZPattern.sub('', releaseDateString)
                Debug.myLog('releaseDateString: ',
                            releaseDateString, xbmc.LOGINFO)

                # "Thu, 14 Feb 2019 00:00:00 -0800",
                releaseDate = datetime.datetime.strptime(
                    releaseDateString, '%a, %d %b %Y %H:%M:%S')
                Debug.myLog('releaseDate: ', releaseDate.strftime(
                    '%d-%m-%Y'), xbmc.LOGINFO)
            else:
                releaseDate = datetime.date.today()

            studio = iTunesMovie.get('studio')
            if studio is None:
                studio = ''

            Debug.myLog('studio: ', studio, xbmc.LOGINFO)

            poster = iTunesMovie.get('poster')
            if poster is None:
                poster = ''

            Debug.myLog('poster: ', poster, xbmc.LOGINFO)

            thumb = string.replace(poster, 'poster.jpg', 'poster-xlarge.jpg')
            fanart = string.replace(poster, 'poster.jpg', 'background.jpg')

            Debug.myLog('thumb:', thumb, ' fanart: ', fanart, xbmc.LOGINFO)

            poster_2x = iTunesMovie.get('poster_2x')
            if poster_2x is None:
                poster_2x = ''

            Debug.myLog('poster_2x: ', poster_2x, xbmc.LOGINFO)

            location = iTunesMovie.get('location')
            if location is None:
                location = ''

            Debug.myLog('location: ', location, xbmc.LOGINFO)

            # Normalize rating
            # We expect the attribute to be named 'mpaa', not 'rating'

            iTunesMovie[Constants.MOVIE_MPAA] = iTunesMovie[u'rating']
            rating = Rating.getMPAArating(
                iTunesMovie.get(Constants.MOVIE_MPAA), iTunesMovie.get(u'adult'))
            Debug.myLog('rating: ', rating, xbmc.LOGINFO)

            genres = iTunesMovie.get('genre')
            Debug.myLog('genres: ', genres, xbmc.LOGINFO)

            directors = iTunesMovie.get('directors')
            if directors is None:
                directors = []

            Debug.myLog('directors: ', directors, xbmc.LOGINFO)

            actors = iTunesMovie.get('actors')
            if actors is None:
                actors = []

            Debug.myLog('actors: ', actors, xbmc.LOGINFO)

            '''
        "trailers":[
                {"postdate":"Tue, 13 Nov 2018 00:00:00 -0800",
                "url":"/trailers/fox/alita-battle-angel/",
                "type":"Trailer 3",
                "exclusive":false,
                    "hd":true},

                 {"postdate":"Mon, 23 Jul 2018 00:00:00 -0700","url":"/trailers/fox/alita-battle-angel/","type":"Trailer 2","exclusive":false,"hd":true},
                 {"postdate":"Fri, 08 Dec 2017 00:00:00 -0800","url":"/trailers/fox/alita-battle-angel/","type":"Trailer","exclusive":false,"hd":true}]
            '''
            excludeTypesSet = {"- JP Sub", "Interview", "- UK", "- BR Sub", "- FR", "- IT", "- AU", "- MX", "- MX Sub", "- BR", "- RU", "- DE",
                               "- ES", "- FR Sub", "- KR Sub", "- Russian", "- French", "- Spanish", "- German", "- Latin American Spanish", "- Italian"}

            iTunesTrailersList = iTunesMovie.get('trailers')
            if iTunesTrailersList is None:
                iTunesTrailersList = []

            Debug.myLog('iTunesTrailersList: ',
                        iTunesTrailersList, xbmc.LOGINFO)
            for iTunesTrailer in iTunesTrailersList:
                Utils.throwExceptionIfShutdownRequested()

                keepTrailer = True
                Debug.myLog('iTunesTrailer: ', iTunesTrailer, xbmc.LOGINFO)
                postDate = iTunesTrailer.get('postdate')
                if postDate is None:
                    postDate = ''

                Debug.myLog('postDate: ', postDate, xbmc.LOGINFO)

                url = iTunesTrailer.get('url')
                if url is None:
                    url = ''

                Debug.myLog('url: ', url, xbmc.LOGINFO)

                trailerType = iTunesTrailer.get('type', u'')

                Debug.myLog('type: ', trailerType, xbmc.LOGINFO)

                if not Settings.getIncludeClips() and (trailerType == 'Clip'):
                    keepTrailer = False
                elif trailerType in excludeTypesSet:
                    keepTrailer = False
                elif not Settings.getIncludeFeaturettes() and (trailerType == u'Featurette'):
                    keepTrailer = False
                elif ((Settings.getIncludeItunesTrailerType() == 0) and
                      (releaseDate < datetime.date.today())):
                    keepTrailer = False
                elif self.genre not in genres:
                    keepTrailer = False
                elif not checkRating(rating):
                    keepTrailer = False

                if keepTrailer:
                    url = APPLE_URL_PREFIX + url + "includes/" + \
                        trailerType.replace('-', '').replace(' ',
                                                             '').lower() + "/large.html"
                    movie = {Constants.MOVIE_TITLE: title,
                             Constants.MOVIE_TRAILER: url,
                             # Not sure of value of Apple's trailer type
                             # 'Trailer 3', etc
                             Constants.ITUNES_TRAILER_TYPE: trailerType,
                             Constants.MOVIE_MPAA: rating,
                             Constants.MOVIE_YEAR: str(releaseDate.year),
                             Constants.MOVIE_THUMBNAIL: thumb,
                             Constants.MOVIE_FANART: fanart,
                             Constants.MOVIE_GENRE: genres,
                             Constants.MOVIE_DIRECTOR: directors,
                             Constants.MOVIE_STUDIO: studio,
                             Constants.MOVIE_SOURCE:
                                 Constants.MOVIE_ITUNES_SOURCE}
                    Debug.myLog('Adding iTunes trailer: ', movie, xbmc.LOGINFO)
                    Debug.validateBasicMovieProperties(movie)
                    self.addToDiscoveredTrailers(movie)
        return


class TmdbTrailerManager(BaseTrailerManager):
    # TODO: Need to add genre filter here

    '''
        TMDB, like iTunes, provides trailers. Query TMDB for trailers
        and manufacture trailer entries for them.
    '''

    _singletonInstance = None

    def __init__(self):
        threadname = Constants.ADDON_PATH + u'.TmdbTrailerManager'
        super(TmdbTrailerManager, self).__init__(group=None, target=None,
                                                 name=threadname,
                                                 args=(), kwargs=None, verbose=None)
        self._lastShuffleTime = datetime.datetime.fromordinal(1)
        self._lastShuffledIndex = -1
        self._trailersToFetchQueue = queue.Queue(maxsize=0)
        self._lock = threading.Condition()
        self._lastShuffledIndex = -1
        self._discoveredTrailers = []

    @staticmethod
    def getInstance():
        if TmdbTrailerManager._singletonInstance is None:
            singleton = TmdbTrailerManager()
            TmdbTrailerManager._singletonInstance = singleton
            BaseTrailerManager.getInstance().addManager(singleton)
            singleton._trailerFetcher = TrailerFetcher()
        return TmdbTrailerManager._singletonInstance

    def discoverBasicInformation(self, genre):
        METHOD_NAME = u'TmdbTrailerManager.discoverBasicInformation'
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)

        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        try:
            self.runWorker()
        except AbortException:
            return  # Just exit thread
        except Exception:
            Debug.logException()

    def runWorker(self):
        Utils.throwExceptionIfShutdownRequested()

        METHOD_NAME = u'TmdbTrailerManager.run'
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        Debug.myLog(METHOD_NAME + u' memory: ' + str(memory), xbmc.LOGDEBUG)
        tmdbSource = Settings.getTmdbSourceSetting()
        if tmdbSource == '0':
            source = 'popular'
        elif tmdbSource == '1':
            source = 'top_rated'
        elif tmdbSource == '2':
            source = 'upcoming'
        elif tmdbSource == '3':
            source = 'now_playing'
        elif tmdbSource == '4':
            source = 'dvd'
        elif tmdbSource == '5':
            source = 'all'

        # TODO: Verify that these rating strings are correct and
        #     complete for Tmdb
        rating_limit = Constants.ADDON.getSetting('rating_limit')
        if rating_limit == '0':
            rating_limit = 'NC-17'
        elif rating_limit == '1':
            rating_limit = 'G'
        elif rating_limit == '2':
            rating_limit = 'PG'
        elif rating_limit == '3':
            rating_limit = 'PG-13'
        elif rating_limit == '4':
            rating_limit = 'R'
        elif rating_limit == '5':
            rating_limit = 'NC-17'

        Debug.myLog(METHOD_NAME + u' source; ' + source, xbmc.LOGDEBUG)

        # ========================
        #
        #   ALL movies, sorted by popularity and limited by rating
        #
        #   The discover/movie API is used. Note that you can filter and
        #   sort by many items, including release date. The entire library
        #   (~400,000 movies) is available.
        #
        # ========================
        if source == 'all':
            data = {}
            data[u'api_key'] = Settings.getTmdbApiKey()
            data[u'sort_by'] = 'popularity.desc'
            data[u'certification_country'] = 'us'
            data[u'certification.lte'] = rating_limit
            url_values = urllib.parse.urlencode(data)
            url = 'http://api.themoviedb.org/3/discover/movie'
            full_url = url + '?' + url_values
            statusCode, infostring = Utils.getJSON(full_url)

            # Get all of the movies from 11 random pages available
            # containing popular movie information

            total_pages = infostring[u'total_pages']
            if total_pages > 1000:
                total_pages = 1000
            for i in range(1, 11):
                Utils.throwExceptionIfShutdownRequested()

                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'sort_by'] = 'popularity.desc'
                data[u'certification_country'] = 'us'
                data[u'certification.lte'] = rating_limit
                data[u'page'] = Utils.RandomGenerator.randrange(
                    1, total_pages + 1)
                url_values = urllib.parse.urlencode(data)
                url = 'http://api.themoviedb.org/3/discover/movie'
                full_url = url + '?' + url_values
                statusCode, infostring = Utils.getJSON(full_url)

                for movie in infostring[u'results']:
                    Utils.throwExceptionIfShutdownRequested()

                    trailerId = movie[u'id']
                    trailerEntry = {Constants.MOVIE_TRAILER: Constants.MOVIE_TMDB_SOURCE,
                                    'id': trailerId,
                                    Constants.MOVIE_SOURCE: Constants.MOVIE_TMDB_SOURCE,
                                    Constants.MOVIE_TITLE: movie[Constants.MOVIE_TITLE]}
                    self.addToDiscoveredTrailers(trailerEntry)
                    Debug.myLog(METHOD_NAME + u' ALL title: ' +
                                trailerEntry[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)

        # ========================
        #
        #   DVDs
        #
        # ========================
        elif source == 'dvd':
            data = {}
            data[u'apikey'] = Settings.getRottonTomatoesApiKey()
            data[u'country'] = 'us'
            url_values = urllib.parse.urlencode(data)
            url = 'http://api.rottentomatoes.com/api/public/v1.0/lists/dvds/new_releases.json'
            full_url = url + '?' + url_values
            statusCode, infostring = Utils.getJSON(full_url)

            for movie in infostring[u'movies']:
                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'query'] = movie[Constants.MOVIE_TITLE]
                data[u'year'] = movie[u'year']
                url_values = urllib.parse.urlencode(data)
                url = 'https://api.themoviedb.org/3/search/movie'
                full_url = url + '?' + url_values
                statusCode, infostring = Utils.getJSON(full_url)

                for m in infostring[u'results']:
                    trailerId = m[u'id']
                    trailerEntry = {Constants.MOVIE_TRAILER: Constants.MOVIE_TMDB_SOURCE,
                                    'id': trailerId,
                                    Constants.MOVIE_SOURCE: Constants.MOVIE_TMDB_SOURCE,
                                    Constants.MOVIE_TITLE: movie[Constants.MOVIE_TITLE]}
                    self.addToDiscoveredTrailers(trailerEntry)

                    Debug.myLog(METHOD_NAME + u' DVD title: ' +
                                trailerEntry[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)
                    break
        # ========================
        #
        #   Everything else (popular, top_rated, upcoming, now playing)
        #
        # ========================
        else:
            page = 0
            #
            # Get only the first 12 pages of info. Typical for 'popular' movies
            # is 993 pages with ~20,000 results. This means about about 20 movies
            # are on each page. Twelve page should have about 240 movies.
            #
            for i in range(0, 11):
                Utils.throwExceptionIfShutdownRequested()

                page = page + 1
                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'page'] = page
                data[u'language'] = 'en'
                url_values = urllib.parse.urlencode(data)
                url = 'https://api.themoviedb.org/3/movie/' + source
                full_url = url + '?' + url_values
                statusCode, infostring = Utils.getJSON(full_url)

                # The returned results has title, description, release date, rating.
                # Does not have actors, etc.
                '''
                    {"total_results": 19844, "total_pages": 993, "page": 1,
                         "results": [{"poster_path": "/5Kg76ldv7VxeX9YlcQXiowHgdX6.jpg",
                                      "title": "Aquaman",
                                       "overview": "Once home to the most advanced civilization
                                          on Earth, the city of Atlantis is now an underwater
                                          ..,",
                                       "release_date": "2018-12-07"
                                       "popularity": 303.019, "
                                       "original_title": "Aquaman",
                                       "backdrop_path": "/5A2bMlLfJrAfX9bqAibOL2gCruF.jpg",
                                       "vote_count": 3134,
                                       "video": false,
                                       "adult": false,
                                       "vote_average": 6.9,
                                       "genre_ids": [28, 14, 878, 12],
                                       "id": 297802,
                                        "original_language": "en"},

                '''

                for result in infostring[u'results']:
                    Utils.throwExceptionIfShutdownRequested()

                    trailerId = result[u'id']
                    trailerEntry = {Constants.MOVIE_TRAILER: Constants.MOVIE_TMDB_SOURCE,
                                    'id': trailerId,
                                    Constants.MOVIE_SOURCE: Constants.MOVIE_TMDB_SOURCE,
                                    Constants.MOVIE_TITLE: result[Constants.MOVIE_TITLE]}
                    Debug.myLog(METHOD_NAME + u' ' + source + u' title: ' +
                                trailerEntry[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)
                    self.addToDiscoveredTrailers(trailerEntry)

                if infostring[u'total_pages'] == page:
                    break

        Debug.myLog(METHOD_NAME + u' exit ' +
                    u' memory: ' + str(memory), xbmc.LOGDEBUG)
        return


class TrailerFetcher(threading.Thread):

    NUMBER_OF_FETCHERS = 1
    _trailerFetchers = []

    def __init__(self):
        Debug.myLog(u'TrailerFetcher.__init__', xbmc.LOGDEBUG)
        threadName = Constants.ADDON_PATH + u'.TrailerFetcher'
        super(TrailerFetcher, self).__init__(name=threadName)

    def startFetchers(self, trailerManager):

        Debug.myLog(u'TrailerFetcher.startFetcher', xbmc.LOGDEBUG)
        WatchDog.registerThread(self)
        i = 0
        while i < self.NUMBER_OF_FETCHERS:
            i += 1
            trailerFetcher = TrailerFetcher()
            trailerFetcher._trailerManager = trailerManager
            TrailerFetcher._trailerFetchers.append(trailerFetcher)
            trailerFetcher.start()
            Debug.myLog(u'TrailerFetcher.startFetcher started', xbmc.LOGDEBUG)

    @staticmethod
    def stop():
        pass

    def run(self):
        try:
            self.runWorker()
        except AbortException:
            return  # Just exit thread
        except Exception:
            Debug.logException()

    def runWorker(self):
        while True:
            Utils.throwExceptionIfShutdownRequested()

            Debug.myLog(u'TrailerFetcher.run waiting to fetch', xbmc.LOGDEBUG)
            trailer = self._trailerManager.getFromFetchQueue()
            Debug.myLog(u'TrailerFetcher.run got trailer: ' +
                        trailer[Constants.MOVIE_TITLE], xbmc.LOGDEBUG)
            self.fetchTrailerToPlay(trailer)

    def fetchTrailerToPlay(self, trailer):
        xbmc.log('In randomtrailers.TrailerFetcher.fetchTrailerToPlay',
                 xbmc.LOGNOTICE)

        if trailer[Constants.MOVIE_TRAILER] == Constants.MOVIE_TMDB_SOURCE:
            #
            # Entries with a'trailer' value of Constants.MOVIE_TMDB_SOURCE are trailers
            # which are not from any movie in Kodi but come from
            # TMDB, similar to iTunes or YouTube.
            #
            # Query TMDB for the details and replace the
            # temporary trailer entry with what is discovered.
            # Note that the Constants.MOVIE_SOURCE value will be
            # set to Constants.MOVIE_TMDB_SOURCE
            #
            status, populatedTrailer = self.getTmdbTrailer(trailer[u'id'])
            Utils.throwExceptionIfShutdownRequested()

            if status == Constants.TOO_MANY_TMDB_REQUESTS:
                pass
            elif populatedTrailer is not None:
                for prop in trailer:
                    Debug.myLog('Prop: ' + prop + ' old: ' + str(trailer.get(prop))
                                + u' new: ' + str(populatedTrailer.get(prop)), xbmc.LOGDEBUG)

                for prop in populatedTrailer:
                    if prop not in trailer:
                        Debug.myLog('New Prop: ' + prop + ' value: ' +
                                    str(populatedTrailer.get(prop)), xbmc.LOGDEBUG)
                trailer.update(populatedTrailer)  # Remember what we found
        else:
            source = trailer[Constants.MOVIE_SOURCE]
            if source == Constants.MOVIE_LIBRARY_SOURCE:
                if trailer[Constants.MOVIE_TRAILER] == '':  # no trailer search tmdb for one
                    trailerId = searchForTrailerFromTMDB(
                        trailer[Constants.MOVIE_TITLE], trailer[u'year'])
                    if trailerId != '':

                        # Returns a tuple of dictionary objects for each movie
                        # found

                        status, newTrailerData = self.getTmdbTrailer(trailerId)
                        Utils.throwExceptionIfShutdownRequested()

                        if status == Constants.TOO_MANY_TMDB_REQUESTS or newTrailerData is None:
                            # Need to try again later
                            self._trailerManager.addToFetchQueue(trailer)
                            return

                        trailer[Constants.MOVIE_TRAILER] = \
                            newTrailerData[Constants.MOVIE_TRAILER]
                        Debug.compareMovies(trailer, newTrailerData)

            elif source == Constants.MOVIE_ITUNES_SOURCE:
                try:
                    content = opener.open(
                        trailer[Constants.MOVIE_TRAILER]).read()
                    match = re.compile(
                        '<a class="movieLink" href="(.+?)"', re.DOTALL).findall(content)
                    urlTemp = match[0]
                    url = urlTemp[:urlTemp.find("?")].replace(
                        "480p", "h" + Settings.getQuality()) + "|User-Agent=iTunes/9.1.1"
                except:
                    url = ''
                trailer[Constants.MOVIE_TRAILER] = url

        Debug.myLog('Exiting randomtrailers.TrailerFetcher.fetchTrailerToPlay movie: ' +
                    trailer.get(Constants.MOVIE_TITLE), xbmc.LOGNOTICE)

        # If no trailer possible then remove it from further consideration

        if trailer[Constants.MOVIE_TRAILER] != u'':
            trailer[Constants.TRAILER_DISCOVERY_STATE] = Constants.TRAILER_DISCOVERY_COMPLETE
            self._trailerManager.addToReadyToPlayQueue(trailer)
        else:
            self._trailerManager.removeDiscoveredTrailer(trailer)

    '''
        Given the movieId from TMDB, query TMDB for trailer details and manufacture
        a trailer entry based on the results. The trailer itself will be a Youtube
        url.
    '''

    def getTmdbTrailer(self, movieId, trailerOnly=False):
        Debug.myLog(u'getTmdbTrailer movieId: ' + str(movieId), xbmc.LOGDEBUG)

        trailer_url = ''
        trailerType = ''
        you_tube_base_url = u'plugin://plugin.video.youtube/?action=play_video&videoid='
        image_base_url = u'http://image.tmdb.org/t/p/'

        # Query The Movie DB for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        data = {}
        data[u'append_to_response'] = u'credits,trailers,releases'
        data[u'api_key'] = Settings.getTmdbApiKey()
        url_values = urllib.parse.urlencode(data)
        url = u'http://api.themoviedb.org/3/movie/' + str(movieId)
        full_url = url + '?' + url_values
        try:
            statusCode, tmdbResult = Utils.getJSON(full_url)
            if statusCode == Constants.TOO_MANY_TMDB_REQUESTS:
                Debug.myLog(u'Request rate to TMDB exceeds limits. Consider getting \
                            an API Key. This session\'s requests: '
                            + str(Constants.tmdbRequestCount), xbmc.LOGINFO)
                return statusCode, None
        except:
            xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
            return -1, None
        else:
            #
            # Grab first trailer
            #
            previousSize = 0
            for tmdbTrailer in tmdbResult[u'trailers'][u'youtube']:
                if Constants.MOVIE_SOURCE in tmdbTrailer:
                    trailerType = tmdbTrailer[u'type']
                    if not Settings.getIncludeFeaturettes() and trailerType == u'Featurette':
                        continue
                    if not Settings.getIncludeClips() and trailerType == u'Clip':
                        continue
                    size = tmdbTrailer[u'size']
                    if previousSize > size:  # HD, HQ, Standard OR number if Video api used
                        continue
                    previousSize = size
                    trailer_url = you_tube_base_url + \
                        tmdbTrailer[u'source']
                    break
            tmdbCountries = tmdbResult[u'releases'][u'countries']
            mpaa = ''
            for c in tmdbCountries:
                if c[u'iso_3166_1'] == 'US':
                    mpaa = c[u'certification']
            if mpaa == '':
                mpaa = Rating.RATING_NR
            year = tmdbResult[u'release_date'][:-6]
            fanart = image_base_url + 'w380' + \
                str(tmdbResult[u'backdrop_path'])
            thumbnail = image_base_url + 'w342' + \
                str(tmdbResult[u'poster_path'])
            title = tmdbResult[Constants.MOVIE_TITLE]
            plot = tmdbResult[u'overview']
            runtime = tmdbResult[u'runtime']
            studios = tmdbResult[u'production_companies']
            studio = []
            for s in studios:
                studio.append(s[u'name'])
            genres = tmdbResult[u'genres']
            genre = []
            for g in genres:
                genre.append(g[u'name'])
            tmdbCastMembers = tmdbResult[u'credits'][u'cast']
            cast = []
            for castMember in tmdbCastMembers:
                cast.append(castMember[u'name'])
            tmdbCrewMembers = tmdbResult[u'credits'][u'crew']
            director = []
            writer = []
            for crewMember in tmdbCrewMembers:
                if crewMember[u'job'] == u'Director':
                    director.append(crewMember[u'name'])
                if crewMember[u'department'] == 'Writing':
                    writer.append(crewMember[u'name'])
            addMovie = False
            for s in tmdbResult[u'spoken_languages']:
                if s[u'name'] == 'English':
                    addMovie = True
            if not Settings.getIncludeAdult() and tmdbResult[u'adult'] == u'true':
                addMovie = False

            # Normalize rating

            mpaa = Rating.getMPAArating(mpaa, None)

            addMovie = checkRating(mpaa)
            if not addMovie:
                dictInfo = None
            else:
                dictInfo = {Constants.MOVIE_TITLE: title,
                            Constants.MOVIE_TRAILER: trailer_url,
                            'year': year,
                            'studio': studio,
                            'mpaa': mpaa,
                            'file': '',
                            'thumbnail': thumbnail,
                            'fanart': fanart,
                            'director': director,
                            'writer': writer,
                            'plot': plot,
                            'cast': cast,
                            'runtime': runtime,
                            'genre': genre,
                            Constants.MOVIE_SOURCE: Constants.MOVIE_TMDB_SOURCE,
                            'type': trailerType}

        Debug.myLog(u'getTmdbTrailer exit : ' +
                    json.dumps(dictInfo, indent=3), xbmc.LOGDEBUG)

        return 0, dictInfo

    def getDetailInfo(self, trailer):
        return
        source = trailer[Constants.MOVIE_SOURCE]
        #control = self.getControl(38001)
        thumbnail = trailer[u'thumbnail']
        # control.setImage(thumbnail)
        # self.getControl(38003).setImage(trailer["fanart"])
        title_font = getTitleFont()
        trailerType = source
        if u'type' in trailer:
            trailerType = trailer[u'type']

        title_string = trailer["title"] + ' - ' + trailer[Constants.MOVIE_SOURCE] + \
            ' ' + trailerType + ' - ' + str(trailer["year"])
        #title = xbmcgui.ControlLabel(10, 40, 380, 40, title_string, title_font)
        #title = self.addControl(title)
        #title = self.getControl(38002)
        #title.setAnimations([('windowclose', 'effect=fade end=0 time=1000')])
        movieDirector = ''
        movieWriter = ''
        genres = ''
        if source == Constants.MOVIE_ITUNES_SOURCE:
            info = getInfo(trailer[Constants.MOVIE_TITLE], trailer[u'year'])
            writers = info[u'writer']
            directors = info[u'director']
            actors = info[u'cast']
            plot = info[u'plot']
            genres = info[u'genre']
            movieActor = ''
            actorcount = 0
            for actor in actors:
                actorcount = actorcount + 1
                movieActor = movieActor + actor + ", "
                if actorcount == 8:
                    break
            if not movieActor == '':
                movieActor = movieActor[:-2]
        else:
            plot = trailer["plot"]
            writers = trailer["writer"]
            directors = trailer["director"]
            actors = trailer["cast"]
            movieActor = ''
            actorcount = 0
            if source == Constants.MOVIE_LIBRARY_SOURCE:
                for actor in actors:
                    actorcount = actorcount + 1
                    movieActor = movieActor + actor[u'name'] + ", "
                    if actorcount == 8:
                        break
                if not movieActor == '':
                    movieActor = movieActor[:-2]
            else:
                movieActor = ''
                actorcount = 0
                for actor in actors:
                    actorcount = actorcount + 1
                    movieActor = movieActor + actor + ", "
                    if actorcount == 8:
                        break
                if not movieActor == '':
                    movieActor = movieActor[:-2]
        for director in directors:
            movieDirector = movieDirector + director + ", "
        if not movieDirector == '':
            movieDirector = movieDirector[:-2]
        for writer in writers:
            movieWriter = movieWriter + writer + ", "
        if not movieWriter == '':
            movieWriter = movieWriter[:-2]
        # self.getControl(38005).setLabel(movieDirector)
        # self.getControl(38006).setLabel(movieActor)
        # self.getControl(38005).setLabel(movieDirector)
        # self.getControl(38007).setLabel(movieWriter)
        # self.getControl(38009).setText(plot)
        movieStudio = ''
        if source == Constants.MOVIE_ITUNES_SOURCE:
            studios = trailer["studio"]
            movieStudio = studios
        if source == Constants.MOVIE_LIBRARY_SOURCE or source == Constants.MOVIE_TMDB_SOURCE:
            studios = trailer["studio"]
            for studio in studios:
                movieStudio = movieStudio + studio + ", "
                if not movieStudio == '':
                    movieStudio = movieStudio[:-2]
        # self.getControl(38010).setLabel(movieStudio)
        movieGenre = ''
        if source == Constants.MOVIE_LIBRARY_SOURCE or source == Constants.MOVIE_TMDB_SOURCE:
            genres = trailer["genre"]
        for genre in genres:
            movieGenre = movieGenre + genre + " / "
        if not movieGenre == '':
            movieGenre = movieGenre[:-3]
        runtime = ''
        if source == Constants.MOVIE_ITUNES_SOURCE:
            runtime = ''
        if source == Constants.MOVIE_LIBRARY_SOURCE:
            runtime = str(trailer["runtime"] / 60)
        if runtime != '':
            runtime = runtime + ' Minutes - '
        #self.getControl(38011).setLabel(runtime + movieGenre)
        rating = Rating.getMPAArating(trailer.get(
            Constants.MOVIE_MPAA), trailer.get(u'adult'))

        imgRating = Rating.getImageForRating(rating)

        return


def getTitleFont():
    xbmc.log('In randomtrailer.getTitleFont', xbmc.LOGNOTICE)
    title_font = 'font13'
    base_size = 20
    multiplier = 1
    skin_dir = xbmc.translatePath("special://skin/")
    list_dir = os.listdir(skin_dir)
    fonts = []
    fontxml_path = ''
    font_xml = ''
    for item in list_dir:
        item = os.path.join(skin_dir, item)
        if os.path.isdir(item):
            font_xml = os.path.join(item, "Font.xml")
        if os.path.exists(font_xml):
            fontxml_path = font_xml
            break
    dom = xml.dom.minidom.parse(fontxml_path)
    fontlist = dom.getElementsByTagName('font')
    for font in fontlist:
        name = font.getElementsByTagName('name')[0].childNodes[0].nodeValue
        size = font.getElementsByTagName('size')[0].childNodes[0].nodeValue
        fonts.append({'name': name, 'size': float(size)})
    fonts = sorted(fonts, key=lambda k: k[u'size'])
    for f in fonts:
        if f[u'name'] == 'font13':
            multiplier = f[u'size'] / 20
            break
    for f in fonts:
        if f[u'size'] >= 38 * multiplier:
            title_font = f[u'name']
            break
    return title_font


'''
    Ask user if they want to only see trailers for a specific genre.
    If so then let the user choose from genres that are actually
    present in the library.
'''


def promptForGenre():
    xbmc.log('In randomtrailer.promptForGenre', xbmc.LOGNOTICE)
    selectedGenre = u''

    # ask user whether they want to select a genre
    a = xbmcgui.Dialog().yesno(Constants.ADDON.getLocalizedString(
        32100), Constants.ADDON.getLocalizedString(32101))
    # deal with the output
    if a == 1:
        # prompt user to select genre
        sortedGenres = getGenresInLibrary()
        selectedIndex = xbmcgui.Dialog().select(
            Constants.ADDON.getLocalizedString(32100), sortedGenres, autoclose=False)
        Debug.myLog(u'got back from promptForGenre selectedIndex: ' +
                    str(selectedIndex), xbmc.LOGDEBUG)
        # check whether user cancelled selection
        if selectedIndex != -1:
            # get the user's chosen genre
            selectedGenre = sortedGenres[selectedIndex]

    return selectedGenre


'''
   Determine which genres are represented in the movie library
'''


def getGenresInLibrary():
    Debug.myLog('In randomtrailer.getGenresInLibrary', xbmc.LOGNOTICE)
    myGenres = []

    genresString = Utils.getKodiJSON(
        '{"jsonrpc": "2.0", "method": "VideoLibrary.GetGenres", "params": { "properties": [ "title"], "type":"movie"}, "id": 1}')

    genreResult = genresString[u'result']
    for genre in genreResult[u'genres']:
        myGenres.append(genre[u'title'])

    myGenres.sort()
    return myGenres


'''
   Does the given movie rating pass the configured limit?
'''


def checkRating(rating):
    passed = False
    maxRating = Settings.getRatingLimitSetting()

    xbmc.log('In randomtrailer.checkRating rating: ' +
             str(rating) + u' limit: ' + maxRating, xbmc.LOGNOTICE)

    if maxRating == '0':
        passed = True
    else:
        do_nr = Settings.getDoNotRatedSetting()
        nyr = ''
        nr = ''

        if Settings.getIncludeNotYetRatedTrailers():
            nyr = 'Not yet rated'

        if do_nr:
            nr = 'NR'

        if maxRating == '1':
            allowedRatings = ('G', nr, nyr)
        elif maxRating == '2':
            allowedRatings = ('G', 'PG', nr, nyr)
        elif maxRating == '3':
            allowedRatings = ('G', 'PG', 'PG-13', nr, nyr)
        elif maxRating == '4':
            allowedRatings = ('G', 'PG', 'PG-13', 'R', nr, nyr)
        elif maxRating == '5':
            allowedRatings = ('G', 'PG', 'PG-13', 'R',
                              'NC-17', 'NC17', nr, nyr)

        if rating in allowedRatings:
            passed = True

    return passed


'''
    The user selects which movie genres that they wish to see
    trailers for. If any genre for a movie was not requested
    by the user, then don't show the trailer.
'''


def genreCheck(movieMPAGenreLabels):
    Debug.myLog('genreCheck:', movieMPAGenreLabels, xbmc.LOGINFO)
    passed = True

    # Eliminate movies that have a genre that was
    # NOT selected

    for genre in Genre.ALLOWED_GENRES:
        if not genre.genreSetting and (genre.genreMPAALabel not in movieMPAGenreLabels):
            passed = False
            Debug.myLog('genre failed:', genre.genreSetting, xbmc.LOGINFO)
            break

    return passed


def getInfo(title, year):
    data = {}
    data[u'query'] = title
    data[u'year'] = str(year)
    data[u'api_key'] = Settings.getTmdbApiKey()
    data[u'language'] = 'en'
    url_values = urllib.parse.urlencode(data)
    url = 'https://api.themoviedb.org/3/search/movie'
    full_url = url + '?' + url_values
    statusCode, infostring = Utils.getJSON(full_url)

    if len(infostring[u'results']) > 0:
        results = infostring[u'results'][0]
        movieId = str(results[u'id'])
        if not movieId == '':
            data = {}
            data[u'api_key'] = Settings.getTmdbApiKey()
            data[u'append_to_response'] = 'credits'
            url_values = urllib.parse.urlencode(data)
            url = 'https://api.themoviedb.org/3/movie/' + movieId
            full_url = url + '?' + url_values
            statusCode, infostring = Utils.getJSON(full_url)
            director = []
            writer = []
            cast = []
            plot = ''
            runtime = ''
            genre = []
            plot = infostring[u'overview']
            runtime = infostring[u'runtime']
            genres = infostring[u'genres']
            for g in genres:
                genre.append(g[u'name'])
            castMembers = infostring[u'credits'][u'cast']
            for castMember in castMembers:
                cast.append(castMember[u'name'])
            crewMembers = infostring[u'credits'][u'crew']
            for crewMember in crewMembers:
                if crewMember[u'job'] == 'Director':
                    director.append(crewMember[u'name'])
                if crewMember[u'department'] == 'Writing':
                    writer.append(crewMember[u'name'])
    else:
        director = [u'Unavailable']
        writer = [u'Unavailable']
        cast = [u'Unavailable']
        plot = 'Unavailable'
        runtime = 0
        genre = [u'Unavailable']
    dictInfo = {'director': director, 'writer': writer,
                'plot': plot, 'cast': cast, 'runtime': runtime, 'genre': genre}
    return dictInfo


'''
    Get the number of days played since this movie (not the trailer)
    was last played. For invalid or missing values, -1 will be
    returned.
'''


def getDaysSinceLastPlayed(lastPlayedField, movieName):
    daysSincePlayed = -1
    try:
        if lastPlayedField is not None and lastPlayedField != u'':
            pd = time.strptime(lastPlayedField, u'%Y-%m-%d %H:%M:%S')
            pd = time.mktime(pd)
            pd = datetime.datetime.fromtimestamp(pd)
            lastPlay = datetime.datetime.now() - pd
            daysSincePlayed = lastPlay.days
    except Exception as e:
        Debug.myLog(u'Invalid lastPlayed field for ' + movieName + ' : ' +
                    lastPlayedField, xbmc.LOGDEBUG)
        traceBack = traceback.format_exc()
        Debug.myLog(traceBack, xbmc.LOGDEBUG)
        raise e
    return daysSincePlayed


'''
    When we don't have a trailer for a movie, we can
    see if TMDB has one.
'''


def searchForTrailerFromTMDB(title, year):
    Debug.myLog(u'searchForTrailerFromTMDB: title: ' + title, xbmc.LOGDEBUG)

    trailerId = ''
    data = {}
    data[u'api_key'] = Settings.getTmdbApiKey()
    data[u'page'] = '1'
    data[u'query'] = title
    data[u'language'] = 'en'
    url_values = urllib.parse.urlencode(data)
    url = 'https://api.themoviedb.org/3/search/movie'
    full_url = url + '?' + url_values
    statusCode, infostring = Utils.getJSON(full_url)

    for movie in infostring[u'results']:
        xbmc.log("searchForTrailerFromTMDB-result: " +
                 json.dumps(movie, indent=3), xbmc.LOGNOTICE)
        release_date = movie[u'release_date']
        xbmc.log(str(release_date), xbmc.LOGNOTICE)
        if (release_date == ''):
            break

        tmdb_release_date = time.strptime(release_date, '%Y-%m-%d')
        if (tmdb_release_date.tm_year == year):
            trailerId = movie[u'id']
            break
    return trailerId


class BlankWindow(xbmcgui.WindowXML):

    def onInit(self):
        pass


class TrailerWindow(xbmcgui.Window):  # (xbmcgui.WindowXMLDialog):

    trailer = None
    source = None

    @staticmethod
    def setNumberOfTrailersToPlay(numberOfTrailersToPlay):
        TrailerWindow._numberOfTrailersToPlay = numberOfTrailersToPlay

    # [optional] this function is only needed of you are passing optional data to your window
    def __init__(self, *args, **kwargs):
        # get the optional data and add it to a variable you can use elsewhere
        # in your script
        Debug.myLog("In TrailerWindow.__init__", xbmc.LOGDEBUG)
        self._numberOfTrailersToPlay = kwargs[u'numberOfTrailersToPlay']

    def doIt(self, numberOfTrailersToPlay):
        xbmc.log('In doIt', xbmc.LOGDEBUG)
        self._numberOfTrailersToPlay = numberOfTrailersToPlay

        windowstring = Utils.getKodiJSON(
            '{"jsonrpc":"2.0","method":"GUI.GetProperties",\
            "params":{"properties":["currentwindow"]},"id":1}')
        xbmc.log('Trailer_Window_id = ' +
                 str(windowstring[u'result'][u'currentwindow'][u'id']), xbmc.LOGNOTICE)
        global info

        Debug.myLog(
            'randomtrailers.TrailerWindow.onInit about to get TrailerManager.iterator',
            xbmc.LOGDEBUG)

        limitTrailersToPlay = False
        if self._numberOfTrailersToPlay == 0:
            limitTrailersToPlay = True

        trailerManager = BaseTrailerManager.getInstance()
        trailerIterator = iter(trailerManager)
        trailer = next(trailerIterator)
        try:
            while trailer is not None and not Utils.isShutdownRequested():
                Debug.myLog('randomtrailers.TrailerWindow.onInit got trailer to play: ' +
                            trailer.get(Constants.MOVIE_TRAILER), xbmc.LOGDEBUG)

                TrailerWindow.trailer = trailer

                self.source = trailer.get(Constants.MOVIE_SOURCE)
                Debug.myLog(u'ShowInfoDetail: ', str(Settings.getShowInfoDetail()) + ' source: ' +
                            self.source, xbmc.LOGDEBUG)
                showInfoWindow = False
                if Settings.getShowInfoDetail() and self.source != Constants.MOVIE_FOLDER_SOURCE:
                    Debug.myLog(u'TrailerWindow Show Info', xbmc.LOGDEBUG)
                    showInfoWindow = True

                if showInfoWindow:
                    # TODO- prefetch this
                    xbmc.log(u'About to show Info Dialog', xbmc.LOGDEBUG)
                    # w = InfoWindow('script-DialogVideoInfo.xml',
                    #               Constants.ADDON_PATH, 'default', '720p')
                    xbmc.log(u'About to make Info Dialog modal', xbmc.LOGDEBUG)
                    # w.doModal()
                    xbmc.log(u'Made Info Dialog modal', xbmc.LOGDEBUG)

                    Debug.myLog(
                        'randomtrailers.TrailerWindow ShowInfoDetail exitRequested', xbmc.LOGDEBUG)

                if not Utils.isShutdownRequested():
                    Debug.myLog(
                        'About to play: ' + trailer.get(Constants.MOVIE_TRAILER), xbmc.LOGDEBUG)
                    xbmc.Player().play(trailer.get(Constants.MOVIE_TRAILER))
                    xbmc.sleep(5000)
                    #xbmc.Player().play('/movies/XBMC/Movies/30s/Is My Face Red (1932)-trailer.mp4')
                    # xbmc.Player().play('plugin://plugin.video.youtube/?action=play_video&videoid=fAIX12F6958')
                if showInfoWindow:
                    xbmc.log(u'About to delete Info Dialog', xbmc.LOGDEBUG)
                    #del w
                    xbmc.log(u'Deleted Info Dialog', xbmc.LOGDEBUG)

                else:
                    xbmc.log(u'About show Brief Info', xbmc.LOGDEBUG)
                    self.overlayBriefMovieInfoOverTrailer(
                        Settings.getHideTrailerTitle(), trailer)
                    xbmc.log(u'Showed Brief Info', xbmc.LOGDEBUG)

                # If user exits while playing trailer, for a
                # movie in the library, then play the movie
                #
                # if Utils.isShutdownRequested():
                #    Debug.myLog(
                #        'randomtrailers.TrailerWindow exitRequested', xbmc.LOGDEBUG)
                #    xbmc.Player().play(trailer[u'file'])

                while xbmc.Player().isPlaying():
                    xbmc.sleep(250)

                if not showInfoWindow:
                    xbmc.log(u'About to Hide Brief Info', xbmc.LOGDEBUG)
                    self.overlayBriefMovieInfoOverTrailer(False)
                    xbmc.log(u'Hid Brief Info', xbmc.LOGDEBUG)

                trailer = next(trailerIterator)

                if limitTrailersToPlay:
                    self._numberOfTrailersToPlay -= 1
                    if self.numberOfTrailersToPlay < 1:
                        break
        finally:
            xbmc.log(u'About to close TrailerWindow', xbmc.LOGDEBUG)
            self.close()
            xbmc.log(u'Closed TrailerWindow', xbmc.LOGDEBUG)
            xbmc.log(u'About to stop xbmc.Player', xbmc.LOGDEBUG)
            xbmc.Player().stop()
            xbmc.log(u'Stopped xbmc.Player', xbmc.LOGDEBUG)

    def onInit(self):
        xbmc.log('In randomtrailers.TrailerWindow.onInit', xbmc.LOGNOTICE)
        '''
        windowstring = Utils.getKodiJSON(
            '{"jsonrpc":"2.0","method":"GUI.GetProperties",\
            "params":{"properties":["currentwindow"]},"id":1}')
        xbmc.log('Trailer_Window_id = ' +
                 str(windowstring[u'result'][u'currentwindow'][u'id']), xbmc.LOGNOTICE)
        global info

        self.numberOfTrailersToPlay = TrailerWindow._numberOfTrailersToPlay
        Debug.myLog(
            'randomtrailers.TrailerWindow.onInit about to get TrailerManager.iterator',
            xbmc.LOGDEBUG)

        limitTrailersToPlay = False
        if self.numberOfTrailersToPlay == 0:
            limitTrailersToPlay = True

        #trailerManager = BaseTrailerManager.getInstance()
        #trailerIterator = iter(trailerManager)
        #trailer = next(trailerIterator)
        trailer = {Constants.MOVIE_TITLE: u'A Title',
                   Constants.MOVIE_TRAILER: u'bogus path',
                   Constants.ITUNES_TRAILER_TYPE: u'trailer file',
                   Constants.MOVIE_SOURCE:
                   Constants.MOVIE_FOLDER_SOURCE,
                   Constants.MOVIE_FANART: u'',
                   Constants.MOVIE_THUMBNAIL: u'',
                   Constants.MOVIE_FILE: u'',
                   Constants.MOVIE_YEAR: u''}
        try:
            while trailer is not None and not Utils.isShutdownRequested():
                Debug.myLog('randomtrailers.TrailerWindow.onInit got trailer to play: ' +
                            trailer.get(Constants.MOVIE_TRAILER), xbmc.LOGDEBUG)

                TrailerWindow.trailer = trailer

                self.source = trailer.get(Constants.MOVIE_SOURCE)
                Debug.myLog(u'ShowInfoDetail: ', str(Settings.getShowInfoDetail()) + ' source: ' +
                            self.source, xbmc.LOGDEBUG)
                showInfoWindow = False
                if Settings.getShowInfoDetail() and self.source != Constants.MOVIE_FOLDER_SOURCE:
                    Debug.myLog(u'TrailerWindow Show Info', xbmc.LOGDEBUG)
                    showInfoWindow = True

                if showInfoWindow:
                    # TODO- prefetch this
                    xbmc.log(u'About to show Info Dialog', xbmc.LOGDEBUG)
                    w = InfoWindow('script-DialogVideoInfo.xml',
                                   Constants.ADDON_PATH, 'default', '720p')
                    xbmc.log(u'About to make Info Dialog modal', xbmc.LOGDEBUG)
                    w.doModal()
                    xbmc.log(u'Made Info Dialog modal', xbmc.LOGDEBUG)

                    Debug.myLog(
                        'randomtrailers.TrailerWindow ShowInfoDetail exitRequested', xbmc.LOGDEBUG)

                if not Utils.isShutdownRequested():
                    # xbmc.Player().play(trailer.get(Constants.MOVIE_TRAILER))
                    #xbmc.Player().play('/movies/XBMC/Movies/30s/Is My Face Red (1932)-trailer.mp4')
                    xbmc.Player().play('plugin://plugin.video.youtube/?action=play_video&videoid=fAIX12F6958')
                if showInfoWindow:
                    xbmc.log(u'About to delete Info Dialog', xbmc.LOGDEBUG)
                    del w
                    xbmc.log(u'Deleted Info Dialog', xbmc.LOGDEBUG)

                else:
                    xbmc.log(u'About show Brief Info', xbmc.LOGDEBUG)
                    self.overlayBriefMovieInfoOverTrailer(
                        Settings.getHideTrailerTitle(), trailer)
                    xbmc.log(u'Showed Brief Info', xbmc.LOGDEBUG)

                # If user exits while playing trailer, for a
                # movie in the library, then play the movie
                #
                # if Utils.isShutdownRequested():
                #    Debug.myLog(
                #        'randomtrailers.TrailerWindow exitRequested', xbmc.LOGDEBUG)
                #    xbmc.Player().play(trailer[u'file'])

                while xbmc.Player().isPlaying():
                    xbmc.sleep(250)

                if not showInfoWindow:
                    xbmc.log(u'About to Hide Brief Info', xbmc.LOGDEBUG)
                    self.overlayBriefMovieInfoOverTrailer(False)
                    xbmc.log(u'Hid Brief Info', xbmc.LOGDEBUG)

                #trailer = next(trailerIterator)

                if limitTrailersToPlay:
                    self.numberOfTrailersToPlay -= 1
                    if self.numberOfTrailersToPlay < 1:
                        break
        finally:
            xbmc.log(u'About to close TrailerWindow', xbmc.LOGDEBUG)
            self.close()
            xbmc.log(u'Closed TrailerWindow', xbmc.LOGDEBUG)
            xbmc.log(u'About to stop xbmc.Player', xbmc.LOGDEBUG)
            xbmc.Player().stop()
            xbmc.log(u'Stopped xbmc.Player', xbmc.LOGDEBUG)

    '''

    def onAction(self, action):

        xbmc.log('In randomtrailers.TrailerWindow.onAction', xbmc.LOGNOTICE)
        ACTION_PREVIOUS_MENU = 10
        ACTION_BACK = 92
        ACTION_ENTER = 7
        ACTION_I = 11
        ACTION_LEFT = 1
        ACTION_RIGHT = 2
        ACTION_UP = 3
        ACTION_DOWN = 4
        ACTION_TAB = 18
        ACTION_M = 122
        ACTION_Q = 34

        global movie_file

        trailer = TrailerWindow.trailer

        movie_file = ''
        xbmc.log('trailerAction: ' + str(action), xbmc.LOGNOTICE)
        xbmc.log(str(action.getId()), xbmc.LOGNOTICE)
        if action == ACTION_Q:
            strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                trailer[Constants.MOVIE_TITLE]
            xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

        if action == ACTION_PREVIOUS_MENU or action == ACTION_LEFT or action == ACTION_BACK:
            xbmc.Player().stop()
            Utils.setExitRequested()
            self.close()

        if action == ACTION_RIGHT or action == ACTION_TAB:
            xbmc.Player().stop()

        if action == ACTION_ENTER:
            Utils.setExitRequested()
            xbmc.Player().stop()
            movie_file = trailer.get(u'file', u'')
            # self.getControl(38011).setVisible(False)
            self.close()

        if action == ACTION_M:
            self.getControl(38011).setVisible(True)
            xbmc.sleep(2000)
            # self.getControl(38011).setVisible(False)

        if action == ACTION_I or action == ACTION_UP:
            if self.source != Constants.MOVIE_SOURCE:
                # self.getControl(38011).setVisible(False)
                # w = InfoWindow('script-DialogVideoInfo.xml',
                #               Constants.ADDON_PATH, 'default', '720p')
                xbmc.Player().pause()
                # w.doModal()
                xbmc.Player().pause()
            # self.getControl(38011).setVisible(Settings.getHideTrailerTitle())
        pass

    '''
        Overlay the playing trailer with basic information about the movie
    '''


'''
    def overlayBriefMovieInfoOverTrailer(self, visible, trailer=None):
        Debug.myLog('About to  change visibility of overlay', xbmc.LOGDEBUG)
        if visible:
            movieSource = trailer.get(
                Constants.MOVIE_SOURCE, u'Unknown Source')
            movieTitle = trailer.get(
                Constants.MOVIE_TITLE, u'Unknown Title')
            trailerType = trailer.get(
                Constants.ITUNES_TRAILER_TYPE, u'Unknown movie type')
            movieYear = trailer.get(
                Constants.MOVIE_YEAR_KEY, u'Unknown year')
            if movieSource == Constants.MOVIE_FOLDER_SOURCE:
                self.getControl(38011).setLabel(
                    u'[B]' + movieTitle + u' - ' + movieSource + u' ' + trailerType + u'[/B]')
            else:
                self.getControl(38011).setLabel(
                    u'[B]' + movieTitle + u' - ' + movieSource + u' ' + trailerType +
                    movieYear + u'[/B]')
        self.getControl(38011).setVisible(visible)
        Debug.myLog('Changed visibility of overlay', xbmc.LOGDEBUG)
'''
'''
class InfoWindow(xbmcgui.WindowXMLDialog):

    timeOut = True

    def onInit(self):
        try:
            trailer = TrailerWindow.trailer
            memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            xbmc.log('In randomtrailers.InfoWindow.onInit memory: ' +
                     str(memory), xbmc.LOGNOTICE)

            source = trailer[Constants.MOVIE_SOURCE]
            control = self.getControl(38001)
            thumbnail = trailer[u'thumbnail']
            xbmc.log("control: " + str(control) + " thumbnail: " +
                     str(thumbnail), xbmc.LOGNOTICE)
            control.setImage(thumbnail)
            self.getControl(38003).setImage(trailer["fanart"])
            title_font = getTitleFont()
            trailerType = trailer.get(Constants.ITUNES_TRAILER_TYPE, '')

            title_string = trailer["title"] + ' - ' + source + \
                ' ' + trailerType + ' - ' + str(trailer["year"])
            title = xbmcgui.ControlLabel(
                10, 40, 380, 40, title_string, title_font)
            title = self.addControl(title)
            title = self.getControl(38002)
            title.setAnimations(
                [('windowclose', 'effect=fade end=0 time=1000')])
            movieDirector = ''
            movieWriter = ''
            genres = ''
            if source == Constants.MOVIE_ITUNES_SOURCE:
                info = getInfo(trailer[Constants.MOVIE_TITLE], trailer[u'year'])
                writers = info[u'writer']
                directors = info[u'director']
                actors = info[u'cast']
                plot = info[u'plot']
                genres = info[u'genre']
                movieActor = ''
                actorcount = 0
                for actor in actors:
                    actorcount = actorcount + 1
                    movieActor = movieActor + actor + ", "
                    if actorcount == 8:
                        break
                if not movieActor == '':
                    movieActor = movieActor[:-2]
            else:
                plot = trailer["plot"]
                writers = trailer["writer"]
                directors = trailer["director"]
                actors = trailer["cast"]
                movieActor = ''
                actorcount = 0
                if source == Constants.MOVIE_LIBRARY_SOURCE:
                    for actor in actors:
                        actorcount = actorcount + 1
                        movieActor = movieActor + actor[u'name'] + ", "
                        if actorcount == 8:
                            break
                    if not movieActor == '':
                        movieActor = movieActor[:-2]
                else:
                    movieActor = ''
                    actorcount = 0
                    for actor in actors:
                        actorcount = actorcount + 1
                        movieActor = movieActor + actor + ", "
                        if actorcount == 8:
                            break
                    if not movieActor == '':
                        movieActor = movieActor[:-2]
            for director in directors:
                movieDirector = movieDirector + director + ", "
            if not movieDirector == '':
                movieDirector = movieDirector[:-2]
            for writer in writers:
                movieWriter = movieWriter + writer + ", "
            if not movieWriter == '':
                movieWriter = movieWriter[:-2]
            self.getControl(38005).setLabel(movieDirector)
            self.getControl(38006).setLabel(movieActor)
            self.getControl(38005).setLabel(movieDirector)
            self.getControl(38007).setLabel(movieWriter)
            self.getControl(38009).setText(plot)
            movieStudio = ''
            if source == Constants.MOVIE_ITUNES_SOURCE:
                studios = trailer["studio"]
                movieStudio = studios
            if source == Constants.MOVIE_LIBRARY_SOURCE or source == Constants.MOVIE_TMDB_SOURCE:
                studios = trailer["studio"]
                for studio in studios:
                    movieStudio = movieStudio + studio + ", "
                    if not movieStudio == '':
                        movieStudio = movieStudio[:-2]
            self.getControl(38010).setLabel(movieStudio)
            movieGenre = ''
            if source == Constants.MOVIE_LIBRARY_SOURCE or source == Constants.MOVIE_TMDB_SOURCE:
                genres = trailer["genre"]
            for genre in genres:
                movieGenre = movieGenre + genre + " / "
            if not movieGenre == '':
                movieGenre = movieGenre[:-3]
            runtime = ''
            if source == Constants.MOVIE_ITUNES_SOURCE:
                runtime = ''
            if source == Constants.MOVIE_LIBRARY_SOURCE:
                runtime = str(trailer["runtime"] / 60)
            if runtime != '':
                runtime = runtime + ' Minutes - '
            self.getControl(38011).setLabel(runtime + movieGenre)
            rating = Rating.getMPAArating(trailer.get(
                Constants.MOVIE_MPAA), trailer.get(u'adult'))

            if rating == Rating.RATING_G:
                imgRating = 'ratings/g.png'
            elif rating == Rating.RATING_PG:
                imgRating = 'ratings/pg.png'

            elif rating == Rating.RATING_PG_13:
                imgRating = 'ratings/pg13.png'

            elif rating == Rating.RATING_R:
                imgRating = 'ratings/r.png'

            elif rating == Rating.RATING_NC_17:
                imgRating = 'ratings/nc17.png'

            elif rating == Rating.RATING_NR:
                imgRating = 'ratings/notrated.png'

            self.getControl(38013).setImage(imgRating)

            # if InfoWindow.timeOut:
            if not Utils.isShutdownRequested():
                xbmc.sleep(Constants.TRAILER_INFO_DISPLAY_SECONDS)
        finally:
            self.close()

    def onAction(self, action):
        xbmc.log('In randomtrailers.InfoWindow.onAction', xbmc.LOGNOTICE)
        ACTION_PREVIOUS_MENU = 10
        ACTION_BACK = 92
        ACTION_ENTER = 7
        ACTION_I = 11
        ACTION_LEFT = 1
        ACTION_RIGHT = 2
        ACTION_UP = 3
        ACTION_DOWN = 4
        ACTION_TAB = 18
        ACTION_Q = 34

        xbmc.log('onAction trailer ' + str(action), xbmc.LOGNOTICE)
        global movie_file
        movie_file = ''

        if action == ACTION_PREVIOUS_MENU or action == ACTION_LEFT or action == ACTION_BACK:
            InfoWindow.timeOut = False
            xbmc.Player().stop()
            Utils.setExitRequested()
            self.close()

        if action == ACTION_Q:
            strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                TrailerWindow.trailer[Constants.MOVIE_TITLE]
            xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

        if action == ACTION_I or action == ACTION_DOWN:
            self.close()

        if action == ACTION_RIGHT or action == ACTION_TAB:
            xbmc.Player().stop()
            self.close()

        if action == ACTION_ENTER:
            movie_file = TrailerWindow.trailer["file"]
            xbmc.Player().stop()
            Utils.setExitRequested()
            self.close()
'''


def playTrailers():
    memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    xbmc.log(u'In randomtrailers.playTrailers memory: ' +
             str(memory), xbmc.LOGNOTICE)

    global movie_file
    global numberOfTrailersToPlay
    movie_file = ''
    numberOfTrailersToPlay = Settings.getNumberOfTrailersToPlay()
    GROUP_TRAILERS = False
    if Constants.ADDON.getSetting('group_trailers') == u'true':
        GROUP_TRAILERS = True
    GROUP_NUMBER = int(Constants.ADDON.getSetting('group_number'))
    trailersInGroup = GROUP_NUMBER
    GROUP_DELAY = Settings.getGroupDelay()
    suppressOpenCurtain = True  # Already played at startup
    while not Utils.isShutdownRequested():
        if not suppressOpenCurtain and Settings.getShowCurtains():
            xbmc.log(u'Playing OpenCurtain', xbmc.LOGDEBUG)
            xbmc.Player().play(Settings.getOpenCurtainPath())
            while xbmc.Player().isPlaying():
                xbmc.sleep(250)
            xbmc.log(u'Played OpenCurtain', xbmc.LOGDEBUG)

        suppressOpenCurtain = False  # Open curtain before each group
        while not Utils.isShutdownRequested():
            Utils.throwExceptionIfShutdownRequested()

            if GROUP_TRAILERS:
                trailersInGroup = trailersInGroup - 1

            Debug.myLog('About to instantiate TrailerWindow', xbmc.LOGDEBUG)
            # myTrailerWindow = TrailerWindow(
            #    u'script-trailerwindow.xml', Constants.ADDON_PATH, u'default',
            #    numberOfTrailersToPlay=numberOfTrailersToPlay)
            # myTrailerWindow.doModal()

            Debug.myLog('Created and showed BlankWindow', xbmc.LOGDEBUG)
            myTrailerWindow = TrailerWindow(
                numberOfTrailersToPlay=numberOfTrailersToPlay)
            myTrailerWindow.doIt(numberOfTrailersToPlay)

            del myTrailerWindow
            if GROUP_TRAILERS and trailersInGroup == 0:
                trailersInGroup = GROUP_NUMBER
                i = GROUP_DELAY
                while i > 0 and not Utils.isShutdownRequested():
                    xbmc.sleep(500)
                    i = i - 500

        if not Utils.isShutdownRequested():
            if Settings.getShowCurtains():
                xbmc.log(u'Playing CloseCurtain', xbmc.LOGDEBUG)
                xbmc.Player().play(Settings.getCloseCurtainPath())
                while xbmc.Player().isPlaying():
                    xbmc.sleep(250)
                xbmc.log(u'Played CloseCurtain', xbmc.LOGDEBUG)

        Utils.setExitRequested()


def check_for_xsqueeze():
    xbmc.log(u'In randomtrailers.check_for_xsqueeze', xbmc.LOGNOTICE)
    KEYMAPDESTFILE = os.path.join(xbmc.translatePath(
        u'special://userdata/keymaps'), "xsqueeze.xml")
    if os.path.isfile(KEYMAPDESTFILE):
        return True
    else:
        return False

#
# MAIN program
#

# Don't start if Kodi is busy playing something


try:

    if not xbmc.Player().isPlaying() and not check_for_xsqueeze():
        Debug.myLog(u'In randomtrailers.main', xbmc.LOGNOTICE)
        xbmc.log(u'Python path: ' + str(sys.path), xbmc.LOGDEBUG)
        watchdogThread = WatchDog()
        watchdogThread.start()
        trailerManager = BaseTrailerManager.getInstance()

        currentDialogId = xbmcgui.getCurrentWindowDialogId()
        currentWindowId = xbmcgui.getCurrentWindowId()
        Debug.myLog('CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                    u' ' + str(currentWindowId), xbmc.LOGDEBUG)

        # bs = BlankWindow(u'script-BlankWindow.xml',
        #                 Constants.ADDON_PATH, u'default',)
        xbmc.log(u'Activating BlankWindow', xbmc.LOGDEBUG)
        # bs.show()
        xbmc.log(u'Activated BlankWindow', xbmc.LOGDEBUG)

        if Settings.getAdjustVolume():
            muted = xbmc.getCondVisibility("Player.Muted")
            if not muted and Settings.getVolume() == 0:
                xbmc.executebuiltin(u'xbmc.Mute()')
            else:
                xbmc.executebuiltin(
                    u'XBMC.SetVolume(' + str(Settings.getVolume()) + ')')
        if Settings.getShowCurtains():
            xbmc.Player().play(Settings.getOpenCurtainPath())
            xbmc.sleep(500)

        # See if user wants to restrict trailers to a
        # genre

        if Settings.getFilterGenres():
            selectedGenre = promptForGenre()

        # Find trailers for movies in library

        Debug.myLog(u'getIncludeLibraryTrailers', xbmc.LOGDEBUG)

        if Settings.getIncludeLibraryTrailers():
            Debug.myLog(u'LibTrailers True', xbmc.LOGDEBUG)
            libInstance = LibraryTrailerManager.getInstance()
            libInstance.discoverBasicInformation(selectedGenre)
        else:
            Debug.myLog(u'LibTrailers False', xbmc.LOGDEBUG)

        # Manufacture trailer entries for folders which contain trailer
        # files. Note that files are assumed to be videos.
        if Settings.getIncludeTrailerFolders():
            FolderTrailerManager.getInstance().discoverBasicInformation(u'')

        if Settings.getIncludeItunesTrailers():
            ItunesTrailerManager.getInstance().discoverBasicInformation(u'')  # genre broken

        if Settings.getIncludeTMDBTrailers():
            TmdbTrailerManager.getInstance().discoverBasicInformation(selectedGenre)

        # Finish curtain playing before proceeding
        if Settings.getShowCurtains():
            while xbmc.Player().isPlaying():
                xbmc.sleep(250)

        playTrailers()
        #del bs
        if Settings.getAdjustVolume():
            muted = xbmc.getCondVisibility("Player.Muted")
            if muted and Settings.getVolume() == 0:
                xbmc.executebuiltin('xbmc.Mute()')
            else:
                xbmc.executebuiltin(
                    'XBMC.SetVolume(' + str(currentVolume) + ')')
    else:
        xbmc.log('Random Trailers: ' +
                 'Exiting Random Trailers Screen Saver Something is playing!!!!!!', xbmc.LOGNOTICE)
except AbortException:
    xbmc.log('Random Trailers: ' +
             'Exiting Random Trailers Screen Saver due to Kodi Abort!', xbmc.LOGNOTICE)
except Exception:
    Debug.logException()

if Utils.isAbortRequested():
    xbmc.Player().stop()
