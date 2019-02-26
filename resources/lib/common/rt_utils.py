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
    _tmdbRequestCount = 0  # Limit is tmdbRequestLmit every 10 seconds
    _iTunesRequestCount = 0  # Limit is 20/minute

    # Reported in header from every request response to tmdb
    _tmdbRemainingRequests = 0  # header.get(u'X-RateLimit-Remaining')
    _tmdbRequestLmit = 0  # header.get('X-RateLimit-Limit')  # Was 40

    # Limit will be lifted at this time, in epoch seconds

    _tmdbRequestLimitResetTime = 0  # header.get('X-RateLimit-Reset')

    # In order to track the rate of requests over a minute, we have to
    # track the timestamp of each request made in the last minute.
    #
    # Keep in mind for both TMDB and iTunes, that other plugins may be
    # making requests

    TMDB_REQUEST_INDEX = 0
    ITUNES_REQUEST_INDEX = 1
    _requestWindow = []
    _requestWindow.append(datetime.timedelta(seconds=10))  # 10 seconds TMDB
    _requestWindow.append(datetime.timedelta(minutes=1))  # 1 minute iTunes
    _requestLimit = []
    _requestLimit.append(44)
    _requestLimit.append(20)
    _requestsOverTime = []
    _requestsOverTime.append([])
    _requestsOverTime.append([])

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
        requests = Utils._requestsOverTime[destination]
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

        delay = 0
        if len(requests) > 0:
            startingRequestCount = oldestEntry[Utils.REQUEST_COUNT]
            if lastRequestCount - startingRequestCount < Utils._requestLimit[destination]:
                delay = 0  # Now, we should be ok
            else:
                alreadyWaited = now - oldestEntry[Utils.TIME_STAMP]
                delay = Utils._requestWindow[destination] - alreadyWaited
                if delay < 0:
                    Debug.myLog(
                        u'Logic error: timer delay should be > 0', xbmc.LOGERROR)

        return delay

    @staticmethod
    def recordRequestTimestamp(destination, failed=False):
        requests = Utils._requestsOverTime[destination]
        now = datetime.datetime.now()

        lastRequestCount = 0
        if len(requests) > 0:
            lastIndex = len(requests) - 1
            lastRequestCount = requests[lastIndex][Utils.REQUEST_COUNT]

        if failed:
            lastRequestCount += Utils._requestLimit[destination]
        else:
            lastRequestCount += 1

        newEntry = []
        newEntry.append(now)
        newEntry.append(lastRequestCount)
        requests.append(newEntry)

    @staticmethod
    def getJSON(url, forcedTMDBSleep=False, headers={}, params={}, timeout=0.5):
        METHOD_NAME = u'Utils. getJSON'
        talkingToTMDB = False
        talkingToiTunes = False
        destinationString = u''
        if u'themoviedb' in url:
            talkingToTMDB = True
            destinationString = u'TMDB'
            requestIndex = Utils.TMDB_REQUEST_INDEX
        elif backend_constants.APPLE_URL_PREFIX in url:
            talkingToiTunes = True
            destinationString = u'iTunes'
            requestIndex = Utils.ITUNES_REQUEST_INDEX

        timeDelay = Utils.getDelayTime(requestIndex)

        # Some TMDB api calls do NOT give RATE-LIMIT info in header responses
        # In such cases we detect the failure from the status code and retry
        # with a forced sleep of 10 seconds, which is the maximum required
        # wait time.

        if timeDelay > 0:
            Trace.log(u' Waiting for JSON request to ' + destinationString +
                      u' for ' + str(timeDelay) + u' seconds', Trace.STATS)
        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested(timeDelay)
        site = u'TMDB'
        if talkingToiTunes:
            site = u'iTunes'

        if talkingToTMDB:

            secondsUntilReset = Utils._tmdbRequestLimitResetTime - \
                int(time.time())
            if (Utils._tmdbRemainingRequests < 10) and (secondsUntilReset < 2):
                Debug.myLog(
                    u'Sleeping two seconds to avoid TMBD traffic limit.', xbmc.LOGINFO)
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested(2.0)

            Utils._tmdbRequestCount += 1
            requestsToURL = Utils._tmdbRequestCount
        if talkingToiTunes:
            Utils._iTunesRequestCount += 1
            requestsToURL = Utils._iTunesRequestCount

        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=timeout)

        except Exception as e:
            # Retry once
            Trace.log(METHOD_NAME + u' request to ' + destinationString + u' FAILED' +
                      u' total requests: ' + str(requestsToURL),
                      Trace.STATS)
            if not forcedTMDBSleep:
                statusCode, jsonText = Utils.getJSON(
                    url, forcedTMDBSleep=True, headers=headers)
            else:
                Debug.logException(e)
                statusCode = -1
                jsonText = u''
            return statusCode, jsonText
        finally:
            Utils.recordRequestTimestamp(requestIndex)

        try:
            statusCode = u''
            jsonText = u''
            returnedHeader = {}
            statusCode = response.status_code
            text = response.text
            jsonText = response.json()
            returnedHeader = response.headers
        except Exception as e:
            Debug.myLog(METHOD_NAME + u' Unable to parse jsonText from site: ' + site +
                        u' jsonText: ' + jsonText, xbmc.LOGERROR)
            Debug.myLog(METHOD_NAME + u' response text:  ' +
                        text, xbmc.LOGERROR)
            Debug.myLog(METHOD_NAME + u' returned header: ' + str(returnedHeader),
                        xbmc.LOGERROR)
            Debug.logException(e)

        Debug.myLog(u'Headers from : ' + site + u' ' + str(returnedHeader),
                    xbmc.LOGDEBUG)

        # TODO- delete or control by setting or logger

        if True:  # talkingToTMDB:
            tmp = returnedHeader.get(u'X-RateLimit-Remaining')
            if tmp is not None:
                Utils._tmdbRemainingRequests = int(tmp)
                if talkingToiTunes:
                    Trace.log(u'Got X-RateLimit-Remaining from iTunes: ' +
                              tmp, Trace.STATS)

            tmp = returnedHeader.get('X-RateLimit-Limit')
            if tmp is not None:
                Utils._tmdbRequestLmit = int(tmp)
                if talkingToiTunes:
                    Trace.log(u'Got X-RateLimit-Limit from iTunes: ' +
                              tmp, Trace.STATS)

            # Limit will be lifted at this time, in epoch seconds
            tmp = returnedHeader.get('X-RateLimit-Reset')
            if tmp is not None:
                Utils._tmdbRequestLimitResetTime = int(tmp)
                if talkingToiTunes:
                    Trace.log(
                        'Got X-RateLimit-Reset from iTunes: ' + tmp, Trace.STATS)
            else:
                # Some calls don't return X-RateLimit-Reset, in those cases there
                # should be Retry-After indicating how many more seconds to wait
                # before traffic can resume

                retryAfterValue = 0
                tmp = returnedHeader.get(u'Retry-After')
                msg = u''
                if tmp is not None:
                    if talkingToiTunes:
                        Trace.log('Got Retry-After from iTunes: ' + tmp,
                                  Trace.STATS)
                    retryAfterValue = int(tmp)
                    Utils._tmdbRequestLimitResetTime = int(
                        time.time()) + retryAfterValue
                    msg = u'Retry-After ' + str(retryAfterValue) + ' present.'

                Debug.myLog(
                    u'TMDB response header missing X-RateLimit info.' + msg, xbmc.LOGDEBUG)

        try:
            status = jsonText.get(u'status_code')
            if status is not None:
                statusCode = status

            # Debug.myLog(u'StatusCode from jsonText: ' + str(status), xbmc.LOGINFO)
        except Exception as e:
            pass

        # Debug.myLog(u'getJSON jsonText: ' + jsonText.__class__.__name__ +
        #            u' ' + json.dumps(jsonText), xbmc.LOGDEBUG)

        if statusCode == Constants.TOO_MANY_TMDB_REQUESTS:  # Too many requests,
            Debug.myLog(u'Request rate to TMDB exceeds limits ('
                        + str(Utils._tmdbRequestLmit) +
                        u' every 10 seconds). Consider getting API Key. This session\'s requests: '
                        + str(Utils._tmdbRequestCount), xbmc.LOGINFO)
            Trace.log(METHOD_NAME + u' request failed source: ' + destinationString +
                      u' total requests: ' + str(requestsToURL), Trace.STATS)
            #
            # Retry only once
            #

            failed = True
            if not forcedTMDBSleep:
                try:
                    statusCode, jsonText = Utils.getJSON(url, forcedTMDBSleep=True,
                                                         headers=headers, params=params,
                                                         timeout=0.25)
                    failed = False
                finally:
                    Utils.recordRequestTimestamp(requestIndex, failed=failed)

        # else:
        #    Debug.myLog(u'requests: ' + str(Constants.tmdbRequestCount))

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
        Monitor.getSingletonInstance().waitForStartupComplete()
        #
        # During normal operation, check for threads to harvest every 5
        # minutes, but during shutdown, check continuously
        while not Monitor.getSingletonInstance().waitForShutdown(3000):
            try:
                self.joinWithCompletedThreads(0.01, reaperThread=True)
            except Exception as e:
                self._logger.logException(e)

    @logEntry
    def waitForDeathSignal(self):
        localLogger = self._logger.getMethodLogger(
            u'waitForDeathSignal')
        Monitor.getSingletonInstance().waitForShutdown()

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
                        if Monitor.getSingletonInstance().isShutdownRequested():
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
                      str(remaining) + u' threads remaining', Trace.TRACE)
        return remaining

    @staticmethod
    def shutdown():
        localLogger = WatchDog._logger.getMethodLogger(u'shutdown')
        Monitor.getSingletonInstance().shutDownRequested()
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
        if len(args) == 0:
            Debug.myLog(
                u' Playlist constructor requires an argument', xbmc.LOGERROR)
            return None

        playlistName = args[0]
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
            Playlist._playlists.remove(self)

    @staticmethod
    def shutdown():
        try:
            with Playlist._playlistLock:
                for playlist in Playlist._playlists.itervalues():
                    playlist._file.close()
        finally:
            with Playlist._playlistLock:
                Playlist._playlists = {}
