# -*- coding: utf-8 -*-
"""
Created on 4/4/21

@author: Frank Feuerbacher
"""

import sys

import xbmc

from backend.network_stats import NetworkStats
from common.imports import *
from common.exceptions import AbortException
from common.monitor import Monitor
from common.settings import Settings
from backend.api import DiscoveryManager
from common.logger import *
from cache.cache_manager import CacheManager
from __init__ import *

module_logger = BasicLogger.get_module_logger(module_path=__file__)


def startup_non_main_thread() -> None:
    """

    :return:
    """
    post_install()

    Trace.enable_all()
    try:
        pass
        #  Trace.enable(Trace.TRACE_NETWORK)
        Trace.enable(Trace.TRACE_PLAY_STATS)
    except Exception as e:
        module_logger.exception(e)

    Settings.save_settings()
    Monitor.register_settings_changed_listener(
        Settings.on_settings_changed, 'Settings.on_settings_changed')
    Monitor.register_settings_changed_listener(
        BasicLogger.on_settings_changed, 'BasicLogger.on_settings_changed')
    try:
        Settings.get_locale()
    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        module_logger.exception(e)
    DiscoveryManager.load_trailers()

    # Start the periodic garbage collector

    CacheManager.get_instance().start_cache_garbage_collection_thread()
    NetworkStats.auto_report(frequency_minutes=30)


def post_install() -> None:
    #
    # Ensure execute permission
    pass