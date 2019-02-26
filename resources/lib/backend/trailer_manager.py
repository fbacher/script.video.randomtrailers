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


from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_constants import iTunes
from common.rt_utils import Utils, Playlist
from common.debug_utils import Debug
from common.exceptions import AbortException, ShutdownException
from common.monitor import Monitor
from common.rt_utils import WatchDog
from common.logger import Trace, Logger

from backend.trailer_fetcher import TrailerFetcher
from backend.rating import Rating
from backend import backend_constants
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
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
#import xbmcwsgi
from kodi65 import addon
from kodi65 import utils
import xbmcdrm
import xml.dom.minidom
import string


class TrailerManagerInterface(threading.Thread):

    @classmethod
    def getInstance(cls):
        pass

    @staticmethod
    def getBaseInstance():
        pass


class BaseTrailerManager(TrailerManagerInterface):
    _trailerManagers = []
    _aggregateTrailersByNameDate = None
    _discoveredTrailers = None
    _discoveredTrailersQueue = None
    _trailersToFetchQueue = None
    _singletonInstance = None
    _readyToPlayQueue = None

    '''    
        Instance variables
    
        _discoveryComplete = False
        _trailerFetcher
    '''

    _blockUntilTrailersPresent = threading.Condition()

    _iterator = None

    @classmethod
    def getInstance(cls):
        if cls._singletonInstance is None:
            singleton = cls()
            cls._singletonInstance = singleton

            try:
                if singleton.__class__.__name__ == u'BaseTrailerManager':
                    singleton._trailerManagers = []
                else:
                    BaseTrailerManager.getInstance().addManager(singleton)
                    singleton._trailerFetcher = TrailerFetcher()
                    singleton._trailerFetcher.startFetchers(singleton)
            except Exception:
                Debug.logException()

        return cls._singletonInstance

    @staticmethod
    def getBaseInstance():
        return BaseTrailerManager._singletonInstance

    def shutdownThread(self):
        # Force waits to end
        self._trailersAvailableToPlay.set()
        self._trailersDiscovered.set()

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, verbose=None):
        self._logger = Logger(self.__class__.__name__)
        self._logger.enter()
        if name is None or name == u'':
            name = Constants.ADDON_PATH + u'.BaseTrailerManager'
        super(BaseTrailerManager, self).__init__(group, target, name,
                                                 args, kwargs, verbose)

        Debug.myLog(self.__class__.__name__ +
                    u' set _discoveryComplete = False', xbmc.LOGDEBUG)
        WatchDog.registerThread(self)
        self._discoveryComplete = False
        self._trailersAvailableToPlay = threading.Event()
        self._trailersDiscovered = threading.Event()
        self._aggregateTrailersByNameDateLock = threading.Condition()
        self._aggregateTrailersByNameDate = dict()
        self._removedTrailers = 0
        self._next_totalDuration = 0
        self._next_calls = 0
        self._next_attempts = 0
        self._loadFetch_totalDuration = 0
        self._next_failures = 0
        self._next_totalFirstMethodAttempts = 0
        self._next_second_attempts = 0
        self._next_second_total_Duration = 0

        if self.__class__.__name__ != u'BaseTrailerManager':
            self._lastShuffleTime = datetime.datetime.fromordinal(1)
            self._lastShuffledIndex = -1
            self._lock = threading.Condition()
            self._lastShuffledIndex = -1
            self._discoveredTrailers = []  # Access via self._lock
            self._discoveredTrailersQueue = queue.Queue(maxsize=0)
            self._trailersToFetchQueue = queue.Queue(maxsize=3)
            self._trailersToFetchQueueLock = threading.Condition()
            self._readyToPlayQueue = queue.Queue(maxsize=3)
            self._actorMap = {}  # Actor, movies

    def discoverBasicInformation(self, genre):
        pass

    def getManagers(self):
        return self._trailerManagers

    def addManager(self, manager):
        self._trailerManagers.append(manager)

    def setGenre(self, genre):
        self.allowedGenre = genre

    def finishedDiscovery(self):
        METHOD_NAME = self.getName() + u'.finishedDiscovery'
        Debug.myLog(METHOD_NAME +
                    u'.finishedDiscovery.', xbmc.LOGDEBUG)
        Debug.myLog(METHOD_NAME + u' before self._lock', xbmc.LOGDEBUG)

        with self._lock:
            Debug.myLog(METHOD_NAME + u' got self._lock', xbmc.LOGDEBUG)

            self.shuffleDiscoveredTrailers(markUnplayed=False)
            self._discoveryComplete = True
            self._lock.notify

    def addToDiscoveredTrailers(self, movie):
        localLogger = WatchDog._logger.getMethodLogger(
            u'addToDiscoveredTrailers')
        localLogger.debug(movie.get(Movie.TITLE), u'source:',
                          movie.get(Movie.SOURCE))

        # Assume more discovery is required for movie details, etc.

        movie[Movie.TRAILER_PLAYED] = False
        movie[Movie.DISCOVERY_STATE] = Movie.NOT_FULLY_DISCOVERED
        localLogger.debug(u'before self._lock')

        with self._lock:
            localLogger.debug(u'got self._lock')

            self._discoveredTrailers.append(movie)
            self._trailersDiscovered.set()
            secondsSinceLastShuffle = (
                datetime.datetime.now() - self._lastShuffleTime).seconds
            if self._lastShuffleTime != datetime.datetime.fromordinal(1):
                Debug.myLog(u'seconds: ' +
                            str(secondsSinceLastShuffle), xbmc.LOGDEBUG)
            else:
                Debug.myLog(u'FirstShuffle', xbmc.LOGDEBUG)
            self._lock.notify()

        reshuffle = False
        if ((self._lastShuffledIndex * 1.10 + 25) < len(self._discoveredTrailers)
                or secondsSinceLastShuffle > Constants.SECONDS_BEFORE_RESHUFFLE):
            reshuffle = True

        if reshuffle:
            self.shuffleDiscoveredTrailers(markUnplayed=False)

        localLogger.debug(u'Added movie to _discoveredTrailers:',
                          movie.get(Movie.TITLE), u'length:',
                          len(self._discoveredTrailers))

    def shuffleDiscoveredTrailers(self, markUnplayed=False):
        METHOD_NAME = self.getName() + u'.shuffleDiscoveredTrailers'
        Debug.myLog(METHOD_NAME, xbmc.LOGDEBUG)
        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
        Debug.myLog(METHOD_NAME + u' before self._lock', xbmc.LOGDEBUG)

        with self._lock:
            Debug.myLog(METHOD_NAME + u' got self._lock', xbmc.LOGDEBUG)

            if len(self._discoveredTrailers) == 0:
                Debug.myLog(METHOD_NAME + u' nothing to shuffle',
                            xbmc.LOGDEBUG)
                return

            # Shuffle a shallow copy and then put that copy
            # into the._discoveredTrailersQueue
            shuffledTrailers = self._discoveredTrailers[:]
            Debug.myLog('ShuffledTrailers: ' +
                        str(len(shuffledTrailers)), xbmc.LOGDEBUG)

            Utils.RandomGenerator.shuffle(shuffledTrailers)
            if markUnplayed:
                for trailer in shuffledTrailers:
                    trailer[Movie.TRAILER_PLAYED] = False

            self._lastShuffledIndex = len(shuffledTrailers) - 1
            Debug.myLog('lastShuffledIndex: ' + str(self._lastShuffledIndex),
                        xbmc.LOGDEBUG)

            # Drain anything previously in queue

            try:
                while True:
                    self._discoveredTrailersQueue.get(block=False)
            except queue.Empty:
                pass

            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
            Debug.myLog(
                METHOD_NAME + u' reloading _discoveredTrailersQueue', xbmc.LOGDEBUG)
            for trailer in shuffledTrailers:
                if not trailer[Movie.TRAILER_PLAYED]:
                    self._discoveredTrailersQueue.put(trailer)

            Debug.myLog(METHOD_NAME +
                        u' _discoverdTrailerQueue length: ' +
                        str(self._discoveredTrailersQueue.qsize()) +
                        u'_discoveredTrailers length: '
                        + str(len(self._discoveredTrailers)),
                        xbmc.LOGDEBUG)

    def addToReadyToPlayQueue(self, movie):
        METHOD_NAME = self.getName() + u'.addToReadyToPlayQueue'
        Debug.myLog(METHOD_NAME + u' movie: ' +
                    movie[Movie.TITLE] +
                    u' queue empty: ' + str(self._readyToPlayQueue.empty()) +
                    u' full: ' + str(self._readyToPlayQueue.full()), xbmc.LOGDEBUG)
        finished = False
        while not finished:
            try:
                self._readyToPlayQueue.put(movie, timeout=0)
                finished = True
            except queue.Full:
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested(timeout=0.75)

        if not BaseTrailerManager.getInstance()._trailersAvailableToPlay.isSet():
            BaseTrailerManager.getInstance()._trailersAvailableToPlay.set()

        Debug.myLog(u'_readyToPlayQueue size: ' + str(self._readyToPlayQueue.qsize()),
                    xbmc.LOGDEBUG)
        return

    def getNumberOfTrailers(self):
        xbmc.log(u' getNumberOfTrailers: ' +
                 self.__class__.__name__, xbmc.LOGDEBUG)
        return len(self._discoveredTrailers)

    def iter(self):
        return self.__iter__()

    def __iter__(self):
        Debug.myLog('BaseTrailerManager.__iter__', xbmc.LOGDEBUG)

        return self

    def next(self):
        return self.__next__()

    def __next__(self):
        METHOD_NAME = self.__class__.__name__ + u'.next'

        Trace.log(METHOD_NAME + u' trailersAvail: ' +
                  str(BaseTrailerManager.getInstance()._trailersAvailableToPlay.isSet()), Trace.TRACE)

        while not BaseTrailerManager.getInstance()._trailersAvailableToPlay.isSet():
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested(timeout=0.25)

        Debug.myLog(
            'BaseTrailerManager.next after trailersAvail wait', xbmc.LOGDEBUG)
        totalNumberOfTrailers = 0
        startTime = datetime.datetime.now()

        # Considered locking all TrailerManagers here to guarantee
        # that lengths don't change while finding the right trailer
        # but that might block the readyToPlayQueue from getting
        # loaded. Besides, it doesn't matter too much if we play
        # the incorrect trailer, as long as we get one. The
        # major fear is if we have no trailers at all, but that
        # will be handled elsewhere.

        # Get total number of trailers from all managers.

        managers = BaseTrailerManager._singletonInstance.getManagers()
        for manager in managers:
            Debug.myLog('Manager: ' + manager.__class__.__name__ + ' size: '
                        + str(manager.getNumberOfTrailers()), xbmc.LOGDEBUG)
            totalNumberOfTrailers += manager.getNumberOfTrailers()

        Debug.myLog('BaseTrailerManager.next numTrailers: ' +
                    str(totalNumberOfTrailers), xbmc.LOGDEBUG)

        # Now, randomly pick manager to get a trailer from based upon
        # the number of trailers in each.
        #
        # We loop here because there may not be any trailers in the readyToPlayQueue
        # for a specific manager

        trailer = None
        attempts = 0
        while trailer is None and attempts < 10:
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
            trailerIndexToPlay = Utils.RandomGenerator.randint(
                0, totalNumberOfTrailers - 1)
            Debug.myLog(u'BaseTrailerManager.next trailerIndexToPlay: '
                        + str(trailerIndexToPlay), xbmc.LOGDEBUG)

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
                            + u' manager: ' + foundManager.__class__.__name__, xbmc.LOGDEBUG)
                trailer = foundManager._readyToPlayQueue.get(block=False)
                title = trailer[Movie.TITLE] + \
                    u' : ' + trailer[Movie.TRAILER]
                Debug.myLog(u'BaseTrailerManager.next found:: ' +
                            title, xbmc.LOGDEBUG)
            except queue.Empty:
                trailer = None

        durationOfFirstAttempt = datetime.datetime.now() - startTime
        secondAttemptStartTime = None
        secondMethodAttempts = None

        if trailer is None:
            Trace.log(METHOD_NAME +
                      u' trailer not found by preferred method', Trace.TRACE)

            # Alternative method is to pick a random manager to start with and
            # then find one that has a trailer. Otherwise, camp out.

            secondAttemptStartTime = datetime.datetime.now()
            secondMethodAttempts = 0
            numberOfManagers = len(managers)
            startingIndex = Utils.RandomGenerator.randint(
                0, numberOfManagers - 1)
            managerIndex = startingIndex
            while trailer is None:
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
                manager = managers[managerIndex]
                try:
                    if not manager._readyToPlayQueue.empty():
                        trailer = manager._readyToPlayQueue.get(block=False)
                        break
                except queue.Empty:
                    pass  # try again

                managerIndex += 1
                if managerIndex >= numberOfManagers:
                    managerIndex = 0
                    if managerIndex == startingIndex:
                        secondMethodAttempts += 1
                        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested(timeout=0.5)

        movie = trailer[Movie.DETAIL_ENTRY]
        movie[Movie.TRAILER_PLAYED] = True
        title = trailer[Movie.TITLE] + \
            u' : ' + trailer[Movie.TRAILER]
        Debug.myLog(u'BaseTrailerManager.next trailer: ' +
                    title, xbmc.LOGDEBUG)

        duration = datetime.datetime.now() - startTime
        self._next_totalDuration += duration.seconds
        self._next_calls += 1
        self._next_attempts += attempts
        self._next_totalFirstMethodAttempts += attempts

        if trailer is None:
            self._next_failures += 1

        Trace.log(METHOD_NAME + u' elapsedTime: ' + str(duration.seconds) + u' seconds' +
                  u' FirstMethod- elapsedTime: ' +
                  str(durationOfFirstAttempt.seconds)
                  + u' attempts: ' + str(attempts), Trace.STATS)
        if secondMethodAttempts is not None:
            self._next_attempts += secondMethodAttempts
            self._next_second_attempts += secondMethodAttempts
            secondDuration = datetime.datetime.now() - secondAttemptStartTime
            self._next_second_total_Duration += secondDuration.seconds
            Trace.log(METHOD_NAME + u' SecondMethod- attempts: ' +
                      str(secondMethodAttempts) + u' elpasedTime: ' +
                      str(secondDuration.seconds), Trace.STATS)

        Trace.log(METHOD_NAME + u' Playing: ' +
                  trailer[Movie.DETAIL_TITLE], Trace.TRACE)
        return trailer

    '''
        When a trailer can not be found for a movie, then we need to remove it
        so that we don't keep looking for it.
    '''

    def removeDiscoveredTrailer(self, trailer):
        METHOD_NAME = self.getName() + u'.removeDiscoveredTrailer'
        Debug.myLog(METHOD_NAME + u' : ',
                    trailer.get(Movie.TITLE), xbmc.LOGDEBUG)
        Debug.myLog(METHOD_NAME + u' before self._lock', xbmc.LOGDEBUG)

        with self._lock:
            Debug.myLog(METHOD_NAME + u' got self._lock', xbmc.LOGDEBUG)

            try:
                self._discoveredTrailers.remove(trailer)
            except ValueError:  # Already deleted
                pass

            self._lock.notify()

        self._removedTrailers += 1

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
        METHOD_NAME = self.getName() + u'.loadFetchQueue'
        startTime = datetime.datetime.now()
        if BaseTrailerManager._firstLoad:
            Monitor.getSingletonInstance().waitForShutdown(timeout=2.0)
            BaseTrailerManager._firstLoad = False

        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
        finished = False
        attempts = 0
        fetchQueueFull = False
        discoveryFoundNothing = False
        discoveryCompleteQueueEmpty = 0
        discoveredAndFetchQueuesEmpty = 0
        discoveryIncompleteFetchNotEmpty = 0
        discoveryIncompleteFetchQueueEmpty = 0
        getAttempts = 0
        putAttempts = 0
        while not finished:
            trailer = None
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
            attempts += 1
            shuffle = False
            iterationSuccessful = False
            try:
                elapsed = datetime.datetime.now() - startTime
                if attempts > 0:
                    Debug.myLog(METHOD_NAME + u' Attempt: ' +
                                str(attempts) + u' elapsed: ' + str(elapsed.seconds), xbmc.LOGDEBUG)

                if self._trailersToFetchQueue.full():
                    Trace.log(METHOD_NAME +
                              u' _trailersToFetchQueue full', Trace.TRACE)
                    finished = True
                    iterationSuccessful = True
                    fetchQueueFull = True
                elif self._discoveryComplete and len(self._discoveredTrailers) == 0:
                    Trace.log(METHOD_NAME +
                              u' Discovery Complete and nothing found.', Trace.TRACE)
                    finished = True
                    iterationSuccessful = True
                    discoveryFoundNothing = True
                elif self._discoveryComplete and self._discoveredTrailersQueue.empty():
                    Trace.logError(METHOD_NAME +
                                   u'_ discoveryComplete,_discoveredTrailersQueue empty',
                                   Trace.TRACE)
                    shuffle = True
                    discoveryCompleteQueueEmpty += 1
                    #
                    # In the following, Discovery is INCOMPLETE
                    #
                elif (self._discoveredTrailersQueue.empty()
                      and not self._trailersToFetchQueue.empty):
                    discoveredAndFetchQueuesEmpty += 1
                    # Use what we have
                    Trace.log(
                        METHOD_NAME + u' Discovery incomplete._discoveredTrailersQueue ' +
                        u'empty and _trailersToFetchQueue not empty', Trace.TRACE)
                    finished = True
                elif not self._trailersToFetchQueue.empty():
                    # Fetch queue is not empty, nor full. Discovery
                    # is not complete. Get something from _discoveredTrailerQueue
                    # if available

                    try:
                        discoveryIncompleteFetchNotEmpty += 1
                        trailer = self._discoveredTrailersQueue.get(
                            timeout=0.25)
                        Debug.myLog(METHOD_NAME +
                                    u' Got from _discoverdTrailerQueue', xbmc.LOGINFO)
                    except queue.Empty:
                        pass

                    if trailer is not None:
                        try:
                            self._trailersToFetchQueue.put(
                                trailer, timeout=1)
                            Trace.log(METHOD_NAME + u' Put in _trailersToFetchQueue qsize: ' +
                                      str(self._trailersToFetchQueue.qsize()) + u' ' +
                                      trailer.get(Movie.TITLE), Trace.TRACE)
                            iterationSuccessful = True
                        except queue.Full:
                            Trace.log(
                                METHOD_NAME + u' _trailersToFetchQueue.put failed', Trace.TRACE)
                        #
                        # It is not a crisis if the put fails. Since the
                        # fetch queue does have at least one entry, we are ok
                        # Even if the trailer is lost from the FetchQueue,
                        # it will get reloaded once the queue is exhausted.
                        #
                        # But since iterationSuccessful is not true, we might
                        # still fix it at the end.
                        #
                else:
                    # Discovery incomplete, fetch queue is empty
                    # wait until we get an item, or discovery complete

                    discoveryIncompleteFetchQueueEmpty += 1
                    Trace.log(METHOD_NAME + u' Discovery incomplete, ' +
                              u'_trailersToFetchQueue empty, will wait', Trace.TRACE)

                if not iterationSuccessful:
                    if shuffle:  # Because we were empty
                        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
                        self.shuffleDiscoveredTrailers(markUnplayed=False)

                    if trailer is None:
                        getFinished = False
                        while not getFinished:
                            try:
                                getAttempts += 1
                                trailer = self._discoveredTrailersQueue.get(
                                    timeout=0.5)
                                getFinished = True
                            except queue.Empty:
                                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                    putFinished = False
                    while not putFinished:
                        try:
                            putAttempts += 1
                            self._trailersToFetchQueue.put(
                                trailer, timeout=0.25)
                            putFinished = True
                        except queue.Full:
                            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()
                        iterationSuccessful = True

                if trailer is not None:
                    movieTitle = trailer.get(Movie.TITLE)
                else:
                    movieTitle = u'no movie'

                Debug.myLog(METHOD_NAME + u' Queue has: ' + str(self._trailersToFetchQueue.qsize())
                            + u' Put in _trailersToFetchQueue: ' +
                            movieTitle, xbmc.LOGDEBUG)
            except Exception as e:
                Debug.logException(e)
                # TODO Continue?

            if self._trailersToFetchQueue.full():
                finished = True

            if not self._trailersToFetchQueue.empty() and not iterationSuccessful:
                finished = True

            if not finished:
                if attempts % 10 == 0:
                    Trace.logError(METHOD_NAME +
                                   u' hung reloading from._discoveredTrailersQueue.'
                                   + u' length of _discoveredTrailers: '
                                   + str(len(self._discoveredTrailers))
                                   + u' length of._discoveredTrailersQueue: '
                                   + str(self._discoveredTrailersQueue.qsize()), Trace.TRACE)
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested(timeout=0.5)

        stopTime = datetime.datetime.now()
        duration = stopTime - startTime
        self._loadFetch_totalDuration += duration.seconds

        attempts = 0
        discoveryCompleteQueueEmpty = 0
        discoveredAndFetchQueuesEmpty = 0
        discoveryIncompleteFetchNotEmpty = 0
        discoveryIncompleteFetchQueueEmpty = 0
        getAttempts = 0
        putAttempts = 0

        Trace.log(METHOD_NAME + u' took ' +
                  str(duration.seconds) + u' seconds', Trace.STATS)

    def getFromFetchQueue(self):
        METHOD_NAME = self.getName() + u'.getFromFetchQueue'
        Debug.myLog(METHOD_NAME, xbmc.LOGDEBUG)
        self.loadFetchQueue()
        trailer = None
        if self._trailersToFetchQueue.empty():
            Debug.myLog(METHOD_NAME + u': empty', xbmc.LOGDEBUG)
        while trailer is None:
            try:
                trailer = self._trailersToFetchQueue.get(timeout=0.5)
            except queue.Empty:
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

        Debug.myLog(METHOD_NAME + u' ' +
                    trailer[Movie.TITLE], xbmc.LOGDEBUG)
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
        threadName = type(self).__name__
        super(LibraryTrailerManager, self).__init__(group=None, target=None,
                                                    name=threadName,
                                                    args=(), kwargs=None, verbose=None)

    @classmethod
    def getInstance(cls):
        return super(LibraryTrailerManager, cls).getInstance()

    def discoverBasicInformation(self, genre):
        METHOD_NAME = self.getName() + u'.discoverBasicInformation'
        self.setGenre(genre)
        self.start()

        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = self.getName() + u'.run'
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        Debug.myLog(METHOD_NAME + u': memory: ' + str(memory), xbmc.LOGDEBUG)
        startTime = datetime.datetime.now()
        try:
            self.runWorker()
            self.finishedDiscovery()
        except (AbortException, ShutdownException):
            return  # Shut down thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(METHOD_NAME + u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', Trace.STATS)

    def runWorker(self):
        METHOD_NAME = self.getName() + u'.runWorker'

        # Disovery is done in two parts:
        #
        # 1- query DB for every movie in library
        # 2- Get additional information
        #
        # There are three types of trailers for these movies:
        #
        #  a- Movies with local trailers
        #  b- Movies with trailer URLS (typically youtube links from tmdb)
        #    TMdb will need to be queried for details
        #  c. Movies with no trailer information, requiring a check with tmdb
        #     to see if one exists
        #
        # Because of the above, this manager will query the DB for every movie
        # and then only process the ones with local trailers. The others will
        # be handed off to their own managers. This is done because of
        # the way that this application works:
        #    Once enough information to identify a movie that matches
        #    what the user wants, it is added to the pool of movies that
        #    can be randomly selected for playing. Once a movie has been
        #    selected, it is placed into a TrailerFetcherQueue. A
        #    TrailerFetcher then gathers the remaining information so that
        #    it can be played.
        #
        #    If the lion's share of movies in the pool require significant
        #    extra processing because they don't have local trailers, then
        #    the fetcher can get overwhelmed.
        #

        #
        #   Initial Discovery of all movies in Kodi:

        if self.allowedGenre == u'':
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

            query = query % self.allowedGenre

        if Monitor.getSingletonInstance().isShutdownRequested():
            return

        queryResult = Utils.getKodiJSON(query)

        # Debug.myLog('movies: ', json.dumps(movieString, indent=3), xbmc.LOGDEBUG)
        moviesSkipped = 0
        moviesFound = 0
        moviesWithLocalTrailers = 0
        moviesWithTrailerURLs = 0
        moviesWithoutTrailerInfo = 0

        result = queryResult.get('result', {})
        movies = result.get(u'movies', [])
        Utils.RandomGenerator.shuffle(movies)
        for movie in movies:
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

            Debug.myLog('Kodi library movie: ' +
                        json.dumps(movie), xbmc.LOGDEBUG)
            moviesFound += 1
            if Settings.getHideWatchedMovies() and Movie.LAST_PLAYED in movie:
                if getDaysSinceLastPlayed(movie[Movie.LAST_PLAYED],
                                          movie[Movie.TITLE]) > 0:
                    moviesSkipped += 1
                    continue

            # Normalize rating

            Debug.myLog(METHOD_NAME + u': mpaa: ' + movie[Movie.MPAA] +
                        u' movie: ' + movie[Movie.TITLE], xbmc.LOGDEBUG)
            rating = Rating.getMPAArating(
                movie.get(Movie.MPAA), movie.get(u'adult'))
            movie[Movie.SOURCE] = Movie.LIBRARY_SOURCE
            movie.setdefault(Movie.TRAILER, u'')
            movie[Movie.TYPE] = u''

            Debug.validateBasicMovieProperties(movie)

            self.collectActors(movie)

            # Basic discovery is complete at this point. Now send
            # all of the movies without any trailer information to
            # LibraryNoTrailerInfoManager while
            # those with trailer URLs to LibraryURLManager

            libraryURLManager = LibraryURLManager.getInstance()
            libraryNoTrailerInfoManager = LibraryNoTrailerInfoManager.getInstance()

            if Rating.checkRating(rating):
                trailer = movie[Movie.TRAILER]
                if trailer == u'':
                    moviesWithoutTrailerInfo += 1
                    libraryNoTrailerInfoManager.addToDiscoveredTrailers(movie)
                elif trailer.startswith(u'plugin://') or trailer.startswith(u'http'):
                    moviesWithTrailerURLs += 1
                    libraryURLManager.addToDiscoverdTrailers(movie)
                else:
                    moviesWithLocalTrailers += 1
                    self.addToDiscoveredTrailers(movie)

        Trace.log(u'Local movies found in library: ' +
                  str(moviesFound), Trace.STATS)
        Trace.log(u'Local movies filterd out ' +
                  str(moviesSkipped), Trace.STATS)
        Trace.log(u'Movies with local trailers: ' +
                  str(moviesWithLocalTrailers), Trace.STATS)
        Trace.log(u'Movies with trailer URLs: ' +
                  str(moviesWithTrailerURLs), Trace.STATS)
        Trace.log(u'Movies with no trailer information: ' +
                  str(moviesWithoutTrailerInfo), Trace.STATS)

        self.reportActors()

    def collectActors(self, movie):
        actors = movie.get(Movie.CAST, [])
        movieName = movie[Movie.TITLE]
        movieYear = movie[Movie.YEAR]
        movieId = movieName + u' (' + str(movieYear) + u')'

        actorCount = 0
        for actorEntry in actors:
            if u'name' in actorEntry:
                actorCount += 1
                actor = actorEntry[u'name']
                if self._actorMap.get(actor) == None:
                    self._actorMap[actor] = []
                self._actorMap[actor].append(movieId)
            if actorCount == Settings.getMaxTopActors():
                break

    def reportActors(self):
        # First sort by number of movies that each actor is
        # in

        a = sorted(self._actorMap, key=lambda key: len(
            self._actorMap[key]), reverse=True)
        # a = sorted(self._actorMap, key=len(
        #    self._actorMap.__getitem__), reverse=True)
        playlist = Playlist.getPlaylist(
            u'ActorFrequency.playlist', append=False)

        for actor in a:
            moviesIn = self._actorMap[actor]
            buffer = actor + u' : ' + str(len(moviesIn))
            for movie in sorted(moviesIn):
                if len(buffer) > 100:
                    playlist.writeLine(buffer)
                    buffer = u'       '
                buffer = buffer + u' ' + movie

            playlist.writeLine(buffer)

        playlist.close()


