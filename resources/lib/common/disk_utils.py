# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import datetime
import os
import random
import six
import sys

from .constants import (Constants)
from .exceptions import AbortException, ShutdownException
from .logger import (Logger, LazyLogger, Trace)
from .monitor import Monitor
from .settings import Settings

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.disk_utils')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class UsageData(object):
    """

    """

    def __init__(self, cache_name, pattern):
        # type: (TextType, TextType) -> None
        """

        :param cache_name
        :param pattern
        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._cache_name = cache_name
        self._pattern = pattern
        self._aggregate_cache_file_size = 0
        self._aggregate_deleted_size = 0
        self._deleted_files = 0
        self._total_size = None
        self._free_size = None
        self._used_space = None
        self._block_size = None
        self._file_data = {}

    def set_total_size(self, total_size):
        # type: (int) -> None
        """

        :param total_size:
        :return:
        """
        self._total_size = total_size

    def get_total_size(self):
        # type () -> int
        """
            Gets the total disk space on device
        :return:
        """
        return self._total_size

    def set_free_size(self, free_size):
        # type: (int) -> None
        """

        :param free_size:
        :return:
        """
        self._free_size = free_size

    def get_free_size(self):
        # type () -> int
        """
            Gets the free space on device

        :return:
        """
        return self._free_size

    def set_used_space(self, used_space):
        # type: (int) -> None
        """

        :param used_space:
        :return:
        """
        self._used_space = used_space

    def get_used_space(self):
        # type: () -> int
        """
            Gets the used space on device
        :return:
        """
        return self._used_space

    def set_block_size(self, block_size):
        # type: (int) -> None
        """

        :param block_size:
        :return:
        """
        self._block_size = block_size

    def get_block_size(self):
        # type: () -> int
        """
            Gets the block size of device

        :return:
        """
        return self._block_size

    def get_number_of_files(self):
        # type: () -> int
        """
            Gets the number of Files within the original search path
        :return:
        """
        return int(len(self._file_data))

    def add_to_disk_used_by_cache(self, additional_size):
        # type: (int) -> None
        """

        :param additional_size:
        :return:
        """
        self._aggregate_cache_file_size += additional_size

    def get_disk_used_by_cache(self):
        # type: () -> int
        """

        :return:
        """
        return int(self._aggregate_cache_file_size)

    def add_to_disk_deleted(self, deleted_size):
        # type: (int) -> None
        """

        :param deleted_size:
        :return:
        """
        self._aggregate_deleted_size += deleted_size
        self._deleted_files += 1

    def get_disk_deleted_from_cache(self):
        # type: () -> int
        """

        :return:
        """
        return int(self._aggregate_deleted_size)

    def remove_file(self, file_data):
        # type: (FileData) -> None
        """

        :param file_data:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
            self._logger.debug_extra_verbose('will delete- path:', file_data.get_path(),
                                             'creation:', file_data.get_creation_date())
        os.remove(file_data.get_path())
        self._aggregate_deleted_size += file_data.get_size()
        self._aggregate_cache_file_size -= file_data.get_size()
        self._deleted_files += 1

        del self._file_data[file_data.get_path()]
        del file_data

    def get_number_of_deleted_files(self):
        # type () -> int
        """

        :return:
        """
        return self._deleted_files

    def add_file_data(self, file_data):
        # type: (FileData) -> None
        """

        :param file_data:
        :return:
        """
        self._file_data[file_data.get_path()] = file_data

    def get_file_data(self):
        # type: () -> Dict[TextType, FileData]
        """

        :return: Dict of file data indexed by file path
        """
        return self._file_data

    def get_file_data_by_file_size(self):
        # type: () -> List[FileData]
        """

        Gets List of cache file in decreasing order of file size.
        The file path serves as a key to the dict returned by get_file_data

        :return:
        """
        # def sorted(iterable, cmp=None, key=None, reverse=False): # real
        # signature unknown; restored from __doc__

        file_data_list = sorted(self._file_data.values(),
                                key=lambda file_data_element: file_data_element.get_size(),
                                reverse=False)
        return file_data_list

    def get_file_data_by_creation_date(self):
        # type: () -> List[FileData]
        """

        Gets List of cache files in decreasing order of creation data

        :return:
        """
        # type: (str) -> None
        # First sort by number of movies that each genre is
        # in

        file_data_list = (sorted(self._file_data.values(),
                                 key=lambda file_data_element:
                                 file_data_element.get_creation_date(),
                                 reverse=False))
        return file_data_list


