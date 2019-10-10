# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import datetime
from email.utils import parsedate_tz
import glob
import io
import simplejson as json
import os
import random
import re
import requests
from requests.exceptions import (
    ConnectionError,
    ConnectTimeout, ReadTimeout
)

import locale
import threading
import calendar
import six

from kodi_six import xbmc, utils

from common.constants import Constants, Movie
from common.logger import (Logger, LazyLogger, Trace)
from common.exceptions import AbortException, ShutdownException, TrailerIdException
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from backend import backend_constants
from common.disk_utils import DiskUtils, UsageData, FileData
from common.watchdog import WatchDog

RATIO_DECIMAL_DIGITS_TO_PRINT = '{:.4f}'

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'cache.cache_manager')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class CacheData(object):
    """
        Provides generic access to cache-specific (trailer, json)
        data (Settings, stats).
    """

    def __init__(self,
                 trailer_cache  # type: bool
                 ):
        # type: (...) -> None
        """
            Populates this instance with relevant settings. Allows for uniform
            access to those settings.

        :param trailer_cache:
        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._usage_data = None
        self._messages = Messages.get_instance()
        self._is_trailer_cache = trailer_cache
        if trailer_cache:
            self._is_limit_number_of_cached_files = \
                Settings.is_limit_number_of_cached_trailers()
            if self._is_limit_number_of_cached_files:
                self._max_number_of_files = Settings.get_max_number_of_cached_trailers()

            self._is_limit_size_of_cache = Settings.is_limit_size_of_cached_trailers()
            if self._is_limit_size_of_cache:
                self._max_cache_size_mb = Settings.get_max_size_of_cached_trailers_mb()

            self._is_limit_percent_of_cache_disk = \
                Settings.is_limit_percent_of_cached_trailers()
            if self._is_limit_percent_of_cache_disk:
                self._max_percent_of_cache_disk = \
                    Settings.get_max_percent_of_cached_trailers()
                # TODO: Delete me
                # self._max_percent_of_cache_disk = 0.83

        else:
            self._is_limit_number_of_cached_files = \
                Settings.is_limit_number_of_cached_json()
            if self._is_limit_number_of_cached_files:
                self._max_number_of_files = Settings.get_max_number_of_cached_json()

            self._is_limit_size_of_cache = Settings.is_limit_size_of_cached_json()
            if self._is_limit_size_of_cache:
                self._max_cache_size_mb = Settings.get_max_size_of_cached_json_mb()

            self._is_limit_percent_of_cache_disk = \
                Settings.is_limit_percent_of_cached_json()
            if self._is_limit_percent_of_cache_disk:
                self._max_percent_of_cache_disk = \
                    Settings.get_max_percent_of_cached_json()
                # TODO_ delete me
                # self._max_percent_of_cache_disk = 0.0058

        if self._is_limit_number_of_cached_files:
            self._max_number_of_files_str = locale.format("%d",
                                                          self._max_number_of_files,
                                                          grouping=True)
        else:
            self._max_number_of_files = 0
            self._max_number_of_files_str = self._messages.get_msg(
                Messages.UNLIMITED)
        if self._is_limit_size_of_cache:
            self._max_cache_size_mb_str = DiskUtils.sizeof_fmt(
                self._max_cache_size_mb * 1024 * 1024)
        else:
            self._max_cache_size_mb = 0
            self._max_cache_size_mb_str = self._messages.get_msg(
                Messages.UNLIMITED)

        if self._is_limit_percent_of_cache_disk:
            self._max_percent_of_cache_disk_str = RATIO_DECIMAL_DIGITS_TO_PRINT.format(
                self._max_percent_of_cache_disk) + '%'
        else:
            self._max_percent_of_cache_disk = 100.0
            self._max_percent_of_cache_disk_str = self._messages.get_msg(
                Messages.UNLIMITED)

        self._remaining_allowed_files = None
        self._used_space_in_cache_fs = None
        self._free_disk_in_cache_fs = None
        self._total_size_of_cache_fs = None
        self._disk_used_by_cache = None
        self._actual_cache_percent = None

    def add_usage_data(self,
                       usage_data  # type: CacheData
                       ):
        # type: (...) -> None
        """
            Adds Cache UsageData to this instance.

        :param usage_data:
        :return:
        """
        self._usage_data = usage_data

    def report_status(self):
        # type: () -> None
        """
            Produces a simple report about the cache using the Settings
            and UsageData.

        :return:
        """

        try:
            if self._is_trailer_cache:
                msg_max_trailers = 'max allowed trailers:'
                msg_disk_usage = 'max_trailer_cache_disk_usage:'
                msg_cache_percent = 'max percent of trailer cache disk usage:'
                msg_files_in_cache = 'trailers_in_cache:'
                msg_remaining_allowed_files = 'remaining_allowed_trailers:'
                msg_total_size_of_cache_fs = 'Size of trailer cache fs:'
                msg_used_space_in_cache_fs = 'Used space in trailer cache fs:'
                msg_free_space_in_cache_fs = 'free space in trailer cache fs:'
                msg_actual_fs_cache_percent = 'Actual percent of disk used by trailer ' \
                                              'cache:'
                msg_disk_used_by_cache = 'Actual disk used by trailer cache:'

            else:
                msg_max_trailers = 'max number of json files:'
                msg_disk_usage = 'max_json_cache_disk_usage:'
                msg_cache_percent = 'max_percent of json cache disk usage:'
                msg_files_in_cache = 'json_files_in_cache'
                msg_remaining_allowed_files = 'remaining_allowed_json_files'
                msg_total_size_of_cache_fs = 'Size of json cache fs:'
                msg_used_space_in_cache_fs = 'Used space in json cache fs:'
                msg_free_space_in_cache_fs = 'free space in json cache fs:'
                msg_actual_fs_cache_percent = 'Actual percent of disk used by json ' \
                                              'cache:'
                msg_disk_used_by_cache = 'Actual disk used by json cache:'

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(
                    msg_max_trailers, self._max_number_of_files_str)
                self._logger.debug(msg_disk_usage, self._max_cache_size_mb_str)
                self._logger.debug(msg_cache_percent,
                                   self._max_percent_of_cache_disk_str)

            files_in_cache = self._usage_data.get_number_of_files()
            if self._is_limit_number_of_cached_files:
                self._remaining_allowed_files = (self._max_number_of_files -
                                                 files_in_cache)
                remaining_allowed_files_str = locale.format("%d",
                                                            self._remaining_allowed_files,
                                                            grouping=True)
            else:
                self._remaining_allowed_files = None
                remaining_allowed_files_str = self._messages.get_msg(
                    Messages.UNLIMITED)

            self._used_space_in_cache_fs = self._usage_data.get_used_space()
            self._free_disk_in_cache_fs = self._usage_data.get_free_size()
            self._total_size_of_cache_fs = self._usage_data.get_total_size()
            self._disk_used_by_cache = self._usage_data.get_disk_used_by_cache()
            self._actual_cache_percent = (self._disk_used_by_cache /
                                          self._total_size_of_cache_fs) * 100.0

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(msg_total_size_of_cache_fs,
                                   DiskUtils.sizeof_fmt(self._total_size_of_cache_fs))
                self._logger.debug(msg_used_space_in_cache_fs,
                                   DiskUtils.sizeof_fmt(self._used_space_in_cache_fs))
                self._logger.debug(msg_free_space_in_cache_fs,
                                   DiskUtils.sizeof_fmt(self._free_disk_in_cache_fs))

                self._logger.debug(msg_files_in_cache,
                                   locale.format("%d", files_in_cache, grouping=True))
                self._logger.debug(msg_remaining_allowed_files,
                                   remaining_allowed_files_str)

                self._logger.debug(msg_actual_fs_cache_percent,
                                   RATIO_DECIMAL_DIGITS_TO_PRINT.format(
                                       self._actual_cache_percent) + '%')

                self._logger.debug(msg_disk_used_by_cache,
                                   DiskUtils.sizeof_fmt(self._disk_used_by_cache))
        except (Exception) as e:
            self._logger.exception('')

    def collect_garbage(self):
        # type: () -> None
        """
        Runs garbage collection on all of the caches according to the
        settings.

        This is a time-consuming process. It is normally kicked-off by
        drive_garbage_collection

        :return:
        """
        try:
            if self._logger.isEnabledFor(Logger.DEBUG):
                if self._is_trailer_cache:
                    self._logger.debug('TRAILER CACHE')
                else:
                    self._logger.debug('JSON CACHE')

            if self._is_limit_number_of_cached_files:
                #
                # Delete enough of the oldest files to keep the number
                # within limit

                number_of_cache_files_to_delete = - self._remaining_allowed_files
                if number_of_cache_files_to_delete > 0:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'limit_number_of_cached_files. number_of_files_to_delete:',
                            locale.format("%d", number_of_cache_files_to_delete,
                                          grouping=True))
                    # Order json files by age

                    for cache_file in self._usage_data.get_file_data_by_creation_date():
                        self._usage_data.remove_file(cache_file)
                        number_of_cache_files_to_delete -= 1
                        if number_of_cache_files_to_delete <= 0:
                            break
                else:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug(
                            'limit_number_of_cached_files. Additional allowed files:',
                            locale.format("%d", number_of_cache_files_to_delete,
                                          grouping=True))

            if self._is_limit_size_of_cache:
                #
                # Delete enough of the oldest files to keep the number
                # within limit

                max_bytes_in_cache = (self._max_cache_size_mb * 1024 * 1024)
                bytes_of_files_to_delete = (self._usage_data.get_disk_used_by_cache()
                                            - max_bytes_in_cache)
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('limit_size_of_cache. max allowed size:',
                                       DiskUtils.sizeof_fmt(max_bytes_in_cache))
                    self._logger.debug('actual disk used in cache:',
                                       DiskUtils.sizeof_fmt(
                                           self._usage_data.get_disk_used_by_cache()))
                    self._logger.debug('Amount to delete:',
                                       DiskUtils.sizeof_fmt(bytes_of_files_to_delete))
                if bytes_of_files_to_delete > 0:
                    # Order json files by age

                    for cache_file in self._usage_data.get_file_data_by_creation_date():
                        self._usage_data.remove_file(cache_file)
                        bytes_of_files_to_delete = (
                            self._usage_data.get_disk_used_by_cache()
                            - max_bytes_in_cache)
                        if bytes_of_files_to_delete <= 0:
                            break

            if self._is_limit_percent_of_cache_disk:
                #
                # Delete enough of the oldest files to keep the number
                # within limit

                max_bytes_in_cache = (self._total_size_of_cache_fs *
                                      self._max_percent_of_cache_disk / 100.00)
                bytes_of_files_to_delete = (self._usage_data.get_disk_used_by_cache() -
                                            max_bytes_in_cache)

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('limit_percent of cached files. Calculated max size:',
                                       DiskUtils.sizeof_fmt(max_bytes_in_cache))
                    self._logger.debug('size to delete:',
                                       DiskUtils.sizeof_fmt(bytes_of_files_to_delete))
                if bytes_of_files_to_delete > 0:
                    # Order json files by age

                    for cache_file in self._usage_data.get_file_data_by_creation_date():
                        self._usage_data.remove_file(cache_file)
                        bytes_of_files_to_delete = (
                            self._usage_data.get_disk_used_by_cache()
                            - max_bytes_in_cache)
                        if bytes_of_files_to_delete <= 0:
                            break

        except (Exception) as e:
            self._logger.exception('')


class CacheManager(object):
    """
        Provides Management access to the cache, primarily garbage collection.
    """

    _instance = None

    def __init__(self):
        # type: () -> None
        """
        :return: None
        """
        self._logger = module_logger.getChild(self.__class__.__name__)

        self._initial_run = True
        self._cache_monitor_thread = None

    @staticmethod
    def get_instance():
        # type: () -> CacheManager
        """

        :return:
        """
        if CacheManager._instance is None:
            CacheManager._instance = CacheManager()
        return CacheManager._instance

    def get_stats_for_caches(self):
        # type: () -> Dict[TextType, UsageData]
        """
            Get disk usage information for the caches.
            Returns a map of UsageData for each cache. Primarily used
            by garbage collection and reporting.

        :return: # type:Dict[TextType, UsageData]
        """
        self._logger.enter()
        if (Settings.get_downloaded_trailer_cache_path() ==
                Settings.get_remote_db_cache_path()):
            usage_data_map = DiskUtils.get_stats_for_path(
                Settings.get_downloaded_trailer_cache_path(),
                {'trailer': '-trailer.',
                 'json': '.json'})
        else:
            usage_data_map = DiskUtils.get_stats_for_path(
                Settings.get_downloaded_trailer_cache_path(),
                {'trailer': '-trailer.'})
            json_usage_data = DiskUtils.get_stats_for_path(
                Settings.get_remote_db_cache_path(),
                {'json': '.json'})
            usage_data_map['json'] = json_usage_data['json']

        self._logger.exit()
        return usage_data_map

    def start_cache_garbage_collection_thread(self):
        # type () -> None
        """
            Start thread to periodically purge off files when cache space
            limits are exceeded.

        :return: # type: None
        """
        self._initial_run = True
        if self._cache_monitor_thread is None:
            # noinspection PyTypeChecker
            self._cache_monitor_thread = threading.Thread(
                target=self.drive_garbage_collection_wrapper, name='cacheMonitor')
            self._cache_monitor_thread.start()

    def drive_garbage_collection_wrapper(self):
        # type: () -> None
        """
            This method focuses on deleting files when disk space limits
            are exceeded.

        :return:
        """

        try:
            self.drive_garbage_collection()

        except (ShutdownException, AbortException) as e:
            pass
        except (Exception) as e:
            self._logger.exception('')

    def drive_garbage_collection(self):
        # type: () -> None
        """
                This method focuses on deleting files when disk space limits
                are exceeded.

            :return:
        """
        self._logger.enter()

        # Purge off any stray undeleted temp files
        folder = xbmc.translatePath('special://temp').encode("utf-8")
        to_delete = os.path.join(folder, '_rt_*')
        to_delete = glob.glob(to_delete)
        for a_file in to_delete:
            os.remove(a_file)

        del folder
        del to_delete

        start_seconds_from_now = Constants.InitialGarbageCollectionTime

        finished = False
        usage_data_map = None
        try:
            while not finished:
                Monitor.get_instance().throw_exception_if_shutdown_requested(
                    delay=float(start_seconds_from_now))
                usage_data_map = self.get_stats_for_caches()

                # Sizes in MB

                trailer_cache_settings = CacheData(trailer_cache=True)
                json_cache_settings = CacheData(trailer_cache=False)

                trailer_usage_data = usage_data_map['trailer']
                trailer_cache_settings.add_usage_data(trailer_usage_data)
                trailer_cache_settings.report_status()

                json_usage_data = usage_data_map['json']
                json_cache_settings.add_usage_data(json_usage_data)
                json_cache_settings.report_status()

                trailer_cache_settings.collect_garbage()
                del trailer_cache_settings
                json_cache_settings.collect_garbage()
                del json_cache_settings

                # Run subsequently on a daily basis (middle of night)

                start_time = datetime.datetime.combine(datetime.datetime.now(),
                                                       Constants.DailyGarbageCollectionTime)
                start_time_delta = start_time - datetime.datetime.now()
                start_seconds_from_now = start_time_delta.total_seconds()

                if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
                    self._logger.debug_extra_verbose('Daily Schedule',
                                                     'start_time:',
                                                     start_time.strftime(
                                                         "%d/%m/%d %H:%M"),
                                                     'delay:',
                                                     start_seconds_from_now)

                # If start time is less than 5 hours into future, then add a
                # day

                if start_seconds_from_now < 5 * 60 * 60:
                    start_seconds_from_now = start_seconds_from_now + \
                        (24 * 60 * 60)
                    if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
                        self._logger.debug_extra_verbose('New delay:',
                                                         start_seconds_from_now)

        except (ShutdownException, AbortException) as e:
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')
        finally:
            del usage_data_map
