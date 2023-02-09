# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
import queue
import threading
from pathlib import Path
from queue import Queue

import xbmcvfs
from common.imports import *

import datetime
import os
import random
import sys

from common.exceptions import AbortException
from common.logger import *
from common.monitor import Monitor
from common.settings import Settings
from common.utils import Delay
from common.garbage_collector import GarbageCollector
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class UsageData:
    """

    """

    def __init__(self, cache_name: str, pattern: str) -> None:
        """

        :param cache_name
        :param pattern
        """
        self._logger: BasicLogger = module_logger.getChild(self.__class__.__name__)
        self._cache_name: str = cache_name
        self._pattern: str = pattern
        self._aggregate_cache_file_size: int = 0
        self._aggregate_deleted_size: int = 0
        self._deleted_files: int = 0
        self._total_size: int = None
        self._free_size: int = None
        self._used_space: int = None
        self._block_size: int = None
        self._file_data: Dict[str, FileData] = {}

    def set_total_size(self, total_size: int) -> None:
        """

        :param total_size:
        :return:
        """
        self._total_size = total_size

    def get_total_size(self) -> int:
        """
            Gets the total disk space on device
        :return:
        """
        return self._total_size

    def set_free_size(self, free_size: int) -> None:
        """

        :param free_size:
        :return:
        """
        self._free_size = free_size

    def get_free_size(self) -> int:
        """
            Gets the free space on device

        :return:
        """
        return self._free_size

    def set_used_space(self, used_space: int) -> None:
        """

        :param used_space:
        :return:
        """
        self._used_space = used_space

    def get_used_space(self) -> int:
        """
            Gets the used space on device
        :return:
        """
        return self._used_space

    def set_block_size(self, block_size: int) -> None:
        """

        :param block_size:
        :return:
        """
        self._block_size = block_size

    def get_block_size(self) -> int:
        """
            Gets the block size of device

        :return:
        """
        return self._block_size

    def get_number_of_files(self) -> int:
        """
            Gets the number of Files within the original search path
        :return:
        """
        return int(len(self._file_data))

    def add_to_disk_used_by_cache(self, additional_size: int) -> None:
        """

        :param additional_size:
        :return:
        """
        self._aggregate_cache_file_size += additional_size

    def get_disk_used_by_cache(self) -> int:
        """

        :return:
        """
        return int(self._aggregate_cache_file_size)

    def add_to_disk_deleted(self, deleted_size: int) -> None:
        """

        :param deleted_size:
        :return:
        """
        self._aggregate_deleted_size += deleted_size
        self._deleted_files += 1

    def get_disk_deleted_from_cache(self) -> int:
        """

        :return:
        """
        return int(self._aggregate_deleted_size)

    def remove_file(self, file_data: 'FileData') -> None:
        """

        :param file_data:
        :return:
        """
        if self._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            self._logger.debug_extra_verbose(f'will delete path: {file_data.get_path()} '
                                             f'creation: {file_data.get_creation_date()}')
        os.remove(file_data.get_path())
        self._aggregate_deleted_size += file_data.get_size()
        self._aggregate_cache_file_size -= file_data.get_size()
        self._deleted_files += 1

        del self._file_data[file_data.get_path()]
        del file_data

    def get_number_of_deleted_files(self) -> int:
        """

        :return:
        """
        return self._deleted_files

    def add_file_data(self, file_data: 'FileData') -> None:
        """

        :param file_data:
        :return:
        """
        self._file_data[file_data.get_path()] = file_data

    def get_file_data(self) -> Dict[str, 'FileData']:
        """

        :return: Dict of file data indexed by file path
        """
        return self._file_data

    def get_file_data_by_file_size(self) -> List['FileData']:
        """

        Gets List of cache file in decreasing order of file size.
        The file path serves as a key to the dict returned by get_file_data

        :return:
        """
        # def sorted(iterable, cmp=None, key=None, reverse=False): # real
        # signature unknown; restored from __doc__

        file_data_list = sorted(self._file_data.values(),
                                key=lambda
                                    file_data_element: file_data_element.get_size(),
                                reverse=False)
        return file_data_list

    def get_file_data_by_creation_date(self) -> List['FileData']:
        """

        Gets List of cache files in decreasing order of creation data

        :return:
        """
        # First sort by number of movies that each genre is
        # in

        file_data_list = (sorted(self._file_data.values(),
                                 key=lambda file_data_element:
                                 file_data_element.get_creation_date(),
                                 reverse=False))
        return file_data_list


