'''
Created on Feb 28, 2019

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
from common.debug_utils import Debug
from common.exceptions import AbortException, ShutdownException

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


class Messages:

    TRAILER_EXCEEDS_MAX_PLAY_TIME = u'This trailer exceeds the maximum play time. Terminating'
    TMDB_LABEL = u'TMDb'  # Offical name
    ITUNES_LABEL = u'iTunes'  # VERIFY
    MISSING_TITLE = u'Missing movie title'
    MISSING_DETAIL = u'Unavailable'

    GENRE_ACTION = u'Action'
    GENRE_ALEGORY = u'Alegory'
    GENRE_ANTHOLOGY = u'Anthology'
    GENRE_ADVENTURE = u'Adventure'
    GENRE_ANIMATION = u'Animation'
    GENRE_BIOGRAPHY = u'Biography'
    GENRE_BLACK_COMEDY = u'Black Comedy'
    GENRE_CHILDRENS = u'Children\'s'
    GENRE_COMEDY = u'Comedy'
    GENRE_COMEDY_DRAMA = u'Comedy Drama'
    GENRE_CRIME = u'Crime'
    GENRE_DOCUMENTARY = u'Documentary'
    GENRE_DRAMA = u'Drama'
    GENRE_EPIC = u'Epic'
    GENRE_EXPERIMENTAL = u'Experimental'
    GENRE_FAMILY = u'Family'
    GENRE_FANTASY = u'Fantasy'
    GENRE_FILM_NOIR = u'Film Noir'
    GENRE_GAME_SHOW = u'Game Show'
    GENRE_HISTORY = u'History'
    GENRE_HORROR = u'Horror'
    GENRE_MELODRAMA = u'Melodrama'
    GENRE_MUSIC = u'Music'
    GENRE_MUSICAL = u'Musical'
    GENRE_MUSICAL_COMEDY = u'Musical Comedy'
    GENRE_MYSTERY = u'Mystery'
    GENRE_PERFORMANCE = u'Performance'
    GENRE_PRE_CODE = u'Pre-Code'
    GENRE_ROMANCE = u'Romance'
    GENRE_ROMANCE_COMEDY = u'Romance Comedy'
    GENRE_SATIRE = u'Satire'
    GENRE_SCIENCE_FICTION = u'Science Fiction'
    GENRE_SCREWBALL_COMEDY = u'Screwball Comedy'
    GENRE_SWASHBUCKLER = u'Schwasbuckler'
    GENRE_THRILLER = u'Thriller'
    GENRE_TV_MOVIE = u'TV Movie'
    GENRE_VARIETY = u'Variety'
    GENRE_WAR = u'War'
    GENRE_WAR_DOCUMENTARY = u'War Documentary'
    GENRE_WESTERN = u'Western'
    _instance = None

    def __init__(self):
        pass

    @staticmethod
    def getInstance():
        if Messages._instance is None:
            Messages._instance = Messages()
        return Messages._instance

    def getMsg(self, msgKey):
        return msgKey

    def getFormatedTitle(self, movie):
        trailerType = movie.get(Movie.TYPE, u'')
        if trailerType != u'':
            trailerType = trailerType + u' - '

        year = str(movie.get(Movie.YEAR), u'')
        if year != u'':
            year = u'(' + year + u')'

        titleString = (movie[Movie.TITLE] + u' - ' +
                       movie[Movie.SOURCE] +
                       ' ' + trailerType + year)
        return titleString
