# monitors onScreensaverActivated event and checks guisettings.xml for plugin.video.randomtrailers.
# if found it will launch plugin.video.randomtrailers which will show trailers.
# this gets around Kodi killing a screensaver 5 seconds after
# onScreensaverDeactivate

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


def isTrailerScreensaver():
    pguisettings = xbmc.translatePath(os.path.join(
        'special://userdata', 'guisettings.xml')).decode('utf-8')
    xbmc.log(pguisettings)
    name = '<mode>script.video.randomtrailers</mode>'
    if name in file(pguisettings, "r").read():
        xbmc.log('found script.video.randomtrailers in guisettings.html')
        return True
    else:
        xbmc.log('did not find script.video.randomtrailers in guisettings.html')
        return False


class MyMonitor(xbmc.Monitor):

    def __init__(self):
        pass

    def onScreensaverActivated(self):
        if isTrailerScreensaver():
            xbmc.executebuiltin(
                'xbmc.RunScript("script.video.randomtrailers","no_genre")')


m = MyMonitor()
Monitor.getSingletonInstance().waitForShutdown()
xbmc.Player().stop
del m
