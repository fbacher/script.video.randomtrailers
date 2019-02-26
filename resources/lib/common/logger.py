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
from xml.dom import minidom
from kodi65 import addon
from kodi65 import utils
from functools import wraps
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.exceptions import AbortException
from action_map import Action
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
#import xbmcwsgi
import xbmcdrm
import string
import action_map


class Logger:

    _addonName = u''

    @staticmethod
    def setAddonName(name):
        Logger._addonName = name

    def __init__(self, className=u''):
        self._className = className
        self._methodName = u''

    def getMethodLogger(self, methodName=u''):
        methodLogger = Logger(self._className)

        methodLogger._methodName = methodName
        return methodLogger

    def getMsgPrefix(self):
        separator = u''
        prefix = u''
        segments = [Logger._addonName, self._className, self._methodName]
        for segment in segments:
            prefix = prefix + separator + segment
            if len(prefix) > 0:
                separator = u'.'
        return prefix

    def log(self, text, *args, **kwargs):
        kwargs.setdefault(u'prefix', None)
        kwargs.setdefault(u'log_level', xbmc.LOGDEBUG)
        kwargs.setdefault(u'separator', u' ')
        prefix = kwargs[u'prefix']
        log_level = kwargs[u'log_level']
        separator = kwargs[u'separator']
        if not prefix:
            prefix = self.getMsgPrefix()

        log_line = u'[%s] %s' % (prefix, text)

        for text in args:
            log_line = log_line + separator + u'%s' % (text)

        xbmc.log(log_line.encode(u'utf-8'), log_level)

    def debug(self, text, *args, **kwargs):
        kwargs.setdefault(u'prefix', None)
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def info(self, text, *args, **kwargs):
        kwargs.setdefault(u'prefix', None)
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def notice(self, text, *args, **kwargs):
        kwargs.setdefault(u'prefix', None)
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def warning(self, text, *args, **kwargs):
        kwargs.setdefault(u'prefix', None)
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def error(self, text, *args, **kwargs):
        kwargs.setdefault(u'prefix', None)
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def enter(self):
        self.debug(u'Entering')

    def exit(self):
        self.debug(u'Exiting')

    def logException(self, e=None):

        exec_type, exec_value, exec_traceback = sys.exc_info()
        stringBuffer =\
            u'LEAK: TraceBack Traceback traceback stacktrace Stacktrace StackTrace:\n'
        lines = traceback.format_exception(
            exec_type, exec_value, exec_traceback)
        if len(lines) == 0:
            xbmc.log(u'No lines in traceback execType: ' +
                     str(exec_type), xbmc.LOGDEBUG)

            self.dumpStack()

        else:
            for line in lines:
                stringBuffer += line + u'\n'

            xbmc.log(stringBuffer.encode(u'utf-8'), xbmc.LOGERROR)

    def dumpStack(self, msg=u''):
        traceBack = traceback.format_stack(limit=15)
        xbmc.log(msg, xbmc.LOGERROR)
        for line in traceBack:
            xbmc.log(line, xbmc.LOGERROR)


def logExit(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        className = func.__class__.__name__
        methodName = func.__name__
        localLogger = Logger(className).getMethodLogger(methodName)
        func(*args, **kwargs)
        localLogger.exit()
    return func_wrapper


def logEntry(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        className = func.__class__.__name__
        methodName = func.__name__
        localLogger = Logger(className).getMethodLogger(methodName)
        localLogger.enter()
        func(*args, **kwargs)
    return func_wrapper


def logEntryExit(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        className = func.__class__.__name__
        methodName = func.__name__
        localLogger = Logger(className).getMethodLogger(methodName)
        localLogger.enter()
        func(*args, **kwargs)
        localLogger.exit()
    return func_wrapper


class Trace:
    TRACE = u'TRACE'
    STATS = u'STATS'
    TRACE_UI = u'TRACE_UI'
    STATS_UI = u'STATS_UI'
    TRACE_DISCOVERY = u'TRACE_DISCOVERY'
    STATS_DISCOVERY = u'STATS_DISCOVERY'

    _traceCatagories = set()
    _logger = None

    @staticmethod
    def configure():
        if Settings.isTraceEnabled():
            Trace.enable(Trace.TRACE)

        if Settings.isTraceStatsEnabled():
            Trace.enable(Trace.STATS)

    @staticmethod
    def log(msg, *flags):
        if Trace._logger is None:
            Trace._logger = Logger()

        found = False
        prefix = u''
        separator = u''
        for flag in flags:
            if flag in Trace._traceCatagories:
                found = True
                prefix += separator + flag
                separator = u', '

        if found:
            prefix = prefix + u': '
            Trace._logger.log(msg,
                              prefix=prefix, log_level=xbmc.LOGDEBUG)

    @staticmethod
    def logError(msg, *flags):
        Trace.log(msg, *flags)
        Trace._logger.log(msg, prefix=u'', log_level=xbmc.LOGERROR)

    @staticmethod
    def enable(*flags):
        for flag in flags:
            Trace._traceCatagories.add(flag)

    @staticmethod
    def disable(*flags):
        for flag in flags:
            Trace._traceCatagories.remove(flag)
