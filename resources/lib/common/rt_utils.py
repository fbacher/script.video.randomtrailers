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
from six.moves.urllib.parse import urlparse

from common.rt_constants import Constants
from common.rt_constants import Movie
from common.logger import Logger, Trace, logEntry, logExit, logEntryExit
from common.debug_utils import Debug
from common.exceptions import AbortException, ShutdownException
from common.monitor import Monitor
import common.kodi_thread as kodi_thread
from settings import Settings
from backend import backend_constants

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
import xbmcdrm
import string


class Utils:
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exitRequested = False
    _abortRequested = False

    '''
        Note that iTunes and TMDB each have rate limiting:
            TMDB is limited over a period of 10 seconds
            iTunes is limited to 20 requests/minute and 200
            results per search.
            
            For iTunes see:
         https://affiliate.itunes.apple.com/resources/documentation/itunes-store-web-service-search-api/#overview
             All iTunes results are JSON UTF-8
             
    '''

    # In order to track the rate of requests over a minute, we have to
    # track the timestamp of each request made in the last minute.
    #
    # Keep in mind for both TMDB and iTunes, that other plugins may be
    # making requests

    TMDB_REQUEST_INDEX = 0
    ITUNES_REQUEST_INDEX = 1
    ROTTEN_TOMATOES_REQUEST_INDEX = 2
    _requestWindow = []
    _requestWindow.append(datetime.timedelta(seconds=10))  # 10 seconds TMDB
    _requestWindow.append(datetime.timedelta(minutes=1))  # 1 minute iTunes
    _requestWindow.append(datetime.timedelta(minutes=1)
                          )  # TODO: supply correct info
    _logger = Logger(u'Utils')

    # Each entry in the above _requestsOverTime* lists is
    # a list with the timestamp and running request count:

    TIME_STAMP = 0
    REQUEST_COUNT = 1

    @staticmethod
    def getDelayTime(destination):
        #
        # We track the timestamp of each request made as well as the running
        # request count for each destination (TMDB or ITUNES).
        # Here we need to determine what, if any delay is needed so that we
        # don't cause rate-limit errors. (Yeah, we could ignore them, until
        # we get the error and the and then we would still need to calculate
        # a delay).
        #
        # The last request is at the end of the list. Starting from the
        # front of the list (the oldest entry), toss out every entry that
        # is older than our wait window.
        #
        destinationData = Utils.DestinationData.getData(destination)
        requests = destinationData._requestsOverTime
        now = datetime.datetime.now()
        windowExpirationTime = now - Utils._requestWindow[destination]
        lastRequestCount = 0
        if len(requests) > 0:
            lastRequestCount = requests[len(requests) - 1][Utils.REQUEST_COUNT]

        index = 0
        oldestEntry = None
        while index < len(requests):
            oldestEntry = requests[0]
            was = oldestEntry[Utils.TIME_STAMP]
            #
            # Purge expired entries
            #
            if was < windowExpirationTime:
                requests = requests[1:]
            else:
                break

        #
        # Have we hit the maximum number of requests over this
        # time period?

        delay = datetime.timedelta(0)
        if len(requests) > 0:
            startingRequestCount = oldestEntry[Utils.REQUEST_COUNT]
            if lastRequestCount - startingRequestCount < destinationData._requestLimit:
                delay = datetime.timedelta(0)  # Now, we should be ok
            else:
                alreadyWaited = now - oldestEntry[Utils.TIME_STAMP]
                delay = Utils._requestWindow[destination] - alreadyWaited

                if delay < datetime.timedelta(0):
                    localLogger = Utils._logger.getMethodLogger(
                        u'getDelayTime')
                    localLogger.error(
                        u'Logic error: timer delay should be > 0')

        return delay.total_seconds()

    @staticmethod
    def recordRequestTimestamp(destination, failed=False):
        destinationData = Utils.DestinationData.getData(destination)
        requests = destinationData._requestsOverTime
        now = datetime.datetime.now()

        lastRequestCount = 0
        if len(requests) > 0:
            lastIndex = len(requests) - 1
            lastRequestCount = requests[lastIndex][Utils.REQUEST_COUNT]

        if failed:
            lastRequestCount += destinationData._requestLimit
        else:
            lastRequestCount += 1

        newEntry = []
        newEntry.append(now)
        newEntry.append(lastRequestCount)
        requests.append(newEntry)

    @staticmethod
    def dumpDelayInfo(destination):
        localLogger = Utils._logger.getMethodLogger(u'dumpDelayInfo')
        destinationData = Utils.DestinationData.getData(destination)
        requests = destinationData._requestsOverTime
        for request in requests:
            timeStamp = request[Utils.TIME_STAMP]
            requestCount = request[Utils.REQUEST_COUNT]

            localLogger.debug(u'timestamp:', timeStamp,
                              u'count:', requestCount)

    class DestinationData:
        _destinationData = []

        def __init__(self):
            self._requestCount = 0  # Limit is tmdbRequestLmit every 10 seconds

            # Reported in header from every request response to tmdb
            self._remainingRequests = 0  # header.get(u'X-RateLimit-Remaining')
            self._rateLimit = 0  # header.get('X-RateLimit-Limit')  # Was 40

            # Limit will be lifted at this time, in epoch seconds

            self._requestLimitResetTime = 0  # header.get('X-RateLimit-Reset')
            self._requestsOverTime = []

        @staticmethod
        def initialize():
            tmdbData = Utils.DestinationData()
            tmdbData._requestLimit = 44
            Utils.DestinationData._destinationData.append(tmdbData)
            iTunesData = Utils.DestinationData()
            Utils.DestinationData._destinationData.append(iTunesData)
            iTunesData._requestLimit = 20

            # TODO: supply correct info

            rottonTomatoesData = Utils.DestinationData()
            Utils.DestinationData._destinationData.append(rottonTomatoesData)
            rottonTomatoesData._requestLimit = 20

        @staticmethod
        def getData(destination):
            if len(Utils.DestinationData._destinationData) == 0:
                Utils.DestinationData.initialize()

            return Utils.DestinationData._destinationData[destination]

    # Headers needs to be native string (not unicode on v2)
    @staticmethod
    def getJSON(url, secondAttempt=False, dumpResults=False, headers={}, params={}, timeout=2.0):
        localLogger = Utils._logger.getMethodLogger(u'getJSON')

        destinationString = u''
        if u'themoviedb' in url:
            destinationString = u'TMDB'
            requestIndex = Utils.TMDB_REQUEST_INDEX
            site = u'TMDB'
        elif backend_constants.APPLE_URL_PREFIX in url:
            destinationString = u'iTunes'
            requestIndex = Utils.ITUNES_REQUEST_INDEX
            site = u'iTunes'
        elif backend_constants.ROTTEN_TOMATOES_URL_PREFIX in url:
            destinationString = u'RottonTomatoes'
            requestIndex = Utils.ROTTEN_TOMATOES_REQUEST_INDEX
            site = u'Tomatoes'

        timeDelay = Utils.getDelayTime(requestIndex)

        # Some TMDB api calls do NOT give RATE-LIMIT info in header responses
        # In such cases we detect the failure from the status code and retry
        # with a forced sleep of 10 seconds, which is the maximum required
        # wait time.

        if timeDelay > 0:
            Trace.log(u' Waiting for JSON request to ' + destinationString +
                      u' for ' + str(timeDelay) + u' seconds', trace=Trace.STATS)
        Monitor.getInstance().throwExceptionIfShutdownRequested(timeDelay)

        destinationData = Utils.DestinationData.getData(requestIndex)
        secondsUntilReset = destinationData._requestLimitResetTime - \
            int(time.time())
        destinationData._requestCount += 1
        requestsToURL = destinationData._requestCount

        if (destinationData._remainingRequests < 10) and (secondsUntilReset < 2):
            localLogger.info(
                u'Sleeping two seconds to avoid traffic limit.')
            Monitor.getInstance().throwExceptionIfShutdownRequested(2.0)

        requestFailed = True
        try:
            response = requests.get(
                url.encode(u'utf-8'), headers=headers, params=params, timeout=timeout)
            requestFailed = False  # We could change our minds
        except Exception as e:
            # Retry once
            # TODO: Move this after full analysis, not nested

            localLogger.logException(e)
            Trace.log(localLogger.getMsgPrefix(), u'request to', destinationString,
                      u'FAILED total requests:', requestsToURL, trace=Trace.STATS)
            Utils.dumpDelayInfo(requestIndex)
            if secondAttempt:
                statusCode = -1
                jsonText = u''
            return statusCode, jsonText

        try:
            statusCode = u''
            jsonText = u''
            returnedHeader = {}
            statusCode = response.status_code
            text = response.text
            jsonText = response.json()
            returnedHeader = response.headers
        except Exception as e:
            requestFailed = True
            localLogger.error(u'Unable to parse jsonText from site: ' + site +
                              u' jsonText: ' + jsonText)
            localLogger.error(u' response text:  ' + text)
            localLogger.error(u' returned header: ' + str(returnedHeader))
            localLogger.logException(e)
            Utils.dumpDelayInfo(requestIndex)

        localLogger.debug(u'Headers from : ' + site +
                          u' ' + str(returnedHeader))

        # TODO- delete or control by setting or logger

        secondsUntilReset = destinationData._requestLimitResetTime - \
            int(time.time())
        destinationData._requestCount += 1
        requestsToURL = destinationData._requestCount

        tmp = returnedHeader.get(u'X-RateLimit-Remaining')
        if tmp is not None:
            destinationData._remainingRequests = int(tmp)

        tmp = returnedHeader.get('X-RateLimit-Limit')
        if tmp is not None:
            destinationData._rateLimit = int(tmp)

        # Limit will be lifted at this time, in epoch seconds
        tmp = returnedHeader.get('X-RateLimit-Reset')
        if tmp is not None:
            destinationData._requestLimitResetTime = int(tmp)
        else:
            # Some calls don't return X-RateLimit-Reset, in those cases there
            # should be Retry-After indicating how many more seconds to wait
            # before traffic can resume

            retryAfterValue = 0
            tmp = returnedHeader.get(u'Retry-After')
            msg = u''
            if tmp is not None:
                retryAfterValue = int(time.time()) + int(tmp)
                destinationData._requestLimitResetTime = retryAfterValue
                requestFailed = True

            if requestIndex == Utils.TMDB_REQUEST_INDEX:
                localLogger.debug(
                    u'TMDB response header missing X-RateLimit info.', msg)

        try:
            status = jsonText.get(u'status_code')
            if status is not None:
                statusCode = status

            # Debug.myLog(u'StatusCode from jsonText: ' + str(status), xbmc.LOGINFO)
        except Exception as e:
            pass

        # Debug.myLog(u'getJSON jsonText: ' + jsonText.__class__.__name__ +
        #            u' ' + json.dumps(jsonText), xbmc.LOGDEBUG)

        if ((statusCode == Constants.TOO_MANY_TMDB_REQUESTS)
                and (requestIndex == Utils.TMDB_REQUEST_INDEX)):  # Too many requests,
            localLogger.info(u'Request rate to TMDB exceeds limits ('
                             + str(destinationData._requestLimit) +
                             u' every 10 seconds). Consider getting API Key. This session\'s requests: '
                             + str(destinationData._requestCount))
            Trace.log(localLogger.getMsgPrefix(), u' request failed source:',
                      destinationString, u'total requests:', requestsToURL, trace=Trace.STATS)

        Utils.recordRequestTimestamp(requestIndex, failed=requestFailed)
        if requestFailed:
            #
            # Retry only once
            #

            if not secondAttempt:
                try:
                    statusCode, jsonText = Utils.getJSON(url, secondAttempt=True,
                                                         headers=headers, params=params,
                                                         timeout=0.50)
                    requestFailed = True
                finally:
                    Utils.recordRequestTimestamp(
                        requestIndex, failed=requestFailed)

        # else:
        #    Debug.myLog(u'requests: ' + str(Constants.tmdbRequestCount))

        if dumpResults:
            localLogger.debug(u'JASON DUMP:')
            localLogger.debug(json.dumps(jsonText, indent=3, sort_keys=True))
        return statusCode, jsonText

    @staticmethod
    def getKodiJSON(query):
        jsonText = xbmc.executeJSONRPC(query)
        jsonText = json.loads(jsonText, encoding=u'utf-8')
        return jsonText


