# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import threading
from queue import (Queue)


from common.constants import Constants
from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import (Logger, Trace, LazyLogger)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'discovery.abstract_movie_data')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class KodiQueue(object):
    from queue import Full as _Full
    from queue import Empty as _Empty

    Full = _Full
    Empty = _Empty

    def __init__(self, maxsize=0):
        # type: (int) -> None
        """
        :param maxsize:
        :return:
        """
        self._lock = threading.RLock()
        self._logger = module_logger.getChild(self.__class__.__name__)

        self._wrapped_queue = Queue(maxsize=maxsize)

    def put(self, item, block=True, timeout=None):
        # type: (Any, bool, Optional[float]) -> None
        """

        :param item:
        :param block:
        :param timeout:
        :return:
        """

        with self._lock:
            if not block:
                timeout = 0

            if timeout is None:
                timeout = float(60 * 60 * 24 * 365)  # A year

            time_remaining = timeout
            time_chunk = 0.01
            finished = False
            while not finished:
                try:
                    self._wrapped_queue.put(item, block=False)
                    finished = True
                except KodiQueue.Full:
                    Monitor.throw_exception_if_abort_requested(
                        timeout=time_chunk)
                    time_remaining -= time_chunk
                    if time_remaining <= 0:
                        raise KodiQueue.Full

    def get(self, block=True, timeout=None):
        # type: (bool, Optional[float]) -> object
        """

        :param block:
        :param timeout:
        :return:
        """
        with self._lock:
            if not block:
                timeout = 0

            if timeout is None:
                timeout = float(60 * 60 * 24 * 365)  # A year
            time_remaining = timeout
            time_chunk = 0.01
            finished = False
            while not finished:
                try:
                    item = self._wrapped_queue.get(block=False)
                    finished = True
                except KodiQueue.Empty:
                    Monitor.throw_exception_if_abort_requested(
                        timeout=time_chunk)
                    time_remaining -= time_chunk
                    if time_remaining <= 0:
                        raise KodiQueue.Empty

        return item

    def clear(self):
        # type: () -> None
        """

        :return:
        """
        while True:
            try:
                self.get(block=True, timeout=0.10)
            except (KodiQueue.Empty):
                break
        assert len(self._wrapped_queue.empty())

    def qsize(self):
        # type: () -> int
        """

        :return:
        """
        with self._lock:
            size = int(self._wrapped_queue.qsize())

        # self._logger.exit('size:', size)
        return size

    def empty(self):
        # type: () -> bool
        """

        :return:
        """
        # self._logger = self._logger.get_method_logger('empty')

        with self._lock:
            empty = self._wrapped_queue.empty()

        # self._logger.exit('empty:', empty)
        return empty

    def full(self):
        # type () -> bool
        """

        :return:
        """
        # self._logger = self._logger.get_method_logger('full')

        with self._lock:
            full = self._wrapped_queue.full()

        # self._logger.exit('full:', full)
        return full
