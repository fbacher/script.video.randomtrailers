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
from xml.dom.minidom import Node
from multiprocessing.pool import ThreadPool

#from six.moves.urllib.parse import urlparse, urlencode
#from six.moves.urllib.request import urlopen
#from six.moves.urllib.error import HTTPError
from kodi65 import addon
from kodi65 import utils
from common.monitor import Monitor
from common.rt_constants import Constants, Movie, RemoteTrailerPreference
from common.rt_utils import Utils
from common.debug_utils import Debug
from common.rt_utils import Playlist
from common.exceptions import AbortException, ShutdownException
from common.rt_utils import WatchDog
from settings import Settings
from common.tmdb_settings import TmdbSettings
from common.logger import Trace, Logger
from common.messages import Messages

from backend.rating import Rating
from backend.genre import Genre
from backend import backend_constants

import sys
import datetime
import io
import json
import os
import queue
import random
import re
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
#import xbmcwsgi
import xbmcdrm
import string


class TrailerFetcher(threading.Thread):

    NUMBER_OF_FETCHERS = 1
    _trailerFetchers = []

    def __init__(self, threadNamePrefix=u'', threadNameSuffix=u''):
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        threadName = threadNamePrefix + type(self).__name__ + threadNameSuffix
        super(TrailerFetcher, self).__init__(name=threadName)
        self._badTrailerPlaylist = Playlist.getPlaylist(
            Playlist.MISSING_TRAILERS_PLAYLIST, append=True)

    def startFetchers(self, trailerManager):
        localLogger = self._logger.getMethodLogger(u'startFetchers')

        localLogger.enter()
        WatchDog.registerThread(self)
        i = 0
        while i < self.NUMBER_OF_FETCHERS:
            i += 1
            trailerFetcher = TrailerFetcher(threadNamePrefix=type(trailerManager).__name__ + u' :',
                                            threadNameSuffix=str(i))
            trailerFetcher._trailerManager = trailerManager
            TrailerFetcher._trailerFetchers.append(trailerFetcher)
            WatchDog.registerThread(trailerFetcher)
            trailerFetcher.start()
            localLogger.debug(u'trailer fetcher started')

    def shutdownThread(self):
        #self._trailerManager = None
        pass

    def run(self):
        try:
            self.runWorker()
        except ShutdownException:
            return  # Just exit thread
        except Exception:
            Debug.logException()

    def runWorker(self):
        localLogger = self._logger.getMethodLogger(u'runWorker')

        while not self._trailerManager._trailersDiscovered.isSet():
            Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=0.5)

        while True:
            try:
                Monitor.getInstance().throwExceptionIfShutdownRequested()

                localLogger.debug(u'waiting to fetch')
                trailer = self._trailerManager.getFromFetchQueue()
                localLogger.debug(u'got trailer:', trailer[Movie.TITLE])
                self.fetchTrailerToPlay(trailer)
            except (AbortException, ShutdownException) as e:
                raise sys.exc_info()
            except Exception as e:
                localLogger.logException(e)

    def fetchTrailerToPlay(self, trailer):
        localLogger = self._logger.getMethodLogger(u'fetchTrailerToPlay')
        localLogger.debug(trailer[Movie.TITLE], trailer[Movie.SOURCE],
                          trailer[Movie.TRAILER])
        self._startFetchTime = datetime.datetime.now()
        keepNewTrailer = True

        if trailer[Movie.TRAILER] == Movie.TMDB_SOURCE:
            #
            # Entries with a'trailer' value of Movie.TMDB_SOURCE are trailers
            # which are not from any movie in Kodi but come from
            # TMDB, similar to iTunes or YouTube.
            #
            # Query TMDB for the details and replace the
            # temporary trailer entry with what is discovered.
            # Note that the Movie.SOURCE value will be
            # set to Movie.TMDB_SOURCE
            #
            #Debug.dumpJSON(text=u'Original trailer:', data=trailer)
            status, populatedTrailer = self.getTmdbTrailer(trailer[u'id'])
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            if status == Constants.TOO_MANY_TMDB_REQUESTS:
                return
            elif populatedTrailer is not None:
                trailer = populatedTrailer

                #Debug.compareMovies(trailer, populatedTrailer)

                # Remember what we found. Only worry about the fields that
                # we need for detail display
                # self.cloneFields(populatedTrailer, trailer, Movie.TRAILER,
                #                 Movie.SOURCE, Movie.TITLE,
                #                 Movie.FANART, Movie.PLOT,
                #                 Movie.FILE, Movie.THUMBNAIL,
                #                 Movie.YEAR, Movie.TYPE,
                #                 Movie.RUNTIME)
            else:
                # Looks like there isn't an appropriate trailer for
                # this movie.
                self._badTrailerPlaylist.recordPlayedTrailer(
                    trailer, msg=u' Not Found')
                keepNewTrailer = False

        else:
            source = trailer[Movie.SOURCE]
            if source == Movie.LIBRARY_SOURCE:
                if trailer[Movie.TRAILER] == u'':  # no trailer search tmdb for one
                    uniqueId = trailer.get(Movie.UNIQUE_ID, None)
                    tmdbId = None
                    if uniqueId is not None:
                        tmdbId = uniqueId.get(Movie.UNIQUE_ID_TMDB, None)

                    if tmdbId is None or tmdbId == u'':
                        tmdbId = getTmdbIDFromTitleYear(
                            trailer[Movie.TITLE], trailer[u'year'])
                    else:
                        pass
                    if tmdbId == u'':
                        self._badTrailerPlaylist.recordPlayedTrailer(
                            trailer, msg=u' Movie not found at tmdb')
                    else:
                        # Ignore any verification failures. Trust the library (genres,
                        # languages, etc.
                        status, newTrailerData = self.getTmdbTrailer(
                            tmdbId, ignoreFailures=True)
                        Monitor.getInstance().throwExceptionIfShutdownRequested()

                        if status == Constants.TOO_MANY_TMDB_REQUESTS or status == -1:
                            # Give up playing this trailer this time around. It will
                            # still be available for display later.
                            return

                        trailer[Movie.TYPE] = u'TMDB trailer'
                        trailer[Movie.TRAILER] = \
                            newTrailerData[Movie.TRAILER]
                        Debug.compareMovies(trailer, newTrailerData)

            elif source == Movie.ITUNES_SOURCE:
                '''
                try:
                    statusCode, iTunesResult = Utils.getJSON(
                        trailer[Movie.TRAILER], headers={'User-Agent': 'iTunes'})

                    Debug.dumpJSON(text=METHOD_NAME + u' iTunes response:', data=iTunesResult)


                    # match = re.compile(
                    #    '<a class="movieLink" href="(.+?)"', re.DOTALL).findall(content)
                    # urlTemp = match[0]
                    # url = urlTemp[:urlTemp.find("?")].replace(
                    #   "480p", "h" + Settings.getQuality()) + "|User-Agent=iTunes/9.1.1"
                except Exception as e:
                    url = u''
                    Debug.logException(e)
                '''
        localLogger.debug('Exiting movie:',  trailer.get(Movie.TITLE))

        # If no trailer possible then remove it from further consideration

        if keepNewTrailer:
            if Movie.YEAR not in trailer:
                pass

            movieId = trailer[Movie.TITLE] + u'_' + str(trailer[Movie.YEAR])

            movieId = movieId.lower()
            trailerManager = self._trailerManager.getBaseInstance()

            Monitor.getInstance().throwExceptionIfShutdownRequested()
            with trailerManager._aggregateTrailersByNameDateLock:
                if trailer[Movie.TRAILER] == u'':
                    keepNewTrailer = False
                elif movieId in trailerManager._aggregateTrailersByNameDate:
                    keepNewTrailer = False
                    trailerInDictionary = trailerManager._aggregateTrailersByNameDate[movieId]

                    localLogger.debug(u'Duplicate Movie id: ' + movieId + u' found in: ' +
                                      trailerInDictionary[Movie.SOURCE])

                    # Always prefer the local trailer
                    source = trailer[Movie.SOURCE]
                    if source == Movie.LIBRARY_SOURCE:                        #
                        # Joy, two copies, both with trailers. Toss the new one.
                        #
                        pass
                    elif source == Movie.FOLDER_SOURCE:
                        keepNewTrailer = True
                    elif source == Movie.ITUNES_SOURCE:
                        keepNewTrailer = True
                    elif source == Movie.TMDB_SOURCE:
                        keepNewTrailer = True

            if keepNewTrailer:
                trailer[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_COMPLETE
                trailerManager._aggregateTrailersByNameDate[movieId] = trailer

            else:
                self._trailerManager.removeDiscoveredTrailer(trailer)

        if keepNewTrailer:
            fullyPopulatedTrailer = self.getDetailInfo(trailer)
            self._trailerManager.addToReadyToPlayQueue(fullyPopulatedTrailer)

        self._stopFetchTime = datetime.datetime.now()
        self._stopAddReadyToPlayTime = datetime.datetime.now()
        discoveryTime = self._stopFetchTime - self._startFetchTime
        queueTime = self._stopAddReadyToPlayTime - self._stopFetchTime
        Trace.log(localLogger.getMsgPrefix(), u'took: ' + str(discoveryTime.seconds) +
                  u' QueueTime: ' + str(queueTime.seconds) +
                  u' movie: ' +
                  trailer.get(Movie.TITLE) + u' Kept: '
                  + str(keepNewTrailer), trace=Trace.STATS)
    '''
        Called in two situations:
            1) When a local movie does not have any trailer information
            2) When a TMDB search for multiple movies is used, which does NOT return
               detail information, including trailer info.

        Given the movieId from TMDB, query TMDB for details and manufacture
        a trailer entry based on the results. The trailer itself will be a Youtube
        url.
    '''

    def getTmdbTrailer(self, movieId, ignoreFailures=False):
        localLogger = self._logger.getMethodLogger(u'getTmdbTrailer')
        localLogger.debug(u'movieId:', movieId)

        trailerType = u''
        you_tube_base_url = backend_constants.YOUTUBE_URL_PREFIX
        image_base_url = u'http://image.tmdb.org/t/p/'
        includeAdult = u'false'
        if Settings.getIncludeAdult():
            includeAdult = u'true'

        allowedGenres = Genre.getInstance().getGenres(Genre.TMDB_DATABASE)
        allowedTags = Genre.getInstance().getTags(Genre.TMDB_DATABASE)
        voteComparison, voteValue = Settings.getAvgVotePreference()

        # Since we may leave earlly, populate with dummy data
        messages = Messages.getInstance()
        missingDetail = messages.getMsg(Messages.MISSING_DETAIL)
        dictInfo = {}
        dictInfo[Movie.DISCOVERY_STATE] = Movie.NOT_FULLY_DISCOVERED
        dictInfo[Movie.TITLE] = messages.getMsg(Messages.MISSING_TITLE)
        dictInfo[Movie.ORIGINAL_TITLE] = u''
        dictInfo[Movie.YEAR] = 0
        dictInfo[Movie.STUDIO] = [missingDetail]
        dictInfo[Movie.MPAA] = u'NR'
        dictInfo[Movie.THUMBNAIL] = u''
        dictInfo[Movie.TRAILER] = u''
        dictInfo[Movie.FANART] = u''
        dictInfo[Movie.DIRECTOR] = [missingDetail]
        dictInfo[Movie.WRITER] = [missingDetail]
        dictInfo[Movie.PLOT] = missingDetail
        dictInfo[Movie.CAST] = [missingDetail]
        dictInfo[Movie.RUNTIME] = 0
        dictInfo[Movie.GENRE] = [missingDetail]
        dictInfo[Movie.DETAIL_TAGS] = [missingDetail]
        dictInfo[Movie.RATING] = 0
        dictInfo[Movie.VOTES] = 0
        dictInfo[Movie.ADULT] = False
        dictInfo[Movie.SOURCE] = Movie.TMDB_SOURCE
        dictInfo[Movie.TYPE] = u'Trailer'

        # Query The Movie DB for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        data = {}
        data[u'append_to_response'] = u'credits,releases,videos,keywords'
        data[u'api_key'] = Settings.getTmdbApiKey()
        url = u'http://api.themoviedb.org/3/movie/' + str(movieId)

        dumpMsg = localLogger.getMsgPrefix() + u' movieId: ' + str(movieId)
        try:
            statusCode, tmdbResult = Utils.getJSON(
                url, params=data, dumpResults=False, dumpMsg=dumpMsg)
            if statusCode != 0:
                if ignoreFailures:
                    return statusCode, dictInfo
                return statusCode, None,
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            localLogger.logException()
            if ignoreFailures:
                return -1, dictInfo
            return -1, None

        try:
            #
            # First, deal with the trailer. If there is no trailer, there
            # is no point continuing.
            #
            # Grab longest trailer that is in the appropriate language
            #
            bestSizeMap = {u'Featurette': None, u'Clip': None, u'Trailer': None,
                           u'Teaser': None}
            for tmdbTrailer in tmdbResult.get(u'videos', {u'results': []}).get('results', []):
                if tmdbTrailer[u'site'] != u'YouTube':
                    continue

                # TODO: if Settings.getAllowForeignLanguages(), then get primary
                # lang
                if tmdbTrailer[u'iso_639_1'] != Settings.getLang_iso_639_1():
                    continue

                trailerType = tmdbTrailer[u'type']
                size = tmdbTrailer[u'size']
                if trailerType not in bestSizeMap:
                    localLogger.debug(
                        u'Unrecognized trailer type:', trailerType)

                if bestSizeMap.get(trailerType, None) is None:
                    bestSizeMap[trailerType] = tmdbTrailer

                if bestSizeMap[trailerType][u'size'] < size:
                    bestSizeMap[trailerType] = tmdbTrailer

            # Prefer trailer over other types

            trailerKey = None
            if bestSizeMap[u'Trailer'] is not None:
                trailerKey = bestSizeMap[u'Trailer'][u'key']
                trailerType = u'Trailer'
            elif Settings.getIncludeFeaturettes() and bestSizeMap[u'Featurette'] is not None:
                trailerKey = bestSizeMap[u'Featurette'][u'key']
                trailerType = u'Featurette'
            elif Settings.getIncludeClips() and bestSizeMap[u'Clip'] is not None:
                trailerKey = bestSizeMap[u'Clip'][u'key']
                trailerType = u'Clip'

            dictInfo[Movie.TYPE] = trailerType

            # No point going on if we don't have a  trailer

            if trailerKey is None:
                if not ignoreFailures:
                    return 0, None
            else:
                trailerUrl = you_tube_base_url + tmdbTrailer[u'key']
                dictInfo[Movie.TRAILER] = trailerUrl

            currentLanguageFound = False
            for languageEntry in tmdbResult[u'spoken_languages']:
                if languageEntry['iso_639_1'] == Settings.getLang_iso_639_1():
                    currentLanguageFound = True
                    break

            if (not currentLanguageFound and not Settings.getAllowForeignLanguages()
                    and not ignoreFailures):
                return 0, None

            tmdbCountries = tmdbResult[u'releases'][u'countries']
            mpaa = u''
            for c in tmdbCountries:
                if c[u'iso_3166_1'] == Settings.getLang_iso_3166_1():
                    mpaa = c[u'certification']
            if mpaa == u'':
                mpaa = Rating.RATING_NR
            dictInfo[Movie.MPAA] = mpaa

            # release_date TMDB key is different from Kodi's
            try:
                year = tmdbResult[u'release_date'][:-6]
                year = int(year)
            except Exception:
                year = 0

            dictInfo[Movie.YEAR] = year

            fanart = image_base_url + 'w380' + \
                str(tmdbResult[u'backdrop_path'])
            dictInfo[Movie.FANART] = fanart

            thumbnail = image_base_url + 'w342' + \
                str(tmdbResult[u'poster_path'])
            dictInfo[Movie.THUMBNAIL] = thumbnail

            title = tmdbResult[Movie.TITLE]
            if title is not None:
                dictInfo[Movie.TITLE] = title

            plot = tmdbResult[u'overview']
            if plot is not None:
                dictInfo[Movie.PLOT] = plot

            runtime = tmdbResult.get(Movie.RUNTIME, 0)
            if runtime is None:
                runtime = 0
            runtime = runtime * 60  # Kodi measures in seconds

            dictInfo[Movie.RUNTIME] = runtime

            studios = tmdbResult[u'production_companies']
            studio = []
            for s in studios:
                studio.append(s[u'name'])

            if studio is not None:
                dictInfo[Movie.STUDIO] = studio

            tmdbCastMembers = tmdbResult[u'credits'][u'cast']
            cast = []
            for castMember in tmdbCastMembers:
                fakeCastEntry = {}
                fakeCastEntry[u'name'] = castMember[u'name']
                fakeCastEntry[u'character'] = castMember[u'character']
                cast.append(fakeCastEntry)

            dictInfo[Movie.CAST] = cast

            tmdbCrewMembers = tmdbResult[u'credits'][u'crew']
            director = []
            writer = []
            for crewMember in tmdbCrewMembers:
                if crewMember[u'job'] == u'Director':
                    director.append(crewMember[u'name'])
                if crewMember[u'department'] == 'Writing':
                    writer.append(crewMember[u'name'])

            dictInfo[Movie.DIRECTOR] = director
            dictInfo[Movie.WRITER] = writer

            # Vote is float on a 0-10 scale

            voteAverage = tmdbResult[u'vote_average']
            votes = tmdbResult[u'vote_count']

            if voteAverage is not None:
                dictInfo[Movie.RATING] = voteAverage
            if votes is not None:
                dictInfo[Movie.VOTES] = votes

            genreFound = False
            tagFound = False
            genres = tmdbResult[u'genres']
            genre = []
            for g in genres:
                genre.append(g[u'name'])
                if g in allowedGenres:
                    genreFound = True

            dictInfo[Movie.GENRE] = genre

            keywords = tmdbResult.get(u'keywords', [])
            tmbResultTags = keywords.get(u'keywords', [])
            tags = []
            for t in tmbResultTags:
                tags.append(t[u'name'])
                if t in allowedTags:
                    tagFound = True

            dictInfo[Movie.DETAIL_TAGS] = tags

            addMovie = True
            if not tagFound and not genreFound:
                addMovie = False

            if voteComparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if voteComparison == RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                    if voteAverage < voteValue:
                        addMovie = False
                elif voteComparison == RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                    if voteAverage > voteValue:
                        addMovie = False

            languageFound = False
            for s in tmdbResult[u'spoken_languages']:
                if s[u'iso_639_1'] == Settings.getLang_iso_639_1():
                    languageFound = True

            if not languageFound:
                addMovie = False

            # originalLanguage = tmdbResult[u'original_language']
            originalTitle = tmdbResult[u'original_title']
            if originalTitle is not None:
                dictInfo[Movie.ORIGINAL_TITLE] = originalTitle

            adultMovie = tmdbResult[u'adult'] == u'true'
            if adultMovie and not includeAdult:
                addMovie = False

            dictInfo[Movie.ADULT] = adultMovie
            dictInfo[Movie.SOURCE] = Movie.TMDB_SOURCE

            # Normalize rating

            mpaa = Rating.getMPAArating(mpaa, None)
            if not Rating.checkRating(mpaa):
                addMovie = False
            #Debug.dumpJSON(text=u'getTmdbTrailer exit:', data=dictInfo)

            if not addMovie and not ignoreFailures:
                dictInfo = None

        except (AbortException, ShutdownException) as e:
            raise sys.exc_info()
        except Exception as e:
            jsonText = json.dumps(tmdbResult, indent=3, sort_keys=True)
            localLogger.logException(e, msg=jsonText)
            if not ignoreFailures:
                dictInfo = None

        return 0, dictInfo

    def getDetailInfo(self, trailer):
        detailTrailer = dict()
        detailTrailer[Movie.DETAIL_ENTRY] = trailer
        self.cloneFields(trailer, detailTrailer, Movie.TRAILER,
                         Movie.SOURCE, Movie.TITLE,
                         Movie.FANART, Movie.PLOT,
                         Movie.FILE, Movie.THUMBNAIL,
                         Movie.YEAR, Movie.TYPE)
        source = trailer[Movie.SOURCE]

        detailTrailer.setdefault(Movie.THUMBNAIL, u'')

        titleString = Messages.getInstance().getFormatedTitle(trailer)
        detailTrailer[Movie.DETAIL_TITLE] = titleString

        info = None
        if source == Movie.ITUNES_SOURCE:
            movieId = getTmdbIDFromTitleYear(
                trailer[Movie.TITLE], trailer[u'year'])
            info = self.getTmdbTrailer(movieId, ignoreFailures=True)

            # TODO: Verify that more fields should be cloned

            self.cloneFields(info, detailTrailer, Movie.PLOT)

        movieWriters = self.getWriters(trailer, info, source)
        detailTrailer[Movie.DETAIL_WRITERS] = movieWriters

        movieDirectors = self.getDirectors(trailer, info, source)
        detailTrailer[Movie.DETAIL_DIRECTORS] = movieDirectors

        actors = self.getActors(trailer, info, source)
        detailTrailer[Movie.DETAIL_ACTORS] = actors

        movieStudios = self.getStudios(trailer, info, source)
        detailTrailer[Movie.DETAIL_STUDIOS] = movieStudios

        genres = self.getGenres(trailer, info, source)
        detailTrailer[Movie.DETAIL_GENRES] = genres

        runTime = self.getRuntime(trailer, info, source)
        detailTrailer[Movie.DETAIL_RUNTIME] = runTime

        rating = Rating.getMPAArating(trailer.get(
            Movie.MPAA), trailer.get(Movie.ADULT))
        detailTrailer[Movie.DETAIL_RATING] = rating

        imgRating = Rating.getImageForRating(rating)
        detailTrailer[Movie.DETAIL_RATING_IMAGE] = imgRating

        trailer[Movie.DISCOVERY_STATE] = Movie.DISCOVERY_READY_TO_DISPLAY

        return detailTrailer

    def cloneFields(self, trailer, detailTrailer, *argv):
        for arg in argv:
            detailTrailer[arg] = trailer.get(arg, arg + u' was None at clone')

    def getWriters(self, trailer, info, source):
        if source == Movie.ITUNES_SOURCE:
            writers = info.get(Movie.WRITER, [])
        else:
            writers = trailer.get(Movie.WRITER, [])

        movieWriter = u''
        separator = u''
        for writer in writers:
            movieWriter = movieWriter + separator + writer
            separator = u', '

        return movieWriter

    def getDirectors(self, trailer, info, source):

        directors = trailer.get(Movie.DIRECTOR, [])

        movieDirectors = u''
        separator = u''
        for director in directors:
            movieDirectors = movieDirectors + separator + director
            separator = u', '

        return movieDirectors

    def getActors(self, trailer, info, source):
        movieActors = u''
        actorcount = 0
        separator = u''
        actors = trailer.get(Movie.CAST, [])
        for actor in actors:
            if u'name' in actor:
                actorcount += 1
                movieActors = movieActors + actor[u'name'] + separator
                separator = u', '
            if actorcount == 6:
                break

        return movieActors

    def getStudios(self, trailer, info, source):
        studiosString = u''
        if (source == Movie.LIBRARY_SOURCE or source == Movie.TMDB_SOURCE
                or source == Movie.ITUNES_SOURCE):

            separator = u''
            studios = trailer.get(Movie.STUDIO, [])
            for studio in studios:
                studiosString = studiosString + separator + studio
                separator = u', '

        return studiosString

    def getGenres(self, trailer, info, source):
        genres = u''

        if (source == Movie.LIBRARY_SOURCE or Movie.ITUNES_SOURCE or source == Movie.TMDB_SOURCE):
            separator = u''
            for genre in trailer.get(Movie.GENRE, []):
                genres = genres + separator + genre
                separator = u' / '

        return genres

    def getPlot(self, trailer, info, source):
        plot = u''
        if Movie.PLOT not in trailer or trailer[Movie.PLOT] == u'':
            trailer[Movie.PLOT] = info.get(Movie.PLOT, u'')

        if source == Movie.ITUNES_SOURCE:
            plot = info.get(Movie.PLOT, u'')
        else:
            plot = trailer.get(Movie.PLOT, u'')

        return plot

    def getRuntime(self, trailer, info, source):
        runtime = u''
        if Movie.RUNTIME not in trailer or trailer[Movie.RUNTIME] == 0:
            if info is not None:
                trailer[Movie.RUNTIME] = info.get(Movie.RUNTIME, 0)

        if isinstance(trailer.get(Movie.RUNTIME), int):
            runtime = str(
                trailer[Movie.RUNTIME] / 60) + u' Minutes'

        # if source == Movie.LIBRARY_SOURCE or source == Movie.ITUNES_SOURCE:
        #    if isinstance(trailer.get(Movie.RUNTIME), int):
        #        runtime = str(
        #            trailer[Movie.RUNTIME] / 60) + u' Minutes'
        # elif source == Movie.TMDB_SOURCE:
        #    if isinstance(trailer.get(Movie.RUNTIME), int):
        #        runtime = str(
        #            trailer[Movie.RUNTIME]) + u' Minutes'

        return runtime


'''
    The user selects which movie genres that they wish to see
    trailers for. If any genre for a movie was not requested
    by the user, then don't show the trailer.
'''


def genreCheck(movieMPAGenreLabels):
    localLogger = Logger(u'genreCheck')

    localLogger.debug(u'movieMPAGenreLabels:', movieMPAGenreLabels)
    passed = True

    # Eliminate movies that have a genre that was
    # NOT selected

    for genre in Genre.getEnabledGenres():
        if not genre.genreSetting and (genre.genreMPAALabel not in movieMPAGenreLabels):
            passed = False
            localLogger.debug('genre failed:', genre.genreSetting)
            break

    return passed


'''
    When we don't have a trailer for a movie, we can
    see if TMDB has one.
'''


def getTmdbIDFromTitleYear(title, year):
    localLogger = Logger(u'getTmdbIDFromTitleYear')

    localLogger.debug(u'getTmdbIDFromTitleYear: title:', title)

    trailerId = 0
    data = {}
    data[u'api_key'] = Settings.getTmdbApiKey()
    data[u'page'] = '1'
    data[u'query'] = title
    data[u'language'] = Settings.getLang_iso_639_1()
    data[u'year'] = year

    includeAdult = u'false'
    if Settings.getIncludeAdult():
        includeAdult = u'true'
    data[u'include_adult'] = includeAdult

    url = 'https://api.themoviedb.org/3/search/movie'
    statusCode, infostring = Utils.getJSON(url, params=data)

    results = infostring.get(u'results', [])
    if len(results) > 1:
        localLogger.debug(u'Unexpectedly got multiple matching movies:', title)
    for movie in results:
        release_date = movie.get(u'release_date', u'')
        Debug.myLog(str(release_date), xbmc.LOGNOTICE)

        videoAvailable = infostring.get(u'video', None)
        if videoAvailable is None or videoAvailable:
            trailerId = movie.get(u'id', 0)

    return trailerId