class FileData:
    """

    """

    def __init__(self, path: str, creation_date: datetime.datetime,
                 size: int) -> None:
        """

        :param path:
        :param creation_date:
        :param size:
        """
        self._path = path
        self._creation_date = creation_date
        self._size = size

    def get_path(self) -> str:
        """

        :return:
        """
        return self._path

    def get_creation_date(self) -> datetime.datetime:
        """

        :return:
        """
        return self._creation_date

    def get_size(self) -> int:
        """

        :return:
        """
        return self._size


class DiskUtils:
    """
            Provides disk utilities
    """
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exit_requested = False
    _logger = module_logger.getChild('DiskUtils')

    @classmethod
    def class_init(cls) -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)

    @classmethod
    def create_path_if_needed(cls, path: str) -> None:
        """
            Creates as many directories as necessary to make path a valid path

        :param path:
        :return:
        """
        try:
            if not os.path.exists(path):
                os.makedirs(path)
        except Exception as e:
            cls._logger.exception('')

    @staticmethod
    def is_url(path: str) -> bool:
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
    def remove_cache_file(cls, path: str) -> None:
        #  file_data = UsageData.get_file_data().get(path)
        #  if file_data is not None:
        #     UsageData.remove_file(file_data)
        try:
            os.remove(path)
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def disk_usage(cls, path: str) -> Optional[Dict[str, int]]:
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
                Monitor.throw_exception_if_abort_requested()
            except AbortException as e:
                reraise(*sys.exc_info())
            except Exception as e:
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
                Monitor.throw_exception_if_abort_requested()
            except AbortException as e:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.exception('')
                usage = None
        # 'cluster_sectors:', cluster_sectors, 'sector_size:',
        # sector_size)
        else:
            if cls._logger.isEnabledFor(DEBUG):
                cls._logger.debug('Not supported on this platform')
            usage = None

        if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            if usage is None:
                cls._logger.debug_extra_verbose('Result: None')
            else:
                cls._logger.debug_extra_verbose(f'total: {usage["total"]}'
                                                f'used: {usage["used"]} '
                                                f'free: {usage["free"]}')

        return usage

    @classmethod
    def get_stats_for_path(cls,
                           top: str,
                           patterns: Dict[str, Tuple[str, str]],
                           delay_scale_factor: float = 0.0
                           ) -> Dict[str, UsageData]:
        """
            Gets disk usage information for a subtree of the filesystem

        :param top:
        :param patterns:
        :param delay_scale_factor: if non-zero, then delays are added during file
               traversal to reduce cpu and memory impact. The delays are non-linear.
        :return:
        """
        usage_data = None
        file_map = {}

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

            for cache_name, (pattern, cache_type) in patterns.items():
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
            now: datetime.datetime = datetime.datetime.now()

            found_directories: Set[Path] = set()
            finder: FindFiles = FindFiles(top)

            #  Delay one second on each call.
            delay = Delay(bias=1.0, call_scale_factor=0.0, scale_factor=0.0)
            path: Path

            for path in finder:
                for cache_name, (pattern, cache_type) in patterns.items():
                    delay.delay()  # Can throw AbortException
                    Monitor.throw_exception_if_abort_requested()
                    usage_data = usage_data_map[cache_name]
                    if path.match(pattern):
                        mod_time: datetime.datetime = now
                        try:
                            if path.is_file():
                                st: os.stat_result = path.stat()
                                mod_time = datetime.datetime.fromtimestamp(st.st_mtime)
                                size_in_blocks = st.st_size
                                size_on_disk = int(((size_in_blocks - 1) /
                                                block_size + 1) * block_size)
                            else:
                                found_directories.add(path)
                                continue
                        except OSError as e:
                            continue  # File doesn't exist
                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            cls._logger.exception('')
                            continue

                        deleted = False
                        try:
                            if (top == db_cache_path_top
                                    and cache_type == 'json'):
                                if ((now - mod_time).total_seconds() >
                                        db_cache_file_expiration_seconds):
                                    if cls._logger.isEnabledFor(INFO):
                                        cls._logger.info(f'deleting: {path.absolute()}')
                                    path.unlink()
                                    deleted = True
                                    usage_data.add_to_disk_deleted(
                                        size_on_disk)
                                break  # Next file

                            if (top == trailer_cache_path_top
                                    and cache_type == 'movie'):
                                if ((now - mod_time).total_seconds() >
                                        trailer_cache_file_expiration_seconds):
                                    if cls._logger.isEnabledFor(INFO):
                                        cls._logger.info(
                                            f'deleting: {path.absolute()}')
                                    path.unlink()
                                    deleted = True
                                    usage_data.add_to_disk_deleted(
                                        size_on_disk)
                                break  # Next file

                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            cls._logger.exception('')

                        if not deleted:
                            file_data = FileData(
                                str(path), mod_time, size_on_disk)
                            usage_data.add_file_data(file_data)
                            usage_data.add_to_disk_used_by_cache(
                                size_on_disk)

            for directory in found_directories:
                try:
                    # If empty
                    if next(directory.iterdir(), None) is None:
                        directory.rmdir()
                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    pass

        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            cls._logger.exception('')

        cls._logger.debug()
        return usage_data_map

    @staticmethod
    def sizeof_fmt(num: Union[int, float], suffix: str = 'B') -> str:
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


