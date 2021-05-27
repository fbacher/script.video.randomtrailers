# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import sys
import datetime
import glob
import os
import locale
import threading

import xbmcvfs

from common.constants import Constants
from common.imports import *
from common.logger import LazyLogger, Trace
from common.exceptions import AbortException
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from common.disk_utils import DiskUtils, UsageData

RATIO_DECIMAL_DIGITS_TO_PRINT = '{:.4f}'

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class CacheData:
    """
        Provides generic access to cache-specific (trailer, json)
        data (Settings, stats).
    """

    _logger = None

    def __init__(self, trailer_cache: bool) -> None:
        """
            Populates this instance with relevant settings. Allows for uniform
            access to those settings.

        :param trailer_cache:
        """
        local_class = CacheData
        if local_class._logger is None:
            local_class._logger = module_logger.getChild(local_class.__name__)

        self._usage_data: UsageData = None
        self._remaining_allowed_files: int = None
        self._used_space_in_cache_fs: int = None
        self._free_disk_in_cache_fs: int = None
        self._total_size_of_cache_fs: int = None
        self._disk_used_by_cache: int = None
        self._actual_cache_percent: int = None
        self._is_trailer_cache: bool = trailer_cache
        self._is_limit_number_of_cached_files: bool
        self._max_number_of_files: bool
        self._is_limit_size_of_cache: bool
        self._max_cache_size_mb: bool
        self._is_limit_percent_of_cache_disk: bool
        self._max_percent_of_cache_disk: bool

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
            self._max_number_of_files_str = Messages.get_msg(
                Messages.UNLIMITED)
        if self._is_limit_size_of_cache:
            self._max_cache_size_mb_str = DiskUtils.sizeof_fmt(
                self._max_cache_size_mb * 1024 * 1024)
        else:
            self._max_cache_size_mb = 0
            self._max_cache_size_mb_str = Messages.get_msg(
                Messages.UNLIMITED)

        if self._is_limit_percent_of_cache_disk:
            self._max_percent_of_cache_disk_str = RATIO_DECIMAL_DIGITS_TO_PRINT.format(
                self._max_percent_of_cache_disk) + '%'
        else:
            self._max_percent_of_cache_disk = 100.0
            self._max_percent_of_cache_disk_str = Messages.get_msg(
                Messages.UNLIMITED)

    def add_usage_data(self, usage_data: UsageData) -> None:
        """
            Adds Cache UsageData to this instance.

        :param usage_data:
        :return:
        """
        self._usage_data = usage_data

    def report_status(self) -> None:
        """
            Produces a simple report about the cache using the Settings
            and UsageData.

        :return:
        """
        local_class = CacheData

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

            if local_class._logger.isEnabledFor(LazyLogger.INFO):
                local_class._logger.info(msg_max_trailers,
                                                self._max_number_of_files_str,
                                                trace=Trace.STATS_CACHE)
                local_class._logger.info(msg_disk_usage,
                                                self._max_cache_size_mb_str,
                                                trace=Trace.STATS_CACHE)
                local_class._logger.info(msg_cache_percent,
                                                self._max_percent_of_cache_disk_str,
                                                trace=Trace.STATS_CACHE)

            files_in_cache = self._usage_data.get_number_of_files()
            if self._is_limit_number_of_cached_files:
                self._remaining_allowed_files = (self._max_number_of_files -
                                                 files_in_cache)
                remaining_allowed_files_str = locale.format("%d",
                                                            self._remaining_allowed_files,
                                                            grouping=True)
            else:
                self._remaining_allowed_files = None
                remaining_allowed_files_str = Messages.get_msg(
                    Messages.UNLIMITED)

            self._used_space_in_cache_fs = self._usage_data.get_used_space()
            self._free_disk_in_cache_fs = self._usage_data.get_free_size()
            self._total_size_of_cache_fs = self._usage_data.get_total_size()
            self._disk_used_by_cache = self._usage_data.get_disk_used_by_cache()
            self._actual_cache_percent = (self._disk_used_by_cache /
                                          self._total_size_of_cache_fs) * 100.0

            if local_class._logger.isEnabledFor(LazyLogger.INFO):
                local_class._logger.info(msg_total_size_of_cache_fs,
                                   DiskUtils.sizeof_fmt(self._total_size_of_cache_fs))
                local_class._logger.info(msg_used_space_in_cache_fs,
                                   DiskUtils.sizeof_fmt(self._used_space_in_cache_fs))
                local_class._logger.info(msg_free_space_in_cache_fs,
                                   DiskUtils.sizeof_fmt(self._free_disk_in_cache_fs))

                local_class._logger.info(msg_files_in_cache,
                                   locale.format_string("%d", files_in_cache,
                                                        grouping=True))
                local_class._logger.info(msg_remaining_allowed_files,
                                   remaining_allowed_files_str)

                local_class._logger.info(msg_actual_fs_cache_percent,
                                   RATIO_DECIMAL_DIGITS_TO_PRINT.format(
                                       self._actual_cache_percent) + '%')

                local_class._logger.info(msg_disk_used_by_cache,
                                   DiskUtils.sizeof_fmt(self._disk_used_by_cache))
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            local_class._logger.exception('')

    def collect_garbage(self) -> None:
        """
        Runs garbage collection on all of the caches according to the
        settings.

        This is a time-consuming process. It is normally kicked-off by
        drive_garbage_collection

        :return:
        """
        local_class = CacheData
        try:
            if local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                if self._is_trailer_cache:
                    local_class._logger.debug_extra_verbose('TRAILER CACHE')
                else:
                    local_class._logger.debug_extra_verbose('JSON CACHE')

            if self._is_limit_number_of_cached_files:
                #
                # Delete enough of the oldest files to keep the number
                # within limit

                number_of_cache_files_to_delete = - self._remaining_allowed_files
                if number_of_cache_files_to_delete > 0:
                    if local_class._logger.isEnabledFor(LazyLogger.INFO):
                        local_class._logger.info(
                            'limit_number_of_cached_files. number_of_files_to_delete:',
                            locale.format("%d", number_of_cache_files_to_delete,
                                          grouping=True))
                    # Order json files by age

                    for cache_file in self._usage_data.get_file_data_by_creation_date():
                        Monitor.throw_exception_if_abort_requested()
                        self._usage_data.remove_file(cache_file)
                        number_of_cache_files_to_delete -= 1
                        if number_of_cache_files_to_delete <= 0:
                            break
                else:
                    if local_class._logger.isEnabledFor(LazyLogger.INFO):
                        local_class._logger.info(
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
                if local_class._logger.isEnabledFor(LazyLogger.INFO):
                    local_class._logger.info('limit_size_of_cache. max allowed size:',
                                       DiskUtils.sizeof_fmt(max_bytes_in_cache))
                    local_class._logger.debug('actual disk used in cache:',
                                       DiskUtils.sizeof_fmt(
                                           self._usage_data.get_disk_used_by_cache()))
                    local_class._logger.debug('Amount to delete:',
                                       DiskUtils.sizeof_fmt(bytes_of_files_to_delete))
                if bytes_of_files_to_delete > 0:
                    # Order json files by age

                    for cache_file in self._usage_data.get_file_data_by_creation_date():
                        Monitor.throw_exception_if_abort_requested()
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

                if local_class._logger.isEnabledFor(LazyLogger.INFO):
                    local_class._logger.info(
                        'limit_percent of cached files. Calculated max size:',
                        DiskUtils.sizeof_fmt(max_bytes_in_cache))
                    local_class._logger.info('size to delete:',
                                             DiskUtils.sizeof_fmt(
                                                 bytes_of_files_to_delete))
                if bytes_of_files_to_delete > 0:
                    # Order json files by age

                    for cache_file in self._usage_data.get_file_data_by_creation_date():
                        Monitor.throw_exception_if_abort_requested()
                        self._usage_data.remove_file(cache_file)
                        bytes_of_files_to_delete = (
                            self._usage_data.get_disk_used_by_cache()
                            - max_bytes_in_cache)
                        if bytes_of_files_to_delete <= 0:
                            break

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            local_class._logger.exception('')


class CacheManager:
    """
        Provides Management access to the cache, primarily garbage collection.
    """

    _instance = None
    _logger = None

    def __init__(self) -> None:
        """
        :return: None
        """
        local_class = CacheManager
        if local_class._logger is None:
            local_class._logger = module_logger.getChild(local_class.__name__)

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

    def get_stats_for_caches(self) -> Dict[str, UsageData]:
        """
            Get disk usage information for the caches.
            Returns a map of UsageData for each cache. Primarily used
            by garbage collection and reporting.

        :return:
        """
        local_class = CacheManager


        TRAILER_TYPE = 'trailer'
        JSON_TYPE = 'json'

        # When the Trailer Cache and Data Cache (.json) are the same

        if (Settings.get_downloaded_trailer_cache_path() ==
                Settings.get_remote_db_cache_path()):
            usage_data_map = DiskUtils.get_stats_for_path(
                Settings.get_downloaded_trailer_cache_path(),
                {'trailer': (Constants.TRAILER_GLOB_PATTERN, TRAILER_TYPE),
                 'json': (Constants.JSON_GLOB_PATTERN, JSON_TYPE),
                 'tfh': (Constants.TFH_GLOB_PATTERN, TRAILER_TYPE)})
        else:
            # When Trailer Cache and Data Cache are different directories.

            usage_data_map = DiskUtils.get_stats_for_path(
                Settings.get_downloaded_trailer_cache_path(),
                {'trailer': (Constants.TRAILER_GLOB_PATTERN, TRAILER_TYPE),
                 'tfh': (Constants.TFH_GLOB_PATTERN, TRAILER_TYPE)})
            json_usage_data = DiskUtils.get_stats_for_path(
                Settings.get_remote_db_cache_path(),
                {'json': (Constants.JSON_GLOB_PATTERN, JSON_TYPE)})
            usage_data_map['json'] = json_usage_data['json']

        return usage_data_map

    def start_cache_garbage_collection_thread(self) -> None:
        """
            Start thread to periodically purge off files when cache space
            limits are exceeded.

        :return: # type: None
        """
        self._initial_run = True
        if self._cache_monitor_thread is None:
            self._cache_monitor_thread = threading.Thread(
                target=self.drive_garbage_collection_wrapper, name='cacheMonitor')
            self._cache_monitor_thread.start()
            # For some reason did not see thread name while using debugger
            self._cache_monitor_thread.setName('cacheMonitor')

    def drive_garbage_collection_wrapper(self) -> None:
        """
            This method focuses on deleting files when disk space limits
            are exceeded.

        :return:
        """
        local_class = CacheManager
        try:
            self.drive_garbage_collection()

        except AbortException as e:
            pass  # Thread dies
        except Exception as e:
            local_class._logger.exception('')

    def drive_garbage_collection(self) -> None:
        """
                This method focuses on deleting files when disk space limits
                are exceeded.

            :return:
        """
        local_class = CacheManager

        # Purge off any stray undeleted temp files
        folder = xbmcvfs.translatePath('special://temp')
        to_delete = os.path.join(folder, '_rt_*')
        to_delete = glob.glob(to_delete)
        for a_file in to_delete:
            Monitor.throw_exception_if_abort_requested()
            os.remove(a_file)

        del folder
        del to_delete

        start_seconds_from_now = Constants.InitialGarbageCollectionTime

        finished = False
        usage_data_map = None
        try:
            while not finished:
                Monitor.throw_exception_if_abort_requested(
                    timeout=float(start_seconds_from_now))
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
                start_time_delta = datetime.datetime.now() - start_time
                start_seconds_from_now = start_time_delta.total_seconds()

                if local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    local_class._logger.debug_extra_verbose('Daily Schedule',
                                                            'start_time:',
                                                            start_time.strftime(
                                                                "%d/%m/%d %H:%M"),
                                                            'delay:',
                                                            start_seconds_from_now,
                                                            trace=Trace.STATS_CACHE)

                # If start time is less than 5 hours into future, then add a
                # day

                if start_seconds_from_now < 5 * 60 * 60:
                    start_seconds_from_now = start_seconds_from_now + \
                        (24 * 60 * 60)
                    if local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        local_class._logger.debug_extra_verbose('New delay:',
                                                                start_seconds_from_now,
                                                                trace=Trace.STATS_CACHE)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            local_class._logger.exception('')
        finally:
            del usage_data_map


