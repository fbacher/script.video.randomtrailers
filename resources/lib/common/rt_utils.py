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
from common.messages import Messages
from common.monitor import Monitor
import common.kodi_thread as kodi_thread
from settings import Settings
from backend import backend_constants

import sys
import datetime
from email.utils import parsedate_tz
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
import calendar
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

    TMDB_NAME = u'tmdb'
    TMDB_REQUEST_INDEX = 0
    TMDB_WINDOW_TIME_PERIOD = datetime.timedelta(seconds=20)
    TMDB_WINDOW_MAX_REQUESTS = 40

    ITUNES_NAME = u'iTunes'
    ITUNES_REQUEST_INDEX = 1
    ITUNES_WINDOW_TIME_PERIOD = datetime.timedelta(minutes=1)
    ITUNES_WINDOW_MAX_REQUESTS = 20

    ROTTEN_TOMATOES_NAME = u'Rotten Tomatoes'
    ROTTEN_TOMATOES_REQUEST_INDEX = 2

    # Values not specified in available docs. Not using Rotten Tomatoes
    # at this time

    ROTTEN_TOMATOES_WINDOW_TIME_PERIOD = datetime.timedelta(minutes=1)
    ROTTEN_TOMATOES_WINDOW_MAX_REQUESTS = 20

    _logger = Logger(u'Utils')

    # Each entry in the above _requestWindow* lists is
    # a list with the timestamp and running request count:

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
        threadName = threading.currentThread().getName()
        destinationData = Utils.DestinationData.getData(destination)
        destinationName = destinationData._name
        localLogger = Utils._logger.getMethodLogger(unicode(threadName) +
                                                    u' getDelayTime destination: ' + destinationName)

        requestWindow = destinationData._requestWindow
        lastRequestCount = 0
        if len(requestWindow) > 0:
            newestRequest = requestWindow[len(requestWindow) - 1]
            lastRequestCount = newestRequest.getRequestCount()
            newestResponseTimeStamp = newestRequest.getTimeStamp()
        else:
            # Create a dummy timestamp
            newestResponseTimeStamp = datetime.datetime.now()

        # Remove any entry that has expired. The _windowTimePeriod has how
        # many seconds ago we have to retain entries.

        windowExpirationTime = newestResponseTimeStamp - destinationData._windowTimePeriod

        Trace.log(localLogger.getMsgPrefix(), u'destination', destinationName,
                  u'expiration:', windowExpirationTime,
                  u'#requestWindow:', len(requestWindow), u'lastRequestCount:',
                  lastRequestCount, u'transaction timestamp:',
                  newestResponseTimeStamp,
                  trace=Trace.TRACE_JSON)
        index = 0
        oldestEntry = None
        while index < len(requestWindow):
            oldestEntry = requestWindow[0]
            was = oldestEntry.getTimeStamp()
            #
            # Purge expired entries
            #
            localLogger.debug(
                u'was: ', was, u'requestWindow length:', len(requestWindow))
            if was < windowExpirationTime:
                # Purge
                del requestWindow[0]
            else:
                break

        localLogger.debug(u'requestWindow length:', len(requestWindow),
                          u'destinationData._requestWindow length:',
                          len(destinationData._requestWindow))

        # At this point, requestWindow[0] should be the oldest, un-expired
        # entry

        if oldestEntry is None:
            Trace.log(localLogger.getMsgPrefix(), u'oldestEntry: None',
                      u'expiration:', windowExpirationTime, u'hardCodedRequestsPerTimePeriod:',
                      destinationData._hardCodedRequestsPerTimePeriod, trace=Trace.TRACE_JSON)
        else:
            Trace.log(localLogger.getMsgPrefix(), u'oldestEntry:', oldestEntry.getTimeStamp(),
                      u'expiration:', windowExpirationTime, u'oldest RequestCount:',
                      oldestEntry.getRequestCount(), u'hardCodedRequestsPerTimePeriod:',
                      destinationData._hardCodedRequestsPerTimePeriod, trace=Trace.TRACE_JSON)
        #
        # Have we hit the maximum number of requests over this
        # time period? If we have, then how long do we have to wait before the
        # next request.
        #
        # This calculation is based soley on counts
        # and ignores what the server may be telling us from the last response
        # _hardCodedRequestsPerTimePeriod and _actualOldestRequestInWindowExpirationTime

        delay = datetime.timedelta(0)
        calculatedNumberOfRequestsPending = 0
        if len(requestWindow) > 0:
            startingRequestCount = oldestEntry.getRequestCount()

            # How many additional requests can be made before we are blocked?

            calculatedNumberOfRequestsPending = lastRequestCount - startingRequestCount + 1
            Trace.log(localLogger.getMsgPrefix(), u'calculatedNumberOfRequestsPending:',
                      calculatedNumberOfRequestsPending, u'length of requestWindow:',
                      len(requestWindow), u'numberOfAdditionalRequetsAllowedByServer from server:',
                      destinationData._numberOfAdditionalRequetsAllowedByServer,
                      u'startingRequestCount',
                      startingRequestCount, u'limit:',
                      destinationData._hardCodedRequestsPerTimePeriod, trace=Trace.TRACE_JSON)

         # If the server gives us this info directly, then replace
         # our calculated value with the server value.

        # If server does not give us actual number of remaining requests, then
        # see if server specifies the number in a time period

        maxRequestsInTimePeriod = destinationData._hardCodedRequestsPerTimePeriod
        if destinationData._actualMaxRequestsPerTimePeriod >= 0:
            Trace.log(localLogger.getMsgPrefix(),
                      u'Setting maxRequestsInTimePeriod to value from server',
                      trace=Trace.TRACE_JSON)
            maxRequestsInTimePeriod = destinationData._actualMaxRequestsPerTimePeriod

        numberOfRequestsThatCanStillBeMade = maxRequestsInTimePeriod - \
            calculatedNumberOfRequestsPending

        # If server gives us actual number of remaining requests, then
        # use that instead of what we calculated above.

        if destinationData._numberOfAdditionalRequetsAllowedByServer >= 0:
            numberOfRequestsThatCanStillBeMade = destinationData._numberOfAdditionalRequetsAllowedByServer
            Trace.log(localLogger.getMsgPrefix(),
                      u'Using _numberOfAdditionalRequetsAllowedByServer:',
                      numberOfRequestsThatCanStillBeMade, trace=Trace.TRACE_JSON)

        # Based on the above, calculate any delay time required before making
        # next request

        if numberOfRequestsThatCanStillBeMade > 0:
            delay = datetime.timedelta(0)  # Now, we should be ok
            Trace.log(localLogger.getMsgPrefix(), u'delay:', delay,
                      u'#requests:', len(requestWindow), trace=Trace.TRACE_JSON)
        elif len(requestWindow) > 0:
            alreadyWaited = newestResponseTimeStamp - oldestEntry.getTimeStamp()
            delay = destinationData._windowTimePeriod - alreadyWaited

            Trace.log(localLogger.getMsgPrefix(), u'alreadyWaited:', alreadyWaited,
                      u'delay:', delay, trace=Trace.TRACE_JSON)
            if delay.total_seconds() <= 0:
                localLogger.error(
                    u'Logic error: timer delay should be > 0')

        # If the server gave us information about how long to delay before
        # making a request, then use that instead of the calcualted value
        #
        # The server can give delay information in two ways:
        # 1) the timestamp for the oldest request. Waiting until expires will
        #    guarantee that at least one more request can be made.
        #
        # 2) After a request failure, the server may give how much time
        #    must elapse before trying again.
        #
        correctedDelay = 0
        if numberOfRequestsThatCanStillBeMade <= 0:
            if destinationData._actualOldestRequestInWindowExpirationTime is not None:
                resetTimeFromServer = (destinationData._actualOldestRequestInWindowExpirationTime
                                       + datetime.timedelta(0, 1))
                correctedDelay = resetTimeFromServer - datetime.datetime.now()
                Trace.log(localLogger.getMsgPrefix(), u'correctedDelay:',
                          correctedDelay.total_seconds(), trace=Trace.TRACE_JSON)

        # Second method:
        #
        # Not all requests provide an X-RateLimit-Reset value in the header
        # but when a limit failure the header contains
        # 'Retry-After' which tells you when you can retry again.

        correctedDelay2 = 0
        if destinationData._serverBlockingRequestUntil is not None:
            correctedDelay2 = destinationData._serverBlockingRequestUntil - \
                datetime.datetime.now()
            Trace.log(localLogger.getMsgPrefix(), u'correctedDelay2:',
                      correctedDelay2.total_seconds(), trace=Trace.TRACE_JSON)

        # If server's calculated expirationTime disagrees significantly than ours,
        # then use it.

        if correctedDelay != 0:
            delay = correctedDelay

        # If server is rejecting requests, then use it's delay time.

        if correctedDelay2 != 0:
            delay = correctedDelay2

        delaySeconds = delay.total_seconds()

        Trace.log(localLogger.getMsgPrefix(), u'delaySeconds:',
                  delaySeconds, trace=Trace.TRACE_JSON)

        if delaySeconds < 0:
            delaySeconds = 0

        return delaySeconds

    class RequestTimestamp:
        def __init__(self, timeStamp, requestCount):
            self._timeStamp = timeStamp
            self._requestCount = requestCount

        def getTimeStamp(self):
            return self._timeStamp

        def getRequestCount(self):
            return self._requestCount

    @staticmethod
    def recordRequestTimestamp(destination, responseTimeStamp, failed=False):
        destinationData = Utils.DestinationData.getData(destination)
        requestWindow = destinationData._requestWindow
        localLogger = Utils._logger.getMethodLogger(
            u'recordRequestTimestamp')
        Trace.log(localLogger.getMsgPrefix(), u'JSON destination:',
                  destination, u'timestamp:', responseTimeStamp, trace=Trace.TRACE_JSON)
        Utils.dumpDelayInfo(destination)

        lastIndex = -1
        lastRequestCount = 0
        if len(requestWindow) > 0:
            lastIndex = len(requestWindow) - 1
            lastRequestCount = requestWindow[lastIndex].getRequestCount()

        if failed:
            lastRequestCount += destinationData._hardCodedRequestsPerTimePeriod
        else:
            lastRequestCount += 1

        newEntry = Utils.RequestTimestamp(responseTimeStamp, lastRequestCount)
        requestWindow.append(newEntry)

        Trace.log(localLogger.getMsgPrefix(), u'lastRequestCount:', lastRequestCount, u'lastIndex:',
                  lastIndex, u'length:', len(requestWindow),
                  u'failed:', failed, trace=Trace.TRACE_JSON)
        Utils.dumpDelayInfo(
            destination, msg=u'Exiting recordRequestTimestamp')

    @staticmethod
    def dumpDelayInfo(destination, msg=u''):
        localLogger = Utils._logger.getMethodLogger(u'dumpDelayInfo')
        destinationData = Utils.DestinationData.getData(destination)
        requestWindow = destinationData._requestWindow
        for request in requestWindow:
            timeStamp = request.getTimeStamp()
            requestCount = request.getRequestCount()

        try:
            if len(requestWindow) != 0:
                localLogger.debug(msg + u'\n', u'timestamp:', str(timeStamp),
                                  u'count:', str(requestCount) + u'\n')
            else:
                Trace.log(localLogger.getMsgPrefix(),
                          u'no requests', trace=Trace.TRACE_JSON)
        except Exception as e:
            localLogger.logException()

    class DestinationData:

        _destinationData = []

        def __init__(self):
            self._totalRequests = 0  # Total requests made

            # Reported in header from every request response to tmdb
            # header.get(u'X-RateLimit-Remaining')
            self._numberOfAdditionalRequetsAllowedByServer = -1

            # Number of requests that can be made over a period of time
            # For TMDB, most APIs return this value in the header:
            # header.get('X-RateLimit-Limit')  # Was 40
            self._actualMaxRequestsPerTimePeriod = 0

            # When X-RateLimt-Limit is not available, then _hardCodedRequestsPerTimePeriod
            # contains the maximum number of requests that can occur over
            # a period of time. This is a constant per site.

            self._hardCodedRequestsPerTimePeriod = 0

            # For TMDB, the header contains when the running rate limit
            # will expire.  header.get('X-RateLimit-Reset')
            # Limit will be lifted at this time, in epoch seconds

            self._actualOldestRequestInWindowExpirationTime = None

            # Not all requests utilize the above, but when a limit failure occurs,
            # use 'Retry-After' header value which tells you when you can retry
            # again.

            self._serverBlockingRequestUntil = None
            self._windowTimePeriod = None  # Set in initialize()
            self._responseTimeStamp = None

            self._requestWindow = []
            self._lock = threading.RLock()

        @staticmethod
        def initialize():
            tmdbData = Utils.DestinationData()
            tmdbData._name = Utils.TMDB_NAME
            tmdbData._hardCodedRequestsPerTimePeriod = Utils.TMDB_WINDOW_MAX_REQUESTS
            tmdbData._windowTimePeriod = Utils.TMDB_WINDOW_TIME_PERIOD
            Utils.DestinationData._destinationData.append(tmdbData)

            iTunesData = Utils.DestinationData()
            iTunesData._name = Utils.ITUNES_NAME
            iTunesData._hardCodedRequestsPerTimePeriod = Utils.ITUNES_WINDOW_MAX_REQUESTS
            iTunesData._windowTimePeriod = Utils.ITUNES_WINDOW_TIME_PERIOD
            Utils.DestinationData._destinationData.append(iTunesData)

            # TODO: supply correct info

            rottenTomatoesData = Utils.DestinationData()
            rottenTomatoesData._name = Utils.ROTTEN_TOMATOES_NAME
            rottenTomatoesData._hardCodedRequestsPerTimePeriod = Utils.ROTTEN_TOMATOES_WINDOW_MAX_REQUESTS
            rottenTomatoesData._windowTimePeriod = Utils.ROTTEN_TOMATOES_WINDOW_TIME_PERIOD
            Utils.DestinationData._destinationData.append(rottenTomatoesData)

        @staticmethod
        def getData(destination):
            if len(Utils.DestinationData._destinationData) == 0:
                Utils.DestinationData.initialize()

            return Utils.DestinationData._destinationData[destination]

        @staticmethod
        def getLock(destination):
            return Utils.DestinationData.getData(destination)._lock

    # Headers needs to be native string (not unicode on v2)
    @staticmethod
    def getJSON(url, secondAttempt=False, dumpResults=False, dumpMsg=u'',
                headers={}, params={}, timeout=3.0):
        threadName = threading.currentThread().getName()
        localLogger = Utils._logger.getMethodLogger(
            unicode(threadName) + u': getJSON')

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
            destinationString = u'RottenTomatoes'
            requestIndex = Utils.ROTTEN_TOMATOES_REQUEST_INDEX
            site = u'Tomatoes'

        with Utils.DestinationData.getLock(requestIndex):
            timeDelay = Utils.getDelayTime(requestIndex)

            # Some TMDB api calls do NOT give RATE-LIMIT info in header responses
            # In such cases we detect the failure from the status code and retry
            # with a forced sleep of 10 seconds, which is the maximum required
            # wait time.

            destinationData = Utils.DestinationData.getData(requestIndex)
            Trace.log(localLogger.getMsgPrefix(), u'requestCount:',
                      destinationData._totalRequests,
                      u'serverBlockingRequestUntil:',
                      destinationData._serverBlockingRequestUntil,
                      u'numberOfAdditionalRequetsAllowedByServer:',
                      destinationData._numberOfAdditionalRequetsAllowedByServer,
                      u'hardCodedRequestsPerTimePeriod:',
                      destinationData._hardCodedRequestsPerTimePeriod,
                      u'requestLimitFromServer:',
                      destinationData._actualMaxRequestsPerTimePeriod,
                      u'actualOldestRequestInWindowExpirationTime:',
                      destinationData._actualOldestRequestInWindowExpirationTime,
                      trace=Trace.TRACE_JSON)
            if timeDelay > 0:
                Trace.log(localLogger.getMsgPrefix(), u' Waiting for JSON request to '
                          + destinationString +
                          u' for ' + str(timeDelay) + u' seconds', trace=[Trace.STATS,
                                                                          Trace.TRACE_JSON])
            Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=timeDelay)
            if timeDelay > 0:
                Trace.log(localLogger.getMsgPrefix(), u'After Waiting for JSON request',
                          trace=[Trace.STATS, Trace.TRACE_JSON])
            destinationData._totalRequests += 1
            requestsToURL = destinationData._totalRequests

            requestFailed = True
            now = datetime.datetime.now()
            responseTimeStamp = now

            try:
                response = requests.get(
                    url.encode(u'utf-8'), headers=headers, params=params, timeout=timeout)
                requestFailed = False  # We could change our minds
                now = datetime.datetime.now()
                responseTimeStamp = now
                statusCode = response.status_code
                text = response.text
                jsonText = response.json()
                returnedHeader = response.headers
            except (AbortException, ShutdownException):
                raise sys.exc_info()
            except Exception as e:
                # Retry once

                # TODO: Move this after full analysis, not nested

                localLogger.logException(e)
                Trace.log(localLogger.getMsgPrefix(), u'request to', destinationString,
                          u'FAILED total requests:', requestsToURL,
                          trace=[Trace.STATS, Trace.TRACE_JSON])
                Utils.dumpDelayInfo(requestIndex)
                if secondAttempt:
                    statusCode = -1
                    jsonText = u''
                    return statusCode, jsonText

            try:
                text = u''
                statusCode = u''
                jsonText = u''
                returnedHeader = {}
                statusCode = response.status_code
                text = response.text
                jsonText = response.json()
                returnedHeader = response.headers
            except (AbortException, ShutdownException):
                raise sys.exc_info()
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

            destinationData._numberOfAdditionalRequetsAllowedByServer = -1
            destinationData._actualMaxRequestsPerTimePeriod = 0
            destinationData._actualOldestRequestInWindowExpirationTime = None
            destinationData._serverBlockingRequestUntil = None

            tmp = returnedHeader.get(u'X-RateLimit-Remaining')
            if tmp is not None:
                destinationData._numberOfAdditionalRequetsAllowedByServer = int(
                    tmp)

            tmp = returnedHeader.get('X-RateLimit-Limit')
            if tmp is not None:
                destinationData._actualMaxRequestsPerTimePeriod = int(tmp)

            # Limit will be lifted at this time, in epoch seconds
            tmp = returnedHeader.get('X-RateLimit-Reset')
            if tmp is not None:
                destinationData._actualOldestRequestInWindowExpirationTime = (
                    datetime.datetime.fromtimestamp(int(tmp)))
            else:
                # Some calls don't return X-RateLimit-Reset, in those cases there
                # should be Retry-After indicating how many more seconds to wait
                # before traffic can resume

                serverBlockingRequestUntilValue = 0
                tmp = returnedHeader.get(u'Retry-After')
                msg = u''
                if tmp is not None:
                    seconds = int(tmp) + 1
                    serverBlockingRequestUntilValue = responseTimeStamp + \
                        datetime.timedelta(0, seconds)
                    destinationData._serverBlockingRequestUntil = serverBlockingRequestUntilValue
                    requestFailed = True

                # TODO: This is messy. The Date string returned is probably dependent
                # upon the locale of the user, which means the format will be different
                # Note also that the time zone GMT, or any timezone, is not recognized
                # on input and it is assumed that you are in the same timezone (yeesh)
                # Have to manually clobber the TZ field and reset to UTC.

                tmp = returnedHeader.get(u'Date')
                if tmp is not None:
                    localLogger.debug(u'Date: ', tmp)
                    parsedDate = parsedate_tz(tmp)
                    timeStamp = datetime.datetime.strptime(tmp,
                                                           u'%a, %d %b %Y %H:%M:%S %Z')
                    unixTimeStamp = calendar.timegm(parsedDate)
                    timeStamp = datetime.datetime.fromtimestamp(unixTimeStamp)

                    delta = timeStamp - responseTimeStamp
                    localLogger.debug(u'Timestamp from server:', timeStamp,
                                      u'difference from client:',
                                      delta.total_seconds())

                if requestIndex == Utils.TMDB_REQUEST_INDEX:
                    localLogger.debug(
                        u'TMDB response header missing X-RateLimit info.', msg)

            try:
                status = jsonText.get(u'status_code')
                if status is not None:
                    statusCode = status

                # Debug.myLog(u'StatusCode from jsonText: ' + str(status), xbmc.LOGINFO)
            except (AbortException, ShutdownException):
                raise sys.exc_info()
            except Exception:
                pass

            # Debug.myLog(u'getJSON jsonText: ' + jsonText.__class__.__name__ +
            #            u' ' + json.dumps(jsonText), xbmc.LOGDEBUG)

            if ((statusCode == Constants.TOO_MANY_TMDB_REQUESTS)
                    and (requestIndex == Utils.TMDB_REQUEST_INDEX)):  # Too many requests,
                Trace.log(localLogger.getMsgPrefix(),
                          u'JSON Request rate to TMDB exceeds limits ('
                          + str(destinationData._hardCodedRequestsPerTimePeriod) +
                          u' every', destinationData._windowTimePeriod.total_seconds(),
                          u' seconds). Consider getting API Key. This session\'s requests: '
                          + str(destinationData._totalRequests), trace=Trace.TRACE_JSON)

                Utils.dumpDelayInfo(requestIndex)

            Trace.log(localLogger.getMsgPrefix(), u'JSON request source:',
                      destinationString, u'total requests:', requestsToURL,
                      u'serverBlockingRequestUntil:',
                      destinationData._serverBlockingRequestUntil,
                      u'numberOfAdditionalRequetsAllowedByServer:',
                      destinationData._numberOfAdditionalRequetsAllowedByServer,
                      u'hardCodedRequestsPerTimePeriod:',
                      destinationData._hardCodedRequestsPerTimePeriod,
                      u'actualMaxRequestsPerTimePeriod:',
                      destinationData._actualMaxRequestsPerTimePeriod,
                      u'actualOldestRequestInWindowExpirationTime:',
                      destinationData._actualOldestRequestInWindowExpirationTime,
                      trace=[Trace.STATS, Trace.TRACE_JSON])
            Utils.recordRequestTimestamp(
                requestIndex, responseTimeStamp, failed=requestFailed)
            if requestFailed:
                #
                # Retry only once
                #

                if not secondAttempt:
                    try:
                        statusCode, jsonText = Utils.getJSON(url, secondAttempt=True,
                                                             headers=headers,
                                                             params=params,
                                                             timeout=0.50)
                        requestFailed = True
                    finally:
                        Utils.recordRequestTimestamp(
                            requestIndex, responseTimeStamp, failed=requestFailed)

        # else:
        #    Debug.myLog(u'requests: ' + str(Constants.tmdbRequestCount))

        if dumpResults:
            localLogger.debug(u'JSON DUMP:', dumpMsg)
            localLogger.debug(json.dumps(jsonText, indent=3, sort_keys=True))
        return statusCode, jsonText

    @staticmethod
    def getKodiJSON(query,  dumpResults=False):
        localLogger = Utils._logger.getMethodLogger(u'getKodiJSON')

        jsonText = xbmc.executeJSONRPC(query)
        jsonText = json.loads(jsonText, encoding=u'utf-8')
        if dumpResults:
            localLogger.debug(u'JASON DUMP:')
            localLogger.debug(json.dumps(jsonText, indent=3, sort_keys=True))
        return jsonText

    @staticmethod
    def getCachedJSON(url, cache=True, dumpResults=False, dumpMsg=u'',
                      headers={}, params={}, timeout=3.0):
        if cache:
            pass

        status, jsonText = Utils.getJSON(url, dumpResults, dumpMsg,
                                         headers, params, timeout)
        return status, jsonText


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
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            self._logger.logException()

    def reapDeadThreads(self):
        '''
            While waiting for shutdown, reap any zombie threads
        '''
        localLogger = self._logger.getMethodLogger(
            u'reapDeadThreads')
        localLogger.enter()
        Monitor.getInstance().waitForStartupComplete()
        localLogger.debug(u'StartupComplete')
        #
        # During normal operation, check for threads to harvest every 5
        # minutes, but during shutdown, check continuously
        while not Monitor.getInstance().waitForShutdown(3000):
            try:
                localLogger.debug(u'waitForShutdown complete')
                self.joinWithCompletedThreads(0.01, reaperThread=True)
            except (AbortException, ShutdownException):
                raise sys.exc_info()
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
                except Exception as e:
                    localLogger.logException()

        localLogger.debug(u'WatchDog: _deathIsNigh!')
        deathTime = 4.5
        if not Monitor.getInstance().abortRequested():
            deathTime = 6

        WatchDog._reaperThread.join(deathTime)
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
    MISSING_TRAILERS_PLAYLIST = u'missingTrailers.playlist'
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

    def recordPlayedTrailer(self, trailer, msg=u''):
        name = trailer.get(Movie.TITLE, u'unknown Title')
        year = u'(' + str(trailer.get(Movie.YEAR, u'unknown Year')) + u')'
        movieType = trailer.get(Movie.TYPE, u'Unknown MovieType')
        trailerPath = trailer.get(Movie.TRAILER, u'')
        missingDetailMsg = Messages.getInstance().getMsg(Messages.MISSING_DETAIL)
        if trailerPath == missingDetailMsg:
            trailerPath = u''
        if name is None:
            name = u'name is None'
        if year is None:
            year = u'year is None'
        if movieType is None:
            movieType = u'movieType is None'

        with Playlist._playlistLock:
            # file closed
            if self._file is None:
                return

            self._file.writelines(name + u'  ' + year + u'  # path: '
                                  + movieType + u' ' + trailerPath + msg + u'\n')

    def writeLine(self, line):
        self._file.writelines(line + u'\n')

    def close(self):
        self._file.close()
        self._file = None
        with Playlist._playlistLock:
            del Playlist._playlists[self._playlistName]

    @staticmethod
    def shutdown():
        try:
            with Playlist._playlistLock:
                for playlist in Playlist._playlists.copy().itervalues():
                    playlist.close()
        finally:
            with Playlist._playlistLock:
                Playlist._playlists = {}
