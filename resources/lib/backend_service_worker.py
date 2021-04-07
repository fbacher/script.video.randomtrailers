# -*- coding: utf-8 -*-
"""
Created on 4/4/21

@author: Frank Feuerbacher
"""

import sys

import xbmc

from common.imports import *
from common.exceptions import AbortException
from common.monitor import Monitor
from common.settings import Settings
from backend.api import load_trailers
from common.logger import (LazyLogger)
from cache.cache_manager import CacheManager

xbmc.log('main thread after PythonDebugger.enable 2', xbmc.LOGDEBUG)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)
xbmc.log('main thread after PythonDebugger.enable 3', xbmc.LOGDEBUG)


def startup_non_main_thread() -> None:
    """

    :return:
    """

    post_install()

    if module_logger.isEnabledFor(LazyLogger.DEBUG):
        module_logger.debug('%s', 'Enter', lazy_logger=False)

    Settings.save_settings()
    Monitor.register_settings_changed_listener(
        Settings.on_settings_changed)
    Monitor.register_settings_changed_listener(
        LazyLogger.on_settings_changed)
    try:
        Settings.get_locale()
    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        pass
    load_trailers()

    # Start the periodic garbage collector

    CacheManager.get_instance().start_cache_garbage_collection_thread()
    Monitor.register_settings_changed_listener(load_trailers)


def post_install() -> None:
    #
    # Ensure execute permission
    pass