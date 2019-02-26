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

from kodi65 import addon
from kodi65 import utils
from multiprocessing.pool import ThreadPool
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import *
from common.debug_utils import Debug
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
import urllib
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
import string


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
