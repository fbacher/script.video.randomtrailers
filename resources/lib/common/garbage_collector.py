# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import threading

from common.monitor import Monitor
from common.imports import *
from common.logger import LazyLogger

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection PyClassHasNoInit
class GarbageCollector:
    """

    """
    _lock = threading.RLock()
    _threads_to_join: List[threading.Thread] = []

    def __init__(self):
        raise NotImplemented()

    @classmethod
    def add_thread(cls, thread: threading.Thread) -> None:
        with cls._lock:
            cls._threads_to_join.append(thread)

    @classmethod
    def init_class(cls):
        garbage_collector = threading.Thread(
            target=cls.join_dead_threads,
            name='Thread garbage collection')

        garbage_collector.start()

    @classmethod
    def join_dead_threads(cls):
        finished = False
        while not finished:
            with cls._lock:
                joined_threads: List[threading.Thread] = []
                for thread in cls._threads_to_join:
                    if not thread.is_alive():
                        thread.join(timeout=0.0)
                        if not thread.is_alive():
                            joined_threads.append(thread)

                for thread in joined_threads:
                    cls._threads_to_join.remove(thread)

            if Monitor.wait_for_abort(timeout=10.0):
                finished = True


GarbageCollector.init_class()