class LibraryURLManager(BaseTrailerManager):

    '''
        This manager does not do any discovery, it receives local movies 
        with trailer URLs from LibraryManager. This manager primarily 
        acts as a container to hold the list of movies while the 
        TrailerFetcher and BaseTrailerManager does the work
    '''

    _singletonInstance = None

    def __init__(self):
        threadName = type(self).__name__
        super(LibraryURLManager, self).__init__(group=None, target=None,
                                                name=threadName,
                                                args=(), kwargs=None, verbose=None)

    @classmethod
    def getInstance(cls):
        return super(LibraryURLManager, cls).getInstance()

    def discoverBasicInformation(self, genre):
        METHOD_NAME = self.getName() + u'.discoverBasicInformation'
        Debug.myLog(METHOD_NAME + u' dummy method', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = self.getName() + u'.run'
        Debug.myLog(METHOD_NAME + u' dummy thread', xbmc.LOGDEBUG)


class LibraryNoTrailerInfoManager(BaseTrailerManager):

    '''
        This manager does not do any discovery, it receives local movies 
        without any trailer information from LibraryManager. This manager 
        primarily acts as a container to hold the list of movies while the 
        TrailerFetcher and BaseTrailerManager does the work
    '''

    _singletonInstance = None

    def __init__(self):
        threadName = type(self).__name__
        super(LibraryNoTrailerInfoManager, self).__init__(group=None, target=None,
                                                          name=threadName,
                                                          args=(), kwargs=None, verbose=None)

    @classmethod
    def getInstance(cls):
        return super(LibraryNoTrailerInfoManager, cls).getInstance()

    def discoverBasicInformation(self, genre):
        METHOD_NAME = self.getName() + u'.discoverBasicInformation'
        Debug.myLog(METHOD_NAME + u' dummy method', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = self.getName() + u'.run'
        Debug.myLog(METHOD_NAME + u' dummy thread', xbmc.LOGDEBUG)


class FolderTrailerManager(BaseTrailerManager):

    '''
        The subtrees specified by the path/multipath are
        assumed to contain movie trailers.
        Create skeleton movie info for every file found,
        containing only the file and directory names.
    '''

    _singletonInstance = None

    def __init__(self):
        threadName = type(self).__name__
        super(FolderTrailerManager, self).__init__(group=None, target=None,
                                                   name=threadName,
                                                   args=(), kwargs=None, verbose=None)

    @classmethod
    def getInstance(cls):
        return super(FolderTrailerManager, cls).getInstance()

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
        startTime = datetime.datetime.now()
        try:
            self.discoverBasicInformationWorker(Settings.getTrailersPaths())
        except (AbortException, ShutdownException):
            return  # Just exit thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(METHOD_NAME + u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', Trace.STATS)

    def discoverBasicInformationWorker(self, path):
        METHOD_NAME = u'FolderTrailerManager.discoverBasicInformationWorker'
        folders = []
        if str(path).startswith(u'multipath://'):
            # get all paths from the multipath
            paths = path[12:-1].split('/')
            for item in paths:
                folders.append(requests.utils.unquote_unreserved(item))
        else:
            folders.append(path)
        Utils.RandomGenerator.shuffle(folders)
        for folder in folders:
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

            if xbmcvfs.exists(xbmc.translatePath(folder)):
                # get all files and subfolders
                dirs, files = xbmcvfs.listdir(folder)

                # Assume every file is a movie trailer. Manufacture
                # a movie name and other info from the filename.
                Utils.RandomGenerator.shuffle(files)
                for item in files:
                    filePath = os.path.join(folder, item)
                    title = xbmc.translatePath(filePath)
                    title = os.path.basename(title)
                    title = os.path.splitext(title)[0]
                    newTrailer = {Movie.TITLE: title,
                                  Movie.TRAILER: filePath,
                                  Movie.TYPE: u'trailer file',
                                  Movie.SOURCE:
                                  Movie.FOLDER_SOURCE,
                                  Movie.FANART: u'',
                                  Movie.THUMBNAIL: u'',
                                  Movie.FILE: u'',
                                  Movie.YEAR: u''}
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
        threadName = type(self).__name__
        super(ItunesTrailerManager, self).__init__(group=None, target=None,
                                                   name=threadName,
                                                   args=(), kwargs=None, verbose=None)
    _singletonInstance = None

    @classmethod
    def getInstance(cls):
        return super(ItunesTrailerManager, cls).getInstance()

    def discoverBasicInformation(self, genre):
        METHOD_NAME = u'ItunesTrailerManager.discoverBasicInformation'
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)

        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = self.__class__.__name__ + u'.run'
        startTime = datetime.datetime.now()
        try:
            self.runWorker()
        except (AbortException, ShutdownException):
            return  # Just exit thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(METHOD_NAME + u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', Trace.STATS)

    def runWorker(self):
        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

        METHOD_NAME = self.__class__.__name__ + u'.runWorker'
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        showOnlyiTunesTrailersOfThisType = Settings.getIncludeItunesTrailerType()
        Debug.myLog('trailer_type: ' +
                    str(showOnlyiTunesTrailersOfThisType), xbmc.LOGINFO)
        if showOnlyiTunesTrailersOfThisType > 4:
            Debug.myLog(u'Invalid iTunes Trailer Type: ' +
                        str(showOnlyiTunesTrailersOfThisType), xbmc.LOGERROR)
            return

        if showOnlyiTunesTrailersOfThisType == iTunes.COMMING_SOON:
            jsonURL = u'/trailers/home/feeds/studios.json'
        elif showOnlyiTunesTrailersOfThisType == iTunes.JUST_ADDED:
            jsonURL = u'/trailers/home/feeds/just_added.json'
        elif showOnlyiTunesTrailersOfThisType == iTunes.POPULAR:
            jsonURL = u'/trailers/home/feeds/most_pop.json'
        elif showOnlyiTunesTrailersOfThisType == iTunes.EXCLUSIVE:
            jsonURL = u'/trailers/home/feeds/exclusive.json'
        elif showOnlyiTunesTrailersOfThisType == iTunes.ALL:
            jsonURL = u'/trailers/home/feeds/studios.json'

        jsonURL = backend_constants.APPLE_URL_PREFIX + jsonURL
        Debug.myLog(u'iTunes jsonURL: ' + jsonURL, xbmc.LOGDEBUG)
        statusCode, parsedContent = Utils.getJSON(jsonURL)
        Utils.RandomGenerator.shuffle(parsedContent)
        Debug.myLog(u'parsedContent: ', json.dumps(parsedContent, ensure_ascii=False,
                                                   encoding='unicode', indent=4,
                                                   sort_keys=True), xbmc.LOGINFO)
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

        # Debug.myLog(u'Itunes parsedContent type: ' +
        #            type(parsedContent).__name__, xbmc.LOGDEBUG)

        for iTunesMovie in parsedContent:
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

            Debug.myLog(u'value: ', iTunesMovie, xbmc.LOGINFO)

            title = iTunesMovie.get(
                Movie.TITLE, u'Missing title from iTunes')
            Debug.myLog('title: ', title, xbmc.LOGINFO)

            releaseDateString = iTunesMovie.get('releasedate')
            # Debug.myLog('releaseDateString: ',
            #            releaseDateString, xbmc.LOGINFO)
            if releaseDateString != u'':
                STRIP_TZ_PATTERN = ' .[0-9]{4}$'

                stripTZPattern = re.compile(STRIP_TZ_PATTERN)
                releaseDateString = stripTZPattern.sub('', releaseDateString)
            #    Debug.myLog('releaseDateString: ',
            #                releaseDateString, xbmc.LOGINFO)

                # "Thu, 14 Feb 2019 00:00:00 -0800",
                releaseDate = datetime.datetime.strptime(
                    releaseDateString, '%a, %d %b %Y %H:%M:%S')
            #    Debug.myLog('releaseDate: ', releaseDate.strftime(
            #        '%d-%m-%Y'), xbmc.LOGINFO)
            else:
                releaseDate = datetime.date.today()

            studio = iTunesMovie.get('studio')
            if studio is None:
                studio = u''

            #Debug.myLog('studio: ', studio, xbmc.LOGINFO)

            poster = iTunesMovie.get('poster')
            if poster is None:
                poster = u''

            #Debug.myLog('poster: ', poster, xbmc.LOGINFO)

            thumb = string.replace(poster, 'poster.jpg', 'poster-xlarge.jpg')
            fanart = string.replace(poster, 'poster.jpg', 'background.jpg')

            #Debug.myLog('thumb:', thumb, ' fanart: ', fanart, xbmc.LOGINFO)

            poster_2x = iTunesMovie.get('poster_2x')
            if poster_2x is None:
                poster_2x = u''

            #Debug.myLog('poster_2x: ', poster_2x, xbmc.LOGINFO)

            location = iTunesMovie.get('location')
            if location is None:
                location = u''

            #Debug.myLog('location: ', location, xbmc.LOGINFO)

            # Normalize rating
            # We expect the attribute to be named 'mpaa', not 'rating'

            iTunesMovie[Movie.MPAA] = iTunesMovie[u'rating']
            rating = Rating.getMPAArating(
                iTunesMovie.get(Movie.MPAA), iTunesMovie.get(u'adult'))
            #Debug.myLog('rating: ', rating, xbmc.LOGINFO)

            genres = iTunesMovie.get(u'genre')
            #Debug.myLog('genres: ', genres, xbmc.LOGINFO)

            directors = iTunesMovie.get('directors')
            if directors is None:
                directors = []

            #Debug.myLog('directors: ', directors, xbmc.LOGINFO)

            actors = iTunesMovie.get('actors')
            if actors is None:
                actors = []

            #Debug.myLog('actors: ', actors, xbmc.LOGINFO)

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

            # Debug.myLog('iTunesTrailersList: ',
            #            iTunesTrailersList, xbmc.LOGINFO)
            for iTunesTrailer in iTunesTrailersList:
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                keepTrailer = True
                Debug.myLog('iTunesTrailer: ', iTunesTrailer, xbmc.LOGINFO)
                postDate = iTunesTrailer.get('postdate')
                if postDate is None:
                    postDate = u''

                #Debug.myLog('postDate: ', postDate, xbmc.LOGINFO)

                url = iTunesTrailer.get('url')
                if url is None:
                    url = u''

                Debug.myLog('url: ', url, xbmc.LOGINFO)
                # RE_URL_INFO = re.compile('trailers\/([^\/]+)\/([^\/]+)')
                # RE_URL_INFO.

                trailerType = iTunesTrailer.get('type', u'')

                Debug.myLog('type: ', trailerType, xbmc.LOGINFO)

                if trailerType.startswith(u'Clip') and not Settings.getIncludeClips():
                    Debug.myLog('Rejecting due to clip', xbmc.LOGDEBUG)
                    keepTrailer = False
                elif trailerType in excludeTypesSet:
                    Debug.myLog(
                        'Rejecting due to exclude Trailer Type', xbmc.LOGDEBUG)
                    keepTrailer = False
                elif not Settings.getIncludeFeaturettes() and (trailerType == u'Featurette'):
                    Debug.myLog('Rejecting due to Featurette', xbmc.LOGDEBUG)
                    keepTrailer = False
                elif ((Settings.getIncludeItunesTrailerType() == iTunes.COMMING_SOON) and
                      (releaseDate < datetime.date.today())):
                    Debug.myLog(
                        'Rejecting due to COMMING_SOON and already released', xbmc.LOGDEBUG)
                    keepTrailer = False
                elif self.allowedGenre != u'' and self.allowedGenre not in genres:
                    keepTrailer = False
                    Debug.myLog('Rejecting due to genre: ' +
                                self.allowedGenre, xbmc.LOGDEBUG)
                elif not Rating.checkRating(rating):
                    keepTrailer = False
                    Debug.myLog('Rejecting due to rating: ' +
                                rating, xbmc.LOGDEBUG)
                if keepTrailer:
                    # "url": "/trailers/independent/the-standoff-at-sparrow-creek/"
                    # Change leading "/trailers" to "/movies"
                    url = url.replace(u'^/trailers', u'/movies')
                    urlPathElements = re.split(u'/', url)
                    trailerMovieName = urlPathElements[3]
                    # could "HD" field impact the name?
                    # trailerType is: 'Trailer' | 'Trailer '[0-9]+
                    matches = re.findall(u'[0-9]+', trailerType)
                    if len(matches) == 0:
                        trailerCount = u'1'
                    else:
                        trailerCount = matches[0]

                    suffix = u'-trailer-' + trailerCount + u'_i320.m4v'
                    # trailerURL = backend_constants.APPLE_URL_PREFIX + url + "includes/" + \
                    #    trailerType.replace('-', '').replace(' ',
                    #                                         '').lower() + "/large.html"
                    trailerStudio = urlPathElements[2]
                    trailerURL = u'https://movietrailers.apple.com' + u'/movies/' + \
                        trailerStudio + u'/' + trailerMovieName + u'/' + trailerMovieName + suffix

# Working URL:
# https://movietrailers.apple.com/movies/wb/the-lego-movie-2-the-second-part/the-lego-movie-2-clip-palace-of-infinite-relection_i320.m4v
# https://movietrailers.apple.com/movies/independent/the-final-wish/the-final-wish-trailer-1_i320.m4v
# https://movietrailers.apple.com/movies/wb/shazam/shazam-teaser-1-usca_i320.m4v
 # u'/trailers/independent/the-final-wish/

                    # https://movietrailers.apple.com/movies/universal/a-dogs-journey/a-dogs-journey-trailer-1_i320.m4v
                    # https://movietrailers.apple.com/trailers/independent/the-final-wish/the-final-wish-trailer-1_i320.m4v
                    #trailer[Movie.TRAILER] = u'https://movietrailers.apple.com/movies/independent/the-standoff-at-sparrow-creek/the-standoff-at-sparrow-creek-trailer-1_i320.m4v'

                    # url = u'http://trailers.apple.com/trailers/fox/alita-battle-angel/includes/trailer3/large.html'
                    # url = u'http://trailers.apple.com/trailers/independent/an-affair-to-die-for/includes/trailer/large.html'

                    # match = re.compile('"url":"(.+?)","type":"(.+?)"',
                    #       re.DOTALL).findall(entry)
                    # for url, type in match:

                    # trailerURL = url2

                    '''                                         
                    RE_URL_INFO = Regex('trailers\/([^\/]+)\/([^\/]+)')
                    
                    for clip in json_obj['clips']:

                        clip_type = String.Quote(clip['title'])

                        try:
                            oc.add(URLService.MetadataObjectForURL(MOVIE_URL % (studio, movie_title, clip_type)))
                            except:
                                pass
                                           data = {}
            data[u'api_key'] = Settings.getTmdbApiKey()
            data[u'sort_by'] = 'popularity.desc'
            data[u'certification_country'] = 'us'
            data[u'certification.lte'] = rating_limit
            url = 'http://api.themoviedb.org/3/discover/movie'
            
            MOVIE_URL = 'http://movietrailers.apple.com/trailers/%s/%s/#%s'
            url = MOVIE_URL
            data = {}
            data[u'studio'] = studio
            data[u'movie-title'] = movieTitle
            data[u'clip_type'] = clipType
            
            encoded_args = urlparse(data)
            url = url + encoded_args
            
            > from urllib.parse import urlencode
>>> encoded_args = urlencode({'arg': 'value'})
>>> url = 'http://httpbin.org/post?' + encoded_args
                    '''
                    movie = {Movie.TITLE: title,
                             Movie.TRAILER: trailerURL,
                             Movie.FILE: u'',
                             # It looks like TrailerType is simply "trailer-" +
                             # trailer number
                             Movie.TYPE: trailerType,
                             Movie.MPAA: rating,
                             Movie.YEAR: str(releaseDate.year),
                             Movie.THUMBNAIL: thumb,
                             Movie.FANART: fanart,
                             Movie.GENRE: genres,
                             Movie.DIRECTOR: directors,
                             Movie.STUDIO: studio,
                             Movie.SOURCE:
                                 Movie.ITUNES_SOURCE}
                    Debug.myLog('Adding iTunes trailer: ',
                                movie, xbmc.LOGINFO)
                    Debug.validateBasicMovieProperties(movie)
                    self.addToDiscoveredTrailers(movie)

        # self.getItunesTrailersOld()
        return

    def getItunesTrailersOld(self):
        trailers = []

        urlMain = backend_constants.APPLE_URL_PREFIX
        requestURL = urlMain + "/trailers/home/feeds/studios.json"
        response = requests.get(requestURL, timeout=0.5)

        Debug.myLog(u'response: ' + type(response).__name__, xbmc.LOGDEBUG)
        text = response.text
        Debug.myLog(u'text: ' + type(text).__name__, xbmc.LOGDEBUG)

        spl = text.split('"title"')
        for i in range(1, len(spl), 1):
            entry = spl[i]
            match = re.compile('"poster":"(.+?)"', re.DOTALL).findall(entry)
            thumb = urlMain + \
                match[0].replace('poster.jpg', 'poster-xlarge.jpg')
            fanart = urlMain + match[0].replace('poster.jpg', 'background.jpg')
            match = re.compile('"rating":"(.+?)"', re.DOTALL).findall(entry)
            rating = match[0]
            match = re.compile('"releasedate":"(.+?)"',
                               re.DOTALL).findall(entry)
            if len(match) > 0:
                month = match[0][8:-20]
                day = int(match[0][5:-24])
                year = int(match[0][12:-15])
                if month == 'Jan':
                    month = 1
                if month == 'Feb':
                    month = 2
                if month == 'Mar':
                    month = 3
                if month == 'Apr':
                    month = 4
                if month == 'May':
                    month = 5
                if month == 'Jun':
                    month = 6
                if month == 'Jul':
                    month = 7
                if month == 'Aug':
                    month = 8
                if month == 'Sep':
                    month = 9
                if month == 'Oct':
                    month = 10
                if month == 'Nov':
                    month = 11
                if month == 'Dec':
                    month = 12
                releasedate = datetime.date(year, month, day)
            else:
                releasedate = datetime.date.today()
            match = re.compile('"(.+?)"', re.DOTALL).findall(entry)
            title = match[0]
            match = re.compile('"genre":(.+?),', re.DOTALL).findall(entry)
            genre = match[0]
            match = re.compile('"directors":(.+?),', re.DOTALL).findall(entry)
            director = match[0]
            match = re.compile('"studio":"(.+?)",', re.DOTALL).findall(entry)
            studio = match[0]
            match = re.compile('"type":"(.+?)",', re.DOTALL).findall(entry)
            trailerType = match[0]
            match = re.compile('"url":"(.+?)","type":"(.+?)"',
                               re.DOTALL).findall(entry)
            for url, trailerType in match:
                filter = ["- JP Sub", "Interview", "- UK", "- BR Sub", "- FR", "- IT", "- AU", "- MX", "- MX Sub", "- BR", "- RU", "- DE",
                          "- ES", "- FR Sub", "- KR Sub", "- Russian", "- French", "- Spanish", "- German", "- Latin American Spanish", "- Italian"]
                filtered = False
                for f in filter:
                    if f in trailerType:
                        filtered = True

                url = urlMain + url + "includes/" + \
                    trailerType.replace('-', '').replace(' ',
                                                         '').lower() + "/large.html"
                trailer = {'title': title, 'trailer': url, 'type': trailerType, 'mpaa': rating, 'year': year, 'thumbnail': thumb,
                           'fanart': fanart, 'genre': genre, 'director': director, 'studio': studio, 'source': 'iTunes'}
                trailers.append(trailer)
                Debug.myLog(title + u' ' + url + u' oldURL', xbmc.LOGDEBUG)
                Debug.myLog(title + u' oldType: ' + trailerType, xbmc.LOGDEBUG)

        return trailers


class TmdbTrailerManager(BaseTrailerManager):
    # TODO: Need to add genre filter here

    '''
        TMDB, like iTunes, provides trailers. Query TMDB for trailers
        and manufacture trailer entries for them.
    '''

    _singletonInstance = None

    def __init__(self):
        threadname = type(self).__name__
        super(TmdbTrailerManager, self).__init__(group=None, target=None,
                                                 name=threadname,
                                                 args=(), kwargs=None, verbose=None)

    @classmethod
    def getInstance(cls):
        return super(TmdbTrailerManager, cls).getInstance()

    def discoverBasicInformation(self, genre):
        METHOD_NAME = u'TmdbTrailerManager.discoverBasicInformation'
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)

        Debug.myLog(METHOD_NAME + u': started', xbmc.LOGDEBUG)

    def run(self):
        METHOD_NAME = self.__class__.__name__ + u'.run'

        startTime = datetime.datetime.now()
        try:
            self.runWorker()
        except (AbortException, ShutdownException):
            return  # Just exit thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(METHOD_NAME + u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', Trace.STATS)

    def runWorker(self):
        SELECT_FROM_UNIVERSE_OF_TMDB_TRAILERS = True

        Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

        METHOD_NAME = u'TmdbTrailerManager.run'
        #memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        #Debug.myLog(METHOD_NAME + u' memory: ' + str(memory), xbmc.LOGDEBUG)
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
        rating_limit = Constants.ADDON.getSetting(u'rating_limit')
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
        totalPages = 0
        page = 1
        MAX_PAGES = 11
        if source == 'all':

            # Get all of the movies from 11 random pages available
            # containing popular movie information

            for i in range(1, 11):
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'sort_by'] = 'popularity.desc'
                data[u'certification_country'] = 'us'
                data[u'certification.lte'] = rating_limit
                data[u'page'] = page
                url = 'http://api.themoviedb.org/3/discover/movie'
                statusCode, infostring = Utils.getJSON(url, params=data)

                if totalPages == 0:
                    totalPages = infostring[u'total_pages']
                    if totalPages > 1000:
                        totalPages = 1000

                movies = infostring[u'results']
                Debug.myLog(u'Tmdb movies type: ' +
                            type(movies).__name__, xbmc.LOGDEBUG)
                for movie in movies:
                    Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                    trailerId = movie[u'id']
                    trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                    'id': trailerId,
                                    Movie.SOURCE: Movie.TMDB_SOURCE,
                                    Movie.TITLE: movie[Movie.TITLE]}
                    self.addToDiscoveredTrailers(trailerEntry)
                    Debug.myLog(METHOD_NAME + u' ALL title: ' +
                                trailerEntry[Movie.TITLE], xbmc.LOGDEBUG)

                if SELECT_FROM_UNIVERSE_OF_TMDB_TRAILERS and totalPages <= MAX_PAGES:
                    page = Utils.RandomGenerator.randint(2, totalPages)
                else:
                    page += 1
                    if page >= totalPages:
                        break

        # ========================
        #
        #   DVDs
        #
        #  Info comes from Rotton Tomatoes and TMDB
        #  TODO: Need API key?
        #
        # ========================
        elif source == 'dvd':
            data = {}
            data[u'apikey'] = Settings.getRottonTomatoesApiKey()
            data[u'country'] = 'us'
            url = 'http://api.rottentomatoes.com/api/public/v1.0/lists/dvds/new_releases.json'
            statusCode, infostring = Utils.getJSON(url, params=data)

            # TODO- Can you search for more than one move at a time?

            for movie in infostring[u'movies']:
                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'query'] = movie[Movie.TITLE]
                data[u'year'] = movie[u'year']
                url = 'https://api.themoviedb.org/3/search/movie'
                statusCode, infostring = Utils.getJSON(url, params=data)

                for m in infostring[u'results']:
                    trailerId = m[u'id']
                    trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                    'id': trailerId,
                                    Movie.SOURCE: Movie.TMDB_SOURCE,
                                    Movie.TITLE: movie[Movie.TITLE]}
                    self.addToDiscoveredTrailers(trailerEntry)

                    Debug.myLog(METHOD_NAME + u' DVD title: ' +
                                trailerEntry[Movie.TITLE], xbmc.LOGDEBUG)
                    break
        # ========================
        #
        #   Everything else (popular, top_rated, upcoming, now playing)
        #
        # ========================
        else:
            #
            # Get only the first 12 pages of info. Typical for 'popular' movies
            # is 993 pages with ~20,000 results. This means about about 20 movies
            # are on each page. Twelve page should have about 240 movies.
            #
            totalPages = 0
            page = 1
            MAX_PAGES = 11
            for i in range(0, MAX_PAGES):
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'page'] = page
                data[u'language'] = Settings.getLanguage()
                url = 'https://api.themoviedb.org/3/movie/' + source
                statusCode, infostring = Utils.getJSON(url, params=data)

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

                totalResults = infostring[u'total_results']
                totalPages = infostring[u'total_pages']
                Debug.myLog(u'TMDB total_results: ' + str(totalResults) + u' total_pages :' +
                            str(totalPages), xbmc.LOGDEBUG)

                for result in infostring[u'results']:
                    Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                    trailerId = result[u'id']
                    trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                    'id': trailerId,
                                    Movie.SOURCE: Movie.TMDB_SOURCE,
                                    Movie.TITLE: result[Movie.TITLE]}
                    Debug.myLog(METHOD_NAME + u' ' + source + u' title: ' +
                                trailerEntry[Movie.TITLE], xbmc.LOGDEBUG)
                    self.addToDiscoveredTrailers(trailerEntry)

                if SELECT_FROM_UNIVERSE_OF_TMDB_TRAILERS and totalPages <= MAX_PAGES:
                    page = Utils.RandomGenerator.randint(1, totalPages)
                else:
                    page += 1
                    if page >= totalPages:
                        break

        return


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
