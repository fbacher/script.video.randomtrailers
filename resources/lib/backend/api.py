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
from settings import Settings
from common.debug_utils import Debug
from backend.movie_utils import MovieUtils
from common.monitor import Monitor
import xbmc
from backend.trailer_manager import *

'''
from kodi65 import addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import Utils
from common.rt_utils import Playlist
from common.rt_utils import AbortException
from common.rt_utils import WatchDog
from common.rt_utils import Trace
from backend.trailer_fetcher import TrailerFetcher
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
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
import xbmcdrm
import string
'''


def LoadTrailers(selectedGenre):
    # Find trailers for movies in library

    Debug.myLog(u'getIncludeLibraryTrailers', xbmc.LOGDEBUG)

    if Settings.getIncludeLibraryTrailers():
        Debug.myLog(u'LibTrailers True', xbmc.LOGDEBUG)
        libInstance = LibraryTrailerManager.getInstance()
        libInstance.discoverBasicInformation(selectedGenre)
    else:
        Debug.myLog(u'LibTrailers False', xbmc.LOGDEBUG)

    # Manufacture trailer entries for folders which contain trailer
    # files. Note that files are assumed to be videos.
    if Settings.getIncludeTrailerFolders():
        FolderTrailerManager.getInstance().discoverBasicInformation(u'')

    if Settings.getIncludeItunesTrailers():
        ItunesTrailerManager.getInstance().discoverBasicInformation(u'')  # genre broken

    if Settings.getIncludeTMDBTrailers():
        TmdbTrailerManager.getInstance().discoverBasicInformation(selectedGenre)

    xbmc.sleep(1000)
    Monitor.getInstance().setStartupComplete()


def getGenresInLibrary():
    return MovieUtils.getGenresInLibrary()
