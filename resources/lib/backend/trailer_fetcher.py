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
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import Utils
from common.debug_utils import Debug
from common.rt_utils import Playlist
from common.exceptions import AbortException, ShutdownException
from common.rt_utils import WatchDog
from settings import Settings
from common.logger import Trace, Logger

from backend.rating import Rating
from backend.genre import Genre
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

    def startFetchers(self, trailerManager):

        Debug.myLog(u'TrailerFetcher.startFetcher', xbmc.LOGDEBUG)
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
            Debug.myLog(
                u'TrailerFetcher.startFetcher started', xbmc.LOGDEBUG)

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
        while not self._trailerManager._trailersDiscovered.isSet():
            Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=0.5)

        while True:
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            Debug.myLog(
                u'TrailerFetcher.run waiting to fetch', xbmc.LOGDEBUG)
            trailer = self._trailerManager.getFromFetchQueue()
            Debug.myLog(u'TrailerFetcher.run got trailer: ' +
                        trailer[Movie.TITLE], xbmc.LOGDEBUG)
            self.fetchTrailerToPlay(trailer)

    def fetchTrailerToPlay(self, trailer):
        localLogger = self._logger.getMethodLogger(u'fetchTrailerToPlay')
        localLogger.debug(trailer[Movie.TITLE])
        self._startFetchTime = datetime.datetime.now()

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
            status, populatedTrailer = self.getTmdbTrailer(trailer[u'id'])
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            if status == Constants.TOO_MANY_TMDB_REQUESTS:
                pass
            elif populatedTrailer is not None:
                Debug.compareMovies(trailer, populatedTrailer)

                # TODO Rework this, I don't like blindly clobbering

                trailer.update(populatedTrailer)  # Remember what we found
        else:
            source = trailer[Movie.SOURCE]
            if source == Movie.LIBRARY_SOURCE:
                if trailer[Movie.TRAILER] == u'':  # no trailer search tmdb for one
                    trailerId = searchForTrailerFromTMDB(
                        trailer[Movie.TITLE], trailer[u'year'])
                    if trailerId != u'':

                        # Returns a tuple of dictionary objects for each movie
                        # found

                        status, newTrailerData = self.getTmdbTrailer(trailerId)
                        Monitor.getInstance().throwExceptionIfShutdownRequested()

                        if status == Constants.TOO_MANY_TMDB_REQUESTS or newTrailerData is None:
                            # Need to try again later
                            self._trailerManager.addToFetchQueue(trailer)
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

                    Debug.myLog(METHOD_NAME + u' iTunes response: ' +
                                json.dumps(iTunesResult, indent=3), xbmc.LOGDEBUG)

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

        movieId = trailer[Movie.TITLE] + \
            u'_' + str(trailer[Movie.YEAR])

        movieId = movieId.lower()
        keepNewTrailer = True
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
        Given the movieId from TMDB, query TMDB for trailer details and manufacture
        a trailer entry based on the results. The trailer itself will be a Youtube
        url.
    '''

    def getTmdbTrailer(self, movieId, trailerOnly=False):
        Debug.myLog(u'getTmdbTrailer movieId: ' +
                    str(movieId), xbmc.LOGDEBUG)

        trailer_url = u''
        trailerType = u''
        you_tube_base_url = u'plugin://plugin.video.youtube/?action=play_video&videoid='
        image_base_url = u'http://image.tmdb.org/t/p/'

        # Query The Movie DB for Credits, Trailers and Releases for the
        # Specified Movie ID. Many other details are returned as well

        data = {}
        data[u'append_to_response'] = u'credits,trailers,releases'
        data[u'api_key'] = Settings.getTmdbApiKey()
        url = u'http://api.themoviedb.org/3/movie/' + str(movieId)
        try:
            statusCode, tmdbResult = Utils.getJSON(url, params=data)
        except:
            Debug.myLog(traceback.format_exc(), xbmc.LOGERROR)
            return -1, None
        else:
            #
            # Grab first trailer
            #
            previousSize = 0
            for tmdbTrailer in tmdbResult[u'trailers'][u'youtube']:
                if Movie.SOURCE in tmdbTrailer:
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
            mpaa = u''
            for c in tmdbCountries:
                if c[u'iso_3166_1'] == 'US':
                    mpaa = c[u'certification']
            if mpaa == u'':
                mpaa = Rating.RATING_NR
            year = tmdbResult[u'release_date'][:-6]
            fanart = image_base_url + 'w380' + \
                str(tmdbResult[u'backdrop_path'])
            thumbnail = image_base_url + 'w342' + \
                str(tmdbResult[u'poster_path'])
            title = tmdbResult[Movie.TITLE]
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
                if s[u'name'] == Settings.getSpokenLanguage():
                    addMovie = True
            if not Settings.getIncludeAdult() and tmdbResult[u'adult'] == u'true':
                addMovie = False

            # Normalize rating

            mpaa = Rating.getMPAArating(mpaa, None)

            addMovie = Rating.checkRating(mpaa)
            if not addMovie:
                dictInfo = None
            else:
                dictInfo = {Movie.TITLE: title,
                            Movie.TRAILER: trailer_url,
                            Movie.YEAR: year,
                            Movie.STUDIO: studio,
                            Movie.MPAA: mpaa,
                            Movie.FILE: '',
                            Movie.THUMBNAIL: thumbnail,
                            Movie.FANART: fanart,
                            Movie.DIRECTOR: director,
                            Movie.WRITER: writer,
                            Movie.PLOT: plot,
                            Movie.CAST: cast,
                            Movie.RUNTIME: runtime,
                            Movie.GENRE: genre,
                            Movie.SOURCE: Movie.TMDB_SOURCE,
                            Movie.TYPE: trailerType}

        Debug.myLog(u'getTmdbTrailer exit : ' +
                    json.dumps(dictInfo, indent=3), xbmc.LOGDEBUG)

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

        trailerType = trailer.get(Movie.TYPE, u'')
        if trailerType != u'':
            trailerType = trailerType + u' - '

        year = str(trailer.get(Movie.YEAR), u'')
        if year != u'':
            year = u'(' + year + u')'

        titleString = (trailer[Movie.TITLE] + u' - ' +
                       trailer[Movie.SOURCE] +
                       ' ' + trailerType + year)
        detailTrailer[Movie.DETAIL_TITLE] = titleString

        info = None
        if source == Movie.ITUNES_SOURCE:
            info = getInfo(trailer[Movie.TITLE], trailer[u'year'])
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
        if source == Movie.LIBRARY_SOURCE or source == Movie.ITUNES_SOURCE:
            for actor in actors:
                if u'name' in actor:
                    actorcount += 1
                    movieActors = movieActors + actor[u'name'] + separator
                    separator = u', '
                if actorcount == 6:
                    break
        else:
            for actor in actors:
                actorcount += 1
                movieActors = movieActors + separator + actor
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
            trailer[Movie.RUNTIME] = info.get(Movie.RUNTIME, 0)

        if source == Movie.LIBRARY_SOURCE or source == Movie.ITUNES_SOURCE:
            if isinstance(trailer.get(Movie.RUNTIME), int):
                runtime = str(
                    trailer[Movie.RUNTIME] / 60) + u' Minutes'
        elif source == Movie.TMDB_SOURCE:
            if isinstance(trailer.get(Movie.RUNTIME), int):
                runtime = str(
                    trailer[Movie.RUNTIME]) + u' Minutes'

        return runtime


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

    # Note that iTunes is only missing:
    #
    # Plot, runtime, writers
    #
    data = {}
    data[u'query'] = title
    data[u'year'] = str(year)
    data[u'api_key'] = Settings.getTmdbApiKey()
    data[u'language'] = Settings.getLanguage()
    url = 'https://api.themoviedb.org/3/search/movie'
    statusCode, infostring = Utils.getJSON(url, params=data)

    if len(infostring[u'results']) > 0:
        results = infostring[u'results'][0]
        movieId = str(results[u'id'])
        if not movieId == u'':
            data = {}
            data[u'api_key'] = Settings.getTmdbApiKey()
            data[u'append_to_response'] = 'credits'
            url = 'https://api.themoviedb.org/3/movie/' + movieId
            statusCode, infostring = Utils.getJSON(url, params=data)
            director = []
            writer = []
            cast = []
            plot = u''
            runtime = u''
            genre = []
            plot = infostring[u'overview']
            runtime = infostring.get(u'runtime', u'0')
            if runtime is None or runtime == u'':
                runtime = u'0'
            runtime = int(runtime) * 60
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
    When we don't have a trailer for a movie, we can
    see if TMDB has one.
'''


def searchForTrailerFromTMDB(title, year):
    Debug.myLog(u'searchForTrailerFromTMDB: title: ' + title, xbmc.LOGDEBUG)

    trailerId = u''
    data = {}
    data[u'api_key'] = Settings.getTmdbApiKey()
    data[u'page'] = '1'
    data[u'query'] = title
    data[u'language'] = Settings.getLanguage()
    url = 'https://api.themoviedb.org/3/search/movie'
    statusCode, infostring = Utils.getJSON(url, params=data)

    for movie in infostring[u'results']:
        Debug.myLog("searchForTrailerFromTMDB-result: " +
                    json.dumps(movie, indent=3), xbmc.LOGNOTICE)
        release_date = movie[u'release_date']
        Debug.myLog(str(release_date), xbmc.LOGNOTICE)
        if (release_date == u''):
            break

        tmdb_release_date = time.strptime(release_date, '%Y-%m-%d')
        if (tmdb_release_date.tm_year == year):
            trailerId = movie[u'id']
            break
    return trailerId
