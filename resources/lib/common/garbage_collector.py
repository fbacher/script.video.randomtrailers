# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import threading

from common.monitor import Monitor
from common.imports import *
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class GarbageCollector:
    """

    """
    _lock = threading.RLock()
    _stopped = False
    _threads_to_join: List[threading.Thread] = []
    _logger: LazyLogger = None

    def __init__(self) -> None:
        raise NotImplemented()

    @classmethod
    def add_thread(cls, thread: threading.Thread) -> None:
        with cls._lock:
            if not cls._stopped:
                if thread not in cls._threads_to_join:
                    cls._threads_to_join.append(thread)
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'Adding thread: {thread.name} '
                                                        f'{thread.ident}')
                else:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'Duplicate thread: {thread.name} '
                                                        f'{thread.ident}')

    @classmethod
    def init_class(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        garbage_collector = threading.Thread(
            target=cls.join_dead_threads,
            name='Thread garbage collection')

        garbage_collector.start()

        # Did not see thread name while using debugger.
        garbage_collector.setName('Thread garbage collection')

    @classmethod
    def join_dead_threads(cls) -> None:
        finished = False
        # Sometimes thread name doesn't get set.
        threading.current_thread().setName('Thread garbage collection')
        while not finished:
            with cls._lock:
                joined_threads: List[threading.Thread] = []
                for thread in cls._threads_to_join:
                    if not thread.is_alive():
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(
                                f'Purging dead thread: {thread.name} '
                                f'{thread.ident}')
                        joined_threads.append(thread)
                    else:
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(
                                f'Joining thread: {thread.name} '
                                f'{thread.ident}')
                        thread.join(timeout=0.2)
                        if not thread.is_alive():
                            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                cls._logger.debug_extra_verbose(
                                    f'Purging dead thread: {thread.name} '
                                    f'{thread.ident}')
                            joined_threads.append(thread)

                for thread in joined_threads:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'Removing dead thread: '
                                                        f'{thread.name} '
                                                        f'{thread.ident}')
                    cls._threads_to_join.remove(thread)

            if Monitor.wait_for_abort(timeout=10.0):
                del cls._threads_to_join
                finished = True


GarbageCollector.init_class()
