# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''

import queue
import sys
import os
import threading

from common.debug_utils import Debug
from common.exceptions import AbortException, LogicError
from common.imports import *
from common.logger import LazyLogger
from common.monitor import Monitor
from common.movie import AbstractMovie, FolderMovie
from common.movie_constants import MovieField
from frontend.front_end_bridge import FrontendBridge, FrontendBridgeStatus
from common.settings import Settings
from frontend.history_list import HistoryList
from frontend.history_empty import HistoryEmpty

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MovieStatus(FrontendBridgeStatus):
    PREVIOUS_MOVIE: Final[str] = 'PREVIOUS_MOVIE'
    NEXT_MOVIE: Final[str] = 'NEXT_MOVIE'


class MovieManager:

    OPEN_CURTAIN: Final[bool] = True
    CLOSE_CURTAIN: Final[bool] = False

    _logger: LazyLogger = None

    def __init__(self) -> None:
        """
        """
        clz = type(self)
        clz._logger = module_logger.getChild(self.__class__.__name__)
        super().__init__()
        self._play_open_curtain_next = None
        self._play_close_curtain_next = None
        self._movie_history_cursor = None
        FrontendBridge()
        self._play_open_curtain_next = Settings.get_show_curtains()
        self._play_next_trailer = False
        self._play_previous_trailer = False
        self._thread = None
        self._queuedMovie = None
        self._pre_fetched_trailer_queue = queue.Queue(2)
        self.fetched_event = threading.Event()
        self.pre_fetch_trailer()

    def get_next_trailer(self) -> (str, AbstractMovie):
        """

        :return:
        """
        clz = type(self)
        trailer: AbstractMovie = None
        status: str = None
        prefetched: bool = False
        if self._play_open_curtain_next:
            status = MovieStatus.OK
            trailer = FolderMovie({MovieField.SOURCE: 'curtain',
                                   MovieField.TITLE: 'openCurtain',
                                   MovieField.TRAILER: Settings.get_open_curtain_path()})
            self._play_open_curtain_next = False
        elif self._play_close_curtain_next:
            status = MovieStatus.OK
            trailer = FolderMovie({MovieField.SOURCE: 'curtain',
                                   MovieField.TITLE: 'closeCurtain',
                                   MovieField.TRAILER: Settings.get_close_curtain_path()})
            self._play_close_curtain_next = False
        elif self._play_previous_trailer:
            status = MovieStatus.PREVIOUS_MOVIE
            self._play_previous_trailer = False
            try:
                trailer = HistoryList.get_previous_movie()
            except HistoryEmpty:
                reraise(*sys.exc_info())
        elif self._play_next_trailer:
            status = MovieStatus.NEXT_MOVIE
            self._play_next_trailer = False
            trailer = HistoryList.get_next_movie()
            countdown = 50
            while trailer is None and countdown >= 0:
                countdown -= 1
                if not self._pre_fetched_trailer_queue.empty():
                    trailer = self._pre_fetched_trailer_queue.get(timeout=0.1)
                Monitor.throw_exception_if_abort_requested(timeout=0.1)
            if trailer is None:
                status = MovieStatus.TIMED_OUT
            else:
                HistoryList.append(trailer)
        else:
            status = MovieStatus.OK
            trailer = HistoryList.get_next_movie()
            countdown = 50
            while trailer is None and countdown >= 0:
                countdown -= 1
                if not self._pre_fetched_trailer_queue.empty():
                    trailer = self._pre_fetched_trailer_queue.get(timeout=0.1)
                Monitor.throw_exception_if_abort_requested(timeout=0.1)
            if trailer is None:
                status = MovieStatus.TIMED_OUT
            else:
                HistoryList.append(trailer)

        title = None
        if trailer is not None:
            if self.purge_removed_cached_trailers(trailer):
                HistoryList.remove(trailer)
                return self.get_next_trailer()

        if trailer is not None:
            title = trailer.get_title()
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.exit('status:', status, 'movie', title)

        return status, trailer

    def purge_removed_cached_trailers(self, trailer: AbstractMovie) -> None:
        clz = type(self)
        trailer_path = None
        if trailer.get_normalized_trailer_path() != '':
            trailer_path = trailer.get_normalized_trailer_path()
            if not os.path.exists(trailer_path):
                trailer.set_normalized_trailer_path('')
                clz._logger.debug('Does not exist:', trailer_path)
        elif trailer.get_cached_movie() != '':
            trailer_path = trailer.get_cached_movie()
            if not os.path.exists(trailer_path):
                trailer.set_cached_trailer('')
                clz._logger.debug('Does not exist:', trailer_path)
        else:
            trailer_path = trailer.get_trailer_path()
            if not trailer.has_trailer():
                trailer_path = None
            elif not (trailer_path.startswith('plugin') or os.path.exists(trailer_path)):
                trailer.set_trailer_path('')
                clz._logger.debug('Does not exist:', trailer_path)
                trailer_path = None
        return trailer_path is None

    def pre_fetch_trailer(self) -> None:
        self._thread = threading.Thread(
            target=self._pre_fetch_trailer, name='Pre-Fetch trailer')
        self._thread.start()

    def _pre_fetch_trailer(self) -> None:
        try:
            while not Monitor.throw_exception_if_abort_requested():
                status, trailer = FrontendBridge.get_next_trailer()
                if trailer is not None and Debug.validate_detailed_movie_properties(
                        trailer):
                    added = False
                    while not added:
                        try:
                            self._pre_fetched_trailer_queue.put(trailer, timeout=0.1)
                            added = True
                        except queue.Full:
                            if Monitor.throw_exception_if_abort_requested(timeout=0.5):
                                break
        except AbortException:
            pass  # In thread, let die
        except Exception as e:
            clz = type(self)
            clz._logger.exception(e)

    # Put movie in recent history. If full, delete oldest
    # entry. User can traverse backwards through shown
    # trailers

    def play_previous_trailer(self) -> None:
        """

        :return:
        """

        # TODO: probably not needed
        clz = type(self)
        clz._logger.enter()
        self._play_previous_trailer = True

    def play_next_trailer(self) -> None:
        """

        :return:
        """

        # TODO: probably not needed
        clz = type(self)
        clz._logger.enter()
        self._play_next_trailer = True

    def play_curtain_next(self, curtain_type):
        clz = type(self)
        if curtain_type == MovieManager.OPEN_CURTAIN:
            self._play_open_curtain_next = True
            self._play_close_curtain_next = False
        elif curtain_type == MovieManager.CLOSE_CURTAIN:
            self._play_open_curtain_next = False
            self._play_close_curtain_next = True
        else:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                clz._logger.debug('Must specify OPEN or CLOSE curtain')
            raise LogicError()
