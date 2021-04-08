# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import threading
from queue import (Queue)

from common.imports import *
from common.monitor import Monitor
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class KodiQueue:
    from queue import Full as _Full
    from queue import Empty as _Empty

    Full = _Full
    Empty = _Empty
    _logger: LazyLogger = None

    def __init__(self, maxsize: int = 0) -> None:
        """
        :param maxsize:
        :return:
        """
        self._lock = threading.RLock()
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__name__)

        self._wrapped_queue = Queue(maxsize=maxsize)

    def put(self,
            item: Union[MovieType, None],
            block: bool = True,
            timeout: Optional[float] = None) -> None:
        """

        :param item:
        :param block:
        :param timeout:
        :return:
        """

        if not block:
            timeout = 0

        if timeout is None:
            timeout = float(60 * 60 * 24 * 365)  # A year

        time_remaining = timeout
        time_chunk = 0.01
        finished = False
        while not finished:
            try:
                with self._lock:
                    self._wrapped_queue.put(item, block=False)
                finished = True
            except KodiQueue.Full:
                Monitor.throw_exception_if_abort_requested(
                    timeout=time_chunk)
                time_remaining -= time_chunk
                if time_remaining <= 0:
                    raise KodiQueue.Full

    def get(self,
            block: bool = True,
            timeout: Optional[float] = None) -> Union[MovieType, None]:
        """

        :param block:
        :param timeout:
        :return:
        """
        if not block:
            timeout = 0

        if timeout is None:
            timeout = float(60 * 60 * 24 * 365)  # A year
        time_remaining = timeout
        time_chunk = 0.01
        finished = False
        item = None
        while not finished:
            try:
                with self._lock:
                    item = self._wrapped_queue.get(block=False)
                finished = True
            except KodiQueue.Empty:
                Monitor.throw_exception_if_abort_requested(
                    timeout=time_chunk)
                time_remaining -= time_chunk
                if time_remaining <= 0:
                    raise KodiQueue.Empty

        return item

    def clear(self) -> None:
        """

        :return:
        """
        with self._lock:
            while True:
                try:
                    self.get(block=True, timeout=0.10)
                except KodiQueue.Empty:
                    break
            assert self._wrapped_queue.qsize() == 0

    def qsize(self) -> int:
        """

        :return:
        """
        with self._lock:
            size = int(self._wrapped_queue.qsize())

        return size

    def empty(self) -> bool:
        """

        :return:
        """
        with self._lock:
            empty = self._wrapped_queue.empty()

        return empty

    def full(self) -> bool:
        """

        :return:
        """

        with self._lock:
            full = self._wrapped_queue.full()

        return full
