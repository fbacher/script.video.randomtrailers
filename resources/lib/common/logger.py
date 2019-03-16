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
from common.exceptions import AbortException, ShutdownException
from action_map import Action
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
    _logger = None
    _traceGroups = {}

    @staticmethod
    def setAddonName(name):
        Logger._addonName = name

    def __init__(self, className=u'', traceGroupName=None, trace=[],
                 traceDefault=[]):
        try:
            self._className = className
            self._methodName = u''
            self._traceCategories = set()
            self._defaultTraceCategories = set()

            self._traceCategories.update(trace)
            self._defaultTraceCategories.update(traceDefault)

            if traceGroupName is not None:
                if traceGroupName in Logger._traceGroups:
                    msg = (u'Trace group: ' + traceGroupName +
                           u' already exists, will not persist this instance')
                    xbmc.log(msg.encode(u'utf-8'), xbmc.LOGERROR)
                else:
                    Logger._traceGroups[traceGroupName] = self
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            Logger.logException()

    def getMethodLogger(self, methodName=u''):
        methodLogger = Logger(self._className)

        methodLogger._methodName = methodName
        return methodLogger

    def getMsgPrefix(self):
        separator = u''
        prefix = u''
        segments = [Logger._addonName, self._className, self._methodName]
        for segment in segments:
            if len(segment) != 0:
                prefix = prefix + separator + segment
                if len(prefix) > 0:
                    separator = u'.'
        return prefix

    def trace(self, *args, **kwargs):  # log_level=xbmc.LOGDEBUG, trace=[]):
        try:
            kwargs.setdefault(u'log_level', xbmc.LOGDEBUG)
            kwargs.setdefault(u'separator', u' ')
            kwargs.setdefault(u'prefix', self.getMsgPrefix())

            trace = kwargs.get(u'trace', None)

            if trace is None:
                self.error(u'Missing argument: trace=')
                Logger.dumpStack()
                return

            foundSelectedTraceFlag = False
            if isinstance(trace, list):
                for flag in trace:
                    if flag in Trace._traceCatagories:
                        foundSelectedTraceFlag = True
                        break
            else:
                if trace in Trace._traceCatagories:
                    foundSelectedTraceFlag = True

            if not foundSelectedTraceFlag:
                return

            self.log(*args, **kwargs)

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            Logger.logException()

    def log(self, *args, **kwargs):
        try:
            kwargs.setdefault(u'log_level', xbmc.LOGDEBUG)
            kwargs.setdefault(u'separator', u' ')
            kwargs.setdefault(u'prefix', self.getMsgPrefix())
            prefix = kwargs[u'prefix']
            log_level = kwargs[u'log_level']
            separator = kwargs[u'separator']
            trace = kwargs.pop(u'trace', None)

            if trace is not None:
                sep = u''
                traceFlags = u''
                if isinstance(trace, list):
                    for flag in trace:
                        if flag in Trace._traceCatagories:
                            traceFlags += sep + flag
                            sep = separator
                else:
                    if trace in Trace._traceCatagories:
                        traceFlags = trace

                prefix += separator + traceFlags

            log_line = u''
            for arg in args:
                log_line = log_line + separator + u'%s' % (arg)

            log_line = u'[%s] %s' % (prefix, log_line)

            xbmc.log(log_line.encode(u'utf-8'), log_level)

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            Logger.logException()

    def debug(self, text, *args, **kwargs):
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def info(self, text, *args, **kwargs):
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def notice(self, text, *args, **kwargs):
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def warning(self, text, *args, **kwargs):
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def error(self, text, *args, **kwargs):
        kwargs[u'log_level'] = xbmc.LOGDEBUG
        self.log(text, *args, **kwargs)

    def enter(self, *args, **kwargs):
        self.debug(u'Entering', *args, **kwargs)

    def exit(self, *args, **kwargs):
        self.debug(u'Exiting', *args, **kwargs)

    @staticmethod
    def logException(e=None, msg=None):

        try:
            exec_type, exec_value, exec_traceback = sys.exc_info()
            stringBuffer =\
                u'LEAK: TraceBack Traceback traceback stacktrace Stacktrace StackTrace:\n'

            lines = []
            if msg is not None:
                lines.append(msg)

            lines.extend(traceback.format_exception(
                exec_type, exec_value, exec_traceback))
            if len(lines) == 0:
                xbmc.log(u'No lines in traceback execType: ' +
                         str(exec_type), xbmc.LOGDEBUG)

                Logger.dumpStack()

            else:
                for line in lines:
                    stringBuffer += str(line) + u'\n'

                xbmc.log(stringBuffer.encode(u'utf-8'), xbmc.LOGERROR)
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            msg = u'Logger.logException raised exception during processing'
            xbmc.log(msg.encode(u'utf-8'), xbmc.LOGERROR)

    @staticmethod
    def dumpStack(msg=u''):
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
    TRACE_MONITOR = u'TRACE_MONITOR'
    TRACE_JSON = u'TRACE_JSON'
    TRACE_SCREENSAVER = u'TRACE_SCREENSAVER'
    TRACE_UI_CONTROLLER = u'TRACE_UI_CONTROLLER'

    _traceAll = [TRACE, STATS, TRACE_UI, STATS_UI, TRACE_DISCOVERY,
                 STATS_DISCOVERY, TRACE_MONITOR, TRACE_JSON, TRACE_SCREENSAVER,
                 TRACE_UI_CONTROLLER]

    _traceCatagories = set()
    _traceGroups = {}
    _logger = None

    def __init__(self, groupName=u'default', trace=[], traceDefault=[]):
        if Trace._logger is None:
            Trace._logger = Logger(self.__class__.__name__)
        localLogger = Trace._logger.getMethodLogger(u'__init__')

        self._traceCategories = set()
        self._defaultTraceCategories = set()

        self._traceCategories.update(trace)
        self._defaultTraceCategories.update(traceDefault)
        if groupName in Trace._traceGroups:
            localLogger.error(u'Trace group:', groupName,
                              u'already exists, will not persist this instance')
        else:
            Trace._traceGroups[groupName] = self

    @staticmethod
    def getDefaultInstance(trace=u'TRACE', traceDefault=[]):
        if Trace._logger is None:
            Trace._logger = Trace(groupName=u'default',
                                  trace=trace, traceDefault=traceDefault)
        return Trace._logger

    @staticmethod
    def log(*args, **kwargs):  # log_level=xbmc.LOGDEBUG, trace=[]):
        try:
            if Trace._logger is None:
                Trace._logger = Logger()

            prefix = u''
            separator = u''

            trace = kwargs.pop(u'trace', None)
            if trace is None:
                Trace._logger.error(u'Missing argument: trace=')
                Logger.dumpStack()
                return

            if isinstance(trace, list):
                for flag in trace:
                    if flag in Trace._traceCatagories:
                        prefix += separator + flag
                        separator = u' '
            else:
                if trace in Trace._traceCatagories:
                    prefix = trace

            if prefix == u'':
                return

            msg = u''
            separator = u''
            for text in args:
                msg = msg + separator + u'%s' % (text)
                separator = u' '

            log_line = u'[%s] %s' % (prefix, msg)
            log_level = kwargs.pop(u'log_level', xbmc.LOGDEBUG)

            xbmc.log(log_line.encode(u'utf-8'), log_level)

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception:
            Logger.logException()

    @staticmethod
    def logError(msg, *flags):
        Trace.log(msg, *flags)
        Trace._logger.log(msg, prefix=u'', log_level=xbmc.LOGERROR)

    @staticmethod
    def setDefaultTraceCategories(*flags):
        for flag in flags:
            Trace._defaultTraceCategories.add(flag)

    @staticmethod
    def clearDefaultTraceCategories():
        Trace._defaultTraceCategories.clear()

    @staticmethod
    def enable(*flags):
        for flag in flags:
            Trace._traceCatagories.add(flag)

    @staticmethod
    def enableAll():
        for flag in Trace._traceAll:
            Trace.enable(flag)

    @staticmethod
    def disable(*flags):
        for flag in flags:
            Trace._traceCatagories.remove(flag)