class FindFiles(Iterable[Path]):
    _logger: BasicLogger = None

    def __init__(self,
                 top: str,
                 glob_pattern: str = '**/*'
                 ) -> None:
        """
            Gets all file paths matching the given pattern in
            the sub-tree top.

        :param top:
        :param patterns:
        :return:
        """
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__class__.__name__)

        self._die: bool = False
        self._top: str = xbmcvfs.translatePath(top)
        self._path: Path = Path(self._top)
        self._glob_pattern: str = glob_pattern
        #  clz._logger.debug(f'top: {self._top} path: {self._path} pattern:
        #  {self._glob_pattern}')

        self._queue_complete: bool = False

        # Don't make queue too big, just waste lots of memory and cpu building
        # it before it can be used.

        self._file_queue: Queue = Queue(20)
        self._find_thread: threading.Thread = threading.Thread(
            target=self._run,
            name='find files')
        self._find_thread.start()
        self._find_thread.setName(f'Find Files: {top}')

    def _run(self) -> None:
        clz = type(self)
        try:
            # glob uses more resources than iglob since it must build entire
            # list before returning. iglob, returns one at a time.

            self.name = f'Find Files'
            for path in self._path.glob(self._glob_pattern):
                #  clz._logger.debug(f'path: {path}')
                inserted: bool = False
                while not inserted:
                    try:
                        if self._die:
                            break

                        self._file_queue.put(path, block=False)
                        inserted = True
                    except queue.Full:
                        Monitor.throw_exception_if_abort_requested(timeout=0.25)
                if self._die:
                    break
        except AbortException:
            self._die = True   # Let thread die

        except Exception as e:
            clz._logger.exception(msg='')
        finally:
            #  clz._logger.debug('queue complete')
            self._queue_complete = True
            if not self._die:
                self._file_queue.put(None)
            del self._path

    def get_next(self) -> Path:
        clz = type(self)
        if self._file_queue is None:
            #  clz._logger.debug('get_next returning None')
            return None

        next_path: Path = None
        while next_path is None:

            try:
                Monitor.throw_exception_if_abort_requested(timeout=0.1)
                next_path: Path = self._file_queue.get(timeout=0.01)
                self._file_queue.task_done()
            except queue.Empty:
                # Empty because we are done, or empty due to timeout
                if self._queue_complete:
                    clz._logger.debug('Queue empty')
                    try:
                        GarbageCollector.add_thread(self._find_thread)
                    except Exception as e:
                        clz._logger.exception(msg='')
                    finally:
                        self._find_thread = None
                        self._file_queue = None
                        break
            except AbortException:
                reraise(*sys.exc_info())

            except BaseException as e:
                clz._logger.exception(msg='')

        #  clz._logger.debug(f'next_path: {next_path}')
        return next_path

    def kill(self):
        clz = type(self)
        #  clz._logger.debug('In kill')
        self._die = True

    def __iter__(self) -> Iterator:
        clz = type(self)
        #  clz._logger.debug('in __iter__')
        return FindFilesIterator(self)


class FindFilesIterator(Iterator):

    _logger: BasicLogger = None

    def __init__(self, files: FindFiles):
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__class__.__name__)
        #  clz._logger.debug(f'In __init__')

        self._files: FindFiles = files

    def __next__(self) -> Path:
        path: Path = None
        clz = type(self)
        #  clz._logger.debug('In __next__')
        try:
            path = self._files.get_next()
            #  clz._logger.debug(f'__next__ path: {path}')
        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            clz._logger.exception(msg='')

        if path is None:
            clz._logger.debug('iterator path None raising StopIteration')
            raise StopIteration()

        return path

    def __del__(self):
        self._files.kill()


DiskUtils.class_init()