class FileData(object):
    """

    """

    def __init__(self, path, creation_date, size):
        # type: (TextType, datetime.datetime, int) -> None
        """

        :param path:
        :param creation_date:
        :param size:
        """
        self._path = path
        self._creation_date = creation_date
        self._size = size

    def get_path(self):
        # type: () -> TextType
        """

        :return:
        """
        return self._path

    def get_creation_date(self):
        # type: () -> datetime.datetime
        """

        :return:
        """
        return self._creation_date

    def get_size(self):
        # type: () -> int
        """

        :return:
        """
        return self._size


# noinspection PyClassHasNoInit


class DiskUtils(object):
    """
            Provides disk utilities
    """
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exit_requested = False
    _logger = module_logger.getChild('DiskUtils')

    @classmethod
    def class_init(cls):
        # type: () -> None
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)

    @classmethod
    def create_path_if_needed(cls, path):
        # type: (TextType) -> None
        """
            Creates as many directories as necessary to make path a valid path

        :param path:
        :return:
        """
        try:
            if not os.path.exists(path):
                os.makedirs(path)
        except (Exception) as e:
            cls._logger.exception('')

    @staticmethod
    def is_url(path):
        # type: (TextType) -> bool
        """
            Determines whether the path is a URL. Currently a simple test.

        :param path:
        :return: True if a valid url
        """
        if (path.startswith('http://') or path.startswith('https://') or
                path.startswith('plugin://')):
            return True
        return False

    @classmethod
    def disk_usage(cls, path):
        # type: (TextType) -> Optional[Dict[TextType, int]]
        """
            Gets disk usage of the filesystem that the given
            path belongs to.

            Works for Linux and Windows

        :param path:
        :return: a dict of discovered values
        """
        usage = {}

        if hasattr(os, 'statvfs'):  # POSIX
            try:
                st = os.statvfs(path)
                free = st.f_bavail * st.f_frsize
                usage['free'] = free
                total = st.f_blocks * st.f_frsize
                usage['total'] = total
                used = (st.f_blocks - st.f_bfree) * st.f_frsize
                usage['used'] = used
                block_size = st.f_frsize
                usage['blocksize'] = block_size
            except (AbortException, ShutdownException) as e:
                six.reraise(*sys.exc_info())
            except (Exception) as e:
                cls._logger.exception('')
                usage = None
        elif os.name == 'nt':  # Windows
            import ctypes

            try:
                # drive = "%s\\" % os.path.splitdrive(path)[0]
                # cluster_sectors, sector_size = ctypes.c_longlong(0)

                _, total, free = ctypes.c_ulonglong(), ctypes.c_ulonglong(),\
                    ctypes.c_ulonglong()
                fun = ctypes.windll.kernel32.GetDiskFreeSpaceExW
                ret = fun(path, ctypes.byref(_), ctypes.byref(
                    total), ctypes.byref(free))
                if ret == 0:
                    raise ctypes.WinError()
                total_size = total.value
                free_size = free.value
                used = total_size - free_size
                usage['total'] = total_size
                usage['free'] = free_size
                usage['used'] = used
                usage['blocksize'] = 4096  # TODO: fix
            except (AbortException, ShutdownException) as e:
                six.reraise(*sys.exc_info())
            except (Exception) as e:
                cls._logger.exception('')
                usage = None
        # 'cluster_sectors:', cluster_sectors, 'sector_size:',
        # sector_size)
        else:
            if cls._logger.isEnabledFor(Logger.DEBUG):
                cls._logger.debug('Not supported on this platform')
            usage = None

        if cls._logger.isEnabledFor(Logger.DEBUG):
            if usage is None:
                cls._logger.debug('Result: None')
            else:
                cls._logger.debug('total:', usage['total'],
                                  'used', usage['used'],
                                  'free',  usage['free'])

        return usage

    @classmethod
    def get_stats_for_path(cls,
                           top,  # type: TextType
                           patterns  # type: Dict[TextType, TextType]
                           ):
        # type: (...) -> Dict[TextType, UsageData]
        """
            Gets disk usage information for a subtree of the filesystem

        :param top:
        :param patterns:
        :return:
        """
        usage_data = None
        fileMap = {}

        cls._logger.enter('top:', top, 'patterns:', patterns)
        usage_data_map = {}
        try:
            free = 0
            total = 0
            used = 0
            size_on_disk = 0
            block_size = None
            # Available in Python >= 3.3
            # shutil.disk_usage(top)
            # _ntuple_diskusage = collections.namedtuple('usage', 'total used free')

            # units in bytes
            disk_usage = cls.disk_usage(top)

            if disk_usage is not None:
                free = disk_usage['free']
                total = disk_usage['total']
                used = disk_usage['used']
                block_size = disk_usage['blocksize']

            #statvfs = os.statvfs(top)
            #block_size = statvfs.f_bsize
            #free = int(statvfs.f_bavail * statvfs.f_frsize / megaByte)
            #total = int(statvfs.f_blocks * statvfs.f_frsize / megaByte)
            # used = int((statvfs.f_blocks - statvfs.f_bfree) *
            #           statvfs.f_frsize / megaByte)
            # st.f_blocks is # blocks in filesystem
            # f_bavail free blocks for non-super user
            # f_bsize # preferred block size
            # f_frsize # fundamental file system block size
            # f_blocks total blocks in filesystem
            # f_bfree total # free blocks in filesystem

            for cache_name in patterns:
                pattern = patterns[cache_name]
                usage_data = UsageData(cache_name, pattern)
                usage_data.set_free_size(free)
                usage_data.set_total_size(total)
                usage_data.set_used_space(used)
                usage_data.set_block_size(block_size)
                usage_data_map[cache_name] = usage_data

            db_cache_file_expiration_days = \
                Settings.get_expire_remote_db_cache_entry_days()
            db_cache_file_expiration_seconds =\
                db_cache_file_expiration_days * 24 * 60 * 60
            db_cache_path_top = Settings.get_remote_db_cache_path()

            trailer_cache_file_expiration_days = Settings.get_expire_trailer_cache_days()
            trailer_cache_file_expiration_seconds = \
                trailer_cache_file_expiration_days * 24 * 60 * 60
            trailer_cache_path_top = Settings.get_downloaded_trailer_cache_path()
            now = datetime.datetime.now()

            for root, dirs, files in os.walk(top):
                for filename in files:
                    Monitor.get_instance().throw_exception_if_shutdown_requested()
                    for cache_name in patterns:
                        usage_data = usage_data_map[cache_name]
                        pattern = patterns[cache_name]
                        if pattern in filename:
                            path = os.path.join(root, filename)
                            try:
                                st = os.stat(path)
                                mod_time = datetime.datetime.fromtimestamp(
                                    st.st_mtime)
                                size_in_blocks = st.st_size
                                size_on_disk = ((size_in_blocks - 1) /
                                                block_size + 1) * block_size
                            except (OSError) as e:
                                continue  # File doesn't exist
                            except (Exception) as e:
                                cls._logger.exception('')
                                continue

                            deleted = False
                            try:
                                if top == db_cache_path_top:
                                    if filename.endswith('.json'):
                                        if ((now - mod_time).total_seconds() >
                                                db_cache_file_expiration_seconds):
                                            if cls._logger.isEnabledFor(Logger.DEBUG):
                                                cls._logger.debug(
                                                    'deleting:', path)
                                            os.remove(path)
                                            deleted = True
                                            usage_data.add_to_disk_deleted(
                                                size_on_disk)

                                elif top == trailer_cache_path_top:
                                    if '-trailer.' in filename:
                                        if ((now - mod_time).total_seconds() >
                                                trailer_cache_file_expiration_seconds):
                                            if cls._logger.isEnabledFor(Logger.DEBUG):
                                                cls._logger.debug(
                                                    'deleting:', path)
                                            os.remove(path)
                                            deleted = True
                                            usage_data.add_to_disk_deleted(
                                                size_on_disk)
                            except (Exception) as e:
                                cls._logger.exception('')

                            if not deleted:
                                file_data = FileData(
                                    path, mod_time, size_on_disk)
                                usage_data.add_file_data(file_data)
                                usage_data.add_to_disk_used_by_cache(
                                    size_on_disk)

        except (AbortException, ShutdownException) as e:
            pass
        except (Exception) as e:
            cls._logger.exception('')

        cls._logger.exit()
        return usage_data_map

    @staticmethod
    def sizeof_fmt(num, suffix='B'):
        # type: (Union[int, float], TextType) -> TextType
        """
            Convert a disk size to a human friendly format

        :param num:
        :param suffix:
        :return:
        """
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)


DiskUtils.class_init()
