'''
Created on Feb 19, 2019

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


class Debug:

    @staticmethod
    def myLog(*args):
        METHOD_NAME = u'Debug.myLog'
        msg = u''.encode(u'utf-8')
        logType = args[len(args) - 1]
        saveMsg = u''.encode(u'utf-8')

        try:
            for p in args[0:len(args) - 1]:
                myType = None
                if p is None:
                    newP = str('None')
                elif isinstance(p, unicode):
                    newP = p.encode(u'utf-8')
                elif isinstance(p, list):
                    newP = str(p)
                elif isinstance(p, dict):
                    newP = json.dumps(p, ensure_ascii=False,
                                      encoding=u'utf-8', indent=4,
                                      sort_keys=True)
                    newP = str(p)
                elif isinstance(p, bool):
                    newP = str(p)
                elif isinstance(p, int):
                    newP = str(p)
                elif isinstance(p, str):
                    newP = p
                # Checking for class name of 'str' seems nuts, but
                # it has to do with using the _future_ libs
                elif p is not None and type(p).__name__ != u'str':
                    newP = str(p)
                    myType = type(p).__name__
                    xbmc.log(METHOD_NAME + u' unknown type: ' +
                             myType, xbmc.LOGDEBUG)

                msg += newP
                saveMsg = msg
        except Exception as e:
            Debug.logException(e)
            text = u'Blew up creating message for Logging printing log fragment: '
            msg = text + saveMsg

        xbmc.log(msg, logType)

    @staticmethod
    def logException(e=None):

        exec_type, exec_value, exec_traceback = sys.exc_info()
        stringBuffer =\
            u'LEAK: TraceBack Traceback traceback stacktrace Stacktrace StackTrace:\n'
        lines = traceback.format_exception(
            exec_type, exec_value, exec_traceback)
        if len(lines) == 0:
            xbmc.log(u'No lines in traceback execType: ' +
                     str(exec_type), xbmc.LOGDEBUG)

            Debug.dumpStack()

        else:
            for line in lines:
                stringBuffer += line + u'\n'

            xbmc.log(stringBuffer.encode(u'utf-8'), xbmc.LOGERROR)

    @staticmethod
    def dumpDictionaryKeys(d):
        for k, v in d.items():
            if isinstance(v, dict):
                Debug.dumpDictionaryKeys(v)
            else:
                Debug.myLog('{0} : {1}'.format(k, v), xbmc.LOGDEBUG)

    @staticmethod
    def dumpStack(msg=u''):
        traceBack = traceback.format_stack(limit=15)
        xbmc.log(msg, xbmc.LOGERROR)
        for line in traceBack:
            xbmc.log(line, xbmc.LOGERROR)

    @staticmethod
    def dumpAllThreads():
        buffer = u'\n*** STACKTRACE - START ***\n'
        code = []
        for threadId, stack in sys._current_frames().items():
            code.append("\n# ThreadID: %s" % threadId)
            for filename, lineno, name, line in traceback.extract_stack(stack):
                code.append('File: "%s", line %d, in %s' % (filename,
                                                            lineno, name))
                if line:
                    code.append("  %s" % (line.strip()))

        for line in code:
            buffer = buffer + '\n' + line
        buffer = buffer + u'\n*** STACKTRACE - END ***\n'

        xbmc.log(buffer, xbmc.LOGDEBUG)

    @staticmethod
    def dumpAPI():
        x = xbmc.executeJSONRPC(
            '{ "jsonrpc": "2.0", "method": "JSONRPC.Introspect", "params": { "filter": { "id": "VideoLibrary.GetMovies", "type": "method" } }, "id": 1 }')
        x = json.loads(x, encoding=u'utf-8')
        Debug.myLog('introspection: ', x, xbmc.LOGDEBUG)

    @staticmethod
    def compareMovies(trailer, newTrailer):
        for key in trailer:
            if newTrailer.get(key) is None:
                Debug.myLog(u'CompareMovies- key: ' + key + u' is missing from new. Value: ',
                            trailer.get(key), xbmc.LOGINFO)

            elif trailer.get(key) is not None and trailer.get(key) != newTrailer.get(key):
                Debug.myLog(u'Values for: ' + key + u' different: ', trailer.get(key),
                            u' new: ', newTrailer.get(key), xbmc.LOGINFO)

        for key in newTrailer:
            if trailer.get(key) is None:
                Debug.myLog(u'CompareMovies- key: ' + key + u' is missing from old. Value: ',
                            newTrailer.get(key), xbmc.LOGINFO)

    @staticmethod
    def validateBasicMovieProperties(movie):
        basicProperties = (
            Movie.TYPE,
            Movie.FANART,
            Movie.THUMBNAIL,
            Movie.TRAILER,
            Movie.SOURCE,
            Movie.FILE,
            Movie.YEAR,
            Movie.TITLE)

        for propertyName in basicProperties:
            if movie.get(propertyName) is None:
                Debug.dumpStack(u'Missing basicProperty: ' + propertyName)
                movie.setdefault(propertyName, u'default_' + propertyName)

    @staticmethod
    def validateDetailedMovieProperties(movie):

        detailsProperties = (Movie.WRITER,
                             Movie.DETAIL_DIRECTORS,
                             Movie.CAST,
                             Movie.PLOT,
                             Movie.GENRE,
                             Movie.STUDIO,
                             Movie.RUNTIME,
                             # Movie.ADULT,
                             Movie.MPAA)

        Debug.validateBasicMovieProperties(movie)
        for propertyName in detailsProperties:
            if movie.get(propertyName) is None:
                Debug.dumpStack(u'Missing detailsProperty: ' + propertyName)
                movie.setdefault(propertyName, u'default_' + propertyName)