class WatchDog(threading.Thread):

    # TODO:- Cleanup, eliminate deathIsNigh

    # Must use _threadsToWatchLock object to access!
    _threadsToWatch = []
    _threadsToWatchLock = threading.RLock()

    _reaperThread = None
    _watchDogThread = None

    @staticmethod
    def create():
        WatchDog._reaperThread = None
        WatchDog._deathIsNigh = threading.Event()
        WatchDog._completedShutdownPhase1 = threading.Event()

        WatchDog._watchDogThread = WatchDog(False)
        WatchDog._watchDogThread.start()
        WatchDog._createReaper()
        WatchDog._logger = Logger(u'WatchDog')

    @staticmethod
    def _createReaper():
        WatchDog._reaperThread = WatchDog(True)
        WatchDog._reaperThread.start()

    @staticmethod
    def registerThread(thread):
        with WatchDog._threadsToWatchLock:
            WatchDog._threadsToWatch.append(thread)

    def __init__(self, threadReaper):

        if threadReaper:
            threadName = type(self).__name__ + u'_threadReaper'
        else:
            threadName = type(self).__name__

        self._logger = Logger(threadName)
        self._abortTime = None
        super(WatchDog, self).__init__(group=None, target=None,
                                       name=threadName,
                                       args=(), kwargs=None, verbose=None)

    def run(self):
        try:
            if self is WatchDog._reaperThread:
                self.reapDeadThreads()
            else:
                self.waitForDeathSignal()
        except:
            self._logger.logException()

    def reapDeadThreads(self):
        '''
            While waiting for shutdown, reap any zombie threads
        '''
        localLogger = self._logger.getMethodLogger(
            u'reapDeadThreads')
        localLogger.enter()
        Monitor.getInstance().waitForStartupComplete()
        #
        # During normal operation, check for threads to harvest every 5
        # minutes, but during shutdown, check continuously
        while not Monitor.getInstance().waitForShutdown(3000):
            try:
                self.joinWithCompletedThreads(0.01, reaperThread=True)
            except Exception as e:
                self._logger.logException(e)

    @logEntry
    def waitForDeathSignal(self):
        localLogger = self._logger.getMethodLogger(
            u'waitForDeathSignal')
        Monitor.getInstance().waitForShutdown()

        self._abortTime = datetime.datetime.now()
        localLogger.debug(u'WatchDog: Shutting Down!')

        with WatchDog._threadsToWatchLock:
            for aThread in WatchDog._threadsToWatch:
                try:
                    localLogger.debug(u'WatchDog stopping',
                                      aThread.getName())
                    aThread.shutdownThread()
                except:
                    localLogger.logException()

        localLogger.debug(u'WatchDog: _deathIsNigh!')
        WatchDog._reaperThread.join(2.5)
        if WatchDog._reaperThread.isAlive():
            WatchDog._deathIsNigh.set()  # Force exit
            #
            # TODO: don't handle Monitor as special
            #
            Monitor.getInstance().shutdownThread()
            if WatchDog._reaperThread.isAlive():
                WatchDog._reaperThread.join()
            WatchDog._reaperThread = None

        localLogger.debug(u'Joined with reaperThread')
        duration = datetime.datetime.now() - self._abortTime
        localLogger.debug(u'Waited ' + str(duration.seconds),
                          u'seconds to exit after shutdown request.')
        WatchDog._completedShutdownPhase1.set()

    def joinWithCompletedThreads(self, delay, reaperThread=True):
        localLogger = self._logger.getMethodLogger(
            u'joinWithCompletedThreads')
        localLogger.debug(u'Enter reaperThread:', reaperThread)

        reaped = 0
        with WatchDog._threadsToWatchLock:
            for aThread in WatchDog._threadsToWatch:
                try:
                    # Bug out
                    if WatchDog._deathIsNigh.isSet():
                        break

                    if aThread.isAlive():
                        if Monitor.getInstance().isShutdownRequested():
                            localLogger.debug(u'Watchdog joining with ' +
                                              aThread.getName())
                        aThread.join(delay)
                    if not aThread.isAlive():
                        WatchDog._threadsToWatch.remove(aThread)
                        localLogger.debug(u'Thread: ' + aThread.getName() +
                                          u' REAPED.')

                except Exception as e:
                    localLogger.logException(e)
            remaining = len(WatchDog._threadsToWatch)

        if reaperThread or reaped > 0:
            Trace.log(str(reaped) + u' threads REAPed: ' +
                      str(remaining) + u' threads remaining', trace=Trace.TRACE)
        return remaining

    @staticmethod
    def shutdown():
        localLogger = WatchDog._logger.getMethodLogger(u'shutdown')
        Monitor.getInstance().shutDownRequested()
        Debug.dumpAllThreads()

        WatchDog._completedShutdownPhase1.wait()
        Debug.dumpAllThreads()
        with WatchDog._threadsToWatchLock:
            if WatchDog._watchDogThread is not None:
                if WatchDog._watchDogThread.isAlive():
                    localLogger.debug(
                        u'Attempting to join with WatchDogThread')
                    WatchDog._watchDogThread.join()
                    localLogger.debug(u'watchDogThread joined')
                    WatchDog._watchDogThread = None
        Debug.dumpAllThreads()

        localLogger.exit()


