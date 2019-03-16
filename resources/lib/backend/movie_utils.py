'''
Created on Feb 11, 2019

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
from common.messages import Messages
from common.monitor import Monitor
from common.rt_utils import WatchDog
from common.logger import Trace, Logger

from backend.rating import Rating
from backend.genre import Genre
from backend import backend_constants
from backend.itunes import ITunes
from settings import Settings
from common.tmdb_settings import TmdbSettings

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


class MovieUtils:
    _instance = None

    def __init__(self):
        self._genreMap = {}
        self._actorMap = {}
        self._tagMap = {}

    @staticmethod
    def getInstance():
        if MovieUtils._instance is None:
            MovieUtils._instance = MovieUtils()

        return MovieUtils._instance

    '''
       Determine which genres are represented in the movie library
    '''

    @staticmethod
    def getGenresInLibrary():
        Debug.myLog('In randomtrailer.getGenresInLibrary', xbmc.LOGNOTICE)
        myGenres = []

        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetGenres", \
                 "params": {\
                    "type" : "movie"\
                        }, \
                         "id": 1}'
        queryResult = Utils.getKodiJSON(query, dumpResults=True)

        genreResult = queryResult[u'result']
        for genreEntry in genreResult.get(u'genres', []):
            genre = genreEntry[u'label']
            myGenres.append(genre)

        myGenres.sort()
        return myGenres

    def collectData(self, movie):
        self.collectActors(movie)
        self.collectGenres(movie)
        self.collectTags(movie)

    def reportData(self):
        self.reportActors()
        self.reportGenreMap()
        self.reportTagMap()
        genres = MovieUtils.getInstance().getGenresInLibrary()
        MovieUtils.getInstance().reportGenres(genres)
        tags = MovieUtils.getInstance().discoverTags()
        MovieUtils.getInstance().reportTags(tags)

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
                if self._actorMap.get(actor) is None:
                    self._actorMap[actor] = []
                self._actorMap[actor].append(movieId)
            if actorCount == Settings.getMaxTopActors():
                break

    def reportActors(self, msg=u''):
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
            stringBuffer = actor + u' : ' + str(len(moviesIn))
            for movie in sorted(moviesIn):
                if len(stringBuffer) > 100:
                    playlist.writeLine(stringBuffer)
                    stringBuffer = u'       '
                stringBuffer = stringBuffer + u' ' + movie

            playlist.writeLine(stringBuffer)

        playlist.close()

    def collectTags(self, movie):
        tags = movie.get(Movie.TAG, [])
        movieName = movie[Movie.TITLE]
        movieYear = movie[Movie.YEAR]
        movieId = movieName + u' (' + str(movieYear) + u')'

        tagCount = 0
        for tag in tags:
            tagCount += 1
            if self._tagMap.get(tag) is None:
                self._tagMap[tag] = []
            self._tagMap[tag].append(movieId)

    def reportGenreMap(self, msg=u''):
        # First sort by number of movies that each genre is
        # in

        a = sorted(self._genreMap, key=lambda key: len(
            self._genreMap[key]), reverse=True)

        playlist = Playlist.getPlaylist(
            u'GenreFrequency.playlist', append=False)

        for genre in a:
            moviesIn = self._genreMap[genre]
            stringBuffer = genre + u' : ' + str(len(moviesIn))
            for movie in sorted(moviesIn):
                if len(stringBuffer) > 100:
                    playlist.writeLine(stringBuffer)
                    stringBuffer = u'       '
                stringBuffer = stringBuffer + u' ' + movie

            playlist.writeLine(stringBuffer)

        playlist.close()

    def collectGenres(self, movie):
        genres = movie.get(Movie.GENRE, [])
        movieName = movie[Movie.TITLE]
        movieYear = movie[Movie.YEAR]
        movieId = movieName + u' (' + str(movieYear) + u')'

        genreCount = 0
        for genre in genres:
            genreCount += 1
            if self._genreMap.get(genre) is None:
                self._genreMap[genre] = []
            self._genreMap[genre].append(movieId)

    def reportGenres(self, genres):
        stringBuffer = u''
        separator = u''
        playlist = Playlist.getPlaylist(
            u'Genres.playlist', append=False)
        for genre in genres:
            stringBuffer = stringBuffer + separator + genre
            separator = u', '
            if len(stringBuffer) > 100:
                playlist.writeLine(stringBuffer)
                stringBuffer = u'       '
                separator = u''

        playlist.close()

    def discoverTags(self):
        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetTags", \
                    "params": {\
                    "type" : "movie"\
                        }, \
                         "id": 1}'
        queryResult = Utils.getKodiJSON(query)
        tags = []
        for tag in queryResult.get(u'result', {}).get(u'tags', []):
            tags.append(tag[u'label'])

        tags = sorted(tags)
        return tags

    def reportTags(self, tags):
        stringBuffer = u''
        separator = u''
        playlist = Playlist.getPlaylist(
            u'Tags.playlist', append=False)
        for tag in tags:
            stringBuffer = stringBuffer + separator + tag
            separator = u', '
            if len(stringBuffer) > 100:
                playlist.writeLine(stringBuffer)
                stringBuffer = u'       '
                separator = u''

        playlist.close()

    def reportTagMap(self, msg=u''):
        # First sort by number of movies that each tag is
        # in

        a = sorted(self._tagMap, key=lambda key: len(
            self._tagMap[key]), reverse=True)

        playlist = Playlist.getPlaylist(
            u'TagFrequency.playlist', append=False)

        for tag in a:
            moviesIn = self._tagMap[tag]
            stringBuffer = tag + u' : ' + str(len(moviesIn))
            for movie in sorted(moviesIn):
                if len(stringBuffer) > 100:
                    playlist.writeLine(stringBuffer)
                    stringBuffer = u'       '
                stringBuffer = stringBuffer + u' ' + movie

            playlist.writeLine(stringBuffer)

        playlist.close()
