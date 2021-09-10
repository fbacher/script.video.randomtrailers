# -*- coding: utf-8 -*-
"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import xbmc
from kutils.kodiaddon import Addon
from common.imports import *


class CriticalSettings:
    """
        A subset of settings that are used by modules which can not have a
        dependency on Settings.

    """

    DISABLED = 0
    FATAL = 50  # logging.CRITICAL
    ERROR = 40  # logging.ERROR  # 40
    WARNING = 30  # logging.WARNING  # 30
    INFO = 20  # logging.INFO  # 20
    DEBUG = 10  # logging.DEBUG  # 10
    DEBUG_VERBOSE = 8
    DEBUG_EXTRA_VERBOSE = 6
    NOTSET = 0  # logging.NOTSET  # 0

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

        debug_enabled = CriticalSettings.addon.bool_setting('do_debug')
        return debug_enabled

    @staticmethod
    def is_debug_include_thread_info() -> bool:
        """

        :return:
        """
        if CriticalSettings.addon is None:
            return False

        is_debug_include_thread_info = CriticalSettings.addon.bool_setting(
                                            CriticalSettings.DEBUG_INCLUDE_THREAD_INFO)
        return (bool(is_debug_include_thread_info)
                and CriticalSettings.get_logging_level() <= CriticalSettings.DEBUG)

    @staticmethod
    def get_logging_level() -> int:
        """

        :return:
        """
        # log_level_setting is an enum from settings.xml
        # log_level_setting 0 -> xbmc.LOGWARNING
        # log_level_setting 1 => xbmc.LOGINFO
        # log_level_setting 2 => xbmc.LOGDEBUG
        # log_level_setting 3 => DEBUG_VERBOSE
        # log_level_setting 4 => DEBUG_EXTRA_VERBOSE

        # translated_value is a transformation to values that Logger uses:
        #
        # Critical is most important.
        # DISABLED is least important
        # DEBUG_EXTRA_VERBOSE less important that DEBUG

        log_level_setting: int = 0  # WARNING
        translated_value = None

        try:
            # Kodi log values
            # WARNING|INFO|DEBUG|VERBOSE DEBUG|EXTRA VERBOSE DEBUG"

            translated_value = CriticalSettings.WARNING
            try:
                CriticalSettings.addon
            except NameError:
                CriticalSettings.addon = None
                xbmc.log('addon was not defined.', level=xbmc.LOGDEBUG)

            if CriticalSettings.addon is None:
                xbmc.log('Can not access script.video.randomtrailers',
                         level=xbmc.LOGERROR)
                translated_value = CriticalSettings.WARNING
            elif not CriticalSettings.is_debug_enabled():
                log_level_setting = 0
                translated_value = CriticalSettings.WARNING
            else:   # Debug is enabled in Random Trailers Config Experimental Tab
                log_level_setting = CriticalSettings.addon.setting('log_level')
                # msg = f'got log_level_setting from settings: {log_level_setting}'
                # xbmc.log(msg, level=xbmc.LOGDEBUG)
                log_level_setting = int(log_level_setting)
                if log_level_setting <= 0:  # Warning
                    translated_value = CriticalSettings.WARNING
                elif log_level_setting == 1:  # Info
                    translated_value = CriticalSettings.INFO
                elif log_level_setting == 2:  # Debug
                    translated_value = CriticalSettings.DEBUG
                elif log_level_setting == 3:  # Verbose Debug
                    translated_value = CriticalSettings.DEBUG_VERBOSE
                elif log_level_setting >= 4:  # Extra Verbose Debug
                    translated_value = CriticalSettings.DEBUG_EXTRA_VERBOSE

                # prefix = '[Thread {!s} {!s}.{!s}:{!s}]'.format(
                # record.threadName, record.name, record.funcName,
                # record.lineno)
                # msg = f'get_logging_level got log_level_setting: {translated_value}'
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