WatchDog.create()


class Playlist:
    VIEWED_PLAYLIST_FILE = u'Viewed.playlist'
    PLAYLIST_PREFIX = u'RandomTrailer_'
    PLAYLIST_SUFFIX = u'.playlist'
    _playlistLock = threading.Condition()
    _playlists = {}

    def __init__(self, *args, **kwargs):
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')

        if len(args) == 0:
            localLogger.error(
                u' Playlist constructor requires an argument')
            return None

        playlistName = args[0]
        self._playlistName = playlistName
        append = kwargs.get(u'append', True)
        self.playlistName = playlistName
        path = Settings.getAddon().DATA_PATH + u'/' + playlistName
        if append:
            mode = u'at'
        else:
            mode = u'wt'
        self._file = io.open(path, mode=mode, buffering=1, newline=None)

    @staticmethod
    def getPlaylist(playlistName, append=True):
        playlist = None
        with Playlist._playlistLock:
            if Playlist._playlists.get(playlistName) is None:
                Playlist._playlists[playlistName] = Playlist(
                    playlistName, append=append)
            playlist = Playlist._playlists.get(playlistName)
        return playlist

    def recordPlayedTrailer(self, trailer):
        name = trailer.get(Movie.TITLE, u'unknown Title')
        year = u'(' + str(trailer.get(Movie.YEAR, u'unknown Year')) + u')'
        movieType = trailer.get(Movie.TYPE, u'Unknown MovieType')
        if name is None:
            name = u'name is None'
        if year is None:
            year = u'year is None'
        if movieType is None:
            movieType = u'movieType is None'

        self._file.writelines(name + u'  ' + year + u'  # ' +
                              movieType + u'\n')

    def writeLine(self, line):
        self._file.writelines(line + u'\n')

    def close(self):
        self._file.close()
        with Playlist._playlistLock:
            del Playlist._playlists[self._playlistName]

    @staticmethod
    def shutdown():
        try:
            with Playlist._playlistLock:
                for playlist in Playlist._playlists.itervalues():
                    playlist._file.close()
        finally:
            with Playlist._playlistLock:
                Playlist._playlists = {}
