'''
Created on Mar 4, 2019

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
from common.rt_utils import Utils
from common.debug_utils import Debug
from common.rt_utils import Playlist
from common.exceptions import AbortException, ShutdownException
from common.rt_utils import WatchDog
from settings import Settings
from common.logger import Trace, Logger
from common.messages import Messages

from backend.rating import Rating
from backend.genre import Genre
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


class ITunes:
    '''
    On first blush, iTunes appears to use 2-letter country codes (ISO-3166-1 alpha-2 
    as well as ISO -639 language names). It is more likely that they use standardized
    sound/subtitle track language codes. 

     _languageCodes = { u'japanese' : u'JP',
                       }
    '''

    @staticmethod
    def getExcludedTypes():
        iso_639_2_name = Settings.getLang_iso_639_2()
        iso_639_1_name = Settings.getLang_iso_639_1()
        Logger(u'ITunes.getExcludedTypes').debug(
            u'iso_639_2:', iso_639_2_name,
            u'iso_639_1:', iso_639_1_name)

        return {"- JP Sub", "Interview", "- UK", "- BR Sub", "- FR", "- IT", "- AU", "- MX", "- MX Sub", "- BR", "- RU", "- DE",
                "- ES", "- FR Sub", "- KR Sub", "- Russian", "- French", "- Spanish", "- German", "- Latin American Spanish", "- Italian"}
