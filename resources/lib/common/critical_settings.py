# -*- coding: utf-8 -*-
"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import xbmc
from kodi65.kodiaddon import Addon
from common.imports import *


class CriticalSettings:
    """
        A subset of settings that are used by modules which can not have a
        dependency on Settings.

    """

    DEBUG_INCLUDE_THREAD_INFO: Final[str] = 'debug_include_thread_info'
    addon = None
    _plugin_name: str = ""
    try:
        addon = Addon('script.video.randomtrailers')
    except Exception:
        xbmc.log('script.video.randomtrailers was not found.',
                 level=xbmc.LOGERROR)

    @staticmethod
    def is_debug_enabled() -> bool:
        """

        :return:
        """
        if CriticalSettings.addon is None:
            return False

        is_debug_enabled = CriticalSettings.addon.setting('do_debug')
        return bool(is_debug_enabled)

    @staticmethod
    def is_debug_include_thread_info() -> bool:
        """

        :return:
        """
        if CriticalSettings.addon is None:
            return False

        is_debug_include_thread_info = CriticalSettings.addon.setting(
                                            CriticalSettings.DEBUG_INCLUDE_THREAD_INFO)
        return (bool(is_debug_include_thread_info)
                and CriticalSettings.get_logging_level() >= 10)

    @staticmethod
    def get_logging_level() -> int:
        """

        :return:
        """
        log_level = 30
        # xbmc.log('get_logging_level', level=xbmc.LOGDEBUG)
        translated_value = None

        try:

            # log_level is a 0-based enumeration in increasing verbosity
            # Convert to values utilized by our Python logging library
            # based config_logger:
            #  FATAL = logging.CRITICAL # 50
            #  ERROR = logging.ERROR       # 40
            #  WARNING = logging.WARNING   # 30
            #  INFO = logging.INFO         # 20
            #  DEBUG_EXTRA_VERBOSE = 15
            #  DEBUG_VERBOSE = 12
            #  DEBUG = logging.DEBUG       # 10
            #  NOTSET = logging.NOTSET     # 0

            # WARNING|NOTICE|INFO|DEBUG|VERBOSE DEBUG|EXTRA VERBOSE DEBUG"

            translated_value = 3
            try:
                CriticalSettings.addon
            except NameError:
                CriticalSettings.addon = None
                xbmc.log('addon was not defined.', level=xbmc.LOGDEBUG)

            if CriticalSettings.addon is None:
                xbmc.log('Can not access script.video.randomtrailers',
                         level=xbmc.LOGERROR)
                translated_value = 3
            else:
                log_level = CriticalSettings.addon.setting('log_level')
                msg = 'got log_level from settings: {!s}'.format(log_level)
                # xbmc.log(msg, level=xbmc.LOGDEBUG)
                log_level = int(log_level)
                translated_value = 50
                if log_level <= 0:  # Warning
                    translated_value = 30
                elif log_level == 1:  # Info
                    translated_value = 20
                elif CriticalSettings.is_debug_enabled():
                    translated_value = 0  # Not Set
                    if log_level == 2:  # Debug
                        translated_value = 10
                    elif log_level == 3:  # Verbose Debug
                        translated_value = 8
                    elif log_level >= 4:  # Extra Verbose Debug
                        translated_value = 6

                # prefix = '[Thread {!s} {!s}.{!s}:{!s}]'.format(
                # record.threadName, record.name, record.funcName,
                # record.lineno)
                msg = 'get_logging_level got log_level: {!s}'.format(
                    translated_value)
                # xbmc.log(msg, level=xbmc.LOGDEBUG)
        except Exception:
            xbmc.log('Exception occurred in get_logging_level',
                     level=xbmc.LOGERROR)

        return translated_value

    @classmethod
    def set_plugin_name(cls, plugin_name: str):
        cls._plugin_name = plugin_name

    @classmethod
    def get_plugin_name(cls) -> str:
        return cls._plugin_name
