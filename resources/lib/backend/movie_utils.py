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
from xml.dom.minidom import Node
from multiprocessing.pool import ThreadPool

from kodi65 import addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import *
from common.debug_utils import Debug
from settings import Settings
from common.rt_utils import Trace
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
import xbmcdrm
import string


class MovieUtils:
    '''
       Determine which genres are represented in the movie library
    '''

    @staticmethod
    def getGenresInLibrary():
        Debug.myLog('In randomtrailer.getGenresInLibrary', xbmc.LOGNOTICE)
        myGenres = []

        genresString = Utils.getKodiJSON(
            '{"jsonrpc": "2.0", "method": "VideoLibrary.GetGenres", "params": { "properties": [ "title"], "type":"movie"}, "id": 1}')

        genreResult = genresString[u'result']
        for genre in genreResult[u'genres']:
            myGenres.append(genre[u'title'])

        myGenres.sort()
        return myGenres
