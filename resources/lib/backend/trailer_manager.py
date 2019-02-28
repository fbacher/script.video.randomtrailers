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
                Logger.logException()

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
        localLogger = self._logger.getMethodLogger(u'__init__')
        self._logger.enter()
        if name is None or name == u'':
            name = Constants.ADDON_PATH + u'.BaseTrailerManager'
        super(BaseTrailerManager, self).__init__(group, target, name,
                                                 args, kwargs, verbose)

        localLogger.debug(self.__class__.__name__ +
                          u' set _discoveryComplete = False')
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
        localLogger = self._logger.getMethodLogger(u'finishedDiscovery')
        localLogger.debug(u'before self._lock')

        with self._lock:
            localLogger(u'got self._lock')
            self.shuffleDiscoveredTrailers(markUnplayed=False)
            self._discoveryComplete = True
            self._lock.notify

    def addToDiscoveredTrailers(self, movie):
        localLogger = self._logger.getMethodLogger(
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
                localLogger.debug(u'seconds: ' +
                                  str(secondsSinceLastShuffle))
            else:
                localLogger.debug(u'FirstShuffle')
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
        localLogger = self._logger.getMethodLogger(
            u'shuffleDiscoveredTrailers')
        Monitor.getInstance().throwExceptionIfShutdownRequested()
        localLogger.debug(u'before self._lock')

        with self._lock:
            localLogger.debug(u'got self._lock')

            if len(self._discoveredTrailers) == 0:
                localLogger.debug(u'nothing to shuffle')
                return

            # Shuffle a shallow copy and then put that copy
            # into the._discoveredTrailersQueue
            shuffledTrailers = self._discoveredTrailers[:]
            localLogger.debug('ShuffledTrailers:',
                              len(shuffledTrailers))

            Utils.RandomGenerator.shuffle(shuffledTrailers)
            if markUnplayed:
                for trailer in shuffledTrailers:
                    trailer[Movie.TRAILER_PLAYED] = False

            self._lastShuffledIndex = len(shuffledTrailers) - 1
            localLogger.debug('lastShuffledIndex:', self._lastShuffledIndex)

            # Drain anything previously in queue

            try:
                while True:
                    self._discoveredTrailersQueue.get(block=False)
            except queue.Empty:
                pass

            Monitor.getInstance().throwExceptionIfShutdownRequested()
            localLogger.debug(u'reloading _discoveredTrailersQueue')
            for trailer in shuffledTrailers:
                if not trailer[Movie.TRAILER_PLAYED]:
                    self._discoveredTrailersQueue.put(trailer)

            localLogger.debug(u'_discoverdTrailerQueue length:',
                              self._discoveredTrailersQueue.qsize(),
                              u'_discoveredTrailers length:',
                              len(self._discoveredTrailers))

    def addToReadyToPlayQueue(self, movie):
        localLogger = self._logger.getMethodLogger(u'addToReadyToPlayQueue')
        localLogger.debug(u'movie:', movie[Movie.TITLE], u'queue empty:',
                          self._readyToPlayQueue.empty(), u'full:',
                          self._readyToPlayQueue.full())
        finished = False
        while not finished:
            try:
                self._readyToPlayQueue.put(movie, timeout=0)
                finished = True
            except queue.Full:
                Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=0.75)

        if not BaseTrailerManager.getInstance()._trailersAvailableToPlay.isSet():
            BaseTrailerManager.getInstance()._trailersAvailableToPlay.set()

        localLogger.debug(u'readyToPlayQueue size:',
                          self._readyToPlayQueue.qsize())
        return

    def getNumberOfTrailers(self):
        return len(self._discoveredTrailers)

    def iter(self):
        return self.__iter__()

    def __iter__(self):
        return self

    def next(self):
        return self.__next__()

    def __next__(self):
        localLogger = self._logger.getMethodLogger(u'__next__')
        Trace.log(localLogger.getMsgPrefix(), u'trailersAvail:',
                  BaseTrailerManager.getInstance()._trailersAvailableToPlay.isSet(),
                  trace=Trace.TRACE)

        while not BaseTrailerManager.getInstance()._trailersAvailableToPlay.isSet():
            Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=0.25)

        localLogger.debug(u'BaseTrailerManager.next after trailersAvail wait')
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
            localLogger.debug('Manager: ' + manager.__class__.__name__ + ' size: '
                              + str(manager.getNumberOfTrailers()))
            totalNumberOfTrailers += manager.getNumberOfTrailers()

        localLogger.debug('BaseTrailerManager.next numTrailers: ' +
                          str(totalNumberOfTrailers))

        # Now, randomly pick manager to get a trailer from based upon
        # the number of trailers in each.
        #
        # We loop here because there may not be any trailers in the readyToPlayQueue
        # for a specific manager

        trailer = None
        attempts = 0
        while trailer is None and attempts < 10:
            Monitor.getInstance().throwExceptionIfShutdownRequested()
            trailerIndexToPlay = Utils.RandomGenerator.randint(
                0, totalNumberOfTrailers - 1)
            localLogger.debug(u'BaseTrailerManager.next trailerIndexToPlay: '
                              + str(trailerIndexToPlay))

            totalNumberOfTrailers = 0
            foundManager = None
            for manager in managers:
                localLogger.debug('Manager: ' + manager.__class__.__name__ + ' size: '
                                  + str(manager.getNumberOfTrailers()))
                totalNumberOfTrailers += manager.getNumberOfTrailers()
                if trailerIndexToPlay < totalNumberOfTrailers:
                    foundManager = manager
                    break

            try:
                attempts += 1
                localLogger.debug(u'BaseTrailerManager.next Attempt: ' + str(attempts)
                                  + u' manager: ' + foundManager.__class__.__name__)
                trailer = foundManager._readyToPlayQueue.get(block=False)
                title = trailer[Movie.TITLE] + \
                    u' : ' + trailer[Movie.TRAILER]
                localLogger.debug(u'BaseTrailerManager.next found:', title)
            except queue.Empty:
                trailer = None

        durationOfFirstAttempt = datetime.datetime.now() - startTime
        secondAttemptStartTime = None
        secondMethodAttempts = None

        if trailer is None:
            Trace.log(localLogger.getMsgPrefix(),
                      u' trailer not found by preferred method', trace=Trace.TRACE)

            # Alternative method is to pick a random manager to start with and
            # then find one that has a trailer. Otherwise, camp out.

            secondAttemptStartTime = datetime.datetime.now()
            secondMethodAttempts = 0
            numberOfManagers = len(managers)
            startingIndex = Utils.RandomGenerator.randint(
                0, numberOfManagers - 1)
            managerIndex = startingIndex
            while trailer is None:
                Monitor.getInstance().throwExceptionIfShutdownRequested()
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
                        Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=0.5)

        movie = trailer[Movie.DETAIL_ENTRY]
        movie[Movie.TRAILER_PLAYED] = True
        title = trailer[Movie.TITLE] + \
            u' : ' + trailer[Movie.TRAILER]
        localLogger.debug(u'BaseTrailerManager.next trailer: ' +
                          title)

        duration = datetime.datetime.now() - startTime
        self._next_totalDuration += duration.seconds
        self._next_calls += 1
        self._next_attempts += attempts
        self._next_totalFirstMethodAttempts += attempts

        if trailer is None:
            self._next_failures += 1

        Trace.log(localLogger.getMsgPrefix(), u' elapsedTime: ' + str(duration.seconds) + u' seconds' +
                  u' FirstMethod- elapsedTime: ' +
                  str(durationOfFirstAttempt.seconds)
                  + u' attempts: ' + str(attempts), trace=Trace.STATS)
        if secondMethodAttempts is not None:
            self._next_attempts += secondMethodAttempts
            self._next_second_attempts += secondMethodAttempts
            secondDuration = datetime.datetime.now() - secondAttemptStartTime
            self._next_second_total_Duration += secondDuration.seconds
            Trace.log(localLogger.getMsgPrefix(), u' SecondMethod- attempts: ' +
                      str(secondMethodAttempts) + u' elpasedTime: ' +
                      str(secondDuration.seconds), trace=Trace.STATS)

        Trace.log(localLogger.getMsgPrefix(), u' Playing: ' +
                  trailer[Movie.DETAIL_TITLE], trace=Trace.TRACE)
        return trailer

    '''
        When a trailer can not be found for a movie, then we need to remove it
        so that we don't keep looking for it.
    '''

    def removeDiscoveredTrailer(self, trailer):
        localLogger = self._logger.getMethodLogger(u'removeDiscoveredTrailer')
        localLogger.debug(u' : ',
                          trailer.get(Movie.TITLE))
        localLogger.debug(u' before self._lock')

        with self._lock:
            localLogger.debug(u' got self._lock')

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
        localLogger = self._logger.getMethodLogger(u'loadFetchQueue')
        startTime = datetime.datetime.now()
        if BaseTrailerManager._firstLoad:
            Monitor.getInstance().waitForShutdown(timeout=2.0)
            BaseTrailerManager._firstLoad = False

        Monitor.getInstance().throwExceptionIfShutdownRequested()
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
            Monitor.getInstance().throwExceptionIfShutdownRequested()
            attempts += 1
            shuffle = False
            iterationSuccessful = False
            try:
                elapsed = datetime.datetime.now() - startTime
                if attempts > 0:
                    localLogger.debug(u' Attempt: ' +
                                      str(attempts) + u' elapsed: ' + str(elapsed.seconds))

                if self._trailersToFetchQueue.full():
                    Trace.log(localLogger.getMsgPrefix(),
                              u' _trailersToFetchQueue full', trace=Trace.TRACE)
                    finished = True
                    iterationSuccessful = True
                    fetchQueueFull = True
                elif self._discoveryComplete and len(self._discoveredTrailers) == 0:
                    Trace.log(localLogger.getMsgPrefix(),
                              u' Discovery Complete and nothing found.', trace=Trace.TRACE)
                    finished = True
                    iterationSuccessful = True
                    discoveryFoundNothing = True
                elif self._discoveryComplete and self._discoveredTrailersQueue.empty():
                    Trace.logError(localLogger.getMsgPrefix(),
                                   u'_ discoveryComplete,_discoveredTrailersQueue empty',
                                   trace=Trace.TRACE)
                    shuffle = True
                    discoveryCompleteQueueEmpty += 1
                    #
                    # In the following, Discovery is INCOMPLETE
                    #
                elif (self._discoveredTrailersQueue.empty()
                      and not self._trailersToFetchQueue.empty):
                    discoveredAndFetchQueuesEmpty += 1
                    # Use what we have
                    Trace.log(localLogger.getMsgPrefix(), u'Discovery incomplete._discoveredTrailersQueue',
                              u'empty and _trailersToFetchQueue not empty', trace=Trace.TRACE)
                    finished = True
                elif not self._trailersToFetchQueue.empty():
                    # Fetch queue is not empty, nor full. Discovery
                    # is not complete. Get something from _discoveredTrailerQueue
                    # if available

                    try:
                        discoveryIncompleteFetchNotEmpty += 1
                        trailer = self._discoveredTrailersQueue.get(
                            timeout=0.25)
                        localLogger.debug(
                            u' Got from _discoverdTrailerQueue', xbmc.LOGINFO)
                    except queue.Empty:
                        pass

                    if trailer is not None:
                        try:
                            self._trailersToFetchQueue.put(
                                trailer, timeout=1)
                            Trace.log(localLogger.getMsgPrefix(), u' Put in _trailersToFetchQueue qsize: ' +
                                      str(self._trailersToFetchQueue.qsize()) + u' ' +
                                      trailer.get(Movie.TITLE), trace=Trace.TRACE)
                            iterationSuccessful = True
                        except queue.Full:
                            Trace.log(localLogger.getMsgPrefix(),
                                      u' _trailersToFetchQueue.put failed', trace=Trace.TRACE)
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
                    Trace.log(localLogger.getMsgPrefix(), u' Discovery incomplete, ' +
                              u'_trailersToFetchQueue empty, will wait', trace=Trace.TRACE)

                if not iterationSuccessful:
                    if shuffle:  # Because we were empty
                        Monitor.getInstance().throwExceptionIfShutdownRequested()
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
                                Monitor.getInstance().throwExceptionIfShutdownRequested()

                    putFinished = False
                    while not putFinished:
                        try:
                            putAttempts += 1
                            self._trailersToFetchQueue.put(
                                trailer, timeout=0.25)
                            putFinished = True
                        except queue.Full:
                            Monitor.getInstance().throwExceptionIfShutdownRequested()
                        iterationSuccessful = True

                if trailer is not None:
                    movieTitle = trailer.get(Movie.TITLE)
                else:
                    movieTitle = u'no movie'

                localLogger.debug(u' Queue has: ' + str(self._trailersToFetchQueue.qsize())
                                  + u' Put in _trailersToFetchQueue: ' +
                                  movieTitle)
            except Exception as e:
                Debug.logException(e)
                # TODO Continue?

            if self._trailersToFetchQueue.full():
                finished = True

            if not self._trailersToFetchQueue.empty() and not iterationSuccessful:
                finished = True

            if not finished:
                if attempts % 10 == 0:
                    Trace.logError(localLogger.getMsgPrefix(),
                                   u' hung reloading from._discoveredTrailersQueue.'
                                   + u' length of _discoveredTrailers: '
                                   + str(len(self._discoveredTrailers))
                                   + u' length of._discoveredTrailersQueue: '
                                   + str(self._discoveredTrailersQueue.qsize()), trace=Trace.TRACE)
                Monitor.getInstance().throwExceptionIfShutdownRequested(timeout=0.5)

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

        Trace.log(localLogger.getMsgPrefix(), u' took ' +
                  str(duration.seconds) + u' seconds', trace=Trace.STATS)

    def getFromFetchQueue(self):
        localLogger = self._logger.getMethodLogger(u'getFromFetchQueue')
        self.loadFetchQueue()
        trailer = None
        if self._trailersToFetchQueue.empty():
            localLogger.debug(u': empty')
        while trailer is None:
            try:
                trailer = self._trailersToFetchQueue.get(timeout=0.5)
            except queue.Empty:
                Monitor.getInstance().throwExceptionIfShutdownRequested()

        localLogger.debug(u' ' +
                          trailer[Movie.TITLE])
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
        localLogger = self._logger.getMethodLogger(u'discoverBasicInformation')
        self.setGenre(genre)
        self.start()

        localLogger.debug(u': started')

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        localLogger.debug(u': memory: ' + str(memory))
        startTime = datetime.datetime.now()
        try:
            self.runWorker()
            self.finishedDiscovery()
        except (AbortException, ShutdownException):
            return  # Shut down thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(localLogger.getMsgPrefix(), u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', trace=Trace.STATS)

    def runWorker(self):
        localLogger = self._logger.getMethodLogger(u'runWorker')

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

        if Monitor.getInstance().isShutdownRequested():
            return

        queryResult = Utils.getKodiJSON(query)

        # localLogger.debug('movies: ', json.dumps(movieString, indent=3))
        moviesSkipped = 0
        moviesFound = 0
        moviesWithLocalTrailers = 0
        moviesWithTrailerURLs = 0
        moviesWithoutTrailerInfo = 0

        result = queryResult.get('result', {})
        movies = result.get(u'movies', [])
        Utils.RandomGenerator.shuffle(movies)
        for movie in movies:
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            localLogger.debug('Kodi library movie: ' +
                              json.dumps(movie))
            moviesFound += 1
            if Settings.getHideWatchedMovies() and Movie.LAST_PLAYED in movie:
                if getDaysSinceLastPlayed(movie[Movie.LAST_PLAYED],
                                          movie[Movie.TITLE]) > 0:
                    moviesSkipped += 1
                    continue

            # Normalize rating

            localLogger.debug(u': mpaa: ' + movie[Movie.MPAA] +
                              u' movie: ' + movie[Movie.TITLE])
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
                  str(moviesFound), trace=Trace.STATS)
        Trace.log(u'Local movies filterd out ' +
                  str(moviesSkipped), trace=Trace.STATS)
        Trace.log(u'Movies with local trailers: ' +
                  str(moviesWithLocalTrailers), trace=Trace.STATS)
        Trace.log(u'Movies with trailer URLs: ' +
                  str(moviesWithTrailerURLs), trace=Trace.STATS)
        Trace.log(u'Movies with no trailer information: ' +
                  str(moviesWithoutTrailerInfo), trace=Trace.STATS)

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
        localLogger = self._logger.getMethodLogger(u'discoverBasicInformation')
        localLogger.debug(u' dummy method')

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        localLogger.debug(u' dummy thread, Join Me!')


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
        localLogger = self._logger.getMethodLogger(u'discoverBasicInformation')
        localLogger.debug(u' dummy method')

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        localLogger.debug(u' dummy thread, Join Me!')


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
        localLogger = self._logger.getMethodLogger(u'discoverBasicInformation')
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)
        localLogger.debug(u': started')

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        localLogger.debug(u': memory: ' + str(memory))
        startTime = datetime.datetime.now()
        try:
            self.discoverBasicInformationWorker(Settings.getTrailersPaths())
        except (AbortException, ShutdownException):
            return  # Just exit thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(localLogger.getMsgPrefix(), u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', trace=Trace.STATS)

    def discoverBasicInformationWorker(self, path):
        localLogger = self._logger.getMethodLogger(
            u'discoverBasicInformationWorker')
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
            Monitor.getInstance().throwExceptionIfShutdownRequested()

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
        localLogger = self._logger.getMethodLogger(u'discoverBasicInformation')
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)

        localLogger.debug(u': started')

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        startTime = datetime.datetime.now()
        try:
            self.runWorker()
        except (AbortException, ShutdownException):
            return  # Just exit thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(localLogger.getMsgPrefix(), u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', trace=Trace.STATS)

    def runWorker(self):
        localLogger = self._logger.getMethodLogger(u'runWorker')
        Monitor.getInstance().throwExceptionIfShutdownRequested()

        showOnlyiTunesTrailersOfThisType = Settings.getIncludeItunesTrailerType()
        localLogger.debug('trailer_type: ' +
                          str(showOnlyiTunesTrailersOfThisType), xbmc.LOGINFO)
        if showOnlyiTunesTrailersOfThisType > 4:
            localLogger.debug(u'Invalid iTunes Trailer Type: ' +
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
        localLogger.debug(u'iTunes jsonURL: ' + jsonURL)
        statusCode, parsedContent = Utils.getJSON(jsonURL)
        Utils.RandomGenerator.shuffle(parsedContent)
        localLogger.debug(u'parsedContent: ', json.dumps(parsedContent, ensure_ascii=False,
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

        # localLogger.debug(u'Itunes parsedContent type: ' +
        #            type(parsedContent).__name__)

        for iTunesMovie in parsedContent:
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            localLogger.debug(u'value: ', iTunesMovie, xbmc.LOGINFO)

            title = iTunesMovie.get(
                Movie.TITLE, u'Missing title from iTunes')
            localLogger.debug('title: ', title, xbmc.LOGINFO)

            releaseDateString = iTunesMovie.get('releasedate', u'')
            # localLogger.debug('releaseDateString: ',
            #            releaseDateString, xbmc.LOGINFO)
            if releaseDateString != u'':
                STRIP_TZ_PATTERN = ' .[0-9]{4}$'

                stripTZPattern = re.compile(STRIP_TZ_PATTERN)
                releaseDateString = stripTZPattern.sub('', releaseDateString)
            #    localLogger.debug('releaseDateString: ',
            #                releaseDateString, xbmc.LOGINFO)

                # "Thu, 14 Feb 2019 00:00:00 -0800",
                releaseDate = datetime.datetime.strptime(
                    releaseDateString, '%a, %d %b %Y %H:%M:%S')
            #    localLogger.debug('releaseDate: ', releaseDate.strftime(
            #        '%d-%m-%Y'), xbmc.LOGINFO)
            else:
                releaseDate = datetime.date.today()

            studio = iTunesMovie.get('studio', u'')

            #localLogger.debug('studio: ', studio, xbmc.LOGINFO)

            poster = iTunesMovie.get('poster', u'')

            #localLogger.debug('poster: ', poster, xbmc.LOGINFO)

            thumb = string.replace(poster, 'poster.jpg', 'poster-xlarge.jpg')
            fanart = string.replace(poster, 'poster.jpg', 'background.jpg')

            #localLogger.debug('thumb:', thumb, ' fanart: ', fanart, xbmc.LOGINFO)

            poster_2x = iTunesMovie.get('poster_2x', u'')

            #localLogger.debug('poster_2x: ', poster_2x, xbmc.LOGINFO)

            location = iTunesMovie.get('location', u'')

            #localLogger.debug('location: ', location, xbmc.LOGINFO)

            # Normalize rating
            # We expect the attribute to be named 'mpaa', not 'rating'

            iTunesMovie[Movie.MPAA] = iTunesMovie[u'rating']
            rating = Rating.getMPAArating(
                iTunesMovie.get(Movie.MPAA), iTunesMovie.get(u'adult'))
            #localLogger.debug('rating: ', rating, xbmc.LOGINFO)

            genres = iTunesMovie.get(u'genre', u'')
            #localLogger.debug('genres: ', genres, xbmc.LOGINFO)

            directors = iTunesMovie.get('directors', [])

            #localLogger.debug('directors: ', directors, xbmc.LOGINFO)

            actors = iTunesMovie.get('actors', [])

            #localLogger.debug('actors: ', actors, xbmc.LOGINFO)

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

            iTunesTrailersList = iTunesMovie.get('trailers', [])

            # localLogger.debug('iTunesTrailersList: ',
            #            iTunesTrailersList, xbmc.LOGINFO)
            for iTunesTrailer in iTunesTrailersList:
                Monitor.getInstance().throwExceptionIfShutdownRequested()

                keepTrailer = True
                localLogger.debug('iTunesTrailer: ',
                                  iTunesTrailer, xbmc.LOGINFO)
                postDate = iTunesTrailer.get('postdate', u'')

                #localLogger.debug('postDate: ', postDate, xbmc.LOGINFO)

                url = iTunesTrailer.get('url', u'')

                localLogger.debug('url: ', url, xbmc.LOGINFO)
                # RE_URL_INFO = re.compile('trailers\/([^\/]+)\/([^\/]+)')
                # RE_URL_INFO.

                trailerType = iTunesTrailer.get('type', u'')

                localLogger.debug('type: ', trailerType, xbmc.LOGINFO)

                if trailerType.startswith(u'Clip') and not Settings.getIncludeClips():
                    localLogger.debug('Rejecting due to clip')
                    keepTrailer = False
                elif trailerType in excludeTypesSet:
                    localLogger.debug(
                        'Rejecting due to exclude Trailer Type')
                    keepTrailer = False
                elif not Settings.getIncludeFeaturettes() and (trailerType == u'Featurette'):
                    localLogger.debug('Rejecting due to Featurette')
                    keepTrailer = False
                elif ((Settings.getIncludeItunesTrailerType() == iTunes.COMMING_SOON) and
                      (releaseDate < datetime.date.today())):
                    localLogger.debug(
                        'Rejecting due to COMMING_SOON and already released')
                    keepTrailer = False
                elif self.allowedGenre != u'' and self.allowedGenre not in genres:
                    keepTrailer = False
                    localLogger.debug('Rejecting due to genre: ' +
                                      self.allowedGenre)
                elif not Rating.checkRating(rating):
                    keepTrailer = False
                    localLogger.debug('Rejecting due to rating: ' +
                                      rating)
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
                    localLogger.debug('Adding iTunes trailer: ',
                                      movie, xbmc.LOGINFO)
                    Debug.validateBasicMovieProperties(movie)
                    self.addToDiscoveredTrailers(movie)

        # self.getItunesTrailersOld()
        return


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
        localLogger = self._logger.getMethodLogger(u'discoverBasicInformation')
        self.setGenre(genre)
        self.start()
        self._trailerFetcher.startFetchers(self)

        localLogger.debug(u': started')

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')

        startTime = datetime.datetime.now()
        try:
            self.runWorker()
        except (AbortException, ShutdownException):
            return  # Just exit thread
        except Exception:
            Debug.logException()

        duration = datetime.datetime.now() - startTime
        Trace.log(localLogger.getMsgPrefix(), u' Time to discover: ' +
                  str(duration.seconds) + u' seconds', trace=Trace.STATS)

    def runWorker(self):
        localLogger = self._logger.getMethodLogger(u'runWorker')

        SELECT_FROM_UNIVERSE_OF_TMDB_TRAILERS = True
        Monitor.getInstance().throwExceptionIfShutdownRequested()

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

        localLogger.debug(u' source; ' + source)

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
                Monitor.getInstance().throwExceptionIfShutdownRequested()

                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                # We don't need a sort do we?
                data[u'sort_by'] = 'popularity.desc'
                data[u'certification_country'] = 'us'
                data[u'certification.lte'] = rating_limit
                data[u'page'] = page
                # TODO: include_adult boolean
                # language
                # string
                # Specify a language to query translatable fields with.
                # minLength: 2
                # pattern: ([a-z]{2})-([A-Z]{2})
                # default: en-US
                '''
                    
                    Specify a ISO 3166-1 code to filter release dates. Must be uppercase.
                    pattern: ^[A-Z]{2}$
                    optional
                    sort_by
                    string
                    
                    Choose from one of the many available sort options.
                    optional
                    certification_country
                    string
                    
                    Used in conjunction with the certification filter, use this to specify
                     a country with a valid certification.
                    optional
                    certification
                    string
                    
                    Filter results with a valid certification from the 'certification_country' field.
                    optional
                    certification.lte
                    string
                    
                    Filter and only include movies that have a certification that is
                     less than or equal to the specified value.
                    optional
                    include_adult
                    boolean
                    
                    A filter and include or exclude adult movies.
                    optional
                    include_video
                    boolean
                    
                    A filter to include or exclude videos.
                    default
                    optional
                    page
                    integer
                    
                    Specify the page of results to query.
                    minimum: 1
                    maximum: 1000
                    default: 1
                    optional
                    primary_release_year
                    integer
                    
                    A filter to limit the results to a specific primary release year.
                    optional
                    primary_release_date.gte
                    string
                    
                    Filter and only include movies that have a primary release date 
                    that is greater or equal to the specified value.
                    format: date
                    optional
                    primary_release_date.lte
                    string
                    
                    Filter and only include movies that have a primary release date 
                    that is less than or equal to the specified value.
                    optional
                    release_date.gte
                    string
                    
                    Filter and only include movies that have a release date (looking at
                     all release dates) that is greater or equal to the specified value.
                    format: date
                    optional
                    release_date.lte
                    string
                    
                    Filter and only include movies that have a release date (looking at 
                    all release dates) that is less than or equal to the specified value.
                    format: date
                    optional
                    vote_count.gte
                    integer
                    
                    Filter and only include movies that have a vote count that is 
                    greater or equal to the specified value.
                    minimum: 0
                    optional
                    vote_count.lte
                    integer
                    
                    Filter and only include movies that have a vote count that is l
                    ess than or equal to the specified value.
                    minimum: 1
                    optional
                    vote_average.gte
                    number
                    
                    Filter and only include movies that have a rating that is greater
                     or equal to the specified value.
                    minimum: 0
                    optional
                    vote_average.lte
                    number
                    
                    Filter and only include movies that have a rating that is less 
                    than or equal to the specified value.
                    minimum: 0
                    optional
                    with_cast
                    string
                    
                    A comma separated list of person ID's. Only include movies that
                     have one of the ID's added as an actor.
                    optional
                    with_crew
                    string
                    
                    A comma separated list of person ID's. Only include movies that 
                    have one of the ID's added as a crew member.
                    optional
                    with_companies
                    string
                    
                    A comma separated list of production company ID's. Only include 
                    
                    movies that have one of the ID's added as a production company.
                    optional
                    with_genres
                    string
                    
                    Comma separated value of genre ids that you want to include in 
                    the results.
                    optional
                    with_keywords
                    string
                    
                    A comma separated list of keyword ID's. Only include movies that
                     have one of the ID's added as a keyword.
                    optional
                    with_people
                    string
                    
                    A comma separated list of person ID's. Only include movies that 
                    have one of the ID's added as a either a actor or a crew member.
                    optional
                    year
                    integer
                    
                    A filter to limit the results to a specific year (looking at all
                     release dates).
                    optional
                    without_genres
                    string
                    
                    Comma separated value of genre ids that you want to exclude from 
                    the results.
                    optional
                    with_runtime.gte
                    integer
                    
                    Filter and only include movies that have a runtime that is greater
                     or equal to a value.
                    optional
                    with_runtime.lte
                    integer
                    
                    Filter and only include movies that have a runtime that is less
                     than or equal to a value.
                    optional
                    with_release_type
                    integer
                    
                    Specify a comma (AND) or pipe (OR) separated value to filter
                     release types by. These release types map to the same values found on the movie release date method.
                    minimum: 1
                    maximum: 6
                    optional
                    with_original_language
                    string
                    
                    Specify an ISO 639-1 string to filter results by their original 
                    language value.
                    optional
                    without_keywords
                    string
                    
                    Exclude items with certain keywords. You can comma and pipe 
                    separate these values to create an 'AND' or 'OR' logic.

                '''
                url = 'http://api.themoviedb.org/3/discover/movie'
                statusCode, infostring = Utils.getJSON(url, params=data)

                if totalPages == 0:
                    totalPages = infostring[u'total_pages']
                    if totalPages > 1000:
                        totalPages = 1000

                movies = infostring[u'results']
                localLogger.debug(u'Tmdb movies type: ' +
                                  type(movies).__name__)
                for movie in movies:
                    Monitor.getInstance().throwExceptionIfShutdownRequested()

                    trailerId = movie[u'id']
                    trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                    'id': trailerId,
                                    Movie.SOURCE: Movie.TMDB_SOURCE,
                                    Movie.TITLE: movie[Movie.TITLE]}
                    self.addToDiscoveredTrailers(trailerEntry)
                    localLogger.debug(u' ALL title: ' +
                                      trailerEntry[Movie.TITLE])

                if SELECT_FROM_UNIVERSE_OF_TMDB_TRAILERS and totalPages <= MAX_PAGES:
                    page = Utils.RandomGenerator.randint(2, totalPages)
                else:
                    page += 1
                    if page >= totalPages:
                        break

        #
        # API key used is marked inactive. Terms from Rotten Tomatoes appears to
        # require logo displayed and probably other disclosures. I have not
        # researched this much, but this seems to go against Kodi's open-source
        # goals, if not rules.
        #
        # ========================
        #
        #   DVDs
        #
        #  Info comes from Rotton Tomatoes and TMDB
        #  TODO: Need API key?
        #
        # ========================
        # elif source == 'dvd':
        #    data = {}
        #    data[u'apikey'] = Settings.getRottonTomatoesApiKey()
        #    data[u'country'] = 'us'
        #    url = 'http://api.rottentomatoes.com/api/public/v1.0/lists/dvds/new_releases.json'
        #    statusCode, infostring = Utils.getJSON(url, params=data)
        #
        #    # TODO- Can you search for more than one move at a time?
        #
        #    for movie in infostring[u'movies']:
        #        data = {}
        #        data[u'api_key'] = Settings.getTmdbApiKey()
        #        data[u'query'] = movie[Movie.TITLE]
        #        data[u'year'] = movie[u'year']
        #        url = 'https://api.themoviedb.org/3/search/movie'
        #        statusCode, infostring = Utils.getJSON(url, params=data)
        #
        #        for m in infostring[u'results']:
        #            trailerId = m[u'id']
        #            trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
        #                            'id': trailerId,
        #                            Movie.SOURCE: Movie.TMDB_SOURCE,
        #                            Movie.TITLE: movie[Movie.TITLE]}
        #            self.addToDiscoveredTrailers(trailerEntry)
        #
        #            localLogger.debug(u' DVD title: ' +
        #                              trailerEntry[Movie.TITLE])
        #            break
        #
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
                Monitor.getInstance().throwExceptionIfShutdownRequested()

                data = {}
                data[u'api_key'] = Settings.getTmdbApiKey()
                data[u'page'] = page
                data[u'language'] = Settings.getLanguage()
                url = 'https://api.themoviedb.org/3/movie/' + source
                statusCode, infostring = Utils.getJSON(
                    url, params=data, dumpResults=True)

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
                localLogger.debug(u'TMDB total_results: ' + str(totalResults) + u' total_pages :' +
                                  str(totalPages))

                for result in infostring[u'results']:
                    Monitor.getInstance().throwExceptionIfShutdownRequested()

                    trailerId = result[u'id']
                    trailerEntry = {Movie.TRAILER: Movie.TMDB_SOURCE,
                                    'id': trailerId,
                                    Movie.SOURCE: Movie.TMDB_SOURCE,
                                    Movie.TITLE: result[Movie.TITLE]}
                    localLogger.debug(u' ' + source + u' title: ' +
                                      trailerEntry[Movie.TITLE])
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
    localLogger = Logger
    (u'getDaysSinceLastPlayed')

    daysSincePlayed = -1
    try:
        if lastPlayedField is not None and lastPlayedField != u'':
            pd = time.strptime(lastPlayedField, u'%Y-%m-%d %H:%M:%S')
            pd = time.mktime(pd)
            pd = datetime.datetime.fromtimestamp(pd)
            lastPlay = datetime.datetime.now() - pd
            daysSincePlayed = lastPlay.days
    except Exception as e:
        localLogger.debug(u'Invalid lastPlayed field for ' + movieName + ' : ' +
                          lastPlayedField)
        traceBack = traceback.format_exc()
        localLogger.debug(traceBack)
        raise e
    return daysSincePlayed
